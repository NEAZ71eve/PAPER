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

    # ---- 阅读器细粒度入口（设计文档 5.2）----

    def render_only(self, pdf_path: Path, progress=None) -> PaperStore:
        """只渲染页面（上传 detect=false）：stage → ready，不做检测。"""
        cb = progress or (lambda stage, done, total, msg: None)
        store = self._render(pdf_path, cb)
        store.session["stage"] = "ready"
        store.save()
        return store

    def render_and_detect(self, pdf_path: Path, progress=None) -> PaperStore:
        """渲染页面 + 全量检测画框：stage detecting → ready；figures 全部 pending。"""
        cb = progress or (lambda stage, done, total, msg: None)
        store = self._render(pdf_path, cb)
        self.detect(store, cb)
        return store

    def detect(self, store: PaperStore, progress=None) -> None:
        """（重新）检测：清空旧结果后全量检测；stage detecting → ready / failed。"""
        cb = progress or (lambda stage, done, total, msg: None)
        s = store.session
        s["stage"] = "detecting"
        s["figures"] = []
        store.save()
        try:
            self._detect_figures(store, cb)
            s["stage"] = "ready"
            store.save()
            cb("ready", len(s["figures"]), len(s["figures"]), "检测完成")
        except Exception as e:  # noqa: BLE001
            s["stage"] = "failed"
            s["error"] = str(e)
            store.save()
            raise

    def parse_figure(self, store: PaperStore, figure_id: str) -> dict:
        """按需解析单张图表：parse_status=done 直接读缓存（零推理）；不存在抛 KeyError。"""
        fig = next((f for f in store.session["figures"] if f["id"] == figure_id), None)
        if fig is None:
            raise KeyError(f"图表不存在: {figure_id}")
        if fig.get("parse_status") != "done":
            self._process_figure(store, fig)
            store.save()
        chart = None
        cj = fig.get("chart_json_path")
        if cj and (store.root / cj).exists():
            chart = json.loads((store.root / cj).read_text(encoding="utf-8"))
        return {
            "id": fig["id"], "page": fig["page"], "type": fig["type"],
            "parse_status": fig.get("parse_status", "pending"),
            "render_status": fig.get("render_status", "pending"),
            "chart": chart,
            "crop_path": fig.get("crop_path"), "code_path": fig.get("code_path"),
            "render_path": fig.get("render_path"), "error": fig.get("error"),
        }

    # ---- 旧全量入口（legacy gradio 使用，对外行为不变）----

    def run(self, pdf_path: Path, progress=None) -> dict:
        cb = progress or (lambda stage, done, total, msg: None)
        store = self._open_store(pdf_path)
        s = store.session
        try:
            self._render_pages(store, cb)
            self._detect_figures(store, cb)
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

    # ---- 内部 ----

    def _open_store(self, pdf_path: Path) -> PaperStore:
        pdf_path = Path(pdf_path)
        pdf_bytes = pdf_path.read_bytes()
        return PaperStore(self.config.cache_dir, pdf_bytes, pdf_path.name)

    def _render(self, pdf_path: Path, cb) -> PaperStore:
        store = self._open_store(pdf_path)
        self._render_pages(store, cb)
        return store

    def _render_pages(self, store: PaperStore, cb) -> None:
        s = store.session
        if not s["pages"]:
            cb("detecting", 0, 1, f"渲染页面（最多 {self.config.max_pages} 页）")
            s["pages"] = render_pages(store.root / "source.pdf", store.root / "pages", self.config.dpi, self.config.max_pages)
            s["n_pages"] = len(s["pages"])
            s["dpi"] = self.config.dpi
            store.save()

    def _detect_figures(self, store: PaperStore, cb) -> None:
        """检测全部页面（已有结果则跳过）；单页 VL 异常 → 该页降级（设计文档 6.1 第 3 步）。"""
        s = store.session
        if s["figures"]:
            return
        figures = []
        pages = s["pages"]
        with fitz.open(store.root / "source.pdf") as doc:
            for i, p in enumerate(pages):
                cb("detecting", i, len(pages), f"检测第 {p['page']} 页")
                page_png = store.root / p["png_path"]
                try:
                    figs = self.detector.detect_page(page_png, doc[p["page"] - 1], p["page"])
                except Exception:  # noqa: BLE001
                    figs = self.fallback.detect_page(page_png, doc[p["page"] - 1], p["page"])
                figures.extend({**asdict(f), "parse_status": "pending", "render_status": "pending"} for f in figs)
        s["figures"] = figures
        store.save()

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
