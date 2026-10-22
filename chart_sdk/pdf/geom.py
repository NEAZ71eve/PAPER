from __future__ import annotations

MIN_SIDE_PX = 40


def norm_to_px(bbox: list, page_w: int, page_h: int) -> list[int]:
    """0-1000 归一化坐标 → 像素坐标（设计文档 5.1 换算规则）。"""
    return [int(round(v / 1000 * d)) for v, d in zip(bbox, (page_w, page_h, page_w, page_h))]


def px_to_norm(bbox: list, page_w: int, page_h: int) -> list[int]:
    out = [int(round(v / d * 1000)) for v, d in zip(bbox, (page_w, page_h, page_w, page_h))]
    return [min(1000, max(0, v)) for v in out]


def clamp_bbox(bbox_px: list, page_w: int, page_h: int, min_side: int = MIN_SIDE_PX) -> list[int] | None:
    """钳制到页面范围；短边小于 min_side 视为退化返回 None。"""
    x0, y0, x1, y1 = (int(round(v)) for v in bbox_px)
    x0 = max(0, min(x0, page_w - 1))
    y0 = max(0, min(y0, page_h - 1))
    x1 = max(x0 + 1, min(x1, page_w))
    y1 = max(y0 + 1, min(y1, page_h))
    if (x1 - x0) < min_side or (y1 - y0) < min_side:
        return None
    return [x0, y0, x1, y1]


def iou(a: list, b: list) -> float:
    ix0, iy0 = max(a[0], b[0]), max(a[1], b[1])
    ix1, iy1 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, ix1 - ix0) * max(0, iy1 - iy0)
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def _area(bbox: list) -> int:
    return max(0, bbox[2] - bbox[0]) * max(0, bbox[3] - bbox[1])


def overlap_ratio(a: list, b: list) -> float:
    """交叠面积 / 较小框面积；接近 1 表示一个框被另一个框包含。"""
    ix0, iy0 = max(a[0], b[0]), max(a[1], b[1])
    ix1, iy1 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, ix1 - ix0) * max(0, iy1 - iy0)
    smaller = min(_area(a), _area(b))
    return inter / smaller if smaller else 0.0


def dedup_bboxes(items: list, thr: float = 0.7, containment: float = 0.85) -> list:
    """去重：IoU 高或包含度高视为同一图框；保留面积较大者，按阅读顺序输出。"""
    kept: list = []
    for it in sorted(items, key=lambda x: _area(x.bbox_px), reverse=True):
        if all(
            iou(it.bbox_px, k.bbox_px) <= thr and overlap_ratio(it.bbox_px, k.bbox_px) < containment
            for k in kept
        ):
            kept.append(it)
    kept.sort(key=lambda x: (x.bbox_px[1], x.bbox_px[0]))
    return kept
