from pathlib import Path

import fitz
from PIL import Image

from chart_sdk.pdf.render import crop_page_region, render_pages


def _make_pdf(path: Path, with_image: bool = False):
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 72), "Test page")
    if with_image:
        png = path.parent / "tmp.png"
        Image.new("RGB", (300, 200), (200, 60, 60)).save(png)
        page.insert_image(fitz.Rect(72, 100, 400, 350), filename=str(png))
        png.unlink()
    doc.save(str(path))
    doc.close()


def test_render_pages(tmp_path):
    pdf = tmp_path / "a.pdf"
    _make_pdf(pdf)
    out = tmp_path / "pages"
    pages = render_pages(pdf, out, dpi=72, max_pages=30)
    assert len(pages) == 1
    assert pages[0]["page"] == 1
    assert pages[0]["png_path"] == "pages/page-01.png"
    assert (out / "page-01.png").exists()
    assert pages[0]["width"] == 595


def test_render_pages_max_pages(tmp_path):
    pdf = tmp_path / "b.pdf"
    doc = fitz.open()
    for _ in range(5):
        doc.new_page()
    doc.save(str(pdf))
    doc.close()
    pages = render_pages(pdf, tmp_path / "p2", dpi=72, max_pages=3)
    assert len(pages) == 3


def test_crop_page_region(tmp_path):
    pdf = tmp_path / "c.pdf"
    _make_pdf(pdf, with_image=True)
    out = tmp_path / "pages"
    pages = render_pages(pdf, out, dpi=72, max_pages=1)
    crop = tmp_path / "crop.png"
    crop_page_region(out / "page-01.png", [72, 100, 400, 350], crop)
    assert crop.exists()
    with Image.open(crop) as im:
        assert im.size == (328, 250)
