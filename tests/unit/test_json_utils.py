from chart_sdk.vision.json_utils import extract_json


def test_plain_json():
    assert extract_json('{"a": 1}') == {"a": 1}
    assert extract_json('[1, 2]') == [1, 2]


def test_markdown_fences():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_prose_wrapped():
    assert extract_json('结果如下：{"bbox_2d": [1,2,3,4]} 以上。') == {"bbox_2d": [1, 2, 3, 4]}


def test_no_json_returns_none():
    assert extract_json("没有内容") is None
