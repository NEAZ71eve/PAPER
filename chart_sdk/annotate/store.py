"""侧车 annotations.json 读写（设计文档 5.1）：坐标归一化 0-1，stroke width 单位 PDF point。"""
from __future__ import annotations

import json
from pathlib import Path

from chart_sdk.cache.store import _atomic_write_json

_TOOLS = ("pen", "highlighter")


def _check_unit_interval(v, name) -> None:
    if not isinstance(v, (int, float)) or isinstance(v, bool) or not (0.0 <= float(v) <= 1.0):
        raise ValueError(f"{name} 必须在 0-1 区间: {v!r}")


def _validate_stroke(s) -> None:
    if not isinstance(s, dict):
        raise ValueError("stroke 必须为对象")
    if not isinstance(s.get("id"), str) or not s["id"]:
        raise ValueError("stroke 缺 id")
    if s.get("tool") not in _TOOLS:
        raise ValueError(f"stroke.tool 非法: {s.get('tool')!r}")
    if not isinstance(s.get("color"), str):
        raise ValueError("stroke.color 必须为字符串")
    if not isinstance(s.get("width"), (int, float)) or isinstance(s.get("width"), bool) or s["width"] <= 0:
        raise ValueError("stroke.width 必须为正数")
    pts = s.get("points")
    if not isinstance(pts, list) or not pts:
        raise ValueError("stroke.points 必须为非空列表")
    for p in pts:
        if not (isinstance(p, list) and len(p) == 2):
            raise ValueError(f"stroke 点坐标非法: {p!r}")
        _check_unit_interval(p[0], "stroke.x")
        _check_unit_interval(p[1], "stroke.y")


def _validate_comment(c) -> None:
    if not isinstance(c, dict):
        raise ValueError("comment 必须为对象")
    if not isinstance(c.get("id"), str) or not c["id"]:
        raise ValueError("comment 缺 id")
    _check_unit_interval(c.get("x"), "comment.x")
    _check_unit_interval(c.get("y"), "comment.y")
    if not isinstance(c.get("text"), str):
        raise ValueError("comment.text 必须为字符串")
    if not isinstance(c.get("resolved"), bool):
        raise ValueError("comment.resolved 必须为布尔")


class AnnotationStore:
    """单篇论文的标注侧车：data/cache/papers/<hash>/annotations.json。"""

    def __init__(self, paper_root):
        self.path = Path(paper_root) / "annotations.json"

    def load(self) -> dict:
        if not self.path.exists():
            return {"version": 1, "pages": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"version": 1, "pages": {}}
        if not isinstance(data, dict) or not isinstance(data.get("pages"), dict):
            return {"version": 1, "pages": {}}
        data["version"] = 1
        return data

    def save(self, data) -> None:
        """结构校验 + 原子写；非法抛 ValueError。"""
        if not isinstance(data, dict) or not isinstance(data.get("pages"), dict):
            raise ValueError("annotations 缺 pages 对象")
        pages = data["pages"]
        for key, entry in pages.items():
            if not str(key).isdigit():
                raise ValueError(f"页码键必须为数字字符串: {key!r}")
            if not isinstance(entry, dict):
                raise ValueError("页条目必须为对象")
            strokes = entry.get("strokes", [])
            comments = entry.get("comments", [])
            if not isinstance(strokes, list) or not isinstance(comments, list):
                raise ValueError("strokes/comments 必须为列表")
            for s in strokes:
                _validate_stroke(s)
            for c in comments:
                _validate_comment(c)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write_json(self.path, {"version": 1, "pages": pages})
