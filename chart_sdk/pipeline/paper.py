from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import fitz

from chart_sdk.cache.store import PaperStore
from chart_sdk.codegen.executor import CodeExecError, execute_code
from chart_sdk.codegen.generator import generate_code
from chart_sdk.config import Config
from chart_sdk.inference.client import VLClient
from chart_sdk.pdf.detector import BitmapFallbackDetector, FigureDetector, VLGroundingDetector
from chart_sdk.pdf.render import crop_page_region, render_pages
from chart_sdk.vision.parser import parse_chart


class PaperPipeline:
    def __init__(self, config: Config, client: VLClient, detector: FigureDetector | None = None, fallback: FigureDetector | None = None):
        self.config = config
        self.client = client
        self.detector = detector or VLGroundingDetector(config, client)
        self.fallback = fallback or BitmapFallbackDetector(config, client)

    def run(self, pdf_path: Path, progress=None) -> dict:
        cb = progress or (lambda stage, done, total, msg: None)
        pdf_path = Path(pdf_path)
        pdf_bytes = pdf_path.read_bytes()
        store = PaperStore(self.config.cache_dir, pdf_bytes, pdf_path.name)
        s = store.session
        try:
            # 1) 页面渲染（已渲染则跳过）
            if not s["pages"]:
                cb("detecting", 0, 1, f"渲染页面（最多 {self.config.max_pages} 页）")
                s["pages"] = render_pages(store.root / "source.pdf", store.root / "pages", self.config.dpi, self.config.max_pages)
                s["n_pages"] = len(s["pages"])
                s["dpi"] = self.config.dpi
                store.save()
            # 2) 图表检测（已有结果则跳过）
            if not s["figures"]:
                figures = []
                pages = s["pages"]
                with fitz.open(store.root / "source.pdf") as doc:
                    for i, p in enumerate(pages):
                        cb("detecting", i, len(pages), f"检测第 {p['page']} 页")
                        page_png = store.root / p["png_path"]
                        try:
                            figs = self.detector.detect_page(page_png, doc[p["page"] - 1], p["page"])
                        except Exception:  # noqa: BLE001 - VL 异常 → 该页降级（设计文档 6.1 第 3 步）
                            figs = self.fallback.detect_page(page_png, doc[p["page"] - 1], p["page"])
                        figures.extend(asdict(f) for f in figs)
                s["figures"] = figures
                store.save()
            # 3) 批量预解析 + 代码生成渲染（跳过已完成）
            figs = s["figures"]
            for i, fig in enumerate(figs):
                if fig.get("parse_status") == "done":
                    continue
                cb("parsing", i, len(figs), f"解析 {fig['id']}")
                self._process_figure(store, fig)
                store.save()
            s["stage"] = "done"
            store.save()
            cb("done", len(figs), len(figs), "完成")
        except Exception as e:  # noqa: BLE001
            s["stage"] = "failed"
            s["error"] = str(e)
            store.save()
            raise
        return s

    def _process_figure(self, store: PaperStore, fig: dict) -> None:
        fdir = store.figure_dir(fig["id"])
        page_png = store.page_png(fig["page"])
        crop_path = fdir / "crop.png"
        try:
            crop_page_region(page_png, fig["bbox_px"], crop_path)
        except Exception as e:  # noqa: BLE001
            fig["parse_status"] = "error"
            fig["error"] = f"裁剪失败: {e}"
            return
        fig["crop_path"] = f"figures/{fig['id']}/crop.png"
        try:
            chart = parse_chart(self.client, crop_path.read_bytes(), config=self.config)
        except Exception as e:  # noqa: BLE001 - 单图级隔离（含 VL 网络异常），失败不阻塞整篇
            fig["parse_status"] = "error"
            fig["error"] = str(e)
            return
        fig["parse_status"] = "done"
        chart_path = fdir / "chart.json"
        chart_path.write_text(json.dumps(chart, ensure_ascii=False, indent=2), encoding="utf-8")
        fig["chart_json_path"] = f"figures/{fig['id']}/chart.json"
        render_path = fdir / "render.png"
        code = generate_code(chart, render_path)
        (fdir / "code.py").write_text(code, encoding="utf-8")
        fig["code_path"] = f"figures/{fig['id']}/code.py"
        try:
            execute_code(code, self.config.exec_timeout)
            fig["render_status"] = "done"
            fig["render_path"] = f"figures/{fig['id']}/render.png"
        except CodeExecError as e:
            fig["render_status"] = "failed"
            fig["render_path"] = None
            fig["error"] = str(e)
