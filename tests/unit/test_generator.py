from chart_sdk.codegen.generator import generate_code


def _chart(ct, **kw):
    base = {
        "chart_type": ct, "title": kw.get("title", "T"),
        "x_axis": {"label": "X", "unit": None}, "y_axis": {"label": "Y", "unit": None},
        "legend": [], "series": [], "heatmap": None, "warnings": [],
    }
    base.update(kw)
    return base


def test_line_code_contains_data_and_savefig(tmp_path):
    chart = _chart("line", legend=["a"], series=[{"name": "a", "x": [1, 2], "y": [71.2, 74.8]}])
    code = generate_code(chart, tmp_path / "r.png")
    assert "ax.plot" in code
    assert "71.2" in code
    assert str(tmp_path / "r.png") in code
    assert 'matplotlib.use("Agg")' in code


def test_bar_code(tmp_path):
    chart = _chart("bar", legend=["a", "b"], series=[
        {"name": "a", "x": ["x1", "x2"], "y": [1.0, 2.0]},
        {"name": "b", "x": ["x1", "x2"], "y": [2.0, 3.0]},
    ])
    code = generate_code(chart, tmp_path / "r.png")
    assert "ax.bar" in code
    assert "set_xticklabels" in code


def test_heatmap_code(tmp_path):
    chart = _chart("heatmap", heatmap={"x_labels": ["a", "b"], "y_labels": ["u"], "matrix": [[1.0, 2.0]], "colormap_hint": None})
    code = generate_code(chart, tmp_path / "r.png")
    assert "imshow" in code
    assert "colorbar" in code


def test_unknown_type_raises(tmp_path):
    import pytest
    from chart_sdk.codegen.generator import CodeGenError
    with pytest.raises(CodeGenError):
        generate_code(_chart("pie"), tmp_path / "r.png")
