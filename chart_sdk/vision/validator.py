from __future__ import annotations

import math


class ValidationError(Exception):
    pass


def _finite(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _axis(d) -> dict:
    d = d if isinstance(d, dict) else {}
    return {"label": d.get("label"), "unit": d.get("unit")}


def validate_chart(data) -> tuple[dict, list[str]]:
    """清洗并校验 chart JSON；致命问题抛 ValidationError，可疑项进 warnings。"""
    if not isinstance(data, dict):
        raise ValidationError("顶层必须是 JSON 对象")
    ct = data.get("chart_type")
    if ct not in ("line", "bar", "combo", "heatmap"):
        raise ValidationError(f"chart_type 非法: {ct!r}")
    raw_series = data.get("series") or []
    raw_kinds = {
        s.get("kind") for s in raw_series
        if isinstance(s, dict) and s.get("kind") in ("line", "bar")
    }
    has_combo_signal = (
        data.get("y_axis_right") is not None
        or any(isinstance(s, dict) and s.get("axis") == "right" for s in raw_series)
        or len(raw_kinds) > 1
    )
    if ct in ("line", "bar") and has_combo_signal:
        ct = "combo"
    warnings: list[str] = []
    if ct == "combo" and len(raw_kinds) == 1:
        # 模型误判组合图：仅一种系列类型 → 按该单类型处理（右轴信息一并忽略）
        ct = next(iter(raw_kinds))
        warnings.append(f"模型返回 combo 但仅含 {ct} 系列，已按 {ct} 处理")
    out = {
        "chart_type": ct,
        "title": str(data.get("title") or ""),
        "x_axis": _axis(data.get("x_axis")),
        "y_axis": _axis(data.get("y_axis")),
        "legend": [str(x) for x in (data.get("legend") or []) if x is not None],
        "series": [],
        "heatmap": None,
        "warnings": warnings,
    }
    if ct == "combo":
        out["y_axis_right"] = _axis(data.get("y_axis_right"))
    if ct in ("line", "bar", "combo"):
        series = data.get("series") or []
        if not series:
            raise ValidationError("series 为空")
        kinds = set()
        for idx, s in enumerate(series, 1):
            s = s if isinstance(s, dict) else {}
            name = str(s.get("name") or f"series{idx}")
            kind = s.get("kind") if ct == "combo" else ct
            axis = s.get("axis", "left") if ct == "combo" else "left"
            if kind not in ("line", "bar"):
                raise ValidationError(f"{name} kind 必须为 line 或 bar")
            if axis not in ("left", "right"):
                raise ValidationError(f"{name} axis 必须为 left 或 right")
            kinds.add(kind)
            xs, ys = list(s.get("x") or []), list(s.get("y") or [])
            if len(xs) != len(ys):
                raise ValidationError(f"{name} x/y 长度不一致")
            pairs = []
            dropped = 0
            for x, y in zip(xs, ys):
                if _finite(y):
                    pairs.append((x, y))
                else:
                    dropped += 1
            if dropped:
                warnings.append(f"{name} 丢弃 {dropped} 个非数值点")
            if not pairs:
                raise ValidationError(f"{name} 无有效数据点")
            clean = {"name": name, "x": [p[0] for p in pairs], "y": [p[1] for p in pairs]}
            if ct == "combo":
                clean.update({"kind": kind, "axis": axis})
            out["series"].append(clean)
        if ct == "combo":
            if kinds != {"line", "bar"}:
                raise ValidationError("combo 必须同时包含 line 和 bar 系列")
            reference_x = out["series"][0]["x"]
            if any(s["x"] != reference_x for s in out["series"][1:]):
                warnings.append("组合图系列的 x 类别不一致，复刻图将按类别并集对齐，请核对")
            if any(s["axis"] == "right" for s in out["series"]):
                if not isinstance(data.get("y_axis_right"), dict):
                    raise ValidationError("右轴系列缺少 y_axis_right")
            elif data.get("y_axis_right") is not None:
                raise ValidationError("存在 y_axis_right 但没有分配到右轴的系列")
            warnings.append("组合图数据由像素估计，请人工核对系列类型、左右轴和数值")
    else:
        hm = data.get("heatmap") or {}
        matrix = hm.get("matrix") or []
        if not matrix or not all(isinstance(r, list) for r in matrix):
            raise ValidationError("heatmap.matrix 为空或格式非法")
        widths = {len(r) for r in matrix}
        if len(widths) != 1:
            raise ValidationError("heatmap 行长度不一致")
        cleaned = []
        bad = 0
        for r in matrix:
            row = []
            for v in r:
                if _finite(v):
                    row.append(float(v))
                else:
                    row.append(0.0)
                    bad += 1
            cleaned.append(row)
        if bad:
            warnings.append(f"heatmap 中 {bad} 个非数值替换为 0")
        out["heatmap"] = {
            "x_labels": [str(v) for v in (hm.get("x_labels") or [])],
            "y_labels": [str(v) for v in (hm.get("y_labels") or [])],
            "matrix": cleaned,
            "colormap_hint": hm.get("colormap_hint"),
        }
    return out, warnings
