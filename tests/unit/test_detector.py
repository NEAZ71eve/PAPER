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


def _make_pdf_with_vector_chart(path: Path):
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.draw_rect(fitz.Rect(100, 150, 480, 400), color=(0, 0, 0))
    page.draw_rect(fitz.Rect(120, 170, 460, 380), color=(0, 0, 0))
    for y in (190, 240, 290, 340, 390):
        page.draw_line((130, y), (450, y), color=(0.7, 0.7, 0.7), width=0.5)
    page.draw_rect(fitz.Rect(160, 330, 210, 390), color=None, fill=(0.1, 0.4, 0.8))
    page.draw_line((180, 250), (300, 210), color=(0.8, 0.3, 0.1), width=2)
    doc.save(str(path))
    doc.close()


def _render(pdf: Path, out_dir: Path, dpi=72):
    from chart_sdk.pdf.render import render_pages
    return render_pages(pdf, out_dir, dpi=dpi, max_pages=30)


def test_finalize_merges_heavily_overlapping_boxes():
    """同一图表被重复检测且框部分交叠时应合并为外接框，避免互相遮挡。"""
    from chart_sdk.pdf.detector import FigureBBox

    def bbox(i, box):
        return FigureBBox(id=f"p1-f{i}", page=1, bbox_norm=[0, 0, 0, 0], bbox_px=list(box),
                          type="line", source="vl_grounding", caption_hint=None)

    items = [
        bbox(1, [372, 476, 988, 1086]),
        bbox(2, [0, 527, 778, 1509]),
    ]
    out = VLGroundingDetector._finalize(items, 1, (1240, 1754))
    assert len(out) == 1
    assert out[0].bbox_px == [0, 476, 988, 1509]


def test_finalize_keeps_separate_boxes():
    from chart_sdk.pdf.detector import FigureBBox

    def bbox(i, box):
        return FigureBBox(id=f"p1-f{i}", page=1, bbox_norm=[0, 0, 0, 0], bbox_px=list(box),
                          type="line", source="vl_grounding", caption_hint=None)

    items = [bbox(1, [100, 100, 500, 300]), bbox(2, [100, 700, 500, 900])]
    out = VLGroundingDetector._finalize(items, 1, (1240, 1754))
    assert [it.bbox_px for it in out] == [[100, 100, 500, 300], [100, 700, 500, 900]]


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


def test_vl_grounding_retries_empty_page_as_overlapping_tiles(tmp_path):
    page_png = tmp_path / "page.png"
    Image.new("RGB", (1000, 1000), "white").save(page_png)
    chart_left = {"bbox_2d": [429, 207, 1000, 766], "type": "line", "caption": "chart"}
    chart_right = {"bbox_2d": [0, 207, 571, 766], "type": "line", "caption": "chart"}
    client = FakeClient([
        "[]", "[]", "[]", json.dumps([chart_left]), json.dumps([chart_right]),
    ])
    detector = VLGroundingDetector(Config.from_env(), client)

    figures = detector.detect_page(page_png, None, 4)

    assert client.calls == 5
    assert len(figures) == 1
    assert figures[0].id == "p4-f1"
    assert figures[0].bbox_px == [300, 445, 700, 836]
    assert figures[0].bbox_norm == [300, 445, 700, 836]


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


def test_vector_fallback_detects_chart_without_embedded_images(tmp_path):
    pdf = tmp_path / "vector.pdf"
    _make_pdf_with_vector_chart(pdf)
    _render(pdf, tmp_path / "vector-pages")
    page_png = tmp_path / "vector-pages" / "page-01.png"
    with fitz.open(pdf) as doc:
        detector = BitmapFallbackDetector(Config.from_env(), FakeClient([json.dumps({"type": "combo"})]))
        figures = detector.detect_page(page_png, doc[0], 1)

    assert len(figures) == 1
    assert detector.client.calls == 1
    assert figures[0].type == "combo"
    assert figures[0].source == "vector_fallback"
