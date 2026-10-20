"""FastAPI 集成测试：上传 → 检测 → 图框 → 按需解析 → 标注往返 → 导出；VL 走 FakeClient 离线。"""
import importlib
import io
import json
import threading
import time

import fitz
import pytest
from fastapi.testclient import TestClient

CHART = {
    "chart_type": "line", "title": "t",
    "x_axis": {"label": "x", "unit": None}, "y_axis": {"label": "y", "unit": None},
    "legend": ["a"], "series": [{"name": "a", "x": [1, 2], "y": [1.0, 2.0]}],
    "heatmap": None, "warnings": [],
}


class FakeClient:
    def chat_image(self, prompt, image_bytes, **kw):
        return json.dumps(CHART)

    def health(self):
        return False

    def model_available(self):
        return False


class FakeDetector:
    def detect_page(self, page_png, page, page_no):
        from chart_sdk.pdf.detector import FigureBBox
        return [FigureBBox(id=f"p{page_no}-f1", page=page_no, bbox_norm=[0, 0, 1, 1],
                           bbox_px=[50, 50, 400, 300], type="line",
                           source="vl_grounding", caption_hint=None)]


def _pdf_bytes(n_pages=2):
    doc = fitz.open()
    for _ in range(n_pages):
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 72), "hello")
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture()
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("CHART_SDK_CACHE_DIR", str(tmp_path / "cache"))
    import app.server as server
    importlib.reload(server)  # 让 config 使用临时缓存目录
    from chart_sdk.pipeline.paper import PaperPipeline
    server.client = FakeClient()
    server.pipeline = PaperPipeline(server.config, server.client,
                                    detector=FakeDetector(), fallback=FakeDetector())
    yield TestClient(server.app), server


def _upload(client, detect="true"):
    r = client.post("/api/papers", files={"file": ("a.pdf", _pdf_bytes(), "application/pdf")},
                    data={"detect": detect})
    assert r.status_code == 200, r.text
    return r.json()


def _wait_ready(client, h, timeout=15):
    deadline = time.time() + timeout
    st = {}
    while time.time() < deadline:
        st = client.get(f"/api/papers/{h}/status").json()
        if st["stage"] in ("ready", "failed", "done"):
            return st
        time.sleep(0.2)
    return st


def test_upload_detect_false(api):
    client, _ = api
    info = _upload(client, detect="false")
    assert info["n_pages"] == 2 and info["truncated"] is False
    st = client.get(f"/api/papers/{info['pdf_hash']}/status").json()
    assert st["stage"] == "ready" and st["n_figures"] == 0


def test_upload_detect_then_figures_and_pages(api):
    client, _ = api
    h = _upload(client)["pdf_hash"]
    st = _wait_ready(client, h)
    assert st["stage"] == "ready" and st["n_figures"] == 2
    figs = client.get(f"/api/papers/{h}/figures").json()["figures"]
    assert len(figs) == 2
    assert figs[0]["parse_status"] == "pending"
    assert figs[0]["bbox_px"] == [50, 50, 400, 300]
    r = client.get(f"/api/papers/{h}/pages/1.png")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert client.get(f"/api/papers/{h}/pages/9.png").status_code == 404


def test_status_reports_detecting_while_running(api):
    client, server = api
    gate = threading.Event()

    class BlockingDetector:
        def detect_page(self, page_png, page, page_no):
            gate.wait(5)
            return FakeDetector().detect_page(page_png, page, page_no)

    server.pipeline.detector = BlockingDetector()
    h = _upload(client)["pdf_hash"]
    st = client.get(f"/api/papers/{h}/status").json()
    assert st["stage"] == "detecting"  # 检测线程被阻塞，但 stage 必须已是 detecting
    gate.set()
    st = _wait_ready(client, h)
    assert st["stage"] == "ready"


def test_parse_endpoint_offline_full_chain(api):
    client, _ = api
    h = _upload(client)["pdf_hash"]
    _wait_ready(client, h)
    r = client.post(f"/api/papers/{h}/figures/p1-f1/parse")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["parse_status"] == "done"
    assert data["chart"]["chart_type"] == "line"
    assert data["code_path"] and data["render_path"]
    # 缓存命中再次调用仍 done
    assert client.post(f"/api/papers/{h}/figures/p1-f1/parse").json()["parse_status"] == "done"
    # 不存在的图表 → 404
    assert client.post(f"/api/papers/{h}/figures/p1-f9/parse").status_code == 404
    # figures 列表状态已更新
    figs = client.get(f"/api/papers/{h}/figures").json()["figures"]
    assert figs[0]["parse_status"] == "done"


def test_annotations_roundtrip(api):
    client, _ = api
    h = _upload(client, detect="false")["pdf_hash"]
    assert client.get(f"/api/papers/{h}/annotations").json() == {"version": 1, "pages": {}}
    payload = {"version": 1, "pages": {"1": {
        "strokes": [{"id": "s-1", "tool": "pen", "color": "#CC2936", "width": 2.0,
                     "points": [[0.1, 0.2], [0.3, 0.4]]}],
        "comments": [{"id": "c-1", "x": 0.5, "y": 0.5, "text": "存疑", "resolved": False,
                      "created_at": "t", "updated_at": "t"}]}}}
    assert client.put(f"/api/papers/{h}/annotations", json=payload).status_code == 200
    got = client.get(f"/api/papers/{h}/annotations").json()
    assert got["pages"]["1"]["strokes"][0]["id"] == "s-1"
    assert client.put(f"/api/papers/{h}/annotations", json={"pages": {"x": {}}}).status_code == 400


def test_export_download(api):
    client, _ = api
    h = _upload(client, detect="false")["pdf_hash"]
    client.put(f"/api/papers/{h}/annotations", json={"version": 1, "pages": {"1": {
        "strokes": [{"id": "s-1", "tool": "pen", "color": "#CC2936", "width": 2.0,
                     "points": [[0.1, 0.2], [0.3, 0.4]]}],
        "comments": [{"id": "c-1", "x": 0.5, "y": 0.5, "text": "存疑", "resolved": False,
                      "created_at": "t", "updated_at": "t"}]}}})
    r = client.post(f"/api/papers/{h}/export")
    assert r.status_code == 200
    assert r.content[:5] == b"%PDF-"
    with fitz.open(stream=r.content, filetype="pdf") as doc:
        assert len(doc) == 2
        assert len(list(doc[0].annots())) == 1


def test_single_parse_endpoint(api):
    client, _ = api
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (200, 150), (255, 255, 255)).save(buf, format="PNG")
    r = client.post("/api/singles/parse", files={"file": ("x.png", buf.getvalue(), "image/png")})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "done"
    assert data["chart"]["chart_type"] == "line"
    assert data["code"] and "matplotlib" in data["code"]
    assert data["input_url"] and data["render_url"]


def test_health_and_unknown_paper(api):
    client, server = api
    assert client.get("/api/health").json() == {
        "ollama": False, "model": False, "model_name": server.config.model}
    assert client.get(f"/api/papers/{'0' * 64}/status").status_code == 404
