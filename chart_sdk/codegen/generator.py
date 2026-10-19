from __future__ import annotations

from pathlib import Path

HEADER = '''import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

fig, ax = plt.subplots(figsize=(7, 4.5), dpi=150)
'''


class CodeGenError(Exception):
    pass


def generate_code(chart: dict, out_png: Path) -> str:
    """按 chart_type 匹配模板，数据以字面量嵌入，生成可独立执行的 matplotlib 代码。"""
    ct = chart.get("chart_type")
    title = repr(chart.get("title") or "")
    xlabel = repr((chart.get("x_axis") or {}).get("label") or "")
    ylabel = repr((chart.get("y_axis") or {}).get("label") or "")
    save = f'plt.savefig(r"{out_png}", bbox_inches="tight")\n'
    if ct == "line":
        body = f"series = {chart['series']!r}\n"
        body += 'for s in series:\n    ax.plot(s["x"], s["y"], marker="o", label=s.get("name") or "")\n'
        if len(chart.get("legend") or []) > 1 or len(chart["series"]) > 1:
            body += "ax.legend()\n"
    elif ct == "bar":
        body = f"series = {chart['series']!r}\n"
        body += "n = max(len(s[\"y\"]) for s in series)\nxs = np.arange(n)\nwidth = 0.8 / max(1, len(series))\n"
        body += 'for i, s in enumerate(series):\n    ax.bar(xs + i * width, s["y"], width, label=s.get("name") or "")\n'
        body += "xt = series[0][\"x\"]\n"
        body += 'ax.set_xticks(xs + width * (len(series) - 1) / 2)\n'
        body += 'ax.set_xticklabels([str(v) for v in xt])\n'
        if len(chart["series"]) > 1:
            body += "ax.legend()\n"
    elif ct == "heatmap":
        hm = chart["heatmap"]
        body = f"matrix = np.array({hm['matrix']!r}, dtype=float)\n"
        body += 'im = ax.imshow(matrix, aspect="auto", cmap="viridis")\nfig.colorbar(im, ax=ax)\n'
        if hm.get("x_labels"):
            body += f"ax.set_xticks(range(len({hm['x_labels']!r})))\nax.set_xticklabels({hm['x_labels']!r}, rotation=45, ha=\"right\")\n"
        if hm.get("y_labels"):
            body += f"ax.set_yticks(range(len({hm['y_labels']!r})))\nax.set_yticklabels({hm['y_labels']!r})\n"
    else:
        raise CodeGenError(f"不支持的 chart_type: {ct!r}")
    tail = f"ax.set_title({title})\nax.set_xlabel({xlabel})\nax.set_ylabel({ylabel})\n{save}"
    return HEADER + body + tail
