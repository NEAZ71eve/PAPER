import pytest

from chart_sdk.codegen.executor import CodeExecError, execute_code
from chart_sdk.codegen.generator import generate_code


def _chart():
    return {
        "chart_type": "line", "title": "t",
        "x_axis": {"label": "x", "unit": None}, "y_axis": {"label": "y", "unit": None},
        "legend": ["a"], "series": [{"name": "a", "x": [1, 2], "y": [1.0, 2.0]}],
        "heatmap": None, "warnings": [],
    }


def test_execute_renders_png(tmp_path):
    out = tmp_path / "render.png"
    code = generate_code(_chart(), out)
    execute_code(code, timeout=30)
    assert out.exists() and out.stat().st_size > 0

def test_combo_chart_renders_bars_and_secondary_axis_line(tmp_path):
    chart = {
        "chart_type": "combo", "title": "connectivity by group",
        "x_axis": {"label": "group", "unit": None},
        "y_axis": {"label": "fragments", "unit": None},
        "y_axis_right": {"label": "edges", "unit": None},
        "series": [
            {"name": "fragments", "kind": "bar", "axis": "left", "x": ["g1", "g2"], "y": [12, 49]},
            {"name": "edges", "kind": "line", "axis": "right", "x": ["g2"], "y": [27]},
        ],
    }
    out = tmp_path / "combo.png"

    code = generate_code(chart, out)
    execute_code(code, timeout=30)

    assert "target.bar" in code
    assert "target.plot" in code
    assert "ax.twinx()" in code
    assert out.exists() and out.stat().st_size > 0


def test_syntax_error_raises(tmp_path):
    with pytest.raises(CodeExecError):
        execute_code("this is not python(", timeout=30)


def test_timeout_raises(tmp_path):
    with pytest.raises(CodeExecError, match="超时|timeout"):
        execute_code("import time; time.sleep(60)", timeout=2)
