"""从 arXiv 下载 2 篇公开论文作为真实样例（需要网络；失败可跳过，合成样例兜底）。"""
from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

PAPERS = {
    "resnet-1512.03385.pdf": "https://export.arxiv.org/pdf/1512.03385v2",
    "attention-1706.03762.pdf": "https://export.arxiv.org/pdf/1706.03762v7",
}
OUT = Path(__file__).resolve().parent.parent / "assets" / "samples"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    failed = []
    for name, url in PAPERS.items():
        dst = OUT / name
        if dst.exists():
            print(f"SKIP {name}")
            continue
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "chart-replica-demo/0.1"})
            dst.write_bytes(urllib.request.urlopen(req, timeout=120).read())
            print(f"OK   {name} ({dst.stat().st_size} bytes)")
        except Exception as e:  # noqa: BLE001
            failed.append(name)
            print(f"FAIL {name}: {e}")
    if failed:
        print(f"失败 {len(failed)} 篇，可重跑或使用 synthetic-demo.pdf")
        sys.exit(1)


if __name__ == "__main__":
    main()
