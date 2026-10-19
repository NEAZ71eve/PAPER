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
    if ct not in ("line", "bar", "heatmap"):
        raise ValidationError(f"chart_type 非法: {ct!r}")
    warnings: list[str] = []
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
    if ct in ("line", "bar"):
        series = data.get("series") or []
        if not series:
            raise ValidationError("series 为空")
        for idx, s in enumerate(series, 1):
            s = s if isinstance(s, dict) else {}
            name = str(s.get("name") or f"series{idx}")
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
            out["series"].append({"name": name, "x": [p[0] for p in pairs], "y": [p[1] for p in pairs]})
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
