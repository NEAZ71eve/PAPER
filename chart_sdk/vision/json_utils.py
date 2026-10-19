from __future__ import annotations

import json


def extract_json(text: str):
    """从模型输出中提取第一个 JSON 值（对象或数组），失败返回 None。"""
    if not text:
        return None
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text[:4].lower() == "json":
            text = text[4:].strip()
    dec = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch in "[{":
            try:
                obj, _ = dec.raw_decode(text[i:])
                return obj
            except json.JSONDecodeError:
                continue
    return None
