import fitz
import pytest

from chart_sdk.annotate.export import export_annotated
from chart_sdk.annotate.store import AnnotationStore


def _make_pdf(path, n_pages=2):
    doc = fitz.open()
    for _ in range(n_pages):
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 72), "hello")
    doc.save(str(path))
    doc.close()


def _seed_annotations(root):
    AnnotationStore(root).save({"version": 1, "pages": {
        "1": {"strokes": [
            {"id": "s-1", "tool": "pen", "color": "#CC2936", "width": 2.0,
             "points": [[0.1, 0.1], [0.5, 0.3], [0.9, 0.2]]},
            {"id": "s-2", "tool": "highlighter", "color": "#FFEB3B", "width": 6.0,
             "points": [[0.2, 0.5], [0.8, 0.5]]},
        ], "comments": []},
        "2": {"strokes": [], "comments": [
            {"id": "c-1", "x": 0.5, "y": 0.5, "text": "这个基线数据存疑", "resolved": False,
             "created_at": "t", "updated_at": "t"},
        ]},
    }})


def test_export_overlay_and_annot(tmp_path):
    src = tmp_path / "paper.pdf"
    _make_pdf(src)
    _seed_annotations(tmp_path)
    out = export_annotated(src, tmp_path, tmp_path / "exports")
    assert out.exists() and out.name == "annotated-paper.pdf"
    with fitz.open(out) as doc:
        assert len(doc) == 2
        assert len(doc[0].get_images()) >= 1          # 第 1 页叠加了墨迹图像层
        annots = list(doc[1].annots())                 # 第 2 页写入了文本便签
        assert len(annots) == 1
        assert "存疑" in annots[0].info.get("content", "")
    # 原 PDF 不受影响
    with fitz.open(src) as doc:
        assert len(doc[0].get_images()) == 0


def test_export_empty_annotations(tmp_path):
    src = tmp_path / "blank.pdf"
    _make_pdf(src)
    out = export_annotated(src, tmp_path, tmp_path / "exports")
    assert out.exists()
    with fitz.open(out) as doc:
        assert len(doc) == 2
        assert len(list(doc[0].annots())) == 0


def test_export_out_of_range_page_skipped(tmp_path):
    src = tmp_path / "range.pdf"
    _make_pdf(src, n_pages=1)
    AnnotationStore(tmp_path).save({"version": 1, "pages": {
        "9": {"strokes": [], "comments": [
            {"id": "c-9", "x": 0.5, "y": 0.5, "text": "越界页", "resolved": False,
             "created_at": "t", "updated_at": "t"}]}}})
    out = export_annotated(src, tmp_path, tmp_path / "exports")
    assert out.exists()
