import json

import pytest

from chart_sdk.annotate.store import AnnotationStore

STROKE = {"id": "s-1", "tool": "pen", "color": "#CC2936", "width": 2.0,
          "points": [[0.1, 0.2], [0.3, 0.4]]}
COMMENT = {"id": "c-1", "x": 0.5, "y": 0.5, "text": "存疑", "resolved": False,
           "created_at": "2026-10-19T22:40:00", "updated_at": "2026-10-19T22:41:00"}


def test_load_empty_skeleton(tmp_path):
    store = AnnotationStore(tmp_path)
    assert store.load() == {"version": 1, "pages": {}}


def test_roundtrip(tmp_path):
    store = AnnotationStore(tmp_path)
    data = {"version": 1, "pages": {"3": {"strokes": [STROKE], "comments": [COMMENT]}}}
    store.save(data)
    again = AnnotationStore(tmp_path).load()
    assert again["pages"]["3"]["strokes"][0]["id"] == "s-1"
    assert again["pages"]["3"]["comments"][0]["text"] == "存疑"
    assert again["version"] == 1


def test_corrupt_file_returns_skeleton(tmp_path):
    (tmp_path / "annotations.json").write_text("{不是JSON", encoding="utf-8")
    assert AnnotationStore(tmp_path).load() == {"version": 1, "pages": {}}


def test_atomic_write_no_tmp_left(tmp_path):
    store = AnnotationStore(tmp_path)
    store.save({"version": 1, "pages": {"1": {"strokes": [STROKE], "comments": []}}})
    assert (tmp_path / "annotations.json").exists()
    assert not (tmp_path / "annotations.json.tmp").exists()


@pytest.mark.parametrize("bad", [
    {"pages": {"x": {"strokes": [], "comments": []}}},                      # 页码键非数字
    {"pages": {"1": {"strokes": [dict(STROKE, tool="crayon")], "comments": []}}},  # 非法工具
    {"pages": {"1": {"strokes": [dict(STROKE, points=[[1.5, 0.2]])], "comments": []}}},  # 坐标越界
    {"pages": {"1": {"strokes": [dict(STROKE, width=0)], "comments": []}}},  # 非正宽度
    {"pages": {"1": {"strokes": [], "comments": [dict(COMMENT, x=2.0)]}}},   # 批注坐标越界
    {"pages": {"1": {"strokes": [], "comments": [dict(COMMENT, resolved="yes")]}}},  # resolved 非布尔
    {"pages": {"1": {"strokes": {}, "comments": []}}},                       # strokes 非列表
    {"foo": 1},                                                              # 缺 pages
])
def test_invalid_structures_raise(tmp_path, bad):
    store = AnnotationStore(tmp_path)
    with pytest.raises(ValueError):
        store.save(bad)


def test_save_creates_parent_dir(tmp_path):
    """paper_root 尚未创建时也能保存（父目录自动创建）。"""
    store = AnnotationStore(tmp_path / "papers" / "h1")
    store.save({"version": 1, "pages": {"1": {"strokes": [STROKE], "comments": []}}})
    assert (tmp_path / "papers" / "h1" / "annotations.json").exists()
