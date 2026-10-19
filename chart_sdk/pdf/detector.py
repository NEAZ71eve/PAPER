from dataclasses import dataclass, field


@dataclass
class FigureBBox:
    id: str
    page: int
    bbox_norm: list
    bbox_px: list
    type: str  # line | bar | heatmap
    source: str  # vl_grounding | bitmap_fallback
    caption_hint: str | None
