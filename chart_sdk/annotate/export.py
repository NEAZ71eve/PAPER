"""叠加标注导出 PDF 副本（设计文档 7）：墨迹→RGBA 图像层；文本批注→PDF text annotation。"""
from __future__ import annotations

import io
from pathlib import Path

import fitz
from PIL import Image, ImageDraw

from chart_sdk.annotate.store import AnnotationStore


def _with_alpha(color: str, alpha: int):
    color = color.lstrip("#")
    if len(color) == 3:
        color = "".join(c * 2 for c in color)
    return (int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16), alpha)


def _render_strokes(strokes: list, page: "fitz.Page", dpi: int) -> bytes:
    """把一页 strokes 按归一化坐标重绘为透明 RGBA PNG 字节（尺寸=页面渲染像素）。"""
    zoom = dpi / 72.0
    w = max(1, round(page.rect.width * zoom))
    h = max(1, round(page.rect.height * zoom))
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    for s in strokes:
        pts = [(p[0] * w, p[1] * h) for p in s["points"]]
        if len(pts) < 2:
            continue
        width = max(1, round(s["width"] * zoom))  # width 单位 point → 像素
        color = _with_alpha(s["color"], 102) if s["tool"] == "highlighter" else s["color"]
        draw.line(pts, fill=color, width=width, joint="curve")
        r = width / 2  # 圆头端点
        for cx, cy in (pts[0], pts[-1]):
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
    buf = io.BytesIO()
    layer.save(buf, format="PNG")
    return buf.getvalue()


def export_annotated(pdf_path, paper_root, out_dir, dpi: int = 150) -> Path:
    """导出叠加全部标注的新 PDF 副本；原 PDF 与 annotations.json 不受影响。"""
    annotations = AnnotationStore(paper_root).load()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = Path(pdf_path)
    out_path = out_dir / f"annotated-{pdf_path.name}"
    with fitz.open(pdf_path) as doc:
        for pno, entry in annotations["pages"].items():
            idx = int(pno) - 1
            if idx < 0 or idx >= len(doc):
                continue
            page = doc[idx]
            strokes = entry.get("strokes") or []
            if strokes:
                page.insert_image(page.rect, stream=_render_strokes(strokes, page, dpi), overlay=True)
            for c in entry.get("comments") or []:
                point = fitz.Point(c["x"] * page.rect.width, c["y"] * page.rect.height)
                annot = page.add_text_annot(point, c.get("text", ""))
                annot.set_info(title="批注")
                annot.update()
        doc.save(str(out_path))
    return out_path
