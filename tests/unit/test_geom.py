from chart_sdk.pdf.geom import clamp_bbox, dedup_bboxes, iou, norm_to_px, px_to_norm
from chart_sdk.pdf.detector import FigureBBox


def test_norm_to_px_spec_example():
    # 设计文档 5.1 示例：A4 150DPI 页面 1240x1754
    assert norm_to_px([120, 300, 880, 720], 1240, 1754) == [149, 526, 1091, 1263]


def test_px_to_norm_roundtrip():
    px = norm_to_px([120, 300, 880, 720], 1240, 1754)
    n = px_to_norm(px, 1240, 1754)
    assert all(abs(a - b) <= 1 for a, b in zip(n, [120, 300, 880, 720]))


def test_clamp_bbox_keeps_valid():
    assert clamp_bbox([10, 10, 200, 200], 1240, 1754) == [10, 10, 200, 200]


def test_clamp_bbox_drops_tiny():
    assert clamp_bbox([10, 10, 30, 30], 1240, 1754) is None


def test_clamp_bbox_pulls_into_page():
    assert clamp_bbox([-50, -50, 200, 200], 1240, 1754) == [0, 0, 200, 200]


def test_iou_identical_and_disjoint():
    assert iou([0, 0, 10, 10], [0, 0, 10, 10]) == 1.0
    assert iou([0, 0, 10, 10], [20, 20, 30, 30]) == 0.0


def _bbox(i, box):
    return FigureBBox(id=f"f{i}", page=1, bbox_norm=[0, 0, 1, 1], bbox_px=box, type="line", source="vl_grounding", caption_hint=None)


def test_dedup_merges_overlap():
    items = [_bbox(0, [0, 0, 100, 100]), _bbox(1, [5, 5, 95, 95]), _bbox(2, [200, 200, 300, 300])]
    out = dedup_bboxes(items, thr=0.7)
    assert len(out) == 2
    assert out[0].id == "f0"
