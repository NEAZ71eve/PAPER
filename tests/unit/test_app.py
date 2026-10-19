from chart_sdk.vision.validator import validate_chart
from app.gradio_app import chart_to_dataframe, draw_page_annotations, hit_test


def _chart():
    return validate_chart({
        "chart_type": "line", "title": "t",
        "x_axis": {"label": "x", "unit": None}, "y_axis": {"label": "y", "unit": None},
        "legend": ["a", "b"],
        "series": [{"name": "a", "x": [1, 2], "y": [1.0, 2.0]}, {"name": "b", "x": [1, 2], "y": [3.0, 4.0]}],
        "heatmap": None,
    })[0]


def test_chart_to_dataframe():
    headers, rows = chart_to_dataframe(_chart())
    assert headers == ["x", "a", "b"]
    assert rows[0] == [1, 1.0, 3.0]


def test_draw_page_annotations(tmp_path):
    from PIL import Image
    png = tmp_path / "page.png"
    Image.new("RGB", (400, 300), (255, 255, 255)).save(png)
    figs = [{"id": "p1-f1", "page": 1, "bbox_px": [50, 50, 200, 150], "type": "line", "source": "vl_grounding", "caption_hint": None, "bbox_norm": [0, 0, 1, 1]}]
    out = draw_page_annotations(png, figs)
    assert out.size == (400, 300)


def test_hit_test():
    figs = [{"id": "p1-f1", "bbox_px": [50, 50, 200, 150]}]
    assert hit_test(figs, 100, 100) == "p1-f1"
    assert hit_test(figs, 300, 300) is None
    assert hit_test(figs, 45, 45) == "p1-f1"  # 容差命中
