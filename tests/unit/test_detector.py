import json
from pathlib import Path

import fitz
from PIL import Image

from chart_sdk.config import Config
from chart_sdk.pdf.detector import BitmapFallbackDetector, VLGroundingDetector


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def chat_image(self, prompt, image_bytes, **kw):
        self.calls += 1
        return self.responses[min(self.calls - 1, len(self.responses) - 1)]


def _make_pdf_with_image(path: Path, dpi_src_png: Path):
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 72), "Fig detector test")
    page.insert_image(fitz.Rect(72, 100, 400, 350), filename=str(dpi_src_png))
    doc.save(str(path))
    doc.close()


def _render(pdf: Path, out_dir: Path, dpi=72):
    from chart_sdk.pdf.render import render_pages
    return render_pages(pdf, out_dir, dpi=dpi, max_pages=30)


def test_vl_grounding_filters_other_and_dedups(tmp_path):
    pdf = tmp_path / "p.pdf"
    doc = fitz.open()
    doc.new_page(width=595, height=842)
    doc.save(str(pdf))
    doc.close()
    pages = _render(pdf, tmp_path / "pg")
    png = tmp_path / "pg" / "page-01.png"
    import fitz as _f
    with _f.open(str(pdf)) as d:
        page = d[0]
        det = VLGroundingDetector(Config.from_env(), FakeClient([
            json.dumps([
                {"bbox_2d": [100, 100, 800, 700], "type": "line", "caption": "Fig 1"},
                {"bbox_2d": [120, 120, 780, 680], "type": "bar", "caption": ""},
                {"bbox_2d": [100, 100, 900, 200], "type": "other", "caption": ""},
            ])
        ]))
        figs = det.detect_page(png, page, 1)
    assert len(figs) == 1  # 重叠的 bar 被去重，other 被过滤
    assert figs[0].type == "line"
    assert figs[0].source == "vl_grounding"
    assert figs[0].id == "p1-f1"


def test_bitmap_fallback_detects_embedded(tmp_path):
    src = tmp_path / "chart.png"
    Image.new("RGB", (300, 200), (30, 120, 220)).save(src)
    pdf = tmp_path / "p2.pdf"
    _make_pdf_with_image(pdf, src)
    pages = _render(pdf, tmp_path / "pg2")
    png = tmp_path / "pg2" / "page-01.png"
    import fitz as _f
    with _f.open(str(pdf)) as d:
        page = d[0]
        det = BitmapFallbackDetector(Config.from_env(), FakeClient([json.dumps({"type": "bar"})]))
        figs = det.detect_page(png, page, 1)
    assert len(figs) == 1
    assert figs[0].type == "bar"
    assert figs[0].source == "bitmap_fallback"
    assert figs[0].bbox_px[2] > figs[0].bbox_px[0]


def test_bitmap_fallback_drops_other(tmp_path):
    src = tmp_path / "photo.png"
    Image.new("RGB", (300, 200), (10, 10, 10)).save(src)
    pdf = tmp_path / "p3.pdf"
    _make_pdf_with_image(pdf, src)
    pages = _render(pdf, tmp_path / "pg3")
    import fitz as _f
    with _f.open(str(pdf)) as d:
        det = BitmapFallbackDetector(Config.from_env(), FakeClient([json.dumps({"type": "other"})]))
        figs = det.detect_page(tmp_path / "pg3" / "page-01.png", d[0], 1)
    assert figs == []
