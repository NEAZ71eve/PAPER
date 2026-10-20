"""自检脚本：环境 + 离线核心链路 + （可选）VL 在线冒烟。逐项 PASS/FAIL，失败返回非零。"""
from __future__ import annotations

import importlib
import io
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

RESULTS = []


def check(name, fn):
    try:
        note = fn() or ""
        RESULTS.append((True, name, note))
        print(f"PASS {name} {note}")
    except Exception as e:  # noqa: BLE001
        RESULTS.append((False, name, str(e)[:200]))
        print(f"FAIL {name} {e}")


def c_python():
    v = sys.version_info
    assert v >= (3, 10), f"需要 Python>=3.10，当前 {v}"
    return f"{v.major}.{v.minor}.{v.micro}"


def c_deps():
    mods = ["gradio", "fitz", "matplotlib", "PIL", "openai", "numpy", "pandas", "pytest",
            "fastapi", "uvicorn", "multipart", "httpx"]
    for m in mods:
        importlib.import_module(m)
    return f"{len(mods)} 个依赖"


def c_offline_chain():
    from chart_sdk.codegen.executor import execute_code
    from chart_sdk.codegen.generator import generate_code
    from chart_sdk.vision.validator import validate_chart
    chart = validate_chart({
        "chart_type": "line", "title": "t",
        "x_axis": {"label": "x", "unit": None}, "y_axis": {"label": "y", "unit": None},
        "legend": ["a"], "series": [{"name": "a", "x": [1, 2], "y": [1.0, 2.0]}],
        "heatmap": None,
    })[0]
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "r.png"
        execute_code(generate_code(chart, out), timeout=30)
        assert out.exists() and out.stat().st_size > 0
    return "校验→代码→渲染 OK"


def c_render_pages():
    from chart_sdk.pdf.render import render_pages
    sample = ROOT / "assets" / "samples" / "synthetic-demo.pdf"
    assert sample.exists(), "缺 synthetic-demo.pdf，请先运行 scripts/make_synthetic_sample.py"
    with tempfile.TemporaryDirectory() as td:
        pages = render_pages(sample, Path(td) / "pages", dpi=72, max_pages=30)
        assert len(pages) == 3
    return "3 页渲染 OK"


def c_ollama():
    from chart_sdk.config import Config
    from chart_sdk.inference.client import VLClient
    c = VLClient(Config.from_env())
    assert c.health(), f"Ollama 不可达: {c.config.base_url}"
    assert c.model_available(), f"模型缺失，请运行: ollama pull {c.config.model}"
    return c.config.model


def c_vl_smoke():
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from chart_sdk.vision.parser import parse_chart
    from chart_sdk.config import Config
    from chart_sdk.inference.client import VLClient
    fig, ax = plt.subplots(figsize=(5, 3.5), dpi=120)
    x = [1, 2, 3, 4]
    ax.plot(x, [10, 20, 15, 30], marker="o")
    fig.savefig(buf := io.BytesIO(), format="png")
    plt.close(fig)
    chart = parse_chart(VLClient(Config.from_env()), buf.getvalue())
    assert chart["series"], "VL 未能提取到数据系列"
    return f"识别 {len(chart['series'])} 条系列"


def c_api_smoke():
    import subprocess
    import time
    import urllib.request
    port = 8123
    env = dict(os.environ, CHART_SDK_CACHE_DIR=str(Path(tempfile.gettempdir()) / "selfcheck-api-cache"))
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.server:app", "--port", str(port)],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=2) as r:
                    import json as _json
                    data = _json.loads(r.read())
                assert "ollama" in data and "model_name" in data
                return f"health 200, model={data['model_name']}"
            except Exception:  # noqa: BLE001 - 服务尚未就绪
                time.sleep(0.5)
        raise RuntimeError("server 未在 30s 内就绪")
    finally:
        proc.terminate()
        try:
            proc.wait(5)
        except Exception:  # noqa: BLE001
            proc.kill()


def main():
    check("Python>=3.10", c_python)
    check("依赖导入", c_deps)
    check("离线链路(校验/代码/渲染)", c_offline_chain)
    check("页面渲染", c_render_pages)
    check("API 冒烟", c_api_smoke)
    ollama_ok = False
    try:
        check("Ollama 与模型", c_ollama)
        ollama_ok = RESULTS[-1][0]
    except Exception:  # noqa: BLE001
        print("SKIP Ollama 与模型（不可达）")
    if ollama_ok:
        check("VL 冒烟(单图解析)", c_vl_smoke)
    else:
        print("SKIP VL 冒烟")
    failed = [r for r in RESULTS if not r[0]]
    print(f"\n{len(RESULTS) - len(failed)} 通过 / {len(failed)} 失败")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
