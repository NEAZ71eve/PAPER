from __future__ import annotations

import io
import json
from dataclasses import dataclass
from pathlib import Path

import fitz
from PIL import Image

from chart_sdk.config import Config
from chart_sdk.inference.client import VLClient
from chart_sdk.pdf.geom import clamp_bbox, dedup_bboxes, iou, norm_to_px, overlap_ratio, px_to_norm
from chart_sdk.pdf.render import crop_page_region
from chart_sdk.vision.json_utils import extract_json
from chart_sdk.vision.prompts import CLASSIFY_PROMPT, DETECT_PROMPT


@dataclass
class FigureBBox:
    id: str
    page: int
    bbox_norm: list
    bbox_px: list
    type: str  # line | bar | combo | heatmap
    source: str  # vl_grounding | bitmap_fallback
    caption_hint: str | None


class FigureDetector:
    def detect_page(self, page_png: Path, page: "fitz.Page", page_no: int) -> list[FigureBBox]:
        raise NotImplementedError


class VLGroundingDetector(FigureDetector):
    """整页优先检测；结果不足两张时用重叠分区补漏。"""

    def __init__(self, config: Config, client: VLClient):
        self.config = config
        self.client = client

    def detect_page(self, page_png: Path, page: "fitz.Page", page_no: int) -> list[FigureBBox]:
        with Image.open(page_png) as im:
            w, h = im.size
            items = self._parse_response(
                self.client.chat_image(DETECT_PROMPT, page_png.read_bytes()),
                page_no, (w, h), (0, 0), (w, h),
            )
            items = self._finalize(items, page_no, (w, h))
            if len(items) >= 2:
                return items

            boxes = self._overlapping_tiles(w, h)
            for x0, y0, x1, y1 in boxes:
                buffer = io.BytesIO()
                im.crop((x0, y0, x1, y1)).save(buffer, format="PNG")
                tile_size = (x1 - x0, y1 - y0)
                resp = self.client.chat_image(DETECT_PROMPT, buffer.getvalue())
                items.extend(self._parse_response(
                    resp, page_no, tile_size, (x0, y0), (w, h),
                ))
        return self._finalize(items, page_no, (w, h))

    @staticmethod
    def _overlapping_tiles(width: int, height: int) -> list[tuple[int, int, int, int]]:
        tile_width = max(1, round(width * 0.7))
        tile_height = max(1, round(height * 0.7))
        x_offsets = (0, width - tile_width)
        y_offsets = (0, height - tile_height)
        return [
            (x0, y0, x0 + tile_width, y0 + tile_height)
            for y0 in y_offsets
            for x0 in x_offsets
        ]

    @staticmethod
    def _parse_response(
        response: str,
        page_no: int,
        image_size: tuple[int, int],
        offset: tuple[int, int],
        page_size: tuple[int, int],
    ) -> list[FigureBBox]:
        data = extract_json(response)
        if not isinstance(data, list):
            return []
        image_width, image_height = image_size
        page_width, page_height = page_size
        offset_x, offset_y = offset
        items = []
        for i, it in enumerate(data, 1):
            if not isinstance(it, dict):
                continue
            if it.get("type") not in ("line", "bar", "combo", "heatmap"):
                continue
            bbox = it.get("bbox_2d")
            if not (isinstance(bbox, list) and len(bbox) == 4):
                continue
            local_px = norm_to_px(bbox, image_width, image_height)
            page_px = [
                local_px[0] + offset_x, local_px[1] + offset_y,
                local_px[2] + offset_x, local_px[3] + offset_y,
            ]
            px = clamp_bbox(page_px, page_width, page_height)
            if px is None:
                continue
            items.append(FigureBBox(
                id=f"p{page_no}-f{i}", page=page_no,
                bbox_norm=px_to_norm(px, page_width, page_height),
                bbox_px=px, type=it["type"], source="vl_grounding",
                caption_hint=str(it.get("caption") or "") or None,
            ))

        return items

    @staticmethod
    def _finalize(items: list[FigureBBox], page_no: int, page_size: tuple[int, int]) -> list[FigureBBox]:
        items = dedup_bboxes(items)
        items = _merge_overlaps(items, page_size)
        items = dedup_bboxes(items)
        items.sort(key=lambda it: (it.bbox_px[1], it.bbox_px[0]))
        for i, it in enumerate(items, 1):
            it.id = f"p{page_no}-f{i}"
        return items


class BitmapFallbackDetector(FigureDetector):
    """嵌入位图或大面积矢量框候选 + VL 分类过滤（降级实现）。"""

    def __init__(self, config: Config, client: VLClient):
        self.config = config
        self.client = client

    def detect_page(self, page_png: Path, page: "fitz.Page", page_no: int) -> list[FigureBBox]:
        with Image.open(page_png) as im:
            w, h = im.size
        ratio = self.config.dpi / 72.0
        items = []
        i = 0
        candidate_boxes = []
        for img in page.get_images(full=True):
            xref = img[0]
            for rect in page.get_image_rects(xref):
                i += 1
                bbox_px = [rect.x0 * ratio, rect.y0 * ratio, rect.x1 * ratio, rect.y1 * ratio]
                px = clamp_bbox(bbox_px, w, h)
                if px is None:
                    continue
                candidate_boxes.append((px, "bitmap_fallback"))

        page_area = page.rect.width * page.rect.height
        vector_boxes = []
        for drawing in page.get_drawings():
            rect = drawing["rect"]
            area = rect.width * rect.height
            aspect = rect.width / rect.height if rect.height else 0
            if not (0.05 <= area / page_area <= 0.65 and 0.4 <= aspect <= 3.0):
                continue
            px = clamp_bbox(
                [rect.x0 * ratio, rect.y0 * ratio, rect.x1 * ratio, rect.y1 * ratio],
                w, h,
            )
            if px is not None:
                vector_boxes.append(px)
        vector_boxes.sort(key=lambda box: (box[2] - box[0]) * (box[3] - box[1]), reverse=True)
        accepted_vectors = []
        for px in vector_boxes:
            if (
                all(not _duplicate_bbox(px, kept) for kept in accepted_vectors)
                and all(not _duplicate_bbox(px, candidate) for candidate, _ in candidate_boxes)
            ):
                accepted_vectors.append(px)
                candidate_boxes.append((px, "vector_fallback"))

        for i, (px, source) in enumerate(candidate_boxes, 1):
            crop = page_png.parent / f"_cls_{page_no}_{i}.png"
            try:
                crop_page_region(page_png, px, crop)
                resp = self.client.chat_image(CLASSIFY_PROMPT, crop.read_bytes())
            finally:
                crop.unlink(missing_ok=True)
            data = extract_json(resp) or {}
            if data.get("type") not in ("line", "bar", "combo", "heatmap"):
                continue
            items.append(FigureBBox(
                id=f"p{page_no}-f{i}", page=page_no, bbox_norm=px_to_norm(px, w, h),
                bbox_px=px, type=data["type"], source=source, caption_hint=None,
            ))
        items = VLGroundingDetector._finalize(items, page_no, (w, h))
        return items


MERGE_IOU = 0.2
MERGE_CONTAINMENT = 0.5


def _merge_overlaps(items: list[FigureBBox], page_size: tuple[int, int]) -> list[FigureBBox]:
    """同一图表被重复检测（框交叠明显）时合并为外接框，避免重叠框互相遮挡。"""
    page_w, page_h = page_size
    merged: list[FigureBBox] = []
    for it in items:
        hit = next(
            (m for m in merged
             if iou(it.bbox_px, m.bbox_px) > MERGE_IOU or overlap_ratio(it.bbox_px, m.bbox_px) >= MERGE_CONTAINMENT),
            None,
        )
        if hit is None:
            merged.append(it)
            continue
        union = [
            min(hit.bbox_px[0], it.bbox_px[0]), min(hit.bbox_px[1], it.bbox_px[1]),
            max(hit.bbox_px[2], it.bbox_px[2]), max(hit.bbox_px[3], it.bbox_px[3]),
        ]
        hit.bbox_px = union
        hit.bbox_norm = px_to_norm(union, page_w, page_h)
    return merged


def _duplicate_bbox(a: list[int], b: list[int]) -> bool:
    ix0, iy0 = max(a[0], b[0]), max(a[1], b[1])
    ix1, iy1 = min(a[2], b[2]), min(a[3], b[3])
    intersection = max(0, ix1 - ix0) * max(0, iy1 - iy0)
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    smaller = min(area_a, area_b)
    return iou(a, b) > 0.7 or (smaller > 0 and intersection / smaller >= 0.85)
