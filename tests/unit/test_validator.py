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
