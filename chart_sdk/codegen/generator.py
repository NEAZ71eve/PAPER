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
    out_png = Path(out_png).resolve()  # 子进程 cwd 为临时目录，相对路径会解析失败 → 强制绝对路径
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
    elif ct == "combo":
        body = f"series = {chart['series']!r}\n"
        body += "categories = list(dict.fromkeys(x for s in series for x in s['x']))\n"
        body += "xs = np.arange(len(categories))\n"
        body += "bar_count = sum(s['kind'] == 'bar' for s in series)\nbar_index = 0\n"
        body += "ax_right = ax.twinx() if any(s['axis'] == 'right' for s in series) else ax\n"
        body += "for s in series:\n    target = ax_right if s['axis'] == 'right' else ax\n"
        body += "    sx = np.array([categories.index(x) for x in s['x']])\n"
        body += "    if s['kind'] == 'bar':\n"
        body += "        width = 0.8 / max(1, bar_count)\n"
        body += "        offset = (bar_index - (bar_count - 1) / 2) * width\n"
        body += "        target.bar(sx + offset, s['y'], width, label=s.get('name') or '')\n"
        body += "        bar_index += 1\n"
        body += "    else:\n        target.plot(sx, s['y'], marker='o', label=s.get('name') or '')\n"
        body += "ax.set_xticks(xs)\nax.set_xticklabels([str(v) for v in categories])\n"
        body += "handles, labels = ax.get_legend_handles_labels()\n"
        body += "if ax_right is not ax:\n    right_handles, right_labels = ax_right.get_legend_handles_labels()\n    handles += right_handles\n    labels += right_labels\n"
        body += "if handles:\n    ax.legend(handles, labels)\n"
        right_label = repr((chart.get("y_axis_right") or {}).get("label") or "")
        body += f"if ax_right is not ax:\n    ax_right.set_ylabel({right_label})\n"
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
