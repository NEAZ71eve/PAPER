import pytest

from chart_sdk.vision.validator import ValidationError, validate_chart


def _line_chart():
    return {
        "chart_type": "line",
        "title": "t",
        "x_axis": {"label": "Epoch", "unit": None},
        "y_axis": {"label": "Acc", "unit": "%"},
        "legend": ["a", "b"],
        "series": [
            {"name": "a", "x": [1, 2, 3], "y": [71.2, 74.8, 76.1]},
            {"name": "b", "x": [1, 2, 3], "y": [73.0, 77.5, 80.3]},
        ],
        "heatmap": None,
    }


def test_valid_line_chart():
    out, warns = validate_chart(_line_chart())
    assert out["chart_type"] == "line"
    assert len(out["series"]) == 2
    assert warns == []


def test_invalid_chart_type():
    with pytest.raises(ValidationError):
        validate_chart({"chart_type": "pie", "series": []})


def test_empty_series_raises():
    d = _line_chart()
    d["series"] = []
    with pytest.raises(ValidationError):
        validate_chart(d)


def test_length_mismatch_raises():
    d = _line_chart()
    d["series"][0]["y"] = [1.0, 2.0]
    with pytest.raises(ValidationError):
        validate_chart(d)


def test_nonfinite_dropped_with_warning():
    d = _line_chart()
    d["series"][0]["y"] = [71.2, "NaN", 76.1]
    d["series"][0]["x"] = [1, 2, 3]
    out, warns = validate_chart(d)
    assert out["series"][0]["y"] == [71.2, 76.1]
    assert warns and "丢弃" in warns[0]


def test_all_points_invalid_raises():
    d = _line_chart()
    d["series"][0]["y"] = ["x", "y", "z"]
    d["series"][0]["x"] = [1, 2, 3]
    with pytest.raises(ValidationError):
        validate_chart(d)


def test_valid_heatmap():
    d = {
        "chart_type": "heatmap",
        "title": "h",
        "x_axis": {"label": None, "unit": None},
        "y_axis": {"label": None, "unit": None},
        "legend": [],
        "series": [],
        "heatmap": {"x_labels": ["a", "b"], "y_labels": ["u", "v"], "matrix": [[1, 2], [3, 4]], "colormap_hint": "viridis"},
    }
    out, warns = validate_chart(d)
    assert out["heatmap"]["matrix"] == [[1.0, 2.0], [3.0, 4.0]]


def test_valid_combo_chart_preserves_series_and_secondary_axis():
    d = {
        "chart_type": "combo",
        "title": "connectivity by group",
        "x_axis": {"label": "group", "unit": None},
        "y_axis": {"label": "fragments", "unit": None},
        "y_axis_right": {"label": "edges", "unit": None},
        "series": [
            {"name": "fragments", "kind": "bar", "axis": "left", "x": ["g1", "g2"], "y": [12, 49]},
            {"name": "edges", "kind": "line", "axis": "right", "x": ["g2"], "y": [27]},
        ],
    }

    out, warnings = validate_chart(d)

    assert out["chart_type"] == "combo"
    assert out["series"][0]["kind"] == "bar"
    assert out["series"][1]["axis"] == "right"
    assert out["y_axis_right"]["label"] == "edges"
    assert any("组合图" in warning for warning in warnings)
    assert any("x 类别不一致" in warning for warning in warnings)


def test_combo_inferred_from_mixed_series_even_when_model_says_line():
    d = {
        "chart_type": "line",
        "title": "connectivity by group",
        "x_axis": {"label": "group", "unit": None},
        "y_axis": {"label": "fragments", "unit": None},
        "y_axis_right": {"label": "edges", "unit": None},
        "series": [
            {"name": "fragments", "kind": "bar", "axis": "left", "x": ["g1", "g2"], "y": [12, 49]},
            {"name": "edges", "kind": "line", "axis": "right", "x": ["g1", "g2"], "y": [2, 27]},
        ],
    }

    out, warnings = validate_chart(d)

    assert out["chart_type"] == "combo"
    assert out["series"][1]["axis"] == "right"
    assert warnings


def test_combo_rejects_secondary_axis_without_right_series():
    d = {
        "chart_type": "combo",
        "title": "invalid axis mapping",
        "x_axis": {"label": "group", "unit": None},
        "y_axis": {"label": "fragments", "unit": None},
        "y_axis_right": {"label": "edges", "unit": None},
        "series": [
            {"name": "bars", "kind": "bar", "axis": "left", "x": ["g1"], "y": [12]},
            {"name": "line", "kind": "line", "axis": "left", "x": ["g1"], "y": [2]},
        ],
    }

    with pytest.raises(ValidationError, match="没有分配到右轴"):
        validate_chart(d)


def test_combo_single_kind_downgrades_to_that_kind():
    """模型误判 combo 且只有一种系列/无右轴信号时降级为单类型，不再报错。"""
    d = {
        "chart_type": "combo",
        "title": "bars only",
        "x_axis": {"label": "group", "unit": None},
        "y_axis": {"label": "value", "unit": None},
        "series": [{"name": "bars", "kind": "bar", "x": ["g1", "g2"], "y": [12, 49]}],
    }
    out, warns = validate_chart(d)
    assert out["chart_type"] == "bar"
    assert "kind" not in out["series"][0]
    assert any("combo" in w for w in warns)


def test_combo_single_kind_with_right_axis_downgrades():
    """combo 只有一种系列但带右轴信息时同样降级，避免复刻直接失败。"""
    d = {
        "chart_type": "combo",
        "title": "bars with stray right axis",
        "x_axis": {"label": "group", "unit": None},
        "y_axis": {"label": "value", "unit": None},
        "y_axis_right": {"label": "unused", "unit": None},
        "series": [{"name": "bars", "kind": "bar", "axis": "right", "x": ["g1"], "y": [12]}],
    }
    out, warns = validate_chart(d)
    assert out["chart_type"] == "bar"
    assert "y_axis_right" not in out
    assert out["series"][0].get("axis") is None
    assert any("combo" in w for w in warns)


def test_heatmap_ragged_raises():
    d = {
        "chart_type": "heatmap",
        "title": "",
        "x_axis": {"label": None, "unit": None},
        "y_axis": {"label": None, "unit": None},
        "legend": [],
        "series": [],
        "heatmap": {"x_labels": [], "y_labels": [], "matrix": [[1, 2], [3]], "colormap_hint": None},
    }
    with pytest.raises(ValidationError):
        validate_chart(d)


def test_heatmap_nonfinite_replaced():
    d = {
        "chart_type": "heatmap",
        "title": "",
        "x_axis": {"label": None, "unit": None},
        "y_axis": {"label": None, "unit": None},
        "legend": [],
        "series": [],
        "heatmap": {"x_labels": [], "y_labels": [], "matrix": [[1, "NaN"], [3, 4]], "colormap_hint": None},
    }
    out, warns = validate_chart(d)
    assert out["heatmap"]["matrix"] == [[1.0, 0.0], [3.0, 4.0]]
    assert warns
