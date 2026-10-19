from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import fitz
from PIL import Image

from chart_sdk.config import Config
from chart_sdk.inference.client import VLClient
from chart_sdk.pdf.geom import clamp_bbox, dedup_bboxes, norm_to_px, px_to_norm
from chart_sdk.pdf.render import crop_page_region
from chart_sdk.vision.json_utils import extract_json
from chart_sdk.vision.prompts import CLASSIFY_PROMPT, DETECT_PROMPT


@dataclass
class FigureBBox:
    id: str
    page: int
    bbox_norm: list
    bbox_px: list
    type: str  # line | bar | heatmap
    source: str  # vl_grounding | bitmap_fallback
    caption_hint: str | None


class FigureDetector:
    def detect_page(self, page_png: Path, page: "fitz.Page", page_no: int) -> list[FigureBBox]:
        raise NotImplementedError


class VLGroundingDetector(FigureDetector):
    """整页图 → VL grounding 输出 bbox+类型（主实现，设计文档 6.1 第 3 步）。"""

    def __init__(self, config: Config, client: VLClient):
        self.config = config
        self.client = client

    def detect_page(self, page_png: Path, page: "fitz.Page", page_no: int) -> list[FigureBBox]:
        with Image.open(page_png) as im:
            w, h = im.size
        resp = self.client.chat_image(DETECT_PROMPT, page_png.read_bytes())
        data = extract_json(resp)
        if not isinstance(data, list):
            return []
        items = []
        for i, it in enumerate(data, 1):
            if not isinstance(it, dict):
                continue
            if it.get("type") not in ("line", "bar", "heatmap"):
                continue
            bbox = it.get("bbox_2d")
            if not (isinstance(bbox, list) and len(bbox) == 4):
                continue
            px = clamp_bbox(norm_to_px(bbox, w, h), w, h)
            if px is None:
                continue
            items.append(FigureBBox(
                id=f"p{page_no}-f{i}", page=page_no, bbox_norm=px_to_norm(px, w, h),
                bbox_px=px, type=it["type"], source="vl_grounding",
                caption_hint=str(it.get("caption") or "") or None,
            ))
        items = dedup_bboxes(items)
        for i, it in enumerate(items, 1):
            it.id = f"p{page_no}-f{i}"
        return items


class BitmapFallbackDetector(FigureDetector):
    """嵌入位图提取（PyMuPDF get_image_rects）+ VL 分类过滤（降级实现）。"""

    def __init__(self, config: Config, client: VLClient):
        self.config = config
        self.client = client

    def detect_page(self, page_png: Path, page: "fitz.Page", page_no: int) -> list[FigureBBox]:
        with Image.open(page_png) as im:
            w, h = im.size
        ratio = self.config.dpi / 72.0
        items = []
        i = 0
        for img in page.get_images(full=True):
            xref = img[0]
            for rect in page.get_image_rects(xref):
                i += 1
                bbox_px = [rect.x0 * ratio, rect.y0 * ratio, rect.x1 * ratio, rect.y1 * ratio]
                px = clamp_bbox(bbox_px, w, h)
                if px is None:
                    continue
                with Image.open(page_png) as im:
                    crop = page_png.parent / f"_cls_{page_no}_{i}.png"
                    crop_page_region(page_png, px, crop)
                try:
                    resp = self.client.chat_image(CLASSIFY_PROMPT, crop.read_bytes())
                finally:
                    crop.unlink(missing_ok=True)
                data = extract_json(resp) or {}
                if data.get("type") not in ("line", "bar", "heatmap"):
                    continue
                items.append(FigureBBox(
                    id=f"p{page_no}-f{i}", page=page_no, bbox_norm=px_to_norm(px, w, h),
                    bbox_px=px, type=data["type"], source="bitmap_fallback", caption_hint=None,
                ))
        items = dedup_bboxes(items)
        for j, it in enumerate(items, 1):
            it.id = f"p{page_no}-f{j}"
        return items
