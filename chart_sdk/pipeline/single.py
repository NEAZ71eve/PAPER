from __future__ import annotations

import json
from pathlib import Path

from chart_sdk.cache.store import SingleStore
from chart_sdk.codegen.executor import CodeExecError, execute_code
from chart_sdk.codegen.generator import generate_code
from chart_sdk.config import Config
from chart_sdk.inference.client import VLClient
from chart_sdk.vision.parser import parse_chart

_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}


def run_single(config: Config, client: VLClient, image_path: Path, progress=None) -> dict:
    cb = progress or (lambda *a: None)
    image_path = Path(image_path)
    data = image_path.read_bytes()
    store = SingleStore(config.cache_dir, data, image_path.name)
    r = store.record
    r["image_hash"] = store.image_hash  # 前端/集成测试依赖此键（含缓存命中路径）
    if r.get("status") == "done":
        cb("done", 1, 1, "命中缓存")
        return r
    cb("parsing", 0, 1, "解析图表")
    r["input_path"] = "input.png"
    (store.root / "input.png").write_bytes(data)
    mime = _MIME.get(image_path.suffix.lower(), "image/png")
    try:
        chart = parse_chart(client, data, mime=mime, config=config)
    except Exception as e:  # noqa: BLE001 - 含 VL 网络异常，工具箱失败优雅展示
        r["status"] = "error"
        r["error"] = str(e)
        store.save()
        return r
    r["chart"] = chart
    r.pop("error", None)
    code = generate_code(chart, store.root / "render.png")
    (store.root / "code.py").write_text(code, encoding="utf-8")
    r["code_path"] = "code.py"
    cb("rendering", 0, 1, "渲染复刻图")
    try:
        execute_code(code, config.exec_timeout)
        r["render_path"] = "render.png"
        r["status"] = "done"
    except CodeExecError as e:
        r["status"] = "render_failed"
        r["error"] = str(e)
    store.save()
    return r
