import json

import pytest

from chart_sdk.vision.parser import ParseError, parse_chart

VALID = json.dumps({
    "chart_type": "line", "title": "t",
    "x_axis": {"label": "x", "unit": None}, "y_axis": {"label": "y", "unit": None},
    "legend": ["a"], "series": [{"name": "a", "x": [1, 2], "y": [1.0, 2.0]}],
    "heatmap": None, "warnings": [],
})


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0
        self.prompts = []

    def chat_image(self, prompt, image_bytes, **kw):
        self.calls += 1
        self.prompts.append(prompt)
        return self.responses[min(self.calls - 1, len(self.responses) - 1)]


def test_parse_valid_json():
    c = FakeClient([VALID])
    chart = parse_chart(c, b"img")
    assert chart["chart_type"] == "line"
    assert c.calls == 1


def test_parse_strips_fences():
    c = FakeClient([f"```json\n{VALID}\n```"])
    assert parse_chart(c, b"img")["chart_type"] == "line"


def test_retry_then_success():
    c = FakeClient(["垃圾输出", VALID])
    assert parse_chart(c, b"img")["chart_type"] == "line"
    assert c.calls == 2


def test_both_fail_raises():
    c = FakeClient(["垃圾", "还是垃圾"])
    with pytest.raises(ParseError):
        parse_chart(c, b"img")
    assert c.calls == 2


def test_validation_failure_retries():
    bad = json.dumps({"chart_type": "pie"})
    c = FakeClient([bad, VALID])
    assert parse_chart(c, b"img")["chart_type"] == "line"
