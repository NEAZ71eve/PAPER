r"""FastAPI 后端：论文阅读器 API + 静态托管（设计文档 6）。

启动：$env:CHART_SDK_MODEL="qwen2.5vl:3b" ; .venv\Scripts\python.exe -m uvicorn app.server:app --port 8000
"""
from __future__ import annotations

import tempfile
import threading
from pathlib import Path

import fitz
from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from chart_sdk.annotate.export import export_annotated
from chart_sdk.annotate.store import AnnotationStore
from chart_sdk.cache.store import PaperStore
from chart_sdk.config import Config
from chart_sdk.inference.client import VLClient
from chart_sdk.pipeline.paper import PaperPipeline
from chart_sdk.pipeline.single import run_single

APP_DIR = Path(__file__).resolve().parent
READER_DIR = APP_DIR / "reader"

config = Config.from_env()
client = VLClient(config)
pipeline = PaperPipeline(config, client)

app = FastAPI(title="论文阅读器")

_detect_lock = threading.Lock()
_detect_running: set[str] = set()
_detect_progress: dict[str, dict] = {}


def _open_store(h: str) -> PaperStore:
    try:
        return PaperStore.open(config.cache_dir, h)
    except KeyError:
        raise HTTPException(404, f"论文不存在: {h}")


def _run_detect(h: str) -> None:
    try:
        store = PaperStore.open(config.cache_dir, h)
        pipeline.detect(store, lambda stage, done, total, msg: _detect_progress.__setitem__(h, {"done": done, "total": total}))
    except Exception:  # noqa: BLE001 - 错误已写入 session.json，前端经 status 可见
        pass
    finally:
        with _detect_lock:
            _detect_running.discard(h)


def _start_detect(h: str) -> bool:
    """后台线程启动检测；已在检测中则返回 False。"""
    with _detect_lock:
        if h in _detect_running:
            return False
        _detect_running.add(h)
    _detect_progress[h] = {"done": 0, "total": 0}
    threading.Thread(target=_run_detect, args=(h,), daemon=True).start()
    return True


@app.post("/api/papers")
def upload_paper(file: UploadFile = File(...), detect: bool = Form(True)):
    data = file.file.read()
    if not data:
        raise HTTPException(400, "空文件")
    store0 = PaperStore(config.cache_dir, data, file.filename or "paper.pdf")
    src = store0.root / "source.pdf"
    store = pipeline.render_only(src)  # 页面渲染同步完成（秒级）
    with fitz.open(src) as doc:
        truncated = len(doc) > config.max_pages
    if detect:
        _start_detect(store.pdf_hash)  # 检测后台执行，前端轮询 status
    return {"pdf_hash": store.pdf_hash, "file_name": store.session["file_name"],
            "n_pages": store.session["n_pages"], "truncated": truncated}


@app.post("/api/papers/{h}/detect")
def start_detect(h: str):
    _open_store(h)
    return {"started": _start_detect(h)}


@app.get("/api/papers/{h}/status")
def paper_status(h: str):
    store = _open_store(h)
    s = store.session
    prog = _detect_progress.get(h, {"done": 0, "total": s.get("n_pages", 0)})
    stage = "detecting" if h in _detect_running else s.get("stage")
    return {"stage": stage, "detect_done": prog["done"], "detect_total": prog["total"],
            "n_figures": len(s.get("figures", [])), "n_pages": s.get("n_pages", 0),
            "file_name": s.get("file_name"), "error": s.get("error")}


@app.get("/api/papers/{h}/pages/{n}.png")
def page_png(h: str, n: int):
    store = _open_store(h)
    try:
        return FileResponse(store.page_png(n), media_type="image/png")
    except KeyError:
        raise HTTPException(404, f"页面不存在: {n}")


@app.get("/api/papers/{h}/figures")
def list_figures(h: str):
    store = _open_store(h)
    return {"figures": [
        {"id": f["id"], "page": f["page"], "bbox_px": f["bbox_px"], "type": f["type"],
         "source": f["source"], "caption_hint": f.get("caption_hint"),
         "parse_status": f.get("parse_status", "pending"), "error": f.get("error"),
         "crop_path": f.get("crop_path"), "render_path": f.get("render_path"),
         "code_path": f.get("code_path")}
        for f in store.session.get("figures", [])
    ]}


@app.post("/api/papers/{h}/figures/{fid}/parse")
def parse_one(h: str, fid: str):
    store = _open_store(h)
    try:
        return pipeline.parse_figure(store, fid)
    except KeyError as e:
        raise HTTPException(404, str(e))


@app.get("/api/papers/{h}/annotations")
def get_annotations(h: str):
    store = _open_store(h)
    return AnnotationStore(store.root).load()


@app.put("/api/papers/{h}/annotations")
def put_annotations(h: str, payload: dict = Body(...)):
    store = _open_store(h)
    try:
        AnnotationStore(store.root).save(payload)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@app.post("/api/papers/{h}/export")
def export_paper(h: str):
    store = _open_store(h)
    try:
        out = export_annotated(store.root / "source.pdf", store.root, store.root / "exports", dpi=config.dpi)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"导出失败: {e}")
    return FileResponse(out, media_type="application/pdf", filename=out.name)


@app.post("/api/singles/parse")
def parse_single(file: UploadFile = File(...)):
    data = file.file.read()
    if not data:
        raise HTTPException(400, "空文件")
    suffix = Path(file.filename or "img.png").suffix or ".png"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tf:
        tf.write(data)
        tmp = Path(tf.name)
    try:
        rec = run_single(config, client, tmp)
    finally:
        tmp.unlink(missing_ok=True)
    out = dict(rec)
    h = rec.get("image_hash", "")
    out["input_url"] = f"/cache/singles/{h}/input.png" if h else None
    out["render_url"] = f"/cache/singles/{h}/{rec['render_path']}" if rec.get("render_path") else None
    code_rel = rec.get("code_path")
    code_file = (Path(config.cache_dir) / "singles" / h / code_rel) if code_rel else None
    out["code"] = code_file.read_text(encoding="utf-8") if code_file and code_file.exists() else None
    return out


@app.get("/api/health")
def health():
    ok = client.health()
    return {"ollama": ok, "model": client.model_available() if ok else False, "model_name": config.model}


Path(config.cache_dir).mkdir(parents=True, exist_ok=True)
READER_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/cache", StaticFiles(directory=config.cache_dir), name="cache")
app.mount("/", StaticFiles(directory=READER_DIR, html=True), name="reader")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.server:app", host="127.0.0.1", port=config.api_port)
