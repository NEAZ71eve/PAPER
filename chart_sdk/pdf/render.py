from __future__ import annotations

from pathlib import Path

import fitz
from PIL import Image

from chart_sdk.pdf.geom import clamp_bbox


def render_pages(pdf_path: Path, out_dir: Path, dpi: int = 150, max_pages: int = 30) -> list[dict]:
    """逐页渲染 PNG；返回 [{page, png_path(相对 out_dir 父目录), width, height}]。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    pages = []
    with fitz.open(pdf_path) as doc:
        for i in range(min(len(doc), max_pages)):
            pix = doc[i].get_pixmap(dpi=dpi)
            name = f"page-{i + 1:02d}.png"
            pix.save(out_dir / name)
            pages.append({"page": i + 1, "png_path": f"pages/{name}", "width": pix.width, "height": pix.height})
    return pages


def crop_page_region(page_png: Path, bbox_px: list, out_path: Path) -> None:
    """按像素 bbox 裁剪页面 PNG（越界自动钳制）。"""
    with Image.open(page_png) as im:
        w, h = im.size
        box = clamp_bbox(bbox_px, w, h, min_side=1)
        if box is None:
            raise ValueError(f"bbox 退化: {bbox_px}")
        im.crop(tuple(box)).save(out_path)
