# 论文阅读器（Word 风格编排 + 墨迹批注 + 按需图表解析）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在已交付的论文图表复刻系统基础上，升级为 Word 风格论文阅读器：空白阅读器导入 PDF（默认检测画框）、阅读中点击图框按需解析、手写墨迹 + 文本批注侧车自动保存、可导出带标注 PDF 副本；单图模式保留为右栏工具箱。

**Architecture:** FastAPI 后端（`app/server.py`，端口 8000）+ 纯 Web SPA 前端（`app/reader/`，原生 HTML/CSS/JS ES modules，无构建）；`chart_sdk` 小改——pipeline 拆出 `render_only/render_and_detect/detect/parse_figure` 细粒度入口，新增 `annotate/` 子包（侧车存储 + 导出）。`app/gradio_app.py` 保留为 legacy 不再维护。设计文档：`docs/superpowers/specs/2026-10-19-paper-reader-design.md`。

**Tech Stack:** Python ≥3.10、fastapi、uvicorn、python-multipart、httpx（测试）、pymupdf、pillow、matplotlib、openai（客户端连 Ollama）、pytest；前端零依赖。

**约定：**
- 下文 `$py` 指代 `.venv\Scripts\python.exe`。所有 pytest/git 命令在 `d:\aicomp` 下运行（PowerShell，用 `;` 分隔多条命令，禁用 `&&`）。
- 运行测试：`$py -m pytest tests\unit -v`（或指定文件）。
- 接口契约（各任务必须一致）：
  - `PaperStore.open(cache_dir, pdf_hash) -> PaperStore`（classmethod，会话不存在抛 `KeyError`）
  - `PaperPipeline.render_only(pdf_path, progress=None) -> PaperStore`（只渲染，stage→ready）
  - `PaperPipeline.render_and_detect(pdf_path, progress=None) -> PaperStore`（渲染+检测+裁剪前置，stage→ready，figures 全 pending）
  - `PaperPipeline.detect(store, progress=None) -> None`（清空旧结果重新检测）
  - `PaperPipeline.parse_figure(store, figure_id) -> dict`（返回 `{id, page, type, parse_status, render_status, chart, crop_path, code_path, render_path, error}`；不存在抛 `KeyError`；done 直接读缓存）
  - `AnnotationStore(paper_root).load() -> dict` / `.save(data) -> None`（结构非法抛 `ValueError`，原子写）
  - `export_annotated(pdf_path, paper_root, out_dir, dpi=150) -> Path`
  - 进度回调签名沿用 `cb(stage, done, total, msg)`
- session.json `stage` ∈ `detecting | ready | parsing | done | failed`（`ready` 为新增：检测完成待按需解析）。
- annotations.json：坐标归一化 0-1；stroke `width` 单位为 **PDF point（1/72 英寸）**，前端换算 `显示px = width × (150/72) × scale`，导出换算 `px = width × dpi/72`；无标注页面不写条目。
- 前端元素 id 契约（index.html 固定，JS 模块按 id 取用）：`btn-import, chk-detect, btn-export, file-input, ink-color, ink-width, btn-undo, btn-redo, btn-clear-page, detect-status, btn-redetect, btn-fit-width, btn-fit-page, zoom-select, btn-show-toolbox, health-light, thumbs, reader, empty-state, page-wrap, page-stage(data-mode), page-img, figure-layer, ink-canvas, comment-layer, comment-catcher(动态创建), btn-prev, btn-next, page-indicator, comments-panel, figure-panel, toolbox-panel, btn-single-upload, single-input, single-result, toast`；类契约：`.ribbon-tab[data-tab], .ribbon-panel[data-panel], .tool-btn[data-tool], .side-tab[data-side], .side-panel[data-panel]`。
- 前端模块契约（`app/reader/js/`，ES modules）：`state.js` 导出 `state, on, emit, uid, toast`；`api.js` 导出 `uploadPaper, getStatus, getFigures, parseFigure, getAnnotations, putAnnotations, startDetect, getHealth, parseSingle, exportPaper`；`annotate.js` 导出 `loadAnnotations, scheduleSave, saveNow, pageAnnot, prunePage`；`viewer.js` 导出 `initViewer, importFile, renderPage, applyScale, setZoom, setFitMode, gotoPage, prevPage, nextPage`；`figures.js` 导出 `initFigures, redetectFigures, renderChartResult`；`ink.js` 导出 `initInk, undoInk, redoInk, clearPageStrokes`；`comments.js` 导出 `initComments`；`ribbon.js` 导出 `initRibbon`；`toolbox.js` 导出 `initToolbox`。
- 事件契约（state.js 总线）：`paper-loaded, page-changed, scale-changed, annotations-changed, switch-side-tab`。
- 提交风格沿用 git log：`feat: 中文摘要` / `fix: ...` / `docs: ...` / `test: ...`。

---

### Task 0: 依赖与配置扩展（fastapi/uvicorn + api_port）

**Files:**
- Modify: `requirements.txt`
- Modify: `chart_sdk/config.py`
- Modify: `tests/unit/test_config.py`

- [ ] **Step 1: requirements.txt 追加四行**

`requirements.txt` 全文变为：

```
gradio>=4.44
pymupdf>=1.24
matplotlib>=3.8
pillow>=10.0
openai>=1.40
numpy>=1.26
pandas>=2.0
pytest>=8.0
fastapi>=0.110
uvicorn>=0.29
python-multipart>=0.0.9
httpx>=0.27
```

- [ ] **Step 2: 写失败测试（test_config.py 追加）**

```python
def test_api_port_default(monkeypatch):
    monkeypatch.delenv("CHART_SDK_API_PORT", raising=False)
    assert Config.from_env().api_port == 8000


def test_api_port_override(monkeypatch):
    monkeypatch.setenv("CHART_SDK_API_PORT", "9000")
    assert Config.from_env().api_port == 9000
```

- [ ] **Step 3: 运行测试确认失败**

Run: `$py -m pytest tests\unit\test_config.py -v`
Expected: FAIL（AttributeError: 'Config' object has no attribute 'api_port'）

- [ ] **Step 4: 实现 config.py 扩展**

`chart_sdk/config.py` 全文替换为：

```python
import os
from dataclasses import dataclass


@dataclass
class Config:
    base_url: str
    model: str
    dpi: int
    max_pages: int
    exec_timeout: float
    vl_timeout: float
    cache_dir: str
    retry: int
    api_port: int

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            base_url=os.getenv("CHART_SDK_BASE_URL", "http://localhost:11434/v1"),
            model=os.getenv("CHART_SDK_MODEL", "qwen2.5vl:7b"),
            dpi=int(os.getenv("CHART_SDK_DPI", "150")),
            max_pages=int(os.getenv("CHART_SDK_MAX_PAGES", "30")),
            exec_timeout=float(os.getenv("CHART_SDK_EXEC_TIMEOUT", "30")),
            vl_timeout=float(os.getenv("CHART_SDK_VL_TIMEOUT", "120")),
            cache_dir=os.getenv("CHART_SDK_CACHE_DIR", "data/cache"),
            retry=1,
            api_port=int(os.getenv("CHART_SDK_API_PORT", "8000")),
        )
```

- [ ] **Step 5: 安装新依赖并运行测试**

Run: `$py -m pip install -r requirements.txt ; $py -m pytest tests\unit\test_config.py -v`
Expected: 全部 PASS

- [ ] **Step 6: 回归全部单测**

Run: `$py -m pytest tests\unit -v`
Expected: 57+2 全部 PASS（注意：若 shell 设了 CHART_SDK_MODEL，test_defaults 可能受污染，属已知环境现象，用干净环境复跑确认）

- [ ] **Step 7: Commit**

```powershell
git add requirements.txt chart_sdk/config.py tests/unit/test_config.py
git commit -m "feat: 阅读器后端依赖（fastapi/uvicorn）与 API 端口配置"
```

---

### Task 1: PaperStore.open（按 hash 重开会话）

**Files:**
- Modify: `chart_sdk/cache/store.py`
- Modify: `tests/unit/test_store.py`

- [ ] **Step 1: 写失败测试（test_store.py 追加）**

```python
def test_paper_store_open(tmp_path):
    from chart_sdk.cache.store import PaperStore
    store = PaperStore(tmp_path / "cache", b"fake-pdf-bytes", "a.pdf")
    store.save()
    again = PaperStore.open(tmp_path / "cache", store.pdf_hash)
    assert again.pdf_hash == store.pdf_hash
    assert again.root == store.root
    assert again.session["file_name"] == "a.pdf"


def test_paper_store_open_missing(tmp_path):
    import pytest
    from chart_sdk.cache.store import PaperStore
    with pytest.raises(KeyError):
        PaperStore.open(tmp_path / "cache", "0" * 64)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `$py -m pytest tests\unit\test_store.py -v`
Expected: FAIL（AttributeError: type object 'PaperStore' has no attribute 'open'）

- [ ] **Step 3: 实现 open 类方法**

在 `chart_sdk/cache/store.py` 的 `PaperStore` 类中（`__init__` 之后）追加：

```python
    @classmethod
    def open(cls, cache_dir, pdf_hash: str) -> "PaperStore":
        """按 hash 重开已有会话（阅读器 API 用）；不存在抛 KeyError。"""
        obj = cls.__new__(cls)
        obj.pdf_hash = pdf_hash
        obj.root = Path(cache_dir) / "papers" / pdf_hash
        sp = obj.root / "session.json"
        if not sp.exists():
            raise KeyError(f"会话不存在: {pdf_hash}")
        obj.session = json.loads(sp.read_text(encoding="utf-8"))
        return obj
```

- [ ] **Step 4: 运行测试确认通过**

Run: `$py -m pytest tests\unit\test_store.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```powershell
git add chart_sdk/cache/store.py tests/unit/test_store.py
git commit -m "feat: PaperStore.open 按 hash 重开论文会话"
```

---

### Task 2: pipeline 细粒度入口（render_only / render_and_detect / detect / parse_figure）

**Files:**
- Modify: `chart_sdk/pipeline/paper.py`（全文重构，run() 对外行为不变）
- Modify: `tests/unit/test_pipeline.py`（追加 5 个测试）

- [ ] **Step 1: 写失败测试（test_pipeline.py 追加；文件已有 FakeClient/FakeDetector/_make_pdf/CHART 可直接用）**

```python
def test_render_only(tmp_path):
    _make_pdf(tmp_path / "ro.pdf")
    cfg = Config.from_env()
    cfg.cache_dir = str(tmp_path / "cache")
    pipe = PaperPipeline(cfg, FakeClient(), detector=FakeDetector(), fallback=FakeDetector([]))
    store = pipe.render_only(tmp_path / "ro.pdf")
    assert store.session["stage"] == "ready"
    assert store.session["figures"] == []
    assert len(store.session["pages"]) == 2


def test_render_and_detect_no_parse(tmp_path):
    _make_pdf(tmp_path / "rd.pdf")
    cfg = Config.from_env()
    cfg.cache_dir = str(tmp_path / "cache")
    client = FakeClient()
    pipe = PaperPipeline(cfg, client, detector=FakeDetector(), fallback=FakeDetector([]))
    store = pipe.render_and_detect(tmp_path / "rd.pdf")
    s = store.session
    assert s["stage"] == "ready"
    assert len(s["pages"]) == 2
    assert len(s["figures"]) == 2  # 两页各一张
    assert all(f["parse_status"] == "pending" for f in s["figures"])
    assert client.parse_calls == 0  # 检测阶段不做数据解析


def test_parse_figure_on_demand(tmp_path):
    _make_pdf(tmp_path / "od.pdf")
    cfg = Config.from_env()
    cfg.cache_dir = str(tmp_path / "cache")
    client = FakeClient()
    pipe = PaperPipeline(cfg, client, detector=FakeDetector(), fallback=FakeDetector([]))
    store = pipe.render_and_detect(tmp_path / "od.pdf")
    fid = store.session["figures"][0]["id"]
    result = pipe.parse_figure(store, fid)
    assert result["parse_status"] == "done"
    assert result["render_status"] == "done"
    assert result["chart"]["chart_type"] == "line"
    assert result["crop_path"] and result["code_path"] and result["render_path"]
    assert client.parse_calls == 1
    # 缓存命中：再次解析零推理
    result2 = pipe.parse_figure(store, fid)
    assert result2["parse_status"] == "done"
    assert client.parse_calls == 1
    # 其他图表不受影响
    assert store.session["figures"][1]["parse_status"] == "pending"


def test_parse_figure_missing(tmp_path):
    import pytest
    _make_pdf(tmp_path / "ms.pdf")
    cfg = Config.from_env()
    cfg.cache_dir = str(tmp_path / "cache")
    pipe = PaperPipeline(cfg, FakeClient(), detector=FakeDetector(), fallback=FakeDetector([]))
    store = pipe.render_only(tmp_path / "ms.pdf")
    with pytest.raises(KeyError):
        pipe.parse_figure(store, "p1-f9")


def test_detect_redetect_clears(tmp_path):
    _make_pdf(tmp_path / "re.pdf")
    cfg = Config.from_env()
    cfg.cache_dir = str(tmp_path / "cache")
    pipe = PaperPipeline(cfg, FakeClient(), detector=FakeDetector(), fallback=FakeDetector([]))
    store = pipe.render_and_detect(tmp_path / "re.pdf")
    assert len(store.session["figures"]) == 2
    pipe2 = PaperPipeline(cfg, FakeClient(), detector=FakeDetector([]), fallback=FakeDetector([]))
    pipe2.detect(store)  # 换无框检测器重新检测
    assert store.session["stage"] == "ready"
    assert store.session["figures"] == []
```

- [ ] **Step 2: 运行测试确认失败**

Run: `$py -m pytest tests\unit\test_pipeline.py -v`
Expected: FAIL（AttributeError: 'PaperPipeline' object has no attribute 'render_only'）

- [ ] **Step 3: 重构 paper.py（全文替换；run() 对外行为与 stage 语义不变，内部复用新方法）**

```python
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
        store = self._render(pdf_path, cb)
        s = store.session
        try:
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

    def _render(self, pdf_path: Path, cb) -> PaperStore:
        pdf_path = Path(pdf_path)
        pdf_bytes = pdf_path.read_bytes()
        store = PaperStore(self.config.cache_dir, pdf_bytes, pdf_path.name)
        s = store.session
        if not s["pages"]:
            cb("detecting", 0, 1, f"渲染页面（最多 {self.config.max_pages} 页）")
            s["pages"] = render_pages(store.root / "source.pdf", store.root / "pages", self.config.dpi, self.config.max_pages)
            s["n_pages"] = len(s["pages"])
            s["dpi"] = self.config.dpi
            store.save()
        return store

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
                figures.extend(asdict(f) for f in figs)
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
```

- [ ] **Step 4: 运行测试确认通过（含旧测试回归）**

Run: `$py -m pytest tests\unit\test_pipeline.py -v`
Expected: 全部 PASS（旧 6 个 + 新 5 个）

- [ ] **Step 5: Commit**

```powershell
git add chart_sdk/pipeline/paper.py tests/unit/test_pipeline.py
git commit -m "feat: pipeline 细粒度入口（render_only/render_and_detect/detect/parse_figure）"
```

---

### Task 3: AnnotationStore（侧车 annotations.json 读写）

**Files:**
- Create: `chart_sdk/annotate/__init__.py`（空文件）
- Create: `chart_sdk/annotate/store.py`
- Create: `tests/unit/test_annotate_store.py`

- [ ] **Step 1: 写失败测试 tests/unit/test_annotate_store.py**

```python
import json

import pytest

from chart_sdk.annotate.store import AnnotationStore

STROKE = {"id": "s-1", "tool": "pen", "color": "#CC2936", "width": 2.0,
          "points": [[0.1, 0.2], [0.3, 0.4]]}
COMMENT = {"id": "c-1", "x": 0.5, "y": 0.5, "text": "存疑", "resolved": False,
           "created_at": "2026-10-19T22:40:00", "updated_at": "2026-10-19T22:41:00"}


def test_load_empty_skeleton(tmp_path):
    store = AnnotationStore(tmp_path)
    assert store.load() == {"version": 1, "pages": {}}


def test_roundtrip(tmp_path):
    store = AnnotationStore(tmp_path)
    data = {"version": 1, "pages": {"3": {"strokes": [STROKE], "comments": [COMMENT]}}}
    store.save(data)
    again = AnnotationStore(tmp_path).load()
    assert again["pages"]["3"]["strokes"][0]["id"] == "s-1"
    assert again["pages"]["3"]["comments"][0]["text"] == "存疑"
    assert again["version"] == 1


def test_corrupt_file_returns_skeleton(tmp_path):
    (tmp_path / "annotations.json").write_text("{不是JSON", encoding="utf-8")
    assert AnnotationStore(tmp_path).load() == {"version": 1, "pages": {}}


def test_atomic_write_no_tmp_left(tmp_path):
    store = AnnotationStore(tmp_path)
    store.save({"version": 1, "pages": {"1": {"strokes": [STROKE], "comments": []}}})
    assert (tmp_path / "annotations.json").exists()
    assert not (tmp_path / "annotations.json.tmp").exists()


@pytest.mark.parametrize("bad", [
    {"pages": {"x": {"strokes": [], "comments": []}}},                      # 页码键非数字
    {"pages": {"1": {"strokes": [dict(STROKE, tool="crayon")], "comments": []}}},  # 非法工具
    {"pages": {"1": {"strokes": [dict(STROKE, points=[[1.5, 0.2]])], "comments": []}}},  # 坐标越界
    {"pages": {"1": {"strokes": [dict(STROKE, width=0)], "comments": []}}},  # 非正宽度
    {"pages": {"1": {"strokes": [], "comments": [dict(COMMENT, x=2.0)]}}},   # 批注坐标越界
    {"pages": {"1": {"strokes": [], "comments": [dict(COMMENT, resolved="yes")]}}},  # resolved 非布尔
    {"pages": {"1": {"strokes": {}, "comments": []}}},                       # strokes 非列表
    {"foo": 1},                                                              # 缺 pages
])
def test_invalid_structures_raise(tmp_path, bad):
    store = AnnotationStore(tmp_path)
    with pytest.raises(ValueError):
        store.save(bad)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `$py -m pytest tests\unit\test_annotate_store.py -v`
Expected: FAIL（ModuleNotFoundError: chart_sdk.annotate）

- [ ] **Step 3: 实现 annotate 包**

`chart_sdk/annotate/__init__.py`：空文件。

`chart_sdk/annotate/store.py`：

```python
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
        _atomic_write_json(self.path, {"version": 1, "pages": pages})
```

- [ ] **Step 4: 运行测试确认通过**

Run: `$py -m pytest tests\unit\test_annotate_store.py -v`
Expected: 12 个测试全部 PASS

- [ ] **Step 5: Commit**

```powershell
git add chart_sdk/annotate tests/unit/test_annotate_store.py
git commit -m "feat: 标注侧车 AnnotationStore（结构校验+原子写）"
```

---

### Task 4: 标注导出 export_annotated（叠加标注 PDF 副本）

**Files:**
- Create: `chart_sdk/annotate/export.py`
- Create: `tests/unit/test_annotate_export.py`

- [ ] **Step 1: 写失败测试 tests/unit/test_annotate_export.py**

```python
import fitz
import pytest

from chart_sdk.annotate.export import export_annotated
from chart_sdk.annotate.store import AnnotationStore


def _make_pdf(path, n_pages=2):
    doc = fitz.open()
    for _ in range(n_pages):
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 72), "hello")
    doc.save(str(path))
    doc.close()


def _seed_annotations(root):
    AnnotationStore(root).save({"version": 1, "pages": {
        "1": {"strokes": [
            {"id": "s-1", "tool": "pen", "color": "#CC2936", "width": 2.0,
             "points": [[0.1, 0.1], [0.5, 0.3], [0.9, 0.2]]},
            {"id": "s-2", "tool": "highlighter", "color": "#FFEB3B", "width": 6.0,
             "points": [[0.2, 0.5], [0.8, 0.5]]},
        ], "comments": []},
        "2": {"strokes": [], "comments": [
            {"id": "c-1", "x": 0.5, "y": 0.5, "text": "这个基线数据存疑", "resolved": False,
             "created_at": "t", "updated_at": "t"},
        ]},
    }})


def test_export_overlay_and_annot(tmp_path):
    src = tmp_path / "paper.pdf"
    _make_pdf(src)
    _seed_annotations(tmp_path)
    out = export_annotated(src, tmp_path, tmp_path / "exports")
    assert out.exists() and out.name == "annotated-paper.pdf"
    with fitz.open(out) as doc:
        assert len(doc) == 2
        assert len(doc[0].get_images()) >= 1          # 第 1 页叠加了墨迹图像层
        annots = list(doc[1].annots())                 # 第 2 页写入了文本便签
        assert len(annots) == 1
        assert "存疑" in annots[0].info.get("content", "")
    # 原 PDF 不受影响
    with fitz.open(src) as doc:
        assert len(doc[0].get_images()) == 0


def test_export_empty_annotations(tmp_path):
    src = tmp_path / "blank.pdf"
    _make_pdf(src)
    out = export_annotated(src, tmp_path, tmp_path / "exports")
    assert out.exists()
    with fitz.open(out) as doc:
        assert len(doc) == 2
        assert len(list(doc[0].annots())) == 0


def test_export_out_of_range_page_skipped(tmp_path):
    src = tmp_path / "range.pdf"
    _make_pdf(src, n_pages=1)
    AnnotationStore(tmp_path).save({"version": 1, "pages": {
        "9": {"strokes": [], "comments": [
            {"id": "c-9", "x": 0.5, "y": 0.5, "text": "越界页", "resolved": False,
             "created_at": "t", "updated_at": "t"}]}}})
    out = export_annotated(src, tmp_path, tmp_path / "exports")
    assert out.exists()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `$py -m pytest tests\unit\test_annotate_export.py -v`
Expected: FAIL（ModuleNotFoundError: chart_sdk.annotate.export）

- [ ] **Step 3: 实现 chart_sdk/annotate/export.py**

```python
"""叠加标注导出 PDF 副本（设计文档 7）：墨迹→RGBA 图像层；文本批注→PDF text annotation。"""
from __future__ import annotations

import io
from pathlib import Path

import fitz
from PIL import Image, ImageDraw

from chart_sdk.annotate.store import AnnotationStore


def _with_alpha(color: str, alpha: int):
    color = color.lstrip("#")
    if len(color) == 3:
        color = "".join(c * 2 for c in color)
    return (int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16), alpha)


def _render_strokes(strokes: list, page: "fitz.Page", dpi: int) -> bytes:
    """把一页 strokes 按归一化坐标重绘为透明 RGBA PNG 字节（尺寸=页面渲染像素）。"""
    zoom = dpi / 72.0
    w = max(1, round(page.rect.width * zoom))
    h = max(1, round(page.rect.height * zoom))
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    for s in strokes:
        pts = [(p[0] * w, p[1] * h) for p in s["points"]]
        if len(pts) < 2:
            continue
        width = max(1, round(s["width"] * zoom))  # width 单位 point → 像素
        color = _with_alpha(s["color"], 102) if s["tool"] == "highlighter" else s["color"]
        draw.line(pts, fill=color, width=width, joint="curve")
        r = width / 2  # 圆头端点
        for cx, cy in (pts[0], pts[-1]):
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
    buf = io.BytesIO()
    layer.save(buf, format="PNG")
    return buf.getvalue()


def export_annotated(pdf_path, paper_root, out_dir, dpi: int = 150) -> Path:
    """导出叠加全部标注的新 PDF 副本；原 PDF 与 annotations.json 不受影响。"""
    annotations = AnnotationStore(paper_root).load()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = Path(pdf_path)
    out_path = out_dir / f"annotated-{pdf_path.name}"
    with fitz.open(pdf_path) as doc:
        for pno, entry in annotations["pages"].items():
            idx = int(pno) - 1
            if idx < 0 or idx >= len(doc):
                continue
            page = doc[idx]
            strokes = entry.get("strokes") or []
            if strokes:
                page.insert_image(page.rect, stream=_render_strokes(strokes, page, dpi), overlay=True)
            for c in entry.get("comments") or []:
                point = fitz.Point(c["x"] * page.rect.width, c["y"] * page.rect.height)
                annot = page.add_text_annot(point, c.get("text", ""))
                annot.set_info(title="批注")
                annot.update()
        doc.save(str(out_path))
    return out_path
```

- [ ] **Step 4: 运行测试确认通过**

Run: `$py -m pytest tests\unit\test_annotate_export.py -v`
Expected: 3 个测试全部 PASS

- [ ] **Step 5: Commit**

```powershell
git add chart_sdk/annotate/export.py tests/unit/test_annotate_export.py
git commit -m "feat: 叠加标注导出 PDF 副本（墨迹图像层+文本便签）"
```

---

### Task 5: FastAPI 后端 app/server.py

**Files:**
- Create: `app/server.py`
- Create: `app/reader/.gitkeep`（reader 目录占位，StaticFiles 挂载需要目录存在——server 内也会 mkdir 兜底）

- [ ] **Step 1: 实现 app/server.py（全文）**

```python
"""FastAPI 后端：论文阅读器 API + 静态托管（设计文档 6）。

启动：$env:CHART_SDK_MODEL="qwen2.5vl:3b" ; .venv\Scripts\python.exe -m uvicorn app.server:app --port 8000
"""
from __future__ import annotations

import tempfile
import threading
from pathlib import Path

import fitz
from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from chart_sdk.annotate.export import export_annotated
from chart_sdk.annotate.store import AnnotationStore
from chart_sdk.cache.store import PaperStore
from chart_sdk.config import Config
from chart_sdk.inference.client import VLClient
from chart_sdk.pipeline.paper import PaperPipeline
from chart_sdk.pipeline.single import run_single

APP_DIR = Path(__file__).resolve().parent
READER_DIR = APP_DIR / "reader"

config = Config.from_env()
client = VLClient(config)
pipeline = PaperPipeline(config, client)

app = FastAPI(title="论文阅读器")

_detect_lock = threading.Lock()
_detect_running: set[str] = set()
_detect_progress: dict[str, dict] = {}


def _open_store(h: str) -> PaperStore:
    try:
        return PaperStore.open(config.cache_dir, h)
    except KeyError:
        raise HTTPException(404, f"论文不存在: {h}")


def _run_detect(h: str) -> None:
    try:
        store = PaperStore.open(config.cache_dir, h)
        pipeline.detect(store, lambda stage, done, total, msg: _detect_progress.__setitem__(h, {"done": done, "total": total}))
    except Exception:  # noqa: BLE001 - 错误已写入 session.json，前端经 status 可见
        pass
    finally:
        with _detect_lock:
            _detect_running.discard(h)


def _start_detect(h: str) -> bool:
    """后台线程启动检测；已在检测中则返回 False。"""
    with _detect_lock:
        if h in _detect_running:
            return False
        _detect_running.add(h)
    _detect_progress[h] = {"done": 0, "total": 0}
    threading.Thread(target=_run_detect, args=(h,), daemon=True).start()
    return True


@app.post("/api/papers")
def upload_paper(file: UploadFile = File(...), detect: bool = Form(True)):
    data = file.file.read()
    if not data:
        raise HTTPException(400, "空文件")
    store0 = PaperStore(config.cache_dir, data, file.filename or "paper.pdf")
    src = store0.root / "source.pdf"
    store = pipeline.render_only(src)  # 页面渲染同步完成（秒级）
    with fitz.open(src) as doc:
        truncated = len(doc) > config.max_pages
    if detect:
        _start_detect(store.pdf_hash)  # 检测后台执行，前端轮询 status
    return {"pdf_hash": store.pdf_hash, "file_name": store.session["file_name"],
            "n_pages": store.session["n_pages"], "truncated": truncated}


@app.post("/api/papers/{h}/detect")
def start_detect(h: str):
    _open_store(h)
    return {"started": _start_detect(h)}


@app.get("/api/papers/{h}/status")
def paper_status(h: str):
    store = _open_store(h)
    s = store.session
    prog = _detect_progress.get(h, {"done": 0, "total": s.get("n_pages", 0)})
    return {"stage": s.get("stage"), "detect_done": prog["done"], "detect_total": prog["total"],
            "n_figures": len(s.get("figures", [])), "n_pages": s.get("n_pages", 0),
            "file_name": s.get("file_name"), "error": s.get("error")}


@app.get("/api/papers/{h}/pages/{n}.png")
def page_png(h: str, n: int):
    store = _open_store(h)
    try:
        return FileResponse(store.page_png(n), media_type="image/png")
    except KeyError:
        raise HTTPException(404, f"页面不存在: {n}")


@app.get("/api/papers/{h}/figures")
def list_figures(h: str):
    store = _open_store(h)
    return {"figures": [
        {"id": f["id"], "page": f["page"], "bbox_px": f["bbox_px"], "type": f["type"],
         "source": f["source"], "caption_hint": f.get("caption_hint"),
         "parse_status": f.get("parse_status", "pending"), "error": f.get("error"),
         "crop_path": f.get("crop_path"), "render_path": f.get("render_path"),
         "code_path": f.get("code_path")}
        for f in store.session.get("figures", [])
    ]}


@app.post("/api/papers/{h}/figures/{fid}/parse")
def parse_one(h: str, fid: str):
    store = _open_store(h)
    try:
        return pipeline.parse_figure(store, fid)
    except KeyError as e:
        raise HTTPException(404, str(e))


@app.get("/api/papers/{h}/annotations")
def get_annotations(h: str):
    store = _open_store(h)
    return AnnotationStore(store.root).load()


@app.put("/api/papers/{h}/annotations")
def put_annotations(h: str, payload: dict = Body(...)):
    store = _open_store(h)
    try:
        AnnotationStore(store.root).save(payload)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@app.post("/api/papers/{h}/export")
def export_paper(h: str):
    store = _open_store(h)
    try:
        out = export_annotated(store.root / "source.pdf", store.root, store.root / "exports", dpi=config.dpi)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"导出失败: {e}")
    return FileResponse(out, media_type="application/pdf", filename=out.name)


@app.post("/api/singles/parse")
def parse_single(file: UploadFile = File(...)):
    data = file.file.read()
    if not data:
        raise HTTPException(400, "空文件")
    suffix = Path(file.filename or "img.png").suffix or ".png"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tf:
        tf.write(data)
        tmp = Path(tf.name)
    try:
        rec = run_single(config, client, tmp)
    finally:
        tmp.unlink(missing_ok=True)
    out = dict(rec)
    h = rec.get("image_hash", "")
    out["input_url"] = f"/cache/singles/{h}/input.png" if h else None
    out["render_url"] = f"/cache/singles/{h}/{rec['render_path']}" if rec.get("render_path") else None
    code_rel = rec.get("code_path")
    code_file = (Path(config.cache_dir) / "singles" / h / code_rel) if code_rel else None
    out["code"] = code_file.read_text(encoding="utf-8") if code_file and code_file.exists() else None
    return out


@app.get("/api/health")
def health():
    ok = client.health()
    return {"ollama": ok, "model": client.model_available() if ok else False, "model_name": config.model}


Path(config.cache_dir).mkdir(parents=True, exist_ok=True)
READER_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/cache", StaticFiles(directory=config.cache_dir), name="cache")
app.mount("/", StaticFiles(directory=READER_DIR, html=True), name="reader")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.server:app", host="127.0.0.1", port=config.api_port)
```

- [ ] **Step 2: 冒烟验证服务可启动**

Run: `$py -c "from app.server import app; print('routes:', len(app.routes))"`
Expected: 正常打印（约 14 条路由），无异常

- [ ] **Step 3: Commit**

```powershell
git add app/server.py app/reader/.gitkeep
git commit -m "feat: FastAPI 阅读器后端（上传/检测/解析/标注/导出/工具箱/健康）"
```

---

### Task 6: API 集成测试（TestClient，离线全链路）

**Files:**
- Create: `tests/integration/test_api.py`

- [ ] **Step 1: 写测试 tests/integration/test_api.py（全文；FakeClient 使 parse/export 全链路离线可跑）**

```python
"""FastAPI 集成测试：上传 → 检测 → 图框 → 按需解析 → 标注往返 → 导出；VL 走 FakeClient 离线。"""
import importlib
import io
import json
import time

import fitz
import pytest
from fastapi.testclient import TestClient

CHART = {
    "chart_type": "line", "title": "t",
    "x_axis": {"label": "x", "unit": None}, "y_axis": {"label": "y", "unit": None},
    "legend": ["a"], "series": [{"name": "a", "x": [1, 2], "y": [1.0, 2.0]}],
    "heatmap": None, "warnings": [],
}


class FakeClient:
    def chat_image(self, prompt, image_bytes, **kw):
        return json.dumps(CHART)

    def health(self):
        return False

    def model_available(self):
        return False


class FakeDetector:
    def detect_page(self, page_png, page, page_no):
        from chart_sdk.pdf.detector import FigureBBox
        return [FigureBBox(id=f"p{page_no}-f1", page=page_no, bbox_norm=[0, 0, 1, 1],
                           bbox_px=[50, 50, 400, 300], type="line",
                           source="vl_grounding", caption_hint=None)]


def _pdf_bytes(n_pages=2):
    doc = fitz.open()
    for _ in range(n_pages):
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 72), "hello")
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture()
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("CHART_SDK_CACHE_DIR", str(tmp_path / "cache"))
    import app.server as server
    importlib.reload(server)  # 让 config 使用临时缓存目录
    from chart_sdk.pipeline.paper import PaperPipeline
    server.client = FakeClient()
    server.pipeline = PaperPipeline(server.config, server.client,
                                    detector=FakeDetector(), fallback=FakeDetector())
    yield TestClient(server.app), server


def _upload(client, detect="true"):
    r = client.post("/api/papers", files={"file": ("a.pdf", _pdf_bytes(), "application/pdf")},
                    data={"detect": detect})
    assert r.status_code == 200, r.text
    return r.json()


def _wait_ready(client, h, timeout=15):
    deadline = time.time() + timeout
    st = {}
    while time.time() < deadline:
        st = client.get(f"/api/papers/{h}/status").json()
        if st["stage"] != "detecting":
            return st
        time.sleep(0.2)
    return st


def test_upload_detect_false(api):
    client, _ = api
    info = _upload(client, detect="false")
    assert info["n_pages"] == 2 and info["truncated"] is False
    st = client.get(f"/api/papers/{info['pdf_hash']}/status").json()
    assert st["stage"] == "ready" and st["n_figures"] == 0


def test_upload_detect_then_figures_and_pages(api):
    client, _ = api
    h = _upload(client)["pdf_hash"]
    st = _wait_ready(client, h)
    assert st["stage"] == "ready" and st["n_figures"] == 2
    figs = client.get(f"/api/papers/{h}/figures").json()["figures"]
    assert len(figs) == 2
    assert figs[0]["parse_status"] == "pending"
    assert figs[0]["bbox_px"] == [50, 50, 400, 300]
    r = client.get(f"/api/papers/{h}/pages/1.png")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert client.get(f"/api/papers/{h}/pages/9.png").status_code == 404


def test_parse_endpoint_offline_full_chain(api):
    client, _ = api
    h = _upload(client)["pdf_hash"]
    _wait_ready(client, h)
    r = client.post(f"/api/papers/{h}/figures/p1-f1/parse")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["parse_status"] == "done"
    assert data["chart"]["chart_type"] == "line"
    assert data["code_path"] and data["render_path"]
    # 缓存命中再次调用仍 done
    assert client.post(f"/api/papers/{h}/figures/p1-f1/parse").json()["parse_status"] == "done"
    # 不存在的图表 → 404
    assert client.post(f"/api/papers/{h}/figures/p1-f9/parse").status_code == 404
    # figures 列表状态已更新
    figs = client.get(f"/api/papers/{h}/figures").json()["figures"]
    assert figs[0]["parse_status"] == "done"


def test_annotations_roundtrip(api):
    client, _ = api
    h = _upload(client, detect="false")["pdf_hash"]
    assert client.get(f"/api/papers/{h}/annotations").json() == {"version": 1, "pages": {}}
    payload = {"version": 1, "pages": {"1": {
        "strokes": [{"id": "s-1", "tool": "pen", "color": "#CC2936", "width": 2.0,
                     "points": [[0.1, 0.2], [0.3, 0.4]]}],
        "comments": [{"id": "c-1", "x": 0.5, "y": 0.5, "text": "存疑", "resolved": False,
                      "created_at": "t", "updated_at": "t"}]}}}
    assert client.put(f"/api/papers/{h}/annotations", json=payload).status_code == 200
    got = client.get(f"/api/papers/{h}/annotations").json()
    assert got["pages"]["1"]["strokes"][0]["id"] == "s-1"
    assert client.put(f"/api/papers/{h}/annotations", json={"pages": {"x": {}}}).status_code == 400


def test_export_download(api):
    client, _ = api
    h = _upload(client, detect="false")["pdf_hash"]
    client.put(f"/api/papers/{h}/annotations", json={"version": 1, "pages": {"1": {
        "strokes": [{"id": "s-1", "tool": "pen", "color": "#CC2936", "width": 2.0,
                     "points": [[0.1, 0.2], [0.3, 0.4]]}],
        "comments": [{"id": "c-1", "x": 0.5, "y": 0.5, "text": "存疑", "resolved": False,
                      "created_at": "t", "updated_at": "t"}]}}})
    r = client.post(f"/api/papers/{h}/export")
    assert r.status_code == 200
    assert r.content[:5] == b"%PDF-"
    with fitz.open(stream=r.content, filetype="pdf") as doc:
        assert len(doc) == 2
        assert len(list(doc[0].annots())) == 1


def test_single_parse_endpoint(api):
    client, _ = api
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (200, 150), (255, 255, 255)).save(buf, format="PNG")
    r = client.post("/api/singles/parse", files={"file": ("x.png", buf.getvalue(), "image/png")})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "done"
    assert data["chart"]["chart_type"] == "line"
    assert data["code"] and "matplotlib" in data["code"]
    assert data["input_url"] and data["render_url"]


def test_health_and_unknown_paper(api):
    client, server = api
    assert client.get("/api/health").json() == {
        "ollama": False, "model": False, "model_name": server.config.model}
    assert client.get(f"/api/papers/{'0' * 64}/status").status_code == 404
```

- [ ] **Step 2: 运行测试确认通过**

Run: `$py -m pytest tests\integration\test_api.py -v`
Expected: 7 个测试全部 PASS（约 20-40s，含 matplotlib 子进程渲染）

- [ ] **Step 3: 全量回归**

Run: `$py -m pytest tests\unit -v`
Expected: 全部 PASS

- [ ] **Step 4: Commit**

```powershell
git add tests/integration/test_api.py
git commit -m "test: 阅读器 API 集成测试（离线全链路）"
```

---

### Task 7: 前端骨架（index.html + styles.css）

**Files:**
- Create: `app/reader/index.html`
- Create: `app/reader/styles.css`
- Create: `app/reader/js/main.js`（占位，Task 8 替换）

- [ ] **Step 1: 创建 app/reader/index.html（全文；元素 id 为后续 JS 模块的固定契约）**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>论文阅读器</title>
<link rel="stylesheet" href="styles.css">
</head>
<body>
<header id="ribbon">
  <div class="ribbon-tabs">
    <button class="ribbon-tab active" data-tab="file">文件</button>
    <button class="ribbon-tab" data-tab="annotate">批注</button>
    <button class="ribbon-tab" data-tab="figures">图表</button>
    <button class="ribbon-tab" data-tab="view">视图</button>
    <button class="ribbon-tab" data-tab="toolbox">工具箱</button>
  </div>
  <div class="ribbon-panels">
    <div class="ribbon-panel active" data-panel="file">
      <button id="btn-import">导入论文</button>
      <label class="check"><input type="checkbox" id="chk-detect" checked> 检测图表并标记</label>
      <button id="btn-export" disabled>导出带标注副本</button>
      <input type="file" id="file-input" accept="application/pdf" hidden>
    </div>
    <div class="ribbon-panel" data-panel="annotate">
      <button data-tool="pen" class="tool-btn" title="手写笔">✏️ 笔</button>
      <button data-tool="highlighter" class="tool-btn" title="荧光笔">🖍 荧光笔</button>
      <button data-tool="eraser" class="tool-btn" title="橡皮">⌫ 橡皮</button>
      <button data-tool="comment" class="tool-btn" title="文本批注">💬 批注</button>
      <span class="sep"></span>
      <input type="color" id="ink-color" value="#CC2936" title="颜色">
      <input type="range" id="ink-width" min="1" max="8" step="0.5" value="2" title="粗细">
      <span class="sep"></span>
      <button id="btn-undo" title="撤销">↶ 撤销</button>
      <button id="btn-redo" title="重做">↷ 重做</button>
      <button id="btn-clear-page" title="清空本页">清空本页</button>
    </div>
    <div class="ribbon-panel" data-panel="figures">
      <span id="detect-status" class="detect-status">未导入论文</span>
      <button id="btn-redetect" disabled>重新检测</button>
    </div>
    <div class="ribbon-panel" data-panel="view">
      <button id="btn-fit-width">适应宽度</button>
      <button id="btn-fit-page">适应页面</button>
      <select id="zoom-select">
        <option value="0.5">50%</option>
        <option value="0.75">75%</option>
        <option value="1" selected>100%</option>
        <option value="1.25">125%</option>
        <option value="1.5">150%</option>
        <option value="2">200%</option>
      </select>
    </div>
    <div class="ribbon-panel" data-panel="toolbox">
      <span class="dim">在右栏「工具箱」页签上传单张图表解析</span>
      <button id="btn-show-toolbox">打开工具箱</button>
    </div>
  </div>
  <div id="health-light" class="health-light" title="检查中…"></div>
</header>
<div id="main">
  <aside id="thumbs"></aside>
  <section id="reader">
    <div id="empty-state">
      <div class="empty-card">
        <h1>论文阅读器</h1>
        <p>点击 ribbon「导入论文」或拖拽 PDF 到此处</p>
        <p class="dim">导入后可圈画批注，点击图表框按需解析复刻</p>
      </div>
    </div>
    <div id="page-wrap" hidden>
      <div id="page-stage" data-mode="read">
        <img id="page-img" alt="">
        <div id="figure-layer"></div>
        <canvas id="ink-canvas"></canvas>
        <div id="comment-layer"></div>
      </div>
      <div id="pager">
        <button id="btn-prev">← 上一页</button>
        <span id="page-indicator">- / -</span>
        <button id="btn-next">下一页 →</button>
      </div>
    </div>
  </section>
  <aside id="sidebar">
    <div class="side-tabs">
      <button class="side-tab active" data-side="comments">批注</button>
      <button class="side-tab" data-side="figure">图表</button>
      <button class="side-tab" data-side="toolbox">工具箱</button>
    </div>
    <div class="side-panel active" data-panel="comments" id="comments-panel">
      <p class="dim">导入论文后可添加批注</p>
    </div>
    <div class="side-panel" data-panel="figure" id="figure-panel">
      <p class="dim">点击页面中的图表框开始解析</p>
    </div>
    <div class="side-panel" data-panel="toolbox" id="toolbox-panel">
      <input type="file" id="single-input" accept="image/*" hidden>
      <button id="btn-single-upload">上传图表图片</button>
      <div id="single-result"></div>
    </div>
  </aside>
</div>
<div id="toast" hidden></div>
<script type="module" src="js/main.js"></script>
</body>
</html>
```

- [ ] **Step 2: 创建 app/reader/styles.css（全文）**

```css
:root {
  --brand: #CC2936;
  --paper-bg: #F5F3EF;
  --ribbon-bg: #FAFAF8;
  --border: #E3E0DA;
  --text: #2B2B2B;
  --dim: #8A8578;
  --ok: #2E7D32;
  --err: #C62828;
}
* { box-sizing: border-box; }
html, body { height: 100%; margin: 0; }
body { font-family: "Segoe UI", "Microsoft YaHei", sans-serif; color: var(--text); background: var(--paper-bg); display: flex; flex-direction: column; overflow: hidden; }
button { font: inherit; cursor: pointer; border: 1px solid var(--border); background: #fff; border-radius: 4px; padding: 4px 10px; }
button:hover:not(:disabled) { border-color: var(--brand); color: var(--brand); }
button:disabled { opacity: .45; cursor: default; }
.dim { color: var(--dim); }
.error-text { color: var(--err); }

/* ---- ribbon（Word 风格选项卡） ---- */
#ribbon { background: var(--ribbon-bg); border-bottom: 1px solid var(--border); position: relative; }
.ribbon-tabs { display: flex; gap: 2px; padding: 6px 12px 0; }
.ribbon-tab { border: none; background: transparent; padding: 6px 14px; border-radius: 4px 4px 0 0; font-size: 13px; }
.ribbon-tab.active { background: #fff; color: var(--brand); font-weight: 600; box-shadow: inset 0 -2px 0 var(--brand); }
.ribbon-panels { background: #fff; border-top: 1px solid var(--border); }
.ribbon-panel { display: none; align-items: center; gap: 8px; padding: 8px 12px; min-height: 44px; font-size: 13px; }
.ribbon-panel.active { display: flex; }
.ribbon-panel .sep { width: 1px; height: 22px; background: var(--border); margin: 0 4px; }
.ribbon-panel .check { display: flex; align-items: center; gap: 4px; }
.tool-btn.active { background: var(--brand); color: #fff; border-color: var(--brand); }
.health-light { position: absolute; top: 10px; right: 14px; width: 12px; height: 12px; border-radius: 50%; background: #bbb; cursor: help; }
.health-light.ok { background: var(--ok); }
.health-light.bad { background: var(--err); }
.detect-status { color: var(--dim); }

/* ---- 主区三栏 ---- */
#main { flex: 1; display: grid; grid-template-columns: 150px 1fr 340px; min-height: 0; }
#thumbs { overflow-y: auto; background: var(--ribbon-bg); border-right: 1px solid var(--border); padding: 8px; }
.thumb { position: relative; margin-bottom: 10px; border: 2px solid transparent; border-radius: 3px; cursor: pointer; }
.thumb img { width: 100%; display: block; box-shadow: 0 1px 3px rgba(0,0,0,.2); }
.thumb span { position: absolute; right: 3px; bottom: 3px; background: rgba(0,0,0,.6); color: #fff; font-size: 10px; padding: 0 4px; border-radius: 2px; }
.thumb.active { border-color: var(--brand); }

#reader { overflow: auto; position: relative; padding: 24px; }
#reader.drag-over { outline: 3px dashed var(--brand); outline-offset: -8px; }
#empty-state { height: 100%; display: flex; align-items: center; justify-content: center; }
.empty-card { text-align: center; color: var(--dim); }
.empty-card h1 { font-family: Georgia, "SimSun", serif; color: var(--text); font-size: 28px; margin: 0 0 8px; }
#page-wrap { display: flex; flex-direction: column; align-items: center; min-height: 100%; }
#page-stage { position: relative; background: #fff; box-shadow: 0 2px 10px rgba(0,0,0,.25); }
#page-img { display: block; width: 100%; height: 100%; user-select: none; }
#figure-layer, #ink-canvas, #comment-layer { position: absolute; inset: 0; }
#figure-layer { z-index: 2; }
#ink-canvas { z-index: 3; }
#comment-layer { z-index: 4; pointer-events: none; }
#page-stage[data-mode="ink"] #ink-canvas { cursor: crosshair; }
#page-stage[data-mode="ink"] #figure-layer,
#page-stage[data-mode="ink"] #comment-layer { pointer-events: none; }
#page-stage[data-mode="read"] #ink-canvas { pointer-events: none; }
#page-stage[data-mode="comment"] #figure-layer,
#page-stage[data-mode="comment"] #ink-canvas { pointer-events: none; }
#page-stage[data-mode="comment"] #comment-layer { pointer-events: auto; }
#comment-catcher { position: absolute; inset: 0; display: none; cursor: text; }
#page-stage[data-mode="comment"] #comment-catcher { display: block; }
#pager { display: flex; align-items: center; gap: 12px; padding: 12px; }

/* 图表高亮框：未解析虚线 / 已解析实线 / 失败红框（设计文档 4.2） */
.fig-box { position: absolute; border: 2px dashed rgba(204,41,54,.85); background: rgba(204,41,54,.07); cursor: pointer; }
.fig-box:hover { background: rgba(204,41,54,.15); }
.fig-box.status-done { border-style: solid; border-color: var(--ok); background: rgba(46,125,50,.07); }
.fig-box.status-error { border-style: solid; border-color: var(--err); background: rgba(198,40,40,.08); }
.fig-badge { position: absolute; top: -10px; left: -10px; min-width: 18px; height: 18px; border-radius: 9px; background: var(--brand); color: #fff; font-size: 11px; line-height: 18px; text-align: center; padding: 0 4px; }
.fig-box.status-done .fig-badge { background: var(--ok); }
.fig-box.status-error .fig-badge { background: var(--err); }

/* 批注锚点 */
.comment-anchor { position: absolute; transform: translate(-50%, -50%); width: 20px; height: 20px; border-radius: 50%; background: var(--brand); color: #fff; font-size: 11px; line-height: 20px; text-align: center; cursor: pointer; pointer-events: auto; box-shadow: 0 1px 3px rgba(0,0,0,.3); }
.comment-anchor.resolved { background: #9e9e9e; }
.comment-anchor.flash { outline: 3px solid rgba(204,41,54,.5); }

/* ---- 右栏 ---- */
#sidebar { background: #fff; border-left: 1px solid var(--border); display: flex; flex-direction: column; min-height: 0; }
.side-tabs { display: flex; border-bottom: 1px solid var(--border); }
.side-tab { flex: 1; border: none; background: var(--ribbon-bg); padding: 8px; font-size: 13px; border-radius: 0; }
.side-tab.active { background: #fff; color: var(--brand); font-weight: 600; box-shadow: inset 0 -2px 0 var(--brand); }
.side-panel { display: none; flex: 1; overflow-y: auto; padding: 10px; }
.side-panel.active { display: block; }

.comment-card { border: 1px solid var(--border); border-radius: 6px; padding: 8px; margin-bottom: 8px; }
.comment-card.flash { border-color: var(--brand); box-shadow: 0 0 0 3px rgba(204,41,54,.2); }
.comment-card.resolved { opacity: .6; background: #fafafa; }
.comment-head { font-size: 12px; color: var(--dim); margin-bottom: 6px; }
.comment-card textarea { width: 100%; resize: vertical; border: 1px solid var(--border); border-radius: 4px; padding: 6px; font: inherit; font-size: 13px; }
.comment-snippet { font-size: 13px; margin: 4px 0; }
.comment-actions { display: flex; gap: 6px; margin-top: 6px; }
.comment-actions button { font-size: 12px; padding: 2px 8px; }
.comment-actions .danger:hover { border-color: var(--err); color: var(--err); }

.result-tabs { display: flex; gap: 2px; border-bottom: 1px solid var(--border); margin-bottom: 8px; }
.result-tab { border: none; background: transparent; padding: 6px 10px; font-size: 13px; }
.result-tab.active { color: var(--brand); font-weight: 600; box-shadow: inset 0 -2px 0 var(--brand); }
.result-pane { display: none; }
.result-pane.active { display: block; }
.result-img { max-width: 100%; border: 1px solid var(--border); }
.chart-title { font-weight: 600; font-size: 13px; }
.data-table { border-collapse: collapse; width: 100%; font-size: 12px; margin-bottom: 10px; }
.data-table th, .data-table td { border: 1px solid var(--border); padding: 3px 6px; text-align: right; }
.data-table th { background: var(--ribbon-bg); }
.code-block { background: #2b2b2b; color: #e8e8e8; font-size: 11px; padding: 10px; border-radius: 6px; overflow: auto; max-height: 420px; white-space: pre; }
.copy-btn { margin-bottom: 6px; font-size: 12px; }

#toast { position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%); background: rgba(30,30,30,.92); color: #fff; padding: 8px 18px; border-radius: 20px; font-size: 13px; z-index: 99; }
```

- [ ] **Step 3: 创建占位 app/reader/js/main.js**

```javascript
// 占位入口：Task 8 替换为完整初始化
window.addEventListener('DOMContentLoaded', () => {});
```

- [ ] **Step 4: 浏览器验证骨架**

Run（终端 A）: `$py -m uvicorn app.server:app --port 8000`
Run（终端 B，全局 python 带 playwright；长连接页面用 domcontentloaded）:

```powershell
python -c "from playwright.sync_api import sync_playwright; p=sync_playwright().start(); b=p.chromium.launch(); pg=b.new_page(); pg.goto('http://127.0.0.1:8000', wait_until='domcontentloaded'); pg.wait_for_timeout(800); errs=[m.text for m in pg.on('console', lambda m: None)] if False else []; print('title:', pg.title()); print('tabs:', pg.locator('.ribbon-tab').count()); print('empty visible:', pg.locator('#empty-state').is_visible()); pg.screenshot(path='work/reader-skeleton.png'); b.close(); p.stop()"
```

Expected: title=论文阅读器，tabs=5，empty visible=True；截图可见 ribbon + 三栏 + 空白引导页

- [ ] **Step 5: Commit**

```powershell
git add app/reader/index.html app/reader/styles.css app/reader/js/main.js
git commit -m "feat: 阅读器前端骨架（Word ribbon 三栏布局）"
```

---

### Task 8: 前端核心（api/state/annotate/viewer/main）——导入与阅读

**Files:**
- Create: `app/reader/js/api.js`
- Create: `app/reader/js/state.js`
- Create: `app/reader/js/annotate.js`
- Create: `app/reader/js/viewer.js`
- Modify: `app/reader/js/main.js`（替换占位）

- [ ] **Step 1: 创建 app/reader/js/state.js**

```javascript
// 全局状态 + 简易事件总线 + 工具函数
export const state = {
  paper: null,          // {pdf_hash, file_name, n_pages, truncated}
  page: 1,
  pageSize: { w: 0, h: 0 },  // 页面自然像素（150 DPI PNG）
  zoom: 1,              // 100% = 自然尺寸
  fitMode: 'width',     // 'width' | 'page' | null
  scale: 1,             // 显示像素 / 自然像素
  tool: 'read',         // read | pen | highlighter | eraser | comment
  inkColor: '#CC2936',
  inkWidth: 2,          // 单位 PDF point
  figures: [],
  annotations: { version: 1, pages: {} },
  undoStack: [],
  redoStack: [],
  status: null,
};

const listeners = {};
export function on(evt, fn) { (listeners[evt] ||= []).push(fn); }
export function emit(evt, ...args) { (listeners[evt] || []).forEach((fn) => fn(...args)); }

export const uid = (prefix) =>
  `${prefix}-${Math.random().toString(16).slice(2, 6)}${Date.now().toString(16).slice(-4)}`;

export function toast(msg, ms = 3200) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(t._tm);
  t._tm = setTimeout(() => { t.hidden = true; }, ms);
}
```

- [ ] **Step 2: 创建 app/reader/js/api.js**

```javascript
// 后端 API 封装（设计文档 6）
async function J(r) {
  if (!r.ok) throw new Error(`HTTP ${r.status}: ${(await r.text()).slice(0, 200)}`);
  return r.json();
}

export async function uploadPaper(file, detect) {
  const fd = new FormData();
  fd.append('file', file);
  fd.append('detect', detect ? 'true' : 'false');
  return J(await fetch('/api/papers', { method: 'POST', body: fd }));
}

export const getStatus = (h) => fetch(`/api/papers/${h}/status`).then(J);
export const getFigures = (h) => fetch(`/api/papers/${h}/figures`).then(J);
export const parseFigure = (h, fid) =>
  fetch(`/api/papers/${h}/figures/${fid}/parse`, { method: 'POST' }).then(J);
export const getAnnotations = (h) => fetch(`/api/papers/${h}/annotations`).then(J);
export const putAnnotations = (h, data) =>
  fetch(`/api/papers/${h}/annotations`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
  }).then(J);
export const startDetect = (h) =>
  fetch(`/api/papers/${h}/detect`, { method: 'POST' }).then(J);
export const getHealth = () => fetch('/api/health').then(J);

export async function parseSingle(file) {
  const fd = new FormData();
  fd.append('file', file);
  return J(await fetch('/api/singles/parse', { method: 'POST', body: fd }));
}

export async function exportPaper(h) {
  const r = await fetch(`/api/papers/${h}/export`, { method: 'POST' });
  if (!r.ok) throw new Error((await r.text()).slice(0, 200));
  const blob = await r.blob();
  const dispo = r.headers.get('Content-Disposition') || '';
  const m = dispo.match(/filename\*?=(?:UTF-8''|")?([^";]+)/i);
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = m ? decodeURIComponent(m[1].replace(/"/g, '')) : 'annotated.pdf';
  a.click();
  URL.revokeObjectURL(a.href);
}
```

- [ ] **Step 3: 创建 app/reader/js/annotate.js**

```javascript
// 标注侧车：加载 / 1s 防抖自动保存 / 页条目工具（设计文档 4.3、5.1）
import { state, emit, toast } from './state.js';
import { getAnnotations, putAnnotations } from './api.js';

let timer = null;

export async function loadAnnotations() {
  try {
    state.annotations = await getAnnotations(state.paper.pdf_hash);
  } catch (e) {
    state.annotations = { version: 1, pages: {} };
    toast(`标注读取失败: ${e.message}`);
  }
  state.undoStack = [];
  state.redoStack = [];
  emit('annotations-changed');
}

export function scheduleSave() {
  clearTimeout(timer);
  timer = setTimeout(saveNow, 1000);
}

export async function saveNow() {
  if (!state.paper) return;
  try {
    await putAnnotations(state.paper.pdf_hash, state.annotations);
  } catch (e) {
    toast('标注保存失败，下次变更将自动重试');
  }
}

export function pageAnnot(n) {
  const pages = state.annotations.pages;
  const key = String(n);
  if (!pages[key]) pages[key] = { strokes: [], comments: [] };
  return pages[key];
}

export function prunePage(n) {
  // 无标注页面不写条目（设计文档 5.1）
  const key = String(n);
  const p = state.annotations.pages[key];
  if (p && p.strokes.length === 0 && p.comments.length === 0) delete state.annotations.pages[key];
}
```

- [ ] **Step 4: 创建 app/reader/js/viewer.js**

```javascript
// 阅读画布：导入 / 页面渲染 / 翻页 / 缩放 / 缩略图导航（设计文档 4.1、4.2）
import { state, emit, toast } from './state.js';
import { uploadPaper } from './api.js';
import { loadAnnotations } from './annotate.js';

const $ = (id) => document.getElementById(id);

export function initViewer() {
  $('btn-import').addEventListener('click', () => $('file-input').click());
  $('file-input').addEventListener('change', (e) => {
    if (e.target.files[0]) importFile(e.target.files[0]);
    e.target.value = '';
  });
  $('btn-prev').addEventListener('click', prevPage);
  $('btn-next').addEventListener('click', nextPage);
  const reader = $('reader');
  reader.addEventListener('dragover', (e) => { e.preventDefault(); reader.classList.add('drag-over'); });
  reader.addEventListener('dragleave', () => reader.classList.remove('drag-over'));
  reader.addEventListener('drop', (e) => {
    e.preventDefault();
    reader.classList.remove('drag-over');
    const f = e.dataTransfer.files[0];
    if (f && (f.type === 'application/pdf' || f.name.toLowerCase().endsWith('.pdf'))) importFile(f);
    else toast('请拖入 PDF 文件');
  });
  window.addEventListener('resize', () => { if (state.fitMode) applyScale(); });
  document.addEventListener('keydown', (e) => {
    if (/^(TEXTAREA|INPUT|SELECT)$/.test(e.target.tagName)) return;
    if (e.key === 'ArrowLeft') prevPage();
    if (e.key === 'ArrowRight') nextPage();
  });
}

export async function importFile(file) {
  toast('导入中：渲染页面…');
  let info;
  try {
    info = await uploadPaper(file, $('chk-detect').checked);
  } catch (e) {
    toast(`导入失败: ${e.message}`);
    return;
  }
  state.paper = info;
  state.page = 1;
  state.zoom = 1;
  state.fitMode = 'width';
  state.figures = [];
  buildThumbs(info.n_pages);
  $('empty-state').hidden = true;
  $('page-wrap').hidden = false;
  await loadAnnotations();
  renderPage();
  emit('paper-loaded');
  toast(`已导入 ${info.file_name}（${info.n_pages} 页${info.truncated ? '，超出页数上限已截断' : ''}）`);
}

export function renderPage() {
  if (!state.paper) return;
  const img = $('page-img');
  const n = state.page;
  img.onload = () => {
    state.pageSize = { w: img.naturalWidth, h: img.naturalHeight };
    applyScale();
    updatePager();
    highlightThumb();
    emit('page-changed', n);
  };
  img.onerror = () => toast(`第 ${n} 页加载失败`);
  img.src = `/api/papers/${state.paper.pdf_hash}/pages/${n}.png`;
}

export function applyScale() {
  const { w, h } = state.pageSize;
  if (!w) return;
  const reader = $('reader');
  let scale = state.zoom;
  if (state.fitMode === 'width') scale = Math.max(0.1, (reader.clientWidth - 48) / w);
  if (state.fitMode === 'page') scale = Math.max(0.1, Math.min((reader.clientWidth - 48) / w, (reader.clientHeight - 110) / h));
  state.scale = scale;
  const stage = $('page-stage');
  stage.style.width = `${w * scale}px`;
  stage.style.height = `${h * scale}px`;
  const canvas = $('ink-canvas');
  canvas.width = Math.round(w * scale);
  canvas.height = Math.round(h * scale);
  emit('scale-changed');
}

export function setZoom(z) { state.zoom = z; state.fitMode = null; applyScale(); }
export function setFitMode(mode) { state.fitMode = mode; applyScale(); }

export function gotoPage(n) {
  if (!state.paper) return;
  const clamped = Math.min(Math.max(1, n), state.paper.n_pages);
  if (clamped === state.page && $('page-img').src) return;
  state.page = clamped;
  renderPage();
}

export function prevPage() { gotoPage(state.page - 1); }
export function nextPage() { gotoPage(state.page + 1); }

function updatePager() {
  $('page-indicator').textContent = `${state.page} / ${state.paper.n_pages}`;
  $('btn-prev').disabled = state.page <= 1;
  $('btn-next').disabled = state.page >= state.paper.n_pages;
}

function buildThumbs(n) {
  const box = $('thumbs');
  box.innerHTML = '';
  for (let i = 1; i <= n; i++) {
    const item = document.createElement('div');
    item.className = 'thumb';
    item.dataset.page = i;
    const img = document.createElement('img');
    img.loading = 'lazy';
    img.src = `/api/papers/${state.paper.pdf_hash}/pages/${i}.png`;
    const label = document.createElement('span');
    label.textContent = i;
    item.appendChild(img);
    item.appendChild(label);
    item.addEventListener('click', () => gotoPage(i));
    box.appendChild(item);
  }
}

function highlightThumb() {
  document.querySelectorAll('.thumb').forEach((el) => {
    el.classList.toggle('active', Number(el.dataset.page) === state.page);
  });
  const active = document.querySelector('.thumb.active');
  if (active) active.scrollIntoView({ block: 'nearest' });
}
```

- [ ] **Step 5: 替换 app/reader/js/main.js（本任务只挂 viewer；figures/ink/comments/ribbon/toolbox 后续任务逐个追加）**

```javascript
import { on } from './state.js';
import { initViewer } from './viewer.js';

function switchSideTab(name) {
  document.querySelectorAll('.side-tab').forEach((b) => b.classList.toggle('active', b.dataset.side === name));
  document.querySelectorAll('.side-panel').forEach((p) => p.classList.toggle('active', p.dataset.panel === name));
}

window.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.side-tab').forEach((b) => b.addEventListener('click', () => switchSideTab(b.dataset.side)));
  on('switch-side-tab', switchSideTab);
  initViewer();
});
```

- [ ] **Step 6: 浏览器验证导入与阅读（无需 VL）**

前置：`assets\samples\synthetic-demo.pdf` 存在（缺则 `$py scripts\make_synthetic_sample.py`）。
Run（终端 A）: `$py -m uvicorn app.server:app --port 8000`
验证脚本 `work\verify_t8.py`（全局 python + playwright，不提交）：

```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto('http://127.0.0.1:8000', wait_until='domcontentloaded')
    pg.locator('#chk-detect').uncheck()  # 不勾检测，纯阅读（无需 VL）
    pg.locator('#file-input').set_input_files(r'd:\aicomp\assets\samples\synthetic-demo.pdf')
    pg.wait_for_selector('#page-wrap:not([hidden])', timeout=15000)
    pg.wait_for_timeout(1200)
    print('thumbs:', pg.locator('.thumb').count())            # 3
    print('indicator:', pg.locator('#page-indicator').inner_text())  # 1 / 3
    pg.locator('#btn-next').click(); pg.wait_for_timeout(600)
    print('after next:', pg.locator('#page-indicator').inner_text())  # 2 / 3
    pg.locator('.thumb').nth(0).click(); pg.wait_for_timeout(600)
    print('after thumb:', pg.locator('#page-indicator').inner_text())  # 1 / 3
    print('stage width:', pg.locator('#page-stage').evaluate('e => e.style.width'))
    print('js errors:', errors)
    pg.screenshot(path=r'work\reader-t8.png')
    b.close()
```

Run: `python work\verify_t8.py`
Expected: thumbs=3、翻页/缩略图跳页正常、stage 有宽度、`js errors: []`

- [ ] **Step 7: Commit**

```powershell
git add app/reader/js
git commit -m "feat: 阅读器前端核心（导入/页面渲染/翻页/缩放/缩略图）"
```

---

### Task 9: figures.js——检测轮询 / 图框层 / 按需解析 / 四件套

**Files:**
- Create: `app/reader/js/figures.js`
- Modify: `app/reader/js/main.js`（追加 initFigures）

- [ ] **Step 1: 创建 app/reader/js/figures.js**

```javascript
// 图表：检测状态轮询 / 图框 DOM 层 / 点击按需解析 / 右栏四件套（设计文档 4.2、4.4）
import { state, on, emit, toast } from './state.js';
import { getStatus, getFigures, parseFigure, startDetect } from './api.js';

const $ = (id) => document.getElementById(id);
let pollTimer = null;

export function initFigures() {
  on('paper-loaded', onPaperLoaded);
  on('page-changed', renderBoxes);
  on('scale-changed', renderBoxes);
}

const hash = () => state.paper.pdf_hash;

async function onPaperLoaded() {
  state.figures = [];
  resetFigurePanel();
  stopPolling();
  try {
    const st = await getStatus(hash());
    updateDetectStatus(st);
    if (st.stage === 'detecting') startPolling();
    else await refreshFigures();
  } catch (e) {
    $('detect-status').textContent = '状态获取失败';
  }
}

function startPolling() {
  stopPolling();
  pollTimer = setInterval(async () => {
    try {
      const st = await getStatus(hash());
      updateDetectStatus(st);
      if (st.stage !== 'detecting') {
        stopPolling();
        await refreshFigures();
        if (st.stage === 'ready') toast(`检测完成，标记 ${st.n_figures} 张图表`);
      }
    } catch (e) { /* 网络抖动下轮重试 */ }
  }, 1000);
}

function stopPolling() { if (pollTimer) { clearInterval(pollTimer); pollTimer = null; } }

export async function redetectFigures() {
  if (!state.paper) return;
  try {
    await startDetect(hash());
    $('detect-status').textContent = '检测中…';
    state.figures = [];
    renderBoxes();
    startPolling();
  } catch (e) { toast(`重新检测失败: ${e.message}`); }
}

async function refreshFigures() {
  try {
    const data = await getFigures(hash());
    state.figures = data.figures;
    renderBoxes();
  } catch (e) { toast('图表列表获取失败'); }
}

function updateDetectStatus(st) {
  const el = $('detect-status');
  if (st.stage === 'detecting') el.textContent = `检测中 ${st.detect_done}/${st.detect_total || '?'} · 已标记 ${st.n_figures} 张`;
  else if (st.stage === 'failed') el.textContent = `检测失败: ${st.error || ''}`;
  else if (st.n_figures > 0) el.textContent = `已标记 ${st.n_figures} 张图表`;
  else el.textContent = '未检测到图表';
}

export function renderBoxes() {
  const layer = $('figure-layer');
  if (!layer || !state.paper) return;
  layer.innerHTML = '';
  const scale = state.scale;
  state.figures.forEach((fig, idx) => {
    if (fig.page !== state.page) return;
    const [x0, y0, x1, y1] = fig.bbox_px;
    const box = document.createElement('div');
    box.className = `fig-box status-${fig.parse_status || 'pending'}`;
    box.style.left = `${x0 * scale}px`;
    box.style.top = `${y0 * scale}px`;
    box.style.width = `${(x1 - x0) * scale}px`;
    box.style.height = `${(y1 - y0) * scale}px`;
    box.title = fig.parse_status === 'done' ? '点击查看解析结果' : '点击解析';
    const badge = document.createElement('span');
    badge.className = 'fig-badge';
    badge.textContent = idx + 1;
    box.appendChild(badge);
    box.addEventListener('click', () => onBoxClick(fig));
    layer.appendChild(box);
  });
}

async function onBoxClick(fig) {
  if (state.tool !== 'read') return;  // 批注/墨迹模式下不触发解析
  emit('switch-side-tab', 'figure');
  const panel = $('figure-panel');
  if (fig.parse_status !== 'done') panel.innerHTML = '<p class="dim">解析中…（约 10-20 秒）</p>';
  try {
    const r = await parseFigure(hash(), fig.id);
    fig.parse_status = r.parse_status;
    renderBoxes();
    if (r.parse_status === 'error') {
      showPanelError(panel, r.error || '解析失败', () => onBoxClick(fig));
      return;
    }
    renderChartResult(panel, {
      inputUrl: r.crop_path ? `/cache/papers/${hash()}/${r.crop_path}` : null,
      chart: r.chart,
      renderUrl: r.render_path ? `/cache/papers/${hash()}/${r.render_path}` : null,
      codeUrl: r.code_path ? `/cache/papers/${hash()}/${r.code_path}` : null,
    });
  } catch (e) {
    showPanelError(panel, e.message, () => onBoxClick(fig));
  }
}

function showPanelError(panel, msg, retry) {
  panel.innerHTML = '';
  const p = document.createElement('p');
  p.className = 'error-text';
  p.textContent = `解析失败: ${msg}`;
  const btn = document.createElement('button');
  btn.textContent = '重试';
  btn.addEventListener('click', retry);
  panel.appendChild(p);
  panel.appendChild(btn);
}

function resetFigurePanel() {
  $('figure-panel').innerHTML = '<p class="dim">点击页面中的图表框开始解析</p>';
}

// ---- 四件套渲染（工具箱 toolbox.js 共用）----

export function renderChartResult(container, { inputUrl, chart, renderUrl, codeUrl, codeText }) {
  container.innerHTML = '';
  const tabs = document.createElement('div');
  tabs.className = 'result-tabs';
  const panes = document.createElement('div');
  panes.className = 'result-panes';
  const defs = [
    ['原图', () => imagePane(inputUrl)],
    ['数据表', () => tablePane(chart)],
    ['复刻图', () => (renderUrl ? imagePane(renderUrl) : msgPane('复刻图渲染失败或缺失'))],
    ['代码', () => codePane(codeUrl, codeText)],
  ];
  defs.forEach(([name, build], i) => {
    const tab = document.createElement('button');
    tab.className = 'result-tab';
    tab.textContent = name;
    const pane = build();
    tab.classList.toggle('active', i === 0);
    pane.classList.toggle('active', i === 0);
    tab.addEventListener('click', () => {
      tabs.querySelectorAll('.result-tab').forEach((t) => t.classList.remove('active'));
      panes.querySelectorAll('.result-pane').forEach((p) => p.classList.remove('active'));
      tab.classList.add('active');
      pane.classList.add('active');
    });
    tabs.appendChild(tab);
    panes.appendChild(pane);
  });
  container.appendChild(tabs);
  container.appendChild(panes);
}

function imagePane(url) {
  const pane = document.createElement('div');
  pane.className = 'result-pane';
  if (!url) { pane.textContent = '暂无图片'; pane.classList.add('dim'); return pane; }
  const img = document.createElement('img');
  img.src = url;
  img.className = 'result-img';
  pane.appendChild(img);
  return pane;
}

function msgPane(text) {
  const pane = document.createElement('div');
  pane.className = 'result-pane dim';
  pane.textContent = text;
  return pane;
}

function tablePane(chart) {
  const pane = document.createElement('div');
  pane.className = 'result-pane';
  if (!chart) { pane.textContent = '暂无数据'; pane.classList.add('dim'); return pane; }
  const title = document.createElement('p');
  title.className = 'chart-title';
  title.textContent = chart.title || '（无标题）';
  pane.appendChild(title);
  if (chart.heatmap && chart.heatmap.matrix) {
    pane.appendChild(heatmapTable(chart.heatmap));
    return pane;
  }
  const series = chart.series || [];
  if (!series.length) { pane.appendChild(msgText('无可展示的数据系列')); return pane; }
  const xLabel = (chart.x_axis && chart.x_axis.label) || 'x';
  const sameX = series.every((s) => JSON.stringify(s.x) === JSON.stringify(series[0].x));
  if (sameX) pane.appendChild(seriesTable(series, xLabel));
  else series.forEach((s) => pane.appendChild(seriesTable([s], xLabel)));
  return pane;
}

function msgText(t) {
  const p = document.createElement('p');
  p.className = 'dim';
  p.textContent = t;
  return p;
}

function seriesTable(series, xLabel) {
  const table = document.createElement('table');
  table.className = 'data-table';
  const head = document.createElement('tr');
  head.appendChild(th(xLabel));
  series.forEach((s) => head.appendChild(th(s.name || 'y')));
  table.appendChild(head);
  (series[0].x || []).forEach((x, i) => {
    const tr = document.createElement('tr');
    tr.appendChild(td(x));
    series.forEach((s) => tr.appendChild(td((s.y || [])[i])));
    table.appendChild(tr);
  });
  return table;
}

function heatmapTable(hm) {
  const table = document.createElement('table');
  table.className = 'data-table';
  const head = document.createElement('tr');
  head.appendChild(th(''));
  (hm.x_labels || []).forEach((x) => head.appendChild(th(x)));
  table.appendChild(head);
  (hm.matrix || []).forEach((row, i) => {
    const tr = document.createElement('tr');
    tr.appendChild(th((hm.y_labels || [])[i] ?? i));
    row.forEach((v) => tr.appendChild(td(v)));
    table.appendChild(tr);
  });
  return table;
}

function th(t) { const el = document.createElement('th'); el.textContent = t ?? ''; return el; }
function td(t) { const el = document.createElement('td'); el.textContent = t ?? ''; return el; }

function codePane(codeUrl, codeText) {
  const pane = document.createElement('div');
  pane.className = 'result-pane';
  const btn = document.createElement('button');
  btn.textContent = '复制代码';
  btn.className = 'copy-btn';
  const pre = document.createElement('pre');
  pre.className = 'code-block';
  pre.textContent = codeText || '加载中…';
  btn.addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(pre.textContent); toast('已复制'); }
    catch (e) { toast('复制失败'); }
  });
  pane.appendChild(btn);
  pane.appendChild(pre);
  if (!codeText && codeUrl) {
    fetch(codeUrl).then((r) => r.text()).then((t) => { pre.textContent = t; })
      .catch(() => { pre.textContent = '代码加载失败'; });
  } else if (!codeText) {
    pre.textContent = '暂无代码';
  }
  return pane;
}
```

- [ ] **Step 2: main.js 追加 initFigures（全文替换为）**

```javascript
import { on } from './state.js';
import { initViewer } from './viewer.js';
import { initFigures } from './figures.js';

function switchSideTab(name) {
  document.querySelectorAll('.side-tab').forEach((b) => b.classList.toggle('active', b.dataset.side === name));
  document.querySelectorAll('.side-panel').forEach((p) => p.classList.toggle('active', p.dataset.panel === name));
}

window.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.side-tab').forEach((b) => b.addEventListener('click', () => switchSideTab(b.dataset.side)));
  on('switch-side-tab', switchSideTab);
  initViewer();
  initFigures();
});
```

- [ ] **Step 3: 浏览器验证图框层（无需 VL：向缓存注入假图框）**

前置：服务运行中（终端 A: `$py -m uvicorn app.server:app --port 8000`）。先按 Task 8 方式导入一次 synthetic-demo.pdf（不勾检测），然后用 PowerShell 向该论文 session.json 注入 1 张假 figure（page 1, bbox [100,200,700,500], parse_status pending）：

```powershell
$h = (Get-ChildItem data\cache\papers | Sort-Object LastWriteTime -Descending | Select-Object -First 1).Name
$p = "data\cache\papers\$h\session.json"
$s = Get-Content $p -Raw | ConvertFrom-Json
$s.figures = @([pscustomobject]@{ id="p1-f1"; page=1; bbox_norm=@(0,0,1,1); bbox_px=@(100,200,700,500); type="line"; source="vl_grounding"; caption_hint=$null; parse_status="pending" })
$s | ConvertTo-Json -Depth 10 | Set-Content $p -Encoding UTF8
```

验证脚本 `work\verify_t9.py`（playwright，不提交）：重新打开页面 → 导入同一文件（同一 hash 命中缓存）→ 应出现 1 个虚线图框；点击图框 → 右栏切到图表页签并显示「解析中…」→ 无 VL 时随后显示错误与重试按钮；`js errors` 为空。截图 `work\reader-t9.png`。

Expected: `.fig-box` 出现且可点击、面板出现重试按钮（VL 不可用属预期失败路径）

- [ ] **Step 4: Commit**

```powershell
git add app/reader/js
git commit -m "feat: 图表图框层与按需解析面板（轮询/四件套/失败重试）"
```

---

### Task 10: ink.js——手写墨迹（笔/荧光笔/橡皮/撤销重做/清空）

**Files:**
- Create: `app/reader/js/ink.js`
- Modify: `app/reader/js/main.js`（追加 initInk）

- [ ] **Step 1: 创建 app/reader/js/ink.js**

> 注：toNorm 必须夹取坐标到 [0,1]——服务端严格校验坐标范围，越界会使整份标注 PUT 400。

```javascript
// 手写墨迹：canvas 笔画采集 / 荧光笔半透明 / 橡皮点选删整条 / 撤销重做双栈 / 清空本页（设计文档 4.3）
import { state, on, uid, toast } from './state.js';
import { pageAnnot, prunePage, scheduleSave } from './annotate.js';

let canvas, ctx, drawing = false, pts = [];

export function initInk() {
  canvas = document.getElementById('ink-canvas');
  ctx = canvas.getContext('2d');
  canvas.addEventListener('pointerdown', onDown);
  canvas.addEventListener('pointermove', onMove);
  window.addEventListener('pointerup', onUp);
  on('page-changed', redrawAll);
  on('scale-changed', redrawAll);
  on('annotations-changed', redrawAll);
}

function pxPerPt() {
  // 自然像素 150 DPI：1pt = 150/72 px；显示再乘 scale
  return (150 / 72) * state.scale;
}

function toNorm(e) {
  const r = canvas.getBoundingClientRect();
  const x = (e.clientX - r.left) / canvas.width;
  const y = (e.clientY - r.top) / canvas.height;
  return [Math.min(1, Math.max(0, x)), Math.min(1, Math.max(0, y))];
}

function onDown(e) {
  if (state.tool === 'pen' || state.tool === 'highlighter') {
    drawing = true;
    pts = [toNorm(e)];
    canvas.setPointerCapture(e.pointerId);
  } else if (state.tool === 'eraser') {
    eraseAt(toNorm(e));
  }
}

function onMove(e) {
  if (!drawing) return;
  const p = toNorm(e);
  drawSegment(pts[pts.length - 1], p, state.tool, state.inkColor, state.inkWidth);
  pts.push(p);
}

function onUp() {
  if (!drawing) return;
  drawing = false;
  if (pts.length >= 2) {
    const stroke = { id: uid('s'), tool: state.tool, color: state.inkColor, width: state.inkWidth, points: pts };
    pageAnnot(state.page).strokes.push(stroke);
    state.undoStack.push({ op: 'add', page: state.page, stroke });
    state.redoStack = [];
    scheduleSave();
  }
  pts = [];
  redrawAll();
}

function drawSegment(a, b, tool, color, widthPt) {
  ctx.save();
  ctx.globalAlpha = tool === 'highlighter' ? 0.4 : 1;
  ctx.strokeStyle = color;
  ctx.lineWidth = Math.max(1, widthPt * pxPerPt());
  ctx.lineJoin = 'round';
  ctx.lineCap = 'round';
  ctx.beginPath();
  ctx.moveTo(a[0] * canvas.width, a[1] * canvas.height);
  ctx.lineTo(b[0] * canvas.width, b[1] * canvas.height);
  ctx.stroke();
  ctx.restore();
}

export function redrawAll() {
  if (!canvas || !canvas.width) return;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  const entry = state.annotations.pages[String(state.page)];
  if (!entry) return;
  for (const s of entry.strokes) {
    for (let i = 1; i < s.points.length; i++) {
      drawSegment(s.points[i - 1], s.points[i], s.tool, s.color, s.width);
    }
  }
}

// 橡皮：点选命中删除整条笔画（设计文档 4.3）
function eraseAt([nx, ny]) {
  const entry = state.annotations.pages[String(state.page)];
  if (!entry) return;
  const x = nx * canvas.width;
  const y = ny * canvas.height;
  for (let i = entry.strokes.length - 1; i >= 0; i--) {
    const s = entry.strokes[i];
    const tol = 6 + (s.width * pxPerPt()) / 2;
    if (hitStroke(s, x, y, tol)) {
      entry.strokes.splice(i, 1);
      state.undoStack.push({ op: 'remove', page: state.page, stroke: s, index: i });
      state.redoStack = [];
      prunePage(state.page);
      scheduleSave();
      redrawAll();
      return;
    }
  }
}

function hitStroke(s, x, y, tol) {
  for (let i = 1; i < s.points.length; i++) {
    const ax = s.points[i - 1][0] * canvas.width;
    const ay = s.points[i - 1][1] * canvas.height;
    const bx = s.points[i][0] * canvas.width;
    const by = s.points[i][1] * canvas.height;
    if (distToSegment(x, y, ax, ay, bx, by) <= tol) return true;
  }
  return false;
}

function distToSegment(px, py, ax, ay, bx, by) {
  const dx = bx - ax;
  const dy = by - ay;
  const len2 = dx * dx + dy * dy;
  let t = len2 ? ((px - ax) * dx + (py - ay) * dy) / len2 : 0;
  t = Math.max(0, Math.min(1, t));
  return Math.hypot(px - (ax + t * dx), py - (ay + t * dy));
}

export function undoInk() {
  const op = state.undoStack.pop();
  if (!op) { toast('没有可撤销的操作'); return; }
  applyInverse(op);
  state.redoStack.push(op);
  prunePage(op.page);
  scheduleSave();
  redrawAll();
}

export function redoInk() {
  const op = state.redoStack.pop();
  if (!op) { toast('没有可重做的操作'); return; }
  applyOp(op);
  state.undoStack.push(op);
  scheduleSave();
  redrawAll();
}

function applyOp(op) {
  const entry = pageAnnot(op.page);
  if (op.op === 'add') entry.strokes.push(op.stroke);
  if (op.op === 'remove') removeById(entry, op.stroke.id);
  if (op.op === 'clear') entry.strokes = [];
}

function applyInverse(op) {
  const entry = pageAnnot(op.page);
  if (op.op === 'add') removeById(entry, op.stroke.id);
  if (op.op === 'remove') entry.strokes.splice(Math.min(op.index, entry.strokes.length), 0, op.stroke);
  if (op.op === 'clear') entry.strokes = [...op.strokes];
}

function removeById(entry, id) {
  const i = entry.strokes.findIndex((s) => s.id === id);
  if (i >= 0) entry.strokes.splice(i, 1);
}

export function clearPageStrokes() {
  const entry = state.annotations.pages[String(state.page)];
  if (!entry || !entry.strokes.length) { toast('本页没有墨迹'); return; }
  state.undoStack.push({ op: 'clear', page: state.page, strokes: [...entry.strokes] });
  state.redoStack = [];
  entry.strokes = [];
  prunePage(state.page);
  scheduleSave();
  redrawAll();
}
```

- [ ] **Step 2: main.js 追加 initInk（import 区加一行、init 区加一行，全文为）**

```javascript
import { on } from './state.js';
import { initViewer } from './viewer.js';
import { initFigures } from './figures.js';
import { initInk } from './ink.js';

function switchSideTab(name) {
  document.querySelectorAll('.side-tab').forEach((b) => b.classList.toggle('active', b.dataset.side === name));
  document.querySelectorAll('.side-panel').forEach((p) => p.classList.toggle('active', p.dataset.panel === name));
}

window.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.side-tab').forEach((b) => b.addEventListener('click', () => switchSideTab(b.dataset.side)));
  on('switch-side-tab', switchSideTab);
  initViewer();
  initFigures();
  initInk();
});
```

- [ ] **Step 3: 浏览器验证墨迹（无需 VL；ribbon 工具切换 Task 12 才有，本任务用控制台设 tool 验证）**

服务运行中。验证脚本 `work\verify_t10.py`（playwright，不提交）：导入 PDF → 控制台 `await import('./js/state.js').then(m => m.state.tool='pen')` 并 `$('page-stage').dataset.mode='ink'` → 用 `pg.mouse` 在画布拖一条线 → 断言 `state.annotations.pages['1'].strokes.length===1`；等 1.5s 后断言磁盘 `annotations.json` 含该笔画；调用 `undoInk` 后 strokes 为 0；`redoInk` 后恢复；截图。

Expected: 笔画采集/防抖落盘/撤销重做全部符合预期，`js errors: []`

- [ ] **Step 4: Commit**

```powershell
git add app/reader/js
git commit -m "feat: 手写墨迹层（笔/荧光笔/橡皮/撤销重做/防抖自动保存）"
```

---

### Task 11: comments.js——文本批注（锚点 + 卡片 + 已解决）

**Files:**
- Create: `app/reader/js/comments.js`
- Modify: `app/reader/js/main.js`（追加 initComments）

- [ ] **Step 1: 创建 app/reader/js/comments.js**

```javascript
// 文本批注：画布放置锚点 / 右栏卡片编辑 / 删除 / 已解决置灰 / 双向定位（设计文档 4.3）
import { state, on, emit, uid } from './state.js';
import { pageAnnot, prunePage, scheduleSave } from './annotate.js';

const $ = (id) => document.getElementById(id);

export function initComments() {
  const catcher = document.createElement('div');
  catcher.id = 'comment-catcher';
  $('comment-layer').appendChild(catcher);
  catcher.addEventListener('click', onPlace);
  on('page-changed', renderAll);
  on('scale-changed', renderAnchors);
  on('annotations-changed', renderAll);
}

function comments() {
  const entry = state.annotations.pages[String(state.page)];
  return entry ? entry.comments : [];
}

function onPlace(e) {
  const r = $('comment-layer').getBoundingClientRect();
  const x = (e.clientX - r.left) / r.width;
  const y = (e.clientY - r.top) / r.height;
  const now = new Date().toISOString();
  const c = { id: uid('c'), x, y, text: '', resolved: false, created_at: now, updated_at: now };
  pageAnnot(state.page).comments.push(c);
  scheduleSave();
  renderAll();
  emit('switch-side-tab', 'comments');
  requestAnimationFrame(() => {
    const ta = document.querySelector(`#card-${c.id} textarea`);
    if (ta) ta.focus();
  });
}

function renderAll() { renderAnchors(); renderCards(); }

function renderAnchors() {
  const layer = $('comment-layer');
  layer.querySelectorAll('.comment-anchor').forEach((el) => el.remove());
  comments().forEach((c, i) => {
    const a = document.createElement('div');
    a.className = 'comment-anchor' + (c.resolved ? ' resolved' : '');
    a.textContent = i + 1;
    a.style.left = `${c.x * 100}%`;
    a.style.top = `${c.y * 100}%`;
    a.title = c.text || '（空批注）';
    a.addEventListener('click', (ev) => {
      ev.stopPropagation();
      emit('switch-side-tab', 'comments');
      flashCard(c.id);
    });
    layer.appendChild(a);
  });
}

function renderCards() {
  const panel = $('comments-panel');
  if (!state.paper) { panel.innerHTML = '<p class="dim">导入论文后可添加批注</p>'; return; }
  const list = comments();
  if (!list.length) {
    panel.innerHTML = '<p class="dim">本页暂无批注。在 ribbon「批注」页签选择 💬 后点击页面放置。</p>';
    return;
  }
  panel.innerHTML = '';
  list.forEach((c, i) => {
    const card = document.createElement('div');
    card.className = 'comment-card' + (c.resolved ? ' resolved' : '');
    card.id = `card-${c.id}`;
    const head = document.createElement('div');
    head.className = 'comment-head';
    head.textContent = `#${i + 1} · 第 ${state.page} 页` + (c.resolved ? ' · 已解决' : '');
    card.appendChild(head);
    if (c.resolved) {
      const snippet = document.createElement('p');
      snippet.className = 'comment-snippet';
      snippet.textContent = c.text || '（空批注）';
      card.appendChild(snippet);
    } else {
      const ta = document.createElement('textarea');
      ta.value = c.text;
      ta.placeholder = '输入批注…';
      ta.rows = 3;
      ta.addEventListener('input', () => {
        c.text = ta.value;
        c.updated_at = new Date().toISOString();
        scheduleSave();  // 不触发重渲染，避免打断输入
      });
      card.appendChild(ta);
    }
    const row = document.createElement('div');
    row.className = 'comment-actions';
    const locate = document.createElement('button');
    locate.textContent = '定位';
    locate.addEventListener('click', () => flashAnchor(c.id));
    const toggle = document.createElement('button');
    toggle.textContent = c.resolved ? '重新打开' : '标记已解决';
    toggle.addEventListener('click', () => {
      c.resolved = !c.resolved;
      c.updated_at = new Date().toISOString();
      scheduleSave();
      renderAll();
    });
    const del = document.createElement('button');
    del.textContent = '删除';
    del.className = 'danger';
    del.addEventListener('click', () => {
      const entry = pageAnnot(state.page);
      entry.comments = entry.comments.filter((x) => x.id !== c.id);
      prunePage(state.page);
      scheduleSave();
      renderAll();
    });
    row.appendChild(locate);
    row.appendChild(toggle);
    row.appendChild(del);
    card.appendChild(row);
    panel.appendChild(card);
  });
}

function flashCard(id) {
  const el = document.getElementById(`card-${id}`);
  if (!el) return;
  el.scrollIntoView({ block: 'nearest' });
  el.classList.add('flash');
  setTimeout(() => el.classList.remove('flash'), 900);
}

function flashAnchor(id) {
  const idx = comments().findIndex((c) => c.id === id);
  if (idx < 0) return;
  const el = document.querySelectorAll('.comment-anchor')[idx];
  if (!el) return;
  el.classList.add('flash');
  setTimeout(() => el.classList.remove('flash'), 900);
}
```

- [ ] **Step 2: main.js 追加 initComments（import 区与 init 区各加一行，参照 Task 10 的模式）**

- [ ] **Step 3: 浏览器验证批注（无需 VL）**

验证脚本 `work\verify_t11.py`（playwright，不提交）：导入 PDF → 控制台设 `state.tool='comment'` + `dataset.mode='comment'` → `pg.mouse.click` 页面中部 → 断言锚点出现且右栏出现卡片 → 在卡片 textarea 输入「测试批注」→ 等 1.5s → 断言磁盘 annotations.json 含该文本 → 点「标记已解决」卡片置灰、锚点变灰 → 刷新页面（重新打开 + 导入同文件）批注仍在 → `js errors: []`。

Expected: 放置/编辑/已解决/刷新恢复全部正常

- [ ] **Step 4: Commit**

```powershell
git add app/reader/js
git commit -m "feat: 文本批注（锚点/卡片编辑/已解决/双向定位/刷新恢复）"
```

---

### Task 12: ribbon.js + toolbox.js——工具切换 / 视图 / 导出 / 健康灯 / 单图工具箱

**Files:**
- Create: `app/reader/js/ribbon.js`
- Create: `app/reader/js/toolbox.js`
- Modify: `app/reader/js/main.js`（追加 initRibbon/initToolbox，为最终完整版）

- [ ] **Step 1: 创建 app/reader/js/ribbon.js**

```javascript
// ribbon：选项卡 / 批注工具 / 颜色粗细 / 撤销重做清空 / 视图缩放 / 导出 / 重新检测 / 健康灯（设计文档 4.1、8）
import { state, on, emit, toast } from './state.js';
import { getHealth, exportPaper } from './api.js';
import { setFitMode, setZoom } from './viewer.js';
import { undoInk, redoInk, clearPageStrokes } from './ink.js';
import { redetectFigures } from './figures.js';

const $ = (id) => document.getElementById(id);

export function initRibbon() {
  document.querySelectorAll('.ribbon-tab').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.ribbon-tab').forEach((b) => b.classList.toggle('active', b === btn));
      document.querySelectorAll('.ribbon-panel').forEach((p) => p.classList.toggle('active', p.dataset.panel === btn.dataset.tab));
    });
  });
  document.querySelectorAll('.tool-btn').forEach((btn) => {
    btn.addEventListener('click', () => setTool(btn.dataset.tool));
  });
  $('ink-color').addEventListener('input', (e) => { state.inkColor = e.target.value; });
  $('ink-width').addEventListener('input', (e) => { state.inkWidth = Number(e.target.value); });
  $('btn-undo').addEventListener('click', undoInk);
  $('btn-redo').addEventListener('click', redoInk);
  $('btn-clear-page').addEventListener('click', clearPageStrokes);
  $('btn-fit-width').addEventListener('click', () => { setFitMode('width'); $('zoom-select').value = ''; });
  $('btn-fit-page').addEventListener('click', () => { setFitMode('page'); $('zoom-select').value = ''; });
  $('zoom-select').addEventListener('change', (e) => setZoom(Number(e.target.value)));
  $('btn-export').addEventListener('click', onExport);
  $('btn-redetect').addEventListener('click', redetectFigures);
  $('btn-show-toolbox').addEventListener('click', () => emit('switch-side-tab', 'toolbox'));
  on('paper-loaded', () => {
    $('btn-export').disabled = false;
    $('btn-redetect').disabled = false;
    refreshHealth();  // Ollama 不健康时重新禁用「重新检测」（设计文档 8）
  });
  refreshHealth();
  setInterval(refreshHealth, 30000);
}

function setTool(tool) {
  state.tool = state.tool === tool ? 'read' : tool;  // 再点当前工具回到阅读模式
  document.querySelectorAll('.tool-btn').forEach((b) => b.classList.toggle('active', b.dataset.tool === state.tool));
  const stage = $('page-stage');
  if (['pen', 'highlighter', 'eraser'].includes(state.tool)) stage.dataset.mode = 'ink';
  else if (state.tool === 'comment') stage.dataset.mode = 'comment';
  else stage.dataset.mode = 'read';
}

async function onExport() {
  if (!state.paper) return;
  toast('导出中…');
  try {
    await exportPaper(state.paper.pdf_hash);
    toast('已导出带标注副本');
  } catch (e) {
    toast(`导出失败: ${e.message}`);
  }
}

async function refreshHealth() {
  const light = $('health-light');
  try {
    const h = await getHealth();
    const ok = h.ollama && h.model;
    light.classList.toggle('ok', ok);
    light.classList.toggle('bad', !ok);
    light.title = ok
      ? `Ollama 正常 · ${h.model_name}`
      : `Ollama 不可用或模型缺失\n请运行: ollama pull ${h.model_name}\n并确认 CHART_SDK_MODEL 环境变量`;
    $('btn-redetect').disabled = !ok || !state.paper;  // 设计文档 8：不健康禁用检测
  } catch (e) {
    light.classList.remove('ok');
    light.classList.add('bad');
    light.title = '后端不可达';
    $('btn-redetect').disabled = true;
  }
}
```

- [ ] **Step 2: 创建 app/reader/js/toolbox.js**

```javascript
// 工具箱：单图上传解析（复用四件套渲染；设计文档 4.1）
import { toast } from './state.js';
import { parseSingle } from './api.js';
import { renderChartResult } from './figures.js';

const $ = (id) => document.getElementById(id);

export function initToolbox() {
  $('btn-single-upload').addEventListener('click', () => $('single-input').click());
  $('single-input').addEventListener('change', (e) => {
    if (e.target.files[0]) doParse(e.target.files[0]);
    e.target.value = '';
  });
}

async function doParse(file) {
  const box = $('single-result');
  box.innerHTML = '<p class="dim">解析中…（约 10-20 秒）</p>';
  try {
    const r = await parseSingle(file);
    if (r.status === 'error') {
      box.innerHTML = `<p class="error-text">解析失败: ${r.error || ''}</p>`;
      return;
    }
    renderChartResult(box, { inputUrl: r.input_url, chart: r.chart, renderUrl: r.render_url, codeText: r.code });
    if (r.status === 'render_failed') toast('复刻图渲染失败，已保留数据与代码');
  } catch (e) {
    box.innerHTML = `<p class="error-text">解析失败: ${e.message}</p>`;
  }
}
```

- [ ] **Step 3: main.js 最终完整版**

```javascript
import { on } from './state.js';
import { initViewer } from './viewer.js';
import { initFigures } from './figures.js';
import { initInk } from './ink.js';
import { initComments } from './comments.js';
import { initRibbon } from './ribbon.js';
import { initToolbox } from './toolbox.js';

function switchSideTab(name) {
  document.querySelectorAll('.side-tab').forEach((b) => b.classList.toggle('active', b.dataset.side === name));
  document.querySelectorAll('.side-panel').forEach((p) => p.classList.toggle('active', p.dataset.panel === name));
}

window.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.side-tab').forEach((b) => b.addEventListener('click', () => switchSideTab(b.dataset.side)));
  on('switch-side-tab', switchSideTab);
  initViewer();
  initFigures();
  initInk();
  initComments();
  initRibbon();
  initToolbox();
});
```

- [ ] **Step 4: 浏览器整体验证（无需 VL 部分）**

验证脚本 `work\verify_t12.py`（playwright，不提交），断言：
1. 打开页面：ribbon 5 个选项卡可切换、健康灯存在（无 Ollama 时为红）
2. 导入 synthetic-demo.pdf（不勾检测）→ 页面/缩略图正常
3. ribbon 批注页签 → 点「✏️ 笔」→ 画布 mouse 拖线 → 笔画可见；点「💬 批注」→ 点页面 → 卡片出现；点「↶ 撤销」墨迹消失
4. 视图页签 → 适应宽度/适应页面/150% 各点一次，stage 尺寸变化
5. 文件页签 → 导出带标注副本 → 下载事件触发（`pg.expect_download`）
6. 右栏工具箱 → 上传一张 PNG（playwright 生成临时文件）→ 无 VL 时显示解析失败提示（预期路径）
7. `js errors: []`，截图 `work\reader-t12.png`

Expected: 全部通过

- [ ] **Step 5: Commit**

```powershell
git add app/reader/js
git commit -m "feat: ribbon 交互与工具箱（工具切换/视图/导出/健康灯/单图解析）"
```

---

### Task 13: selfcheck 扩展（API 冒烟）+ README 更新

**Files:**
- Modify: `scripts/selfcheck.py`
- Modify: `README.md`（全文替换）

- [ ] **Step 1: selfcheck.py 修改**

1. 顶部 import 区加 `import os`（若无）。
2. `c_deps` 的 mods 列表替换为：

```python
    mods = ["gradio", "fitz", "matplotlib", "PIL", "openai", "numpy", "pandas", "pytest",
            "fastapi", "uvicorn", "multipart", "httpx"]
```

3. 在 `c_vl_smoke` 之后追加：

```python
def c_api_smoke():
    import subprocess
    import time
    import urllib.request
    port = 8123
    env = dict(os.environ, CHART_SDK_CACHE_DIR=str(Path(tempfile.gettempdir()) / "selfcheck-api-cache"))
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.server:app", "--port", str(port)],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=2) as r:
                    import json as _json
                    data = _json.loads(r.read())
                assert "ollama" in data and "model_name" in data
                return f"health 200, model={data['model_name']}"
            except Exception:  # noqa: BLE001 - 服务尚未就绪
                time.sleep(0.5)
        raise RuntimeError("server 未在 30s 内就绪")
    finally:
        proc.terminate()
        try:
            proc.wait(5)
        except Exception:  # noqa: BLE001
            proc.kill()
```

4. `main()` 中 `check("页面渲染", c_render_pages)` 之后加一行：`check("API 冒烟", c_api_smoke)`。

- [ ] **Step 2: 运行 selfcheck 确认**

Run: `$py scripts\selfcheck.py`
Expected: 7 项 PASS（含 API 冒烟；Ollama 可达时 8 项）

- [ ] **Step 3: README.md 全文替换**

````markdown
# 论文阅读器（Paper Reader）

完全本地运行的论文阅读与图表复刻系统：导入论文 PDF → 阅读中圈画批注 → 点击图表框按需提取折线/柱状/热力图数据 → 展示数据表、Matplotlib 复刻图与可复制代码。模型经 Ollama 本地量化推理，PDF 与图片不上传公网。

## 快速开始

1. 安装 Python ≥3.10，`python -m venv .venv` 后安装依赖：
   `.venv\Scripts\python.exe -m pip install -r requirements.txt`
2. 安装并启动 [Ollama](https://ollama.com)，拉取模型：`ollama pull qwen2.5vl:3b`（或 7b，并相应设置 `CHART_SDK_MODEL`）
3. 生成样例论文（可选）：`.venv\Scripts\python.exe scripts\make_synthetic_sample.py`；联网时 `.venv\Scripts\python.exe scripts\download_samples.py` 下载 arXiv 真实论文
4. 自检：`.venv\Scripts\python.exe scripts\selfcheck.py`
5. 启动阅读器：
   `$env:CHART_SDK_MODEL="qwen2.5vl:3b" ; .venv\Scripts\python.exe -m uvicorn app.server:app --port 8000`
   浏览器打开 http://127.0.0.1:8000

## 使用（阅读器）

- **导入**：ribbon「文件」→「导入论文」（或拖拽 PDF 到窗口）；「检测图表并标记」默认勾选——页面秒开，检测后台执行，图框陆续浮现；不勾则纯阅读，可随时在「图表」页签点「重新检测」
- **阅读**：左栏缩略图 / 翻页按钮 / 键盘 ←→；「视图」页签适应宽度/适应页面/50–200% 缩放
- **批注**：「批注」页签选手写笔/荧光笔圈画，橡皮点选删除整条笔画，支持撤销/重做/清空本页；选 💬 后点击页面放置文本批注，右栏卡片编辑、删除、标记已解决；标注 1 秒防抖自动保存，重开同一论文自动恢复
- **图表解析**：点击页面中的图框（虚线=未解析）→ 右栏「图表」页签展示原图/数据表/复刻图/代码（一键复制）；绿色实线=已解析（点击秒开），红框=失败（可重试）
- **导出**：「文件」→「导出带标注副本」下载 `annotated-<原名>.pdf`（墨迹叠加为图像层，批注为 PDF 标准便签；原文件不受影响）
- **工具箱**：右栏「工具箱」页签上传单张图表图片，同样四件套输出
- 所有产物缓存于 `data/cache/`（删除即清空）；ribbon 右上角健康灯指示 Ollama 状态

## 手动验收清单（前端）

- [ ] 导入（勾检测）：页面秒开，图框陆续浮现，检测状态实时更新
- [ ] 导入（不勾）：纯阅读；「重新检测」后图框出现
- [ ] 翻页/缩略图/键盘/缩放/适应宽度/适应页面均正常
- [ ] 墨迹：笔/荧光笔/颜色/粗细/橡皮点删/撤销/重做/清空本页
- [ ] 批注：放置→编辑→删除；已解决置灰；锚点↔卡片互定位
- [ ] 自动保存：操作后刷新页面标注仍在
- [ ] 点击图框 → 四件套；失败显示错误+重试；已解析重点击秒开
- [ ] 导出副本在 PDF 查看器中可见墨迹与便签
- [ ] 工具箱单图解析四件套
- [ ] 停掉 Ollama：健康灯变红，检测/解析报错有提示

## 旧版 Gradio 前端（legacy）

`app/gradio_app.py` 为初版双模式前端（上传即全量预解析），保留可用但不再维护：
`.venv\Scripts\python.exe app\gradio_app.py` → http://127.0.0.1:7860

## 配置（环境变量）

| 变量 | 默认 | 说明 |
|---|---|---|
| `CHART_SDK_BASE_URL` | `http://localhost:11434/v1` | Ollama OpenAI 兼容端点 |
| `CHART_SDK_MODEL` | `qwen2.5vl:7b` | 模型名 |
| `CHART_SDK_DPI` | `150` | 页面渲染 DPI |
| `CHART_SDK_MAX_PAGES` | `30` | 最大处理页数 |
| `CHART_SDK_EXEC_TIMEOUT` | `30` | 代码执行超时（秒） |
| `CHART_SDK_VL_TIMEOUT` | `120` | VL 调用超时（秒） |
| `CHART_SDK_CACHE_DIR` | `data/cache` | 缓存根目录 |
| `CHART_SDK_API_PORT` | `8000` | 阅读器服务端口（`python -m app.server` 直启时生效） |

## 目录

```
app/server.py         FastAPI 后端（阅读器 API + 静态托管）
app/reader/           阅读器前端（原生 HTML/CSS/JS，无构建）
app/gradio_app.py     旧版 Gradio 前端（legacy）
chart_sdk/            SDK（inference/pdf/vision/codegen/cache/pipeline/annotate）
scripts/              样例生成/下载与自检
assets/samples/       测试论文样例
tests/                单元+集成测试（pytest tests -v）
docs/superpowers/     设计文档与实施计划
STATUS.md / PLAN.md   验收记录与计划
```

## 开发

设计文档：`docs/superpowers/specs/2026-10-19-paper-reader-design.md`（阅读器）与 `2026-10-19-paper-chart-replication-design.md`（初版）；实施计划：`docs/superpowers/plans/`。运行测试：`.venv\Scripts\python.exe -m pytest tests\unit -v`（API 集成测试离线可跑；VL 集成测试在 Ollama 不可用时自动跳过）。
````

- [ ] **Step 4: 全量测试回归**

Run: `$py -m pytest tests\unit -v ; $py -m pytest tests\integration\test_api.py -v`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```powershell
git add scripts/selfcheck.py README.md
git commit -m "docs: selfcheck API 冒烟项与 README 阅读器手册（含 legacy 说明）"
```

---

## 附：执行分组建议（subagent-driven-development）

- 组 A（基础）：Task 0 + 1 —— 依赖/config + PaperStore.open
- 组 B（SDK）：Task 2 + 3 —— pipeline 拆分 + AnnotationStore
- 组 C（后端）：Task 4 + 5 + 6 —— 导出 + server + API 测试
- 组 D（前端骨架）：Task 7 + 8 —— 布局 + 导入阅读
- 组 E（前端图表）：Task 9
- 组 F（前端标注）：Task 10 + 11
- 组 G（前端收尾+文档）：Task 12 + 13



