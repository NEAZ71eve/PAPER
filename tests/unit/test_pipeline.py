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
        self.boxes = [([50, 50, 400, 300], "line")] if boxes is None else boxes
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


class FlakyClient(FakeClient):
    """首次 VL 调用抛 RuntimeError（网络抖动），其后正常。"""

    def chat_image(self, prompt, image_bytes, **kw):
        self.parse_calls += 1
        if self.parse_calls == 1:
            raise RuntimeError("VL 调用失败: connection reset")
        return json.dumps(self.response)


def test_pipeline_runtime_error_isolated(tmp_path):
    _make_pdf(tmp_path / "d.pdf")
    cfg = Config.from_env()
    cfg.cache_dir = str(tmp_path / "cache")
    client = FlakyClient()
    pipe = PaperPipeline(cfg, client, detector=FakeDetector(), fallback=FakeDetector([]))
    session = pipe.run(tmp_path / "d.pdf")  # 不应抛出
    assert session["stage"] == "done"
    assert session["figures"][0]["parse_status"] == "error"
    assert "VL 调用失败" in session["figures"][0]["error"]
    assert session["figures"][1]["parse_status"] == "done"
    assert session["figures"][1]["render_status"] == "done"


def test_run_single(tmp_path):
    from PIL import Image
    img = tmp_path / "in.png"
    Image.new("RGB", (200, 150), (255, 255, 255)).save(img)
    cfg = Config.from_env()
    cfg.cache_dir = str(tmp_path / "cache")
    r = run_single(cfg, FakeClient(), img)
    assert r["status"] == "done"
    assert "image_hash" in r
    r2 = run_single(cfg, FakeClient(), img)
    assert r2["status"] == "done"  # 命中缓存
    assert "image_hash" in r2


def test_render_only(tmp_path):
    _make_pdf(tmp_path / "ro.pdf")
    cfg = Config.from_env()
    cfg.cache_dir = str(tmp_path / "cache")
    pipe = PaperPipeline(cfg, FakeClient(), detector=FakeDetector(), fallback=FakeDetector([]))
    store = pipe.render_only(tmp_path / "ro.pdf")
    assert store.session["stage"] == "ready"
    assert store.session["figures"] == []
    assert len(store.session["pages"]) == 2


def test_render_and_detect_no_parse(tmp_path):
    _make_pdf(tmp_path / "rd.pdf")
    cfg = Config.from_env()
    cfg.cache_dir = str(tmp_path / "cache")
    client = FakeClient()
    pipe = PaperPipeline(cfg, client, detector=FakeDetector(), fallback=FakeDetector([]))
    store = pipe.render_and_detect(tmp_path / "rd.pdf")
    s = store.session
    assert s["stage"] == "ready"
    assert len(s["pages"]) == 2
    assert len(s["figures"]) == 2  # 两页各一张
    assert all(f["parse_status"] == "pending" for f in s["figures"])
    assert client.parse_calls == 0  # 检测阶段不做数据解析


def test_parse_figure_on_demand(tmp_path):
    _make_pdf(tmp_path / "od.pdf")
    cfg = Config.from_env()
    cfg.cache_dir = str(tmp_path / "cache")
    client = FakeClient()
    pipe = PaperPipeline(cfg, client, detector=FakeDetector(), fallback=FakeDetector([]))
    store = pipe.render_and_detect(tmp_path / "od.pdf")
    fid = store.session["figures"][0]["id"]
    result = pipe.parse_figure(store, fid)
    assert result["parse_status"] == "done"
    assert result["render_status"] == "done"
    assert result["chart"]["chart_type"] == "line"
    assert result["crop_path"] and result["code_path"] and result["render_path"]
    assert client.parse_calls == 1
    # 缓存命中：再次解析零推理
    result2 = pipe.parse_figure(store, fid)
    assert result2["parse_status"] == "done"
    assert client.parse_calls == 1
    # 其他图表不受影响
    assert store.session["figures"][1]["parse_status"] == "pending"


def test_parse_figure_missing(tmp_path):
    import pytest
    _make_pdf(tmp_path / "ms.pdf")
    cfg = Config.from_env()
    cfg.cache_dir = str(tmp_path / "cache")
    pipe = PaperPipeline(cfg, FakeClient(), detector=FakeDetector(), fallback=FakeDetector([]))
    store = pipe.render_only(tmp_path / "ms.pdf")
    with pytest.raises(KeyError):
        pipe.parse_figure(store, "p1-f9")


def test_detect_redetect_clears(tmp_path):
    _make_pdf(tmp_path / "re.pdf")
    cfg = Config.from_env()
    cfg.cache_dir = str(tmp_path / "cache")
    pipe = PaperPipeline(cfg, FakeClient(), detector=FakeDetector(), fallback=FakeDetector([]))
    store = pipe.render_and_detect(tmp_path / "re.pdf")
    assert len(store.session["figures"]) == 2
    pipe2 = PaperPipeline(cfg, FakeClient(), detector=FakeDetector([]), fallback=FakeDetector([]))
    pipe2.detect(store)  # 换无框检测器重新检测
    assert store.session["stage"] == "ready"
    assert store.session["figures"] == []


def test_run_render_failure_sets_failed_stage(tmp_path):
    """渲染失败（非 PDF 内容）时 run() 写回 stage=failed 后重抛（与旧版等价）。"""
    import pytest
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"not a pdf at all")
    cfg = Config.from_env()
    cfg.cache_dir = str(tmp_path / "cache")
    pipe = PaperPipeline(cfg, FakeClient(), detector=FakeDetector(), fallback=FakeDetector([]))
    with pytest.raises(Exception):
        pipe.run(bad)
    from pathlib import Path as _P
    sess = (_P(cfg.cache_dir) / "papers" / list((_P(cfg.cache_dir) / "papers").iterdir())[0].name / "session.json")
    import json as _json
    data = _json.loads(sess.read_text(encoding="utf-8"))
    assert data["stage"] == "failed"
    assert data.get("error")


def test_render_only_clears_stale_figures(tmp_path):
    """同一 PDF 先检测后仅渲染：figures 必须清空（detect=false 为纯阅读）。"""
    _make_pdf(tmp_path / "stale.pdf")
    cfg = Config.from_env()
    cfg.cache_dir = str(tmp_path / "cache")
    pipe = PaperPipeline(cfg, FakeClient(), detector=FakeDetector(), fallback=FakeDetector([]))
    store = pipe.render_and_detect(tmp_path / "stale.pdf")
    assert len(store.session["figures"]) == 2
    store2 = pipe.render_only(tmp_path / "stale.pdf")  # 复用同一 hash 会话
    assert store2.session["figures"] == []
    assert store2.session["stage"] == "ready"
