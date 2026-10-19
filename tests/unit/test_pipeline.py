import json
from pathlib import Path

import fitz

from chart_sdk.config import Config
from chart_sdk.pipeline.paper import PaperPipeline
from chart_sdk.pipeline.single import run_single
from chart_sdk.vision.parser import ParseError
from chart_sdk.vision.validator import ValidationError

CHART = {
    "chart_type": "line", "title": "t",
    "x_axis": {"label": "x", "unit": None}, "y_axis": {"label": "y", "unit": None},
    "legend": ["a"], "series": [{"name": "a", "x": [1, 2], "y": [1.0, 2.0]}],
    "heatmap": None, "warnings": [],
}


class FakeClient:
    def __init__(self, response=CHART, fail=False):
        self.response = response
        self.fail = fail
        self.parse_calls = 0

    def chat_image(self, prompt, image_bytes, **kw):
        self.parse_calls += 1
        if self.fail:
            return "垃圾"
        return json.dumps(self.response)


class FakeDetector:
    def __init__(self, boxes=None):
        self.boxes = boxes or [([50, 50, 400, 300], "line")]
        self.detect_calls = 0

    def detect_page(self, page_png, page, page_no):
        self.detect_calls += 1
        from chart_sdk.pdf.detector import FigureBBox
        out = []
        for i, (box, t) in enumerate(self.boxes, 1):
            out.append(FigureBBox(id=f"p{page_no}-f{i}", page=page_no, bbox_norm=[0, 0, 1, 1],
                                  bbox_px=list(box), type=t, source="vl_grounding", caption_hint=None))
        return out


def _make_pdf(path: Path, n_pages=2):
    doc = fitz.open()
    for _ in range(n_pages):
        doc.new_page(width=595, height=842)
    doc.save(str(path))
    doc.close()


def test_pipeline_full_run(tmp_path):
    _make_pdf(tmp_path / "a.pdf")
    cfg = Config.from_env()
    cfg.cache_dir = str(tmp_path / "cache")
    client = FakeClient()
    det = FakeDetector()
    pipe = PaperPipeline(cfg, client, detector=det, fallback=FakeDetector([]))
    session = pipe.run(tmp_path / "a.pdf")
    assert session["stage"] == "done"
    assert len(session["figures"]) == 2  # 两页各一张
    f = session["figures"][0]
    assert f["parse_status"] == "done" and f["render_status"] == "done"
    root = Path(cfg.cache_dir) / "papers"
    pdir = root / session["pdf_hash"]
    assert (pdir / "figures" / f["id"] / "render.png").exists()
    assert (pdir / "figures" / f["id"] / "code.py").exists()
    assert (pdir / "figures" / f["id"] / "chart.json").exists()


def test_pipeline_resume_skips_work(tmp_path):
    _make_pdf(tmp_path / "b.pdf")
    cfg = Config.from_env()
    cfg.cache_dir = str(tmp_path / "cache")
    client = FakeClient()
    pipe = PaperPipeline(cfg, client, detector=FakeDetector(), fallback=FakeDetector([]))
    pipe.run(tmp_path / "b.pdf")
    n1 = client.parse_calls
    pipe.run(tmp_path / "b.pdf")  # 重复上传：全部命中缓存
    assert client.parse_calls == n1


def test_pipeline_parse_error_isolated(tmp_path):
    _make_pdf(tmp_path / "c.pdf")
    cfg = Config.from_env()
    cfg.cache_dir = str(tmp_path / "cache")
    client = FakeClient(fail=True)
    pipe = PaperPipeline(cfg, client, detector=FakeDetector(), fallback=FakeDetector([]))
    session = pipe.run(tmp_path / "c.pdf")
    assert session["stage"] == "done"
    assert session["figures"][0]["parse_status"] == "error"
    assert session["figures"][0]["error"]


def test_run_single(tmp_path):
    from PIL import Image
    img = tmp_path / "in.png"
    Image.new("RGB", (200, 150), (255, 255, 255)).save(img)
    cfg = Config.from_env()
    cfg.cache_dir = str(tmp_path / "cache")
    r = run_single(cfg, FakeClient(), img)
    assert r["status"] == "done"
    r2 = run_single(cfg, FakeClient(), img)
    assert r2["status"] == "done"  # 命中缓存
