"""生成离线可用的合成样例论文（含折线/柱状/热力图各一页），保证无网络也能演示。"""
from __future__ import annotations

from pathlib import Path

import fitz
import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent.parent
OUT = HERE / "assets" / "samples" / "synthetic-demo.pdf"


def _line_png() -> bytes:
    fig, ax = plt.subplots(figsize=(6, 4), dpi=150)
    x = np.arange(1, 11)
    ax.plot(x, 100 - x * 2.5 + np.random.RandomState(0).randn(10), marker="o", label="baseline")
    ax.plot(x, 95 - x * 1.8 + np.random.RandomState(1).randn(10), marker="s", label="ours")
    ax.set_xlabel("Epoch"); ax.set_ylabel("Error (%)"); ax.legend(); ax.set_title("Training Error")
    fig.savefig(buf := __import__("io").BytesIO(), format="png"); plt.close(fig)
    return buf.getvalue()


def _bar_png() -> bytes:
    fig, ax = plt.subplots(figsize=(6, 4), dpi=150)
    cats = ["A", "B", "C", "D"]
    ax.bar(np.arange(4) - 0.2, [88, 92, 85, 90], 0.4, label="baseline")
    ax.bar(np.arange(4) + 0.2, [91, 95, 89, 93], 0.4, label="ours")
    ax.set_xticks(np.arange(4)); ax.set_xticklabels(cats); ax.set_ylabel("Acc (%)"); ax.legend(); ax.set_title("Accuracy")
    fig.savefig(buf := __import__("io").BytesIO(), format="png"); plt.close(fig)
    return buf.getvalue()


def _heat_png() -> bytes:
    rng = np.random.RandomState(2)
    fig, ax = plt.subplots(figsize=(6, 4), dpi=150)
    im = ax.imshow(rng.rand(8, 12), cmap="viridis", aspect="auto")
    fig.colorbar(im); ax.set_title("Attention Map")
    fig.savefig(buf := __import__("io").BytesIO(), format="png"); plt.close(fig)
    return buf.getvalue()


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    import io
    doc = fitz.open()
    for png in (_line_png(), _bar_png(), _heat_png()):
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 72), "Synthetic demo paper")
        page.insert_image(fitz.Rect(90, 120, 505, 460), stream=png)
    doc.save(str(OUT))
    doc.close()
    print(f"OK {OUT}")


if __name__ == "__main__":
    main()
