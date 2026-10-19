import json

import pytest

from pathlib import Path

from chart_sdk.config import Config
from chart_sdk.inference.client import VLClient

_cfg = Config.from_env()
_client = VLClient(_cfg)
_OLLAMA_OK = _client.health() and _client.model_available()

pytestmark = pytest.mark.skipif(not _OLLAMA_OK, reason="本地 Ollama/模型不可用")


def _chart_png_bytes():
    import io

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(5, 3.5), dpi=120)
    x = [1, 2, 3, 4]
    ax.plot(x, [10, 20, 15, 30], marker="o", label="m1")
    ax.set_xlabel("step"); ax.set_ylabel("value"); ax.legend()
    fig.savefig(buf := io.BytesIO(), format="png")
    plt.close(fig)
    return buf.getvalue()


def test_single_full_flow(tmp_path):
    from PIL import Image
    from chart_sdk.pipeline.single import run_single
    img = tmp_path / "chart.png"
    Image.open(__import__("io").BytesIO(_chart_png_bytes())).save(img)
    cfg = Config.from_env()
    cfg.cache_dir = str(tmp_path / "cache")
    r = run_single(cfg, _client, img)
    assert r["status"] == "done", r.get("error")
    assert (tmp_path / "cache" / "singles" / r["image_hash"] / "render.png").exists()


def test_paper_detect_and_parse(tmp_path):
    from chart_sdk.pipeline.paper import PaperPipeline
    sample = Path(__file__).resolve().parents[2] / "assets" / "samples" / "synthetic-demo.pdf"
    cfg = Config.from_env()
    cfg.cache_dir = str(tmp_path / "cache")
    session = PaperPipeline(cfg, _client).run(sample)
    assert session["stage"] == "done"
    target = [f for f in session["figures"] if f["type"] in ("line", "bar", "heatmap")]
    assert target, "合成样例中至少应检出 1 张目标类型图表"
