# 论文图表复刻系统（MVP）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 从零搭建本地运行的论文图表复刻系统：PDF 导入 → 图表检测裁剪 → VL 结构化解析 → matplotlib 代码生成渲染 → Gradio 图文联动 UI。

**Architecture:** 分层 Python 包 `chart_sdk`（inference / pdf / vision / codegen / cache / pipeline）+ `app/gradio_app.py` 前端。图表检测以整页渲染 + VL grounding 为主，嵌入位图提取为降级。全部产物内容寻址缓存于 `data/cache/`。设计文档：`docs/superpowers/specs/2026-10-19-paper-chart-replication-design.md`。

**Tech Stack:** Python ≥3.10、gradio、pymupdf、matplotlib、pillow、openai（客户端连 Ollama）、numpy、pandas、pytest。

**约定：**
- 下文 `$py` 指代 `.venv\Scripts\python.exe`（Task 0 创建）。所有 pytest/git 命令在 `d:\aicomp` 下运行（PowerShell）。
- 接口契约（各任务必须一致）：`FigureBBox(id, page, bbox_norm, bbox_px, type, source, caption_hint)`；`validate_chart(data)->(dict, list[str])` 抛 `ValidationError`；`parse_chart(client, image_bytes, mime)->dict` 抛 `ParseError`；`generate_code(chart, out_png)->str`；`execute_code(code, timeout)->None` 抛 `CodeExecError`；`detect_page(page_png, page, page_no)->list[FigureBBox]`；`PaperPipeline(config, client, detector=None, fallback=None).run(pdf_path, progress=None)->dict`；`run_single(config, client, image_path)->dict`；进度回调签名 `cb(stage, done, total, msg)`。

---

### Task 0: 环境与项目骨架

**Files:**
- Create: `requirements.txt`, `.gitignore`, `chart_sdk/__init__.py`, `chart_sdk/config.py`, `chart_sdk/{inference,pdf,vision,codegen,cache,pipeline}/__init__.py`, `tests/unit/__init__.py`, `tests/integration/__init__.py`, `tests/unit/test_config.py`

- [ ] **Step 1: 创建 requirements.txt**

```
gradio>=4.44
pymupdf>=1.24
matplotlib>=3.8
pillow>=10.0
openai>=1.40
numpy>=1.26
pandas>=2.0
pytest>=8.0
```

- [ ] **Step 2: 创建 .gitignore**

```
.venv/
__pycache__/
*.pyc
data/cache/
.pytest_cache/
work/
```

- [ ] **Step 3: 创建包骨架**

`chart_sdk/__init__.py`：

```python
__version__ = "0.1.0"
```

六个子包 `__init__.py` 与 `tests/unit/__init__.py`、`tests/integration/__init__.py` 均为空文件。

- [ ] **Step 4: 写失败测试 tests/unit/test_config.py**

```python
import os
from chart_sdk.config import Config


def test_defaults():
    c = Config.from_env()
    assert c.base_url == "http://localhost:11434/v1"
    assert c.model == "qwen2.5vl:7b"
    assert c.dpi == 150
    assert c.max_pages == 30
    assert c.exec_timeout == 30.0
    assert c.vl_timeout == 120.0


def test_env_override(monkeypatch):
    monkeypatch.setenv("CHART_SDK_MODEL", "qwen2.5vl:3b")
    monkeypatch.setenv("CHART_SDK_DPI", "200")
    c = Config.from_env()
    assert c.model == "qwen2.5vl:3b"
    assert c.dpi == 200
```

- [ ] **Step 5: 运行测试确认失败**

Run: `.venv` 尚未创建，先执行下方 Step 6 建环境后再补跑本步——顺序调整：先 Step 6 建环境，再回来运行
Run: `$py -m pytest tests/unit/test_config.py -v`
Expected: FAIL（ModuleNotFoundError: chart_sdk.config）

- [ ] **Step 6: 创建虚拟环境并安装依赖**

Run: `python -m venv .venv ; .venv\Scripts\python.exe -m pip install -r requirements.txt`
Expected: 安装成功无 ERROR

- [ ] **Step 7: 实现 chart_sdk/config.py**

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
        )
```

- [ ] **Step 8: 运行测试确认通过**

Run: `$py -m pytest tests/unit/test_config.py -v`
Expected: 2 passed

- [ ] **Step 9: Commit**

```powershell
git add requirements.txt .gitignore chart_sdk tests
git commit -m "feat: 项目骨架与配置模块"
```

---

### Task 1: 几何工具（坐标换算 / IoU / 去重）

**Files:**
- Create: `chart_sdk/pdf/geom.py`
- Test: `tests/unit/test_geom.py`

- [ ] **Step 1: 写失败测试 tests/unit/test_geom.py**

```python
from chart_sdk.pdf.geom import clamp_bbox, dedup_bboxes, iou, norm_to_px, px_to_norm
from chart_sdk.pdf.detector import FigureBBox


def test_norm_to_px_spec_example():
    # 设计文档 5.1 示例：A4 150DPI 页面 1240x1754
    assert norm_to_px([120, 300, 880, 720], 1240, 1754) == [149, 526, 1091, 1263]


def test_px_to_norm_roundtrip():
    px = norm_to_px([120, 300, 880, 720], 1240, 1754)
    n = px_to_norm(px, 1240, 1754)
    assert all(abs(a - b) <= 1 for a, b in zip(n, [120, 300, 880, 720]))


def test_clamp_bbox_keeps_valid():
    assert clamp_bbox([10, 10, 200, 200], 1240, 1754) == [10, 10, 200, 200]


def test_clamp_bbox_drops_tiny():
    assert clamp_bbox([10, 10, 30, 30], 1240, 1754) is None


def test_clamp_bbox_pulls_into_page():
    assert clamp_bbox([-50, -50, 200, 200], 1240, 1754) == [0, 0, 200, 200]


def test_iou_identical_and_disjoint():
    assert iou([0, 0, 10, 10], [0, 0, 10, 10]) == 1.0
    assert iou([0, 0, 10, 10], [20, 20, 30, 30]) == 0.0


def _bbox(i, box):
    return FigureBBox(id=f"f{i}", page=1, bbox_norm=[0, 0, 1, 1], bbox_px=box, type="line", source="vl_grounding", caption_hint=None)


def test_dedup_merges_overlap():
    items = [_bbox(0, [0, 0, 100, 100]), _bbox(1, [5, 5, 95, 95]), _bbox(2, [200, 200, 300, 300])]
    out = dedup_bboxes(items, thr=0.7)
    assert len(out) == 2
    assert out[0].id == "f0"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `$py -m pytest tests/unit/test_geom.py -v`
Expected: FAIL（ModuleNotFoundError: chart_sdk.pdf.geom）

- [ ] **Step 3: 实现 chart_sdk/pdf/geom.py**

```python
from __future__ import annotations

MIN_SIDE_PX = 40


def norm_to_px(bbox: list, page_w: int, page_h: int) -> list[int]:
    """0-1000 归一化坐标 → 像素坐标（设计文档 5.1 换算规则）。"""
    return [int(round(v / 1000 * d)) for v, d in zip(bbox, (page_w, page_h, page_w, page_h))]


def px_to_norm(bbox: list, page_w: int, page_h: int) -> list[int]:
    out = [int(round(v / d * 1000)) for v, d in zip(bbox, (page_w, page_h, page_w, page_h))]
    return [min(1000, max(0, v)) for v in out]


def clamp_bbox(bbox_px: list, page_w: int, page_h: int, min_side: int = MIN_SIDE_PX) -> list[int] | None:
    """钳制到页面范围；短边小于 min_side 视为退化返回 None。"""
    x0, y0, x1, y1 = (int(round(v)) for v in bbox_px)
    x0 = max(0, min(x0, page_w - 1))
    y0 = max(0, min(y0, page_h - 1))
    x1 = max(x0 + 1, min(x1, page_w))
    y1 = max(y0 + 1, min(y1, page_h))
    if (x1 - x0) < min_side or (y1 - y0) < min_side:
        return None
    return [x0, y0, x1, y1]


def iou(a: list, b: list) -> float:
    ix0, iy0 = max(a[0], b[0]), max(a[1], b[1])
    ix1, iy1 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, ix1 - ix0) * max(0, iy1 - iy0)
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def dedup_bboxes(items: list, thr: float = 0.7) -> list:
    """按顺序保留，与已保留项 IoU>thr 的丢弃（items 需有 bbox_px 属性）。"""
    kept: list = []
    for it in items:
        if all(iou(it.bbox_px, k.bbox_px) <= thr for k in kept):
            kept.append(it)
    return kept
```

- [ ] **Step 4: 运行测试确认通过**

Run: `$py -m pytest tests/unit/test_geom.py -v`
Expected: 7 passed（注意 test_geom 引用了 detector.FigureBBox，需先在 Step 5 中放置最小定义或直接跳过本步顺序：先做 Task 9 的 dataclass？——处理方式：在 `chart_sdk/pdf/detector.py` 先放置 Task 9 Step 3 中定义的 `FigureBBox` dataclass 骨架（仅 dataclass，不含检测器类），使本任务可运行。）

- [ ] **Step 5: 先放置 FigureBBox（属于 Task 9 的一部分，提前引入避免循环）**

`chart_sdk/pdf/detector.py`（本步仅含 dataclass）：

```python
from dataclasses import dataclass, field


@dataclass
class FigureBBox:
    id: str
    page: int
    bbox_norm: list
    bbox_px: list
    type: str  # line | bar | heatmap
    source: str  # vl_grounding | bitmap_fallback
    caption_hint: str | None
```

- [ ] **Step 6: 重跑测试**

Run: `$py -m pytest tests/unit/test_geom.py tests/unit/test_config.py -v`
Expected: 9 passed

- [ ] **Step 7: Commit**

```powershell
git add chart_sdk/pdf/geom.py chart_sdk/pdf/detector.py tests/unit/test_geom.py
git commit -m "feat: 几何工具与 FigureBBox 数据类"
```

---

### Task 2: 推理客户端（Ollama OpenAI 兼容）

**Files:**
- Create: `chart_sdk/inference/client.py`
- Test: `tests/unit/test_client.py`

- [ ] **Step 1: 写失败测试 tests/unit/test_client.py**

```python
import base64
from unittest.mock import MagicMock

from chart_sdk.config import Config
from chart_sdk.inference.client import VLClient


def _client():
    cfg = Config.from_env()
    return VLClient(cfg)


def test_chat_image_builds_data_url(monkeypatch):
    c = _client()
    fake_openai = MagicMock()
    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        msg = MagicMock()
        msg.choices = [MagicMock()]
        msg.choices[0].message.content = "hello"
        resp = MagicMock()
        resp.__getitem__ = lambda self, i: msg.choices[i] if False else None
        wrapper = MagicMock()
        wrapper.choices = msg.choices
        wrapper.message = msg.choices[0].message
        fake_openai.chat.completions.create = fake_create
        return wrapper

    fake_openai.chat.completions.create = fake_create
    monkeypatch.setattr(c, "_client", fake_openai)
    out = c.chat_image("p", b"img")
    assert out == "hello"
    parts = captured["messages"][0]["content"]
    assert parts[0] == {"type": "text", "text": "p"}
    b64 = base64.b64encode(b"img").decode()
    assert parts[1]["image_url"]["url"] == f"data:image/png;base64,{b64}"


def test_health_true_and_false(monkeypatch):
    c = _client()
    ok = MagicMock()
    ok.models.list.return_value = []
    bad = MagicMock()
    bad.models.list.side_effect = RuntimeError("down")
    monkeypatch.setattr(c, "_client", ok)
    assert c.health() is True
    monkeypatch.setattr(c, "_client", bad)
    assert c.health() is False


def test_chat_image_retries_then_succeeds(monkeypatch):
    c = _client()
    fake = MagicMock()
    calls = {"n": 0}

    def flaky(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transient")
        msg = MagicMock()
        msg.choices = [MagicMock()]
        msg.choices[0].message.content = "ok"
        return msg

    fake.chat.completions.create = flaky
    monkeypatch.setattr(c, "_client", fake)
    assert c.chat_image("p", b"img") == "ok"
    assert calls["n"] == 2
```

- [ ] **Step 2: 运行测试确认失败**

Run: `$py -m pytest tests/unit/test_client.py -v`
Expected: FAIL（ModuleNotFoundError: chart_sdk.inference.client）

- [ ] **Step 3: 实现 chart_sdk/inference/client.py**

```python
from __future__ import annotations

import base64

from openai import OpenAI

from chart_sdk.config import Config


class VLClient:
    """Ollama OpenAI 兼容端点客户端（/v1）。"""

    def __init__(self, config: Config):
        self.config = config
        self._client = OpenAI(base_url=config.base_url, api_key="ollama", timeout=config.vl_timeout)

    def health(self) -> bool:
        try:
            self._client.models.list()
            return True
        except Exception:
            return False

    def model_available(self) -> bool:
        try:
            return any(m.id == self.config.model for m in self._client.models.list())
        except Exception:
            return False

    def chat_image(self, prompt: str, image_bytes: bytes, mime: str = "image/png", max_tokens: int = 2048, temperature: float = 0.1) -> str:
        b64 = base64.b64encode(image_bytes).decode()
        message = {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
            ],
        }
        last_err: Exception | None = None
        for _ in range(self.config.retry + 1):
            try:
                resp = self._client.chat.completions.create(
                    model=self.config.model, messages=[message], max_tokens=max_tokens, temperature=temperature
                )
                return resp.choices[0].message.content or ""
            except Exception as e:  # noqa: BLE001 - 统一重试
                last_err = e
        raise RuntimeError(f"VL 调用失败: {last_err}")
```

- [ ] **Step 4: 运行测试确认通过**

Run: `$py -m pytest tests/unit/test_client.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```powershell
git add chart_sdk/inference tests/unit/test_client.py
git commit -m "feat: Ollama OpenAI 兼容推理客户端"
```

---

### Task 3: JSON 提取工具

**Files:**
- Create: `chart_sdk/vision/json_utils.py`
- Test: `tests/unit/test_json_utils.py`

- [ ] **Step 1: 写失败测试 tests/unit/test_json_utils.py**

```python
from chart_sdk.vision.json_utils import extract_json


def test_plain_json():
    assert extract_json('{"a": 1}') == {"a": 1}
    assert extract_json('[1, 2]') == [1, 2]


def test_markdown_fences():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_prose_wrapped():
    assert extract_json('结果如下：{"bbox_2d": [1,2,3,4]} 以上。') == {"bbox_2d": [1, 2, 3, 4]}


def test_no_json_returns_none():
    assert extract_json("没有内容") is None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `$py -m pytest tests/unit/test_json_utils.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现 chart_sdk/vision/json_utils.py**

```python
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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `$py -m pytest tests/unit/test_json_utils.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```powershell
git add chart_sdk/vision tests/unit/test_json_utils.py
git commit -m "feat: 模型输出 JSON 提取工具"
```

---

### Task 4: 页面渲染与裁剪

**Files:**
- Create: `chart_sdk/pdf/render.py`
- Test: `tests/unit/test_render.py`

- [ ] **Step 1: 写失败测试 tests/unit/test_render.py**

```python
from pathlib import Path

import fitz
from PIL import Image

from chart_sdk.pdf.render import crop_page_region, render_pages


def _make_pdf(path: Path, with_image: bool = False):
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 72), "Test page")
    if with_image:
        png = path.parent / "tmp.png"
        Image.new("RGB", (300, 200), (200, 60, 60)).save(png)
        page.insert_image(fitz.Rect(72, 100, 400, 350), filename=str(png))
        png.unlink()
    doc.save(str(path))
    doc.close()


def test_render_pages(tmp_path):
    pdf = tmp_path / "a.pdf"
    _make_pdf(pdf)
    out = tmp_path / "pages"
    pages = render_pages(pdf, out, dpi=72, max_pages=30)
    assert len(pages) == 1
    assert pages[0]["page"] == 1
    assert pages[0]["png_path"] == "pages/page-01.png"
    assert (out / "page-01.png").exists()
    assert pages[0]["width"] == 595


def test_render_pages_max_pages(tmp_path):
    pdf = tmp_path / "b.pdf"
    doc = fitz.open()
    for _ in range(5):
        doc.new_page()
    doc.save(str(pdf))
    doc.close()
    pages = render_pages(pdf, tmp_path / "p2", dpi=72, max_pages=3)
    assert len(pages) == 3


def test_crop_page_region(tmp_path):
    pdf = tmp_path / "c.pdf"
    _make_pdf(pdf, with_image=True)
    out = tmp_path / "pages"
    pages = render_pages(pdf, out, dpi=72, max_pages=1)
    crop = tmp_path / "crop.png"
    crop_page_region(out / "page-01.png", [72, 100, 400, 350], crop)
    assert crop.exists()
    with Image.open(crop) as im:
        assert im.size == (328, 250)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `$py -m pytest tests/unit/test_render.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现 chart_sdk/pdf/render.py**

```python
from __future__ import annotations

from pathlib import Path

import fitz
from PIL import Image

from chart_sdk.pdf.geom import clamp_bbox


def render_pages(pdf_path: Path, out_dir: Path, dpi: int = 150, max_pages: int = 30) -> list[dict]:
    """逐页渲染 PNG；返回 [{page, png_path(相对 out_dir 父目录), width, height}]。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    pages = []
    with fitz.open(pdf_path) as doc:
        for i in range(min(len(doc), max_pages)):
            pix = doc[i].get_pixmap(dpi=dpi)
            name = f"page-{i + 1:02d}.png"
            pix.save(out_dir / name)
            pages.append({"page": i + 1, "png_path": f"pages/{name}", "width": pix.width, "height": pix.height})
    return pages


def crop_page_region(page_png: Path, bbox_px: list, out_path: Path) -> None:
    """按像素 bbox 裁剪页面 PNG（越界自动钳制）。"""
    with Image.open(page_png) as im:
        w, h = im.size
        box = clamp_bbox(bbox_px, w, h, min_side=1)
        if box is None:
            raise ValueError(f"bbox 退化: {bbox_px}")
        im.crop(tuple(box)).save(out_path)
```

注意：`test_crop_page_region` 断言裁剪尺寸 (328, 250) 依赖 `clamp_bbox` 的 min_side=1 传参，与 geom 的默认 40 不冲突。

- [ ] **Step 4: 运行测试确认通过**

Run: `$py -m pytest tests/unit/test_render.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```powershell
git add chart_sdk/pdf/render.py tests/unit/test_render.py
git commit -m "feat: PDF 页面渲染与区域裁剪"
```

---

### Task 5: Prompt 常量与 JSON 校验器

**Files:**
- Create: `chart_sdk/vision/prompts.py`, `chart_sdk/vision/validator.py`
- Test: `tests/unit/test_validator.py`

- [ ] **Step 1: 写失败测试 tests/unit/test_validator.py**

```python
import pytest

from chart_sdk.vision.validator import ValidationError, validate_chart


def _line_chart():
    return {
        "chart_type": "line",
        "title": "t",
        "x_axis": {"label": "Epoch", "unit": None},
        "y_axis": {"label": "Acc", "unit": "%"},
        "legend": ["a", "b"],
        "series": [
            {"name": "a", "x": [1, 2, 3], "y": [71.2, 74.8, 76.1]},
            {"name": "b", "x": [1, 2, 3], "y": [73.0, 77.5, 80.3]},
        ],
        "heatmap": None,
    }


def test_valid_line_chart():
    out, warns = validate_chart(_line_chart())
    assert out["chart_type"] == "line"
    assert len(out["series"]) == 2
    assert warns == []


def test_invalid_chart_type():
    with pytest.raises(ValidationError):
        validate_chart({"chart_type": "pie", "series": []})


def test_empty_series_raises():
    d = _line_chart()
    d["series"] = []
    with pytest.raises(ValidationError):
        validate_chart(d)


def test_length_mismatch_raises():
    d = _line_chart()
    d["series"][0]["y"] = [1.0, 2.0]
    with pytest.raises(ValidationError):
        validate_chart(d)


def test_nonfinite_dropped_with_warning():
    d = _line_chart()
    d["series"][0]["y"] = [71.2, "NaN", 76.1]
    d["series"][0]["x"] = [1, 2, 3]
    out, warns = validate_chart(d)
    assert out["series"][0]["y"] == [71.2, 76.1]
    assert warns and "丢弃" in warns[0]


def test_all_points_invalid_raises():
    d = _line_chart()
    d["series"][0]["y"] = ["x", "y", "z"]
    d["series"][0]["x"] = [1, 2, 3]
    with pytest.raises(ValidationError):
        validate_chart(d)


def test_valid_heatmap():
    d = {
        "chart_type": "heatmap",
        "title": "h",
        "x_axis": {"label": None, "unit": None},
        "y_axis": {"label": None, "unit": None},
        "legend": [],
        "series": [],
        "heatmap": {"x_labels": ["a", "b"], "y_labels": ["u", "v"], "matrix": [[1, 2], [3, 4]], "colormap_hint": "viridis"},
    }
    out, warns = validate_chart(d)
    assert out["heatmap"]["matrix"] == [[1, 2], [3, 4]]


def test_heatmap_ragged_raises():
    d = {
        "chart_type": "heatmap",
        "title": "",
        "x_axis": {"label": None, "unit": None},
        "y_axis": {"label": None, "unit": None},
        "legend": [],
        "series": [],
        "heatmap": {"x_labels": [], "y_labels": [], "matrix": [[1, 2], [3]], "colormap_hint": None},
    }
    with pytest.raises(ValidationError):
        validate_chart(d)


def test_heatmap_nonfinite_replaced():
    d = {
        "chart_type": "heatmap",
        "title": "",
        "x_axis": {"label": None, "unit": None},
        "y_axis": {"label": None, "unit": None},
        "legend": [],
        "series": [],
        "heatmap": {"x_labels": [], "y_labels": [], "matrix": [[1, "NaN"], [3, 4]], "colormap_hint": None},
    }
    out, warns = validate_chart(d)
    assert out["heatmap"]["matrix"] == [[1, 0.0], [3, 4]]
    assert warns
```

- [ ] **Step 2: 运行测试确认失败**

Run: `$py -m pytest tests/unit/test_validator.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现 chart_sdk/vision/prompts.py**

```python
DETECT_PROMPT = """You are a figure detector for academic paper pages.
Find all data charts in the page image: line charts, bar charts, heatmaps.
Do NOT include: photos, diagrams, flowcharts, pie charts, logos, tables, equations.
For each chart output one object:
{"bbox_2d": [x0, y0, x1, y1], "type": "line" | "bar" | "heatmap", "caption": "figure caption text or empty"}
bbox_2d are integers in 0-1000 normalized coordinates of the whole page, order [left, top, right, bottom].
Output ONLY a JSON array. If none found output [].
"""

CLASSIFY_PROMPT = """Classify this image cropped from a paper page.
Answer ONLY a JSON object: {"type": "line" | "bar" | "heatmap" | "other"}
Use "other" for photos, diagrams, flowcharts, pie charts, logos, equations, tables, screenshots.
"""

PARSE_PROMPT = """You are a chart data extraction expert. Extract the data from this chart image.
Output ONLY a JSON object with exactly these keys:
{"chart_type": "line"|"bar"|"heatmap",
 "title": string,
 "x_axis": {"label": string|null, "unit": string|null},
 "y_axis": {"label": string|null, "unit": string|null},
 "legend": [string],
 "series": [{"name": string, "x": [numbers or strings], "y": [numbers]}],
 "heatmap": {"x_labels": [string], "y_labels": [string], "matrix": [[number]], "colormap_hint": string|null} | null,
 "warnings": []}
Rules:
- For line and bar charts: fill "series", set "heatmap" to null. Use numbers for x when the axis is numeric, otherwise category label strings. All y must be numbers.
- For heatmaps: fill "heatmap", set "series" to [].
- Estimate values from pixel positions as accurately as possible.
- All numbers must be finite (no NaN, Infinity, or expressions).
- No markdown, no comments, JSON only.
"""
```

- [ ] **Step 4: 实现 chart_sdk/vision/validator.py**

```python
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
```

- [ ] **Step 5: 运行测试确认通过**

Run: `$py -m pytest tests/unit/test_validator.py -v`
Expected: 9 passed

- [ ] **Step 6: Commit**

```powershell
git add chart_sdk/vision tests/unit/test_validator.py
git commit -m "feat: VL prompt 常量与 chart JSON 校验器"
```

---

### Task 6: 单图解析器（带重试）

**Files:**
- Create: `chart_sdk/vision/parser.py`
- Test: `tests/unit/test_parser.py`

- [ ] **Step 1: 写失败测试 tests/unit/test_parser.py**

```python
import json

import pytest

from chart_sdk.vision.parser import ParseError, parse_chart

VALID = json.dumps({
    "chart_type": "line", "title": "t",
    "x_axis": {"label": "x", "unit": None}, "y_axis": {"label": "y", "unit": None},
    "legend": ["a"], "series": [{"name": "a", "x": [1, 2], "y": [1.0, 2.0]}],
    "heatmap": None, "warnings": [],
})


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0
        self.prompts = []

    def chat_image(self, prompt, image_bytes, **kw):
        self.calls += 1
        self.prompts.append(prompt)
        return self.responses[min(self.calls - 1, len(self.responses) - 1)]


def test_parse_valid_json():
    c = FakeClient([VALID])
    chart = parse_chart(c, b"img")
    assert chart["chart_type"] == "line"
    assert c.calls == 1


def test_parse_strips_fences():
    c = FakeClient([f"```json\n{VALID}\n```"])
    assert parse_chart(c, b"img")["chart_type"] == "line"


def test_retry_then_success():
    c = FakeClient(["垃圾输出", VALID])
    assert parse_chart(c, b"img")["chart_type"] == "line"
    assert c.calls == 2


def test_both_fail_raises():
    c = FakeClient(["垃圾", "还是垃圾"])
    with pytest.raises(ParseError):
        parse_chart(c, b"img")
    assert c.calls == 2


def test_validation_failure_retries():
    bad = json.dumps({"chart_type": "pie"})
    c = FakeClient([bad, VALID])
    assert parse_chart(c, b"img")["chart_type"] == "line"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `$py -m pytest tests/unit/test_parser.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现 chart_sdk/vision/parser.py**

```python
from __future__ import annotations

from chart_sdk.config import Config
from chart_sdk.inference.client import VLClient
from chart_sdk.vision.json_utils import extract_json
from chart_sdk.vision.prompts import PARSE_PROMPT
from chart_sdk.vision.validator import ValidationError, validate_chart


class ParseError(Exception):
    pass


def parse_chart(client: VLClient, image_bytes: bytes, mime: str = "image/png", config: Config | None = None) -> dict:
    """调 VL 解析单张图表图 → 校验；失败重试 1 次（设计文档 7）。"""
    retry = config.retry if config else 1
    last: Exception | None = None
    for attempt in range(retry + 1):
        resp = client.chat_image(PARSE_PROMPT, image_bytes, mime=mime)
        data = extract_json(resp)
        if data is None:
            last = ParseError("模型输出中没有 JSON")
            continue
        try:
            chart, _ = validate_chart(data)
            return chart
        except ValidationError as e:
            last = e
    raise ParseError(f"解析失败（含重试）: {last}")
```

- [ ] **Step 4: 运行测试确认通过**

Run: `$py -m pytest tests/unit/test_parser.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```powershell
git add chart_sdk/vision/parser.py tests/unit/test_parser.py
git commit -m "feat: 单图结构化解析器（重试1次）"
```

---

### Task 7: 代码生成器（模板匹配）

**Files:**
- Create: `chart_sdk/codegen/generator.py`
- Test: `tests/unit/test_generator.py`

- [ ] **Step 1: 写失败测试 tests/unit/test_generator.py**

```python
from chart_sdk.codegen.generator import generate_code


def _chart(ct, **kw):
    base = {
        "chart_type": ct, "title": kw.get("title", "T"),
        "x_axis": {"label": "X", "unit": None}, "y_axis": {"label": "Y", "unit": None},
        "legend": [], "series": [], "heatmap": None, "warnings": [],
    }
    base.update(kw)
    return base


def test_line_code_contains_data_and_savefig(tmp_path):
    chart = _chart("line", legend=["a"], series=[{"name": "a", "x": [1, 2], "y": [71.2, 74.8]}])
    code = generate_code(chart, tmp_path / "r.png")
    assert "ax.plot" in code
    assert "71.2" in code
    assert str(tmp_path / "r.png") in code
    assert 'matplotlib.use("Agg")' in code


def test_bar_code(tmp_path):
    chart = _chart("bar", legend=["a", "b"], series=[
        {"name": "a", "x": ["x1", "x2"], "y": [1.0, 2.0]},
        {"name": "b", "x": ["x1", "x2"], "y": [2.0, 3.0]},
    ])
    code = generate_code(chart, tmp_path / "r.png")
    assert "ax.bar" in code
    assert "set_xticklabels" in code


def test_heatmap_code(tmp_path):
    chart = _chart("heatmap", heatmap={"x_labels": ["a", "b"], "y_labels": ["u"], "matrix": [[1.0, 2.0]], "colormap_hint": None})
    code = generate_code(chart, tmp_path / "r.png")
    assert "imshow" in code
    assert "colorbar" in code


def test_unknown_type_raises(tmp_path):
    import pytest
    from chart_sdk.codegen.generator import CodeGenError
    with pytest.raises(CodeGenError):
        generate_code(_chart("pie"), tmp_path / "r.png")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `$py -m pytest tests/unit/test_generator.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现 chart_sdk/codegen/generator.py**

```python
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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `$py -m pytest tests/unit/test_generator.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```powershell
git add chart_sdk/codegen tests/unit/test_generator.py
git commit -m "feat: line/bar/heatmap matplotlib 代码生成器"
```

---

### Task 8: 代码执行器（子进程渲染）

**Files:**
- Create: `chart_sdk/codegen/executor.py`
- Test: `tests/unit/test_executor.py`

- [ ] **Step 1: 写失败测试 tests/unit/test_executor.py**

```python
import pytest

from chart_sdk.codegen.executor import CodeExecError, execute_code
from chart_sdk.codegen.generator import generate_code


def _chart():
    return {
        "chart_type": "line", "title": "t",
        "x_axis": {"label": "x", "unit": None}, "y_axis": {"label": "y", "unit": None},
        "legend": ["a"], "series": [{"name": "a", "x": [1, 2], "y": [1.0, 2.0]}],
        "heatmap": None, "warnings": [],
    }


def test_execute_renders_png(tmp_path):
    out = tmp_path / "render.png"
    code = generate_code(_chart(), out)
    execute_code(code, timeout=30)
    assert out.exists() and out.stat().st_size > 0


def test_syntax_error_raises(tmp_path):
    with pytest.raises(CodeExecError):
        execute_code("this is not python(", timeout=30)


def test_timeout_raises(tmp_path):
    with pytest.raises(CodeExecError, match="超时|timeout"):
        execute_code("import time; time.sleep(60)", timeout=2)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `$py -m pytest tests/unit/test_executor.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现 chart_sdk/codegen/executor.py**

```python
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


class CodeExecError(Exception):
    pass


def execute_code(code: str, timeout: float) -> None:
    """子进程执行生成的代码（代码内已含 savefig），失败或超时抛 CodeExecError。"""
    with tempfile.TemporaryDirectory(prefix="chart_exec_") as td:
        script = Path(td) / "chart_code.py"
        script.write_text(code, encoding="utf-8")
        env = dict(os.environ, MPLBACKEND="Agg")
        try:
            proc = subprocess.run(
                [sys.executable, str(script)], capture_output=True, text=True, timeout=timeout, env=env, cwd=td
            )
        except subprocess.TimeoutExpired:
            raise CodeExecError(f"代码执行超时（>{timeout}s）")
        if proc.returncode != 0:
            tail = (proc.stderr or "")[-800:]
            raise CodeExecError(f"代码执行失败:\n{tail}")
```

- [ ] **Step 4: 运行测试确认通过**

Run: `$py -m pytest tests/unit/test_executor.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```powershell
git add chart_sdk/codegen/executor.py tests/unit/test_executor.py
git commit -m "feat: matplotlib 子进程执行器（超时保护）"
```

---

### Task 9: 图表检测器（VL grounding 主 + 位图降级）

**Files:**
- Modify: `chart_sdk/pdf/detector.py`（补全 Task 1 预置 dataclass 之外的检测器实现）
- Test: `tests/unit/test_detector.py`

- [ ] **Step 1: 写失败测试 tests/unit/test_detector.py**

```python
import json
from pathlib import Path

import fitz
from PIL import Image

from chart_sdk.config import Config
from chart_sdk.pdf.detector import BitmapFallbackDetector, VLGroundingDetector


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def chat_image(self, prompt, image_bytes, **kw):
        self.calls += 1
        return self.responses[min(self.calls - 1, len(self.responses) - 1)]


def _make_pdf_with_image(path: Path, dpi_src_png: Path):
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 72), "Fig detector test")
    page.insert_image(fitz.Rect(72, 100, 400, 350), filename=str(dpi_src_png))
    doc.save(str(path))
    doc.close()


def _render(pdf: Path, out_dir: Path, dpi=72):
    from chart_sdk.pdf.render import render_pages
    return render_pages(pdf, out_dir, dpi=dpi, max_pages=30)


def test_vl_grounding_filters_other_and_dedups(tmp_path):
    pdf = tmp_path / "p.pdf"
    doc = fitz.open()
    doc.new_page(width=595, height=842)
    doc.save(str(pdf))
    doc.close()
    pages = _render(pdf, tmp_path / "pg")
    png = tmp_path / "pg" / "page-01.png"
    import fitz as _f
    with _f.open(str(pdf)) as d:
        page = d[0]
        det = VLGroundingDetector(Config.from_env(), FakeClient([
            json.dumps([
                {"bbox_2d": [100, 100, 800, 700], "type": "line", "caption": "Fig 1"},
                {"bbox_2d": [120, 120, 780, 680], "type": "bar", "caption": ""},
                {"bbox_2d": [100, 100, 900, 200], "type": "other", "caption": ""},
            ])
        ]))
        figs = det.detect_page(png, page, 1)
    assert len(figs) == 1  # 重叠的 bar 被去重，other 被过滤
    assert figs[0].type == "line"
    assert figs[0].source == "vl_grounding"
    assert figs[0].id == "p1-f1"


def test_bitmap_fallback_detects_embedded(tmp_path):
    src = tmp_path / "chart.png"
    Image.new("RGB", (300, 200), (30, 120, 220)).save(src)
    pdf = tmp_path / "p2.pdf"
    _make_pdf_with_image(pdf, src)
    pages = _render(pdf, tmp_path / "pg2")
    png = tmp_path / "pg2" / "page-01.png"
    import fitz as _f
    with _f.open(str(pdf)) as d:
        page = d[0]
        det = BitmapFallbackDetector(Config.from_env(), FakeClient([json.dumps({"type": "bar"})]))
        figs = det.detect_page(png, page, 1)
    assert len(figs) == 1
    assert figs[0].type == "bar"
    assert figs[0].source == "bitmap_fallback"
    assert figs[0].bbox_px[2] > figs[0].bbox_px[0]


def test_bitmap_fallback_drops_other(tmp_path):
    src = tmp_path / "photo.png"
    Image.new("RGB", (300, 200), (10, 10, 10)).save(src)
    pdf = tmp_path / "p3.pdf"
    _make_pdf_with_image(pdf, src)
    pages = _render(pdf, tmp_path / "pg3")
    import fitz as _f
    with _f.open(str(pdf)) as d:
        det = BitmapFallbackDetector(Config.from_env(), FakeClient([json.dumps({"type": "other"})]))
        figs = det.detect_page(tmp_path / "pg3" / "page-01.png", d[0], 1)
    assert figs == []
```

- [ ] **Step 2: 运行测试确认失败**

Run: `$py -m pytest tests/unit/test_detector.py -v`
Expected: FAIL（VLGroundingDetector 未定义）

- [ ] **Step 3: 补全 chart_sdk/pdf/detector.py**

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import fitz
from PIL import Image

from chart_sdk.config import Config
from chart_sdk.inference.client import VLClient
from chart_sdk.pdf.geom import clamp_bbox, dedup_bboxes, norm_to_px, px_to_norm
from chart_sdk.vision.json_utils import extract_json
from chart_sdk.vision.prompts import CLASSIFY_PROMPT, DETECT_PROMPT
from chart_sdk.pdf.render import crop_page_region


@dataclass
class FigureBBox:
    id: str
    page: int
    bbox_norm: list
    bbox_px: list
    type: str  # line | bar | heatmap
    source: str  # vl_grounding | bitmap_fallback
    caption_hint: str | None


class FigureDetector:
    def detect_page(self, page_png: Path, page: "fitz.Page", page_no: int) -> list[FigureBBox]:
        raise NotImplementedError


class VLGroundingDetector(FigureDetector):
    """整页图 → VL grounding 输出 bbox+类型（主实现，设计文档 6.1 第 3 步）。"""

    def __init__(self, config: Config, client: VLClient):
        self.config = config
        self.client = client

    def detect_page(self, page_png: Path, page: "fitz.Page", page_no: int) -> list[FigureBBox]:
        with Image.open(page_png) as im:
            w, h = im.size
        resp = self.client.chat_image(DETECT_PROMPT, page_png.read_bytes())
        data = extract_json(resp)
        if not isinstance(data, list):
            return []
        items = []
        for i, it in enumerate(data, 1):
            if not isinstance(it, dict):
                continue
            if it.get("type") not in ("line", "bar", "heatmap"):
                continue
            bbox = it.get("bbox_2d")
            if not (isinstance(bbox, list) and len(bbox) == 4):
                continue
            px = clamp_bbox(norm_to_px(bbox, w, h), w, h)
            if px is None:
                continue
            items.append(FigureBBox(
                id=f"p{page_no}-f{i}", page=page_no, bbox_norm=px_to_norm(px, w, h),
                bbox_px=px, type=it["type"], source="vl_grounding",
                caption_hint=str(it.get("caption") or "") or None,
            ))
        items = dedup_bboxes(items)
        for i, it in enumerate(items, 1):
            it.id = f"p{page_no}-f{i}"
        return items


class BitmapFallbackDetector(FigureDetector):
    """嵌入位图提取（PyMuPDF get_image_rects）+ VL 分类过滤（降级实现）。"""

    def __init__(self, config: Config, client: VLClient):
        self.config = config
        self.client = client

    def detect_page(self, page_png: Path, page: "fitz.Page", page_no: int) -> list[FigureBBox]:
        with Image.open(page_png) as im:
            w, h = im.size
        ratio = self.config.dpi / 72.0
        items = []
        i = 0
        for img in page.get_images(full=True):
            xref = img[0]
            for rect in page.get_image_rects(xref):
                i += 1
                bbox_px = [rect.x0 * ratio, rect.y0 * ratio, rect.x1 * ratio, rect.y1 * ratio]
                px = clamp_bbox(bbox_px, w, h)
                if px is None:
                    continue
                with Image.open(page_png) as im:
                    crop = page_png.parent / f"_cls_{page_no}_{i}.png"
                    crop_page_region(page_png, px, crop)
                try:
                    resp = self.client.chat_image(CLASSIFY_PROMPT, crop.read_bytes())
                finally:
                    crop.unlink(missing_ok=True)
                data = extract_json(resp) or {}
                if data.get("type") not in ("line", "bar", "heatmap"):
                    continue
                items.append(FigureBBox(
                    id=f"p{page_no}-f{i}", page=page_no, bbox_norm=px_to_norm(px, w, h),
                    bbox_px=px, type=data["type"], source="bitmap_fallback", caption_hint=None,
                ))
        items = dedup_bboxes(items)
        for j, it in enumerate(items, 1):
            it.id = f"p{page_no}-f{j}"
        return items
```

- [ ] **Step 4: 运行测试确认通过**

Run: `$py -m pytest tests/unit/test_detector.py -v`
Expected: 3 passed

- [ ] **Step 5: 全量回归**

Run: `$py -m pytest tests/unit -v`
Expected: 全部通过

- [ ] **Step 6: Commit**

```powershell
git add chart_sdk/pdf/detector.py tests/unit/test_detector.py
git commit -m "feat: VL grounding 检测器 + 位图降级检测器"
```

---

### Task 10: 缓存存储

**Files:**
- Create: `chart_sdk/cache/store.py`
- Test: `tests/unit/test_store.py`

- [ ] **Step 1: 写失败测试 tests/unit/test_store.py**

```python
import json

from chart_sdk.cache.store import PaperStore, SingleStore, content_hash


def test_content_hash_stable():
    assert content_hash(b"abc") == content_hash(b"abc")
    assert content_hash(b"abc") != content_hash(b"abd")


def test_paper_store_creates_and_resumes(tmp_path):
    s1 = PaperStore(tmp_path, b"pdf-bytes", "a.pdf")
    assert s1.session["stage"] == "detecting"
    assert s1.session["file_name"] == "a.pdf"
    s1.session["stage"] = "done"
    s1.save()
    s2 = PaperStore(tmp_path, b"pdf-bytes", "a.pdf")
    assert s2.session["stage"] == "done"  # 断点续跑：读取已保存会话
    assert s2.root == s1.root


def test_paper_store_dirs(tmp_path):
    s = PaperStore(tmp_path, b"x", "a.pdf")
    assert (s.root / "pages").exists()
    assert (s.root / "figures").exists()
    assert (s.root / "source.pdf").exists()
    fd = s.figure_dir("p1-f1")
    assert fd.name == "p1-f1"


def test_single_store(tmp_path):
    s1 = SingleStore(tmp_path, b"img", "a.png")
    s1.record["status"] = "done"
    s1.save()
    s2 = SingleStore(tmp_path, b"img", "a.png")
    assert s2.record["status"] == "done"


def test_session_json_schema_fields(tmp_path):
    s = PaperStore(tmp_path, b"y", "b.pdf")
    for key in ("pdf_hash", "file_name", "n_pages", "dpi", "stage", "pages", "figures"):
        assert key in s.session
```

- [ ] **Step 2: 运行测试确认失败**

Run: `$py -m pytest tests/unit/test_store.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现 chart_sdk/cache/store.py**

```python
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _atomic_write_json(path: Path, obj: dict) -> None:
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


class PaperStore:
    """论文会话缓存：data/cache/papers/<sha256>/（设计文档 5.3、6.1 第 1 步）。"""

    def __init__(self, cache_dir, pdf_bytes: bytes, file_name: str):
        cache_dir = Path(cache_dir)
        self.pdf_hash = content_hash(pdf_bytes)
        self.root = cache_dir / "papers" / self.pdf_hash
        (self.root / "pages").mkdir(parents=True, exist_ok=True)
        (self.root / "figures").mkdir(exist_ok=True)
        src = self.root / "source.pdf"
        if not src.exists():
            src.write_bytes(pdf_bytes)
        sp = self.root / "session.json"
        if sp.exists():
            self.session = json.loads(sp.read_text(encoding="utf-8"))
        else:
            self.session = {
                "pdf_hash": self.pdf_hash, "file_name": file_name, "n_pages": 0, "dpi": 0,
                "stage": "detecting", "pages": [], "figures": [],
            }

    def save(self) -> None:
        _atomic_write_json(self.root / "session.json", self.session)

    def figure_dir(self, fig_id: str) -> Path:
        d = self.root / "figures" / fig_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def page_png(self, page_no: int) -> Path:
        for p in self.session["pages"]:
            if p["page"] == page_no:
                return self.root / p["png_path"]
        raise KeyError(f"页面未渲染: {page_no}")


class SingleStore:
    """单图缓存：data/cache/singles/<sha256>/。"""

    def __init__(self, cache_dir, image_bytes: bytes, file_name: str):
        cache_dir = Path(cache_dir)
        self.image_hash = content_hash(image_bytes)
        self.root = cache_dir / "singles" / self.image_hash
        self.root.mkdir(parents=True, exist_ok=True)
        rp = self.root / "record.json"
        if rp.exists():
            self.record = json.loads(rp.read_text(encoding="utf-8"))
        else:
            self.record = {"file_name": file_name, "status": "pending"}

    def save(self) -> None:
        _atomic_write_json(self.root / "record.json", self.record)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `$py -m pytest tests/unit/test_store.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```powershell
git add chart_sdk/cache tests/unit/test_store.py
git commit -m "feat: 内容寻址缓存（论文会话/单图，断点续跑）"
```

---

### Task 11: 流水线编排（论文 + 单图）

**Files:**
- Create: `chart_sdk/pipeline/paper.py`, `chart_sdk/pipeline/single.py`
- Test: `tests/unit/test_pipeline.py`

- [ ] **Step 1: 写失败测试 tests/unit/test_pipeline.py**

```python
import json
from pathlib import Path

import fitz

from chart_sdk.config import Config
from chart_sdk.pipeline.paper import PaperPipeline
from chart_sdk.pipeline.single import run_single
from chart_sdk.vision.parser import ParseError
from chart_sdk.vision.validator import ValidationError

CHART = {
    "chart_type": "line", "title": "t",
    "x_axis": {"label": "x", "unit": None}, "y_axis": {"label": "y", "unit": None},
    "legend": ["a"], "series": [{"name": "a", "x": [1, 2], "y": [1.0, 2.0]}],
    "heatmap": None, "warnings": [],
}


class FakeClient:
    def __init__(self, response=CHART, fail=False):
        self.response = response
        self.fail = fail
        self.parse_calls = 0

    def chat_image(self, prompt, image_bytes, **kw):
        self.parse_calls += 1
        if self.fail:
            return "垃圾"
        return json.dumps(self.response)


class FakeDetector:
    def __init__(self, boxes=None):
        self.boxes = boxes or [([50, 50, 400, 300], "line")]
        self.detect_calls = 0

    def detect_page(self, page_png, page, page_no):
        self.detect_calls += 1
        from chart_sdk.pdf.detector import FigureBBox
        out = []
        for i, (box, t) in enumerate(self.boxes, 1):
            out.append(FigureBBox(id=f"p{page_no}-f{i}", page=page_no, bbox_norm=[0, 0, 1, 1],
                                  bbox_px=list(box), type=t, source="vl_grounding", caption_hint=None))
        return out


def _make_pdf(path: Path, n_pages=2):
    doc = fitz.open()
    for _ in range(n_pages):
        doc.new_page(width=595, height=842)
    doc.save(str(path))
    doc.close()


def test_pipeline_full_run(tmp_path):
    _make_pdf(tmp_path / "a.pdf")
    cfg = Config.from_env()
    cfg.cache_dir = str(tmp_path / "cache")
    client = FakeClient()
    det = FakeDetector()
    pipe = PaperPipeline(cfg, client, detector=det, fallback=FakeDetector([]))
    session = pipe.run(tmp_path / "a.pdf")
    assert session["stage"] == "done"
    assert len(session["figures"]) == 2  # 两页各一张
    f = session["figures"][0]
    assert f["parse_status"] == "done" and f["render_status"] == "done"
    root = Path(cfg.cache_dir) / "papers"
    pdir = root / session["pdf_hash"]
    assert (pdir / "figures" / f["id"] / "render.png").exists()
    assert (pdir / "figures" / f["id"] / "code.py").exists()
    assert (pdir / "figures" / f["id"] / "chart.json").exists()


def test_pipeline_resume_skips_work(tmp_path):
    _make_pdf(tmp_path / "b.pdf")
    cfg = Config.from_env()
    cfg.cache_dir = str(tmp_path / "cache")
    client = FakeClient()
    pipe = PaperPipeline(cfg, client, detector=FakeDetector(), fallback=FakeDetector([]))
    pipe.run(tmp_path / "b.pdf")
    n1 = client.parse_calls
    pipe.run(tmp_path / "b.pdf")  # 重复上传：全部命中缓存
    assert client.parse_calls == n1


def test_pipeline_parse_error_isolated(tmp_path):
    _make_pdf(tmp_path / "c.pdf")
    cfg = Config.from_env()
    cfg.cache_dir = str(tmp_path / "cache")
    client = FakeClient(fail=True)
    pipe = PaperPipeline(cfg, client, detector=FakeDetector(), fallback=FakeDetector([]))
    session = pipe.run(tmp_path / "c.pdf")
    assert session["stage"] == "done"
    assert session["figures"][0]["parse_status"] == "error"
    assert session["figures"][0]["error"]


def test_run_single(tmp_path):
    from PIL import Image
    img = tmp_path / "in.png"
    Image.new("RGB", (200, 150), (255, 255, 255)).save(img)
    cfg = Config.from_env()
    cfg.cache_dir = str(tmp_path / "cache")
    r = run_single(cfg, FakeClient(), img)
    assert r["status"] == "done"
    r2 = run_single(cfg, FakeClient(), img)
    assert r2["status"] == "done"  # 命中缓存
```

- [ ] **Step 2: 运行测试确认失败**

Run: `$py -m pytest tests/unit/test_pipeline.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现 chart_sdk/pipeline/paper.py**

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
from chart_sdk.vision.parser import ParseError, parse_chart
from chart_sdk.vision.validator import ValidationError


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
        except (ParseError, ValidationError) as e:
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

- [ ] **Step 4: 实现 chart_sdk/pipeline/single.py**

```python
from __future__ import annotations

import json
from pathlib import Path

from chart_sdk.cache.store import SingleStore
from chart_sdk.codegen.executor import CodeExecError, execute_code
from chart_sdk.codegen.generator import generate_code
from chart_sdk.config import Config
from chart_sdk.inference.client import VLClient
from chart_sdk.vision.parser import ParseError, parse_chart
from chart_sdk.vision.validator import ValidationError

_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}


def run_single(config: Config, client: VLClient, image_path: Path, progress=None) -> dict:
    cb = progress or (lambda *a: None)
    image_path = Path(image_path)
    data = image_path.read_bytes()
    store = SingleStore(config.cache_dir, data, image_path.name)
    r = store.record
    if r.get("status") == "done":
        cb("done", 1, 1, "命中缓存")
        return r
    cb("parsing", 0, 1, "解析图表")
    r["input_path"] = "input.png"
    (store.root / "input.png").write_bytes(data)
    mime = _MIME.get(image_path.suffix.lower(), "image/png")
    try:
        chart = parse_chart(client, data, mime=mime, config=config)
    except (ParseError, ValidationError) as e:
        r["status"] = "error"
        r["error"] = str(e)
        store.save()
        return r
    r["chart"] = chart
    code = generate_code(chart, store.root / "render.png")
    (store.root / "code.py").write_text(code, encoding="utf-8")
    r["code_path"] = "code.py"
    cb("rendering", 0, 1, "渲染复刻图")
    try:
        execute_code(code, config.exec_timeout)
        r["render_path"] = "render.png"
        r["status"] = "done"
    except CodeExecError as e:
        r["status"] = "render_failed"
        r["error"] = str(e)
    store.save()
    return r
```

- [ ] **Step 5: 运行测试确认通过**

Run: `$py -m pytest tests/unit/test_pipeline.py -v`
Expected: 4 passed

- [ ] **Step 6: Commit**

```powershell
git add chart_sdk/pipeline tests/unit/test_pipeline.py
git commit -m "feat: 论文/单图流水线编排（断点续跑、错误隔离）"
```

---

### Task 12: Gradio 前端

**Files:**
- Create: `app/gradio_app.py`
- Test: `tests/unit/test_app.py`

- [ ] **Step 1: 写失败测试 tests/unit/test_app.py**

```python
from chart_sdk.vision.validator import validate_chart
from app.gradio_app import chart_to_dataframe, draw_page_annotations, hit_test


def _chart():
    return validate_chart({
        "chart_type": "line", "title": "t",
        "x_axis": {"label": "x", "unit": None}, "y_axis": {"label": "y", "unit": None},
        "legend": ["a", "b"],
        "series": [{"name": "a", "x": [1, 2], "y": [1.0, 2.0]}, {"name": "b", "x": [1, 2], "y": [3.0, 4.0]}],
        "heatmap": None,
    })[0]


def test_chart_to_dataframe():
    headers, rows = chart_to_dataframe(_chart())
    assert headers == ["x", "a", "b"]
    assert rows[0] == [1, 1.0, 3.0]


def test_draw_page_annotations(tmp_path):
    from PIL import Image
    png = tmp_path / "page.png"
    Image.new("RGB", (400, 300), (255, 255, 255)).save(png)
    figs = [{"id": "p1-f1", "page": 1, "bbox_px": [50, 50, 200, 150], "type": "line", "source": "vl_grounding", "caption_hint": None, "bbox_norm": [0, 0, 1, 1]}]
    out = draw_page_annotations(png, figs)
    assert out.size == (400, 300)


def test_hit_test():
    figs = [{"id": "p1-f1", "bbox_px": [50, 50, 200, 150]}]
    assert hit_test(figs, 100, 100) == "p1-f1"
    assert hit_test(figs, 300, 300) is None
    assert hit_test(figs, 45, 45) == "p1-f1"  # 容差命中
```

- [ ] **Step 2: 运行测试确认失败**

Run: `$py -m pytest tests/unit/test_app.py -v`
Expected: FAIL（ModuleNotFoundError: app）

- [ ] **Step 3: 实现 app/gradio_app.py**

（在 `app/` 下创建 `__init__.py` 空文件与 `gradio_app.py`；文件较长，按下文完整实现）

```python
"""Gradio 前端：论文模式（页面预览+高亮+点击联动）与单图模式。"""
from __future__ import annotations

import json
from pathlib import Path

import gradio as gr
from PIL import Image, ImageDraw

from chart_sdk.cache.store import PaperStore
from chart_sdk.config import Config
from chart_sdk.inference.client import VLClient
from chart_sdk.pipeline.paper import PaperPipeline
from chart_sdk.pipeline.single import run_single

CONFIG = Config.from_env()
_CLIENT: VLClient | None = None

BBOX_PAD = 25  # 点击命中容差（px）


def get_client() -> VLClient:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = VLClient(CONFIG)
    return _CLIENT


def draw_page_annotations(page_png: Path, figures: list) -> Image.Image:
    """页面上画高亮框与编号（设计文档 6.3）。"""
    im = Image.open(page_png).convert("RGB")
    draw = ImageDraw.Draw(im)
    for i, fig in enumerate(figures, 1):
        x0, y0, x1, y1 = fig["bbox_px"]
        draw.rectangle([x0, y0, x1, y1], outline=(230, 30, 30), width=4)
        draw.rectangle([x0, y0 - 26, x0 + 56, y0], fill=(230, 30, 30))
        draw.text((x0 + 8, y0 - 22), f"[{i}]", fill=(255, 255, 255))
    return im


def hit_test(figures: list, x: float, y: float) -> str | None:
    """命中最小包含 bbox（含容差）；无命中返回 None。"""
    hits = []
    for fig in figures:
        x0, y0, x1, y1 = fig["bbox_px"]
        if (x0 - BBOX_PAD) <= x <= (x1 + BBOX_PAD) and (y0 - BBOX_PAD) <= y <= (y1 + BBOX_PAD):
            hits.append(((x1 - x0) * (y1 - y0), fig["id"]))
    return min(hits)[1] if hits else None


def chart_to_dataframe(chart: dict):
    """chart JSON → (headers, rows) 供 gr.Dataframe 展示。"""
    if chart["chart_type"] == "heatmap":
        hm = chart["heatmap"]
        headers = [""] + (hm["x_labels"] or [f"c{i+1}" for i in range(len(hm["matrix"][0]))])
        rows = []
        for j, row in enumerate(hm["matrix"]):
            ylab = hm["y_labels"][j] if j < len(hm["y_labels"]) else f"r{j+1}"
            rows.append([ylab] + list(row))
        return headers, rows
    series = chart["series"]
    n = max(len(s["x"]) for s in series) if series else 0
    headers = ["x"] + [s["name"] for s in series]
    rows = []
    for i in range(n):
        row = [series[0]["x"][i] if i < len(series[0]["x"]) else ""]
        for s in series:
            row.append(s["y"][i] if i < len(s["y"]) else "")
        rows.append(row)
    return headers, rows


def _figure_outputs(root: Path, fig: dict):
    """由 figure 条目产出右栏四标签内容。"""
    crop = root / fig["crop_path"] if fig.get("crop_path") else None
    render = root / fig["render_path"] if fig.get("render_path") else None
    chart = None
    if fig.get("chart_json_path"):
        chart = json.loads((root / fig["chart_json_path"]).read_text(encoding="utf-8"))
    code = (root / fig["code_path"]).read_text(encoding="utf-8") if fig.get("code_path") else ""
    headers, rows = ("无数据", []) if chart is None else chart_to_dataframe(chart)
    status = f'{fig["id"]} | 解析: {fig.get("parse_status")} | 渲染: {fig.get("render_status")}'
    if fig.get("error"):
        status += f' | 错误: {fig["error"][:200]}'
    return (
        crop if crop and crop.exists() else None,
        gr.Dataframe(value=rows, headers=headers, interactive=False) if rows else gr.Dataframe(value=[], headers=["无数据"]),
        render if render and render.exists() else None,
        code,
        status,
    )


def upload_paper(pdf_file, progress=gr.Progress()):
    """论文模式：上传 → 阻塞跑流水线（实时进度）→ 返回页面导航与首屏。"""
    if not pdf_file:
        raise gr.Error("请先上传 PDF")
    try:
        get_client().health()
    except Exception:
        raise gr.Error(f"Ollama 不可达（{CONFIG.base_url}）。请运行: ollama pull {CONFIG.model} 并确认服务已启动")
    pdf_path = Path(pdf_file)
    store = PaperStore(CONFIG.cache_dir, pdf_path.read_bytes(), pdf_path.name)
    session = PaperPipeline(CONFIG, get_client()).run(pdf_path)

    def cb(stage, done, total, msg):
        frac = done / total if total else None
        progress(frac, desc=msg)

    def upd(page_no):
        return page_panel(store, session, page_no)

    pages = [p["page"] for p in session["pages"]]
    first = pages[0] if pages else 1
    img, radio, count = page_panel(store, session, first)
    return (
        gr.update(choices=[f"第 {p} 页" for p in pages], value=f"第 {first} 页", visible=True),
        img, radio, count, session,
    )


def page_panel(store: PaperStore, session: dict, page_no: int):
    """某页的：高亮大图 + 图表单选列表 + 数量提示。"""
    figs = [f for f in session["figures"] if f["page"] == page_no]
    png = store.page_png(page_no)
    img = draw_page_annotations(png, figs) if figs else Image.open(png)
    choices = [f'[{i}] {f["type"]} ({f["id"]})' for i, f in enumerate(figs, 1)]
    count = f"本页检测到 {len(figs)} 个图表" if figs else "本页未检测到目标类型图表"
    return img, gr.update(choices=choices, value=choices[0] if choices else None), count


def select_page(page_label, session):
    store = PaperStore(CONFIG.cache_dir, (Path(CONFIG.cache_dir) / "papers" / session["pdf_hash"] / "source.pdf").read_bytes(), session["file_name"])
    page_no = int(str(page_label).replace("第", "").replace("页", "").strip())
    img, radio, count = page_panel(store, session, page_no)
    return img, radio, count, None, None, None, "", ""


def on_image_select(evt: gr.SelectData, session, page_label):
    """页面图点击 → 命中 bbox → 联动右栏（设计文档 6.3）。"""
    if not session:
        return None, None, None, None, "", ""
    store = _store_of(session)
    page_no = int(str(page_label).replace("第", "").replace("页", "").strip())
    figs = [f for f in session["figures"] if f["page"] == page_no]
    fig_id = hit_test(figs, evt.index[0], evt.index[1])
    if fig_id is None:
        return gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update()
    fig = next(f for f in figs if f["id"] == fig_id)
    label = f'[{figs.index(fig) + 1}] {fig["type"]} ({fig["id"]})'
    outputs = _figure_outputs(store.root, fig)
    return gr.update(value=label), *outputs


def on_radio_change(label, session):
    if not label or not session:
        return None, None, None, "", ""
    store = _store_of(session)
    fig_id = label.rsplit("(", 1)[-1].rstrip(")")
    fig = next((f for f in session["figures"] if f["id"] == fig_id), None)
    if fig is None:
        return None, None, None, "", ""
    return _figure_outputs(store.root, fig)


def _store_of(session: dict) -> PaperStore:
    pdf_bytes = (Path(CONFIG.cache_dir) / "papers" / session["pdf_hash"] / "source.pdf").read_bytes()
    return PaperStore(CONFIG.cache_dir, pdf_bytes, session["file_name"])


def run_single_ui(image, progress=gr.Progress()):
    if image is None:
        raise gr.Error("请先上传图片")
    try:
        get_client().health()
    except Exception:
        raise gr.Error(f"Ollama 不可达（{CONFIG.base_url}）。请运行: ollama pull {CONFIG.model}")
    path = Path(image) if isinstance(image, str) else Path(image.name) if hasattr(image, "name") else None
    if path is None or not path.exists():
        raise gr.Error("图片读取失败")
    result = run_single(CONFIG, get_client(), path)
    if result["status"] == "error":
        raise gr.Error(f"解析失败: {result.get('error')}")
    root = Path(CONFIG.cache_dir) / "singles" / result["image_hash"]
    chart = result.get("chart")
    headers, rows = chart_to_dataframe(chart) if chart else ("无数据", [])
    code = (root / result["code_path"]).read_text(encoding="utf-8") if result.get("code_path") else ""
    render = root / result["render_path"] if result.get("render_path") and (root / result["render_path"]).exists() else None
    status = f"状态: {result['status']}" + (f" | {result.get('error', '')[:200]}" if result.get("error") else "")
    return root / "input.png", gr.Dataframe(value=rows, headers=headers, interactive=False), render, code, status


def build_ui():
    with gr.Blocks(title="论文图表复刻") as demo:
        gr.Markdown("# 论文图表复刻系统\n上传论文 PDF 或单张图表图片，本地解析并复刻 Matplotlib 代码。")
        with gr.Tabs():
            with gr.Tab("论文模式"):
                with gr.Row():
                    with gr.Column(scale=1):
                        pdf_in = gr.File(label="上传论文 PDF", file_types=[".pdf"])
                        upload_btn = gr.Button("解析论文", variant="primary")
                        page_dd = gr.Dropdown(label="页码", visible=False)
                        page_img = gr.Image(label="页面预览（红色框为图表，可点击）", interactive=False)
                        fig_radio = gr.Radio(label="图表列表（点击页面或选择）", visible=False)
                        fig_count = gr.Markdown("")
                    with gr.Column(scale=1):
                        with gr.Tabs():
                            with gr.Tab("原图"):
                                f_crop = gr.Image(label="图表原图", interactive=False)
                            with gr.Tab("数据表"):
                                f_table = gr.Dataframe(interactive=False)
                            with gr.Tab("复刻图"):
                                f_render = gr.Image(label="Matplotlib 复刻图", interactive=False)
                            with gr.Tab("代码"):
                                f_code = gr.Code(label="Matplotlib 代码（可复制）", language="python", interactive=False)
                        f_status = gr.Markdown("")
                session_state = gr.State()
                upload_btn.click(upload_paper, inputs=[pdf_in], outputs=[page_dd, page_img, fig_radio, fig_count, session_state])
                page_dd.select(select_page, inputs=[page_dd, session_state], outputs=[page_img, fig_radio, fig_count, f_crop, f_table, f_render, f_code, f_status])
                page_img.select(on_image_select, inputs=[session_state, page_dd], outputs=[fig_radio, f_crop, f_table, f_render, f_code, f_status])
                fig_radio.change(on_radio_change, inputs=[fig_radio, session_state], outputs=[f_crop, f_table, f_render, f_code, f_status])
            with gr.Tab("单图模式"):
                with gr.Row():
                    with gr.Column():
                        img_in = gr.Image(label="上传图表图片", type="filepath")
                        run_btn = gr.Button("解析图片", variant="primary")
                    with gr.Column():
                        with gr.Tabs():
                            with gr.Tab("原图"):
                                s_crop = gr.Image(interactive=False)
                            with gr.Tab("数据表"):
                                s_table = gr.Dataframe(interactive=False)
                            with gr.Tab("复刻图"):
                                s_render = gr.Image(interactive=False)
                            with gr.Tab("代码"):
                                s_code = gr.Code(label="Matplotlib 代码（可复制）", language="python", interactive=False)
                        s_status = gr.Markdown("")
                run_btn.click(run_single_ui, inputs=[img_in], outputs=[s_crop, s_table, s_render, s_code, s_status])
    return demo


if __name__ == "__main__":
    build_ui().launch(server_name="127.0.0.1", server_port=7860)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `$py -m pytest tests/unit/test_app.py -v`
Expected: 3 passed

- [ ] **Step 5: 冒烟启动（手动检查）**

Run: `$py app\gradio_app.py`，浏览器打开 `http://127.0.0.1:7860`，确认两个 Tab 渲染无异常后 Ctrl+C 停止
Expected: 页面正常打开

- [ ] **Step 6: Commit**

```powershell
git add app tests/unit/test_app.py
git commit -m "feat: Gradio 双模式前端（页面高亮+点击联动）"
```

---

### Task 13: 样例论文与自检脚本

**Files:**
- Create: `scripts/make_synthetic_sample.py`, `scripts/download_samples.py`, `scripts/selfcheck.py`
- Create: `assets/samples/synthetic-demo.pdf`（由脚本生成并提交）

- [ ] **Step 1: 实现 scripts/make_synthetic_sample.py**

```python
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
```

- [ ] **Step 2: 实现 scripts/download_samples.py**

```python
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
```

- [ ] **Step 3: 运行两个脚本生成样例**

Run: `$py scripts\make_synthetic_sample.py ; $py scripts\download_samples.py`
Expected: `OK ...synthetic-demo.pdf`；arXiv 下载成功或明确提示失败（网络问题不阻塞后续）

- [ ] **Step 4: 实现 scripts/selfcheck.py**

```python
"""自检脚本：环境 + 离线核心链路 + （可选）VL 在线冒烟。逐项 PASS/FAIL，失败返回非零。"""
from __future__ import annotations

import importlib
import io
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

RESULTS = []


def check(name, fn):
    try:
        note = fn() or ""
        RESULTS.append((True, name, note))
        print(f"PASS {name} {note}")
    except Exception as e:  # noqa: BLE001
        RESULTS.append((False, name, str(e)[:200]))
        print(f"FAIL {name} {e}")


def c_python():
    v = sys.version_info
    assert v >= (3, 10), f"需要 Python>=3.10，当前 {v}"
    return f"{v.major}.{v.minor}.{v.micro}"


def c_deps():
    mods = ["gradio", "fitz", "matplotlib", "PIL", "openai", "numpy", "pandas", "pytest"]
    for m in mods:
        importlib.import_module(m)
    return f"{len(mods)} 个依赖"


def c_offline_chain():
    from chart_sdk.codegen.executor import execute_code
    from chart_sdk.codegen.generator import generate_code
    from chart_sdk.vision.validator import validate_chart
    chart = validate_chart({
        "chart_type": "line", "title": "t",
        "x_axis": {"label": "x", "unit": None}, "y_axis": {"label": "y", "unit": None},
        "legend": ["a"], "series": [{"name": "a", "x": [1, 2], "y": [1.0, 2.0]}],
        "heatmap": None,
    })[0]
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "r.png"
        execute_code(generate_code(chart, out), timeout=30)
        assert out.exists() and out.stat().st_size > 0
    return "校验→代码→渲染 OK"


def c_render_pages():
    from chart_sdk.pdf.render import render_pages
    sample = ROOT / "assets" / "samples" / "synthetic-demo.pdf"
    assert sample.exists(), "缺 synthetic-demo.pdf，请先运行 scripts/make_synthetic_sample.py"
    with tempfile.TemporaryDirectory() as td:
        pages = render_pages(sample, Path(td) / "pages", dpi=72, max_pages=30)
        assert len(pages) == 3
    return "3 页渲染 OK"


def c_ollama():
    from chart_sdk.config import Config
    from chart_sdk.inference.client import VLClient
    c = VLClient(Config.from_env())
    assert c.health(), f"Ollama 不可达: {c.config.base_url}"
    assert c.model_available(), f"模型缺失，请运行: ollama pull {c.config.model}"
    return c.config.model


def c_vl_smoke():
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from chart_sdk.vision.parser import parse_chart
    from chart_sdk.config import Config
    from chart_sdk.inference.client import VLClient
    fig, ax = plt.subplots(figsize=(5, 3.5), dpi=120)
    x = [1, 2, 3, 4]
    ax.plot(x, [10, 20, 15, 30], marker="o")
    fig.savefig(buf := io.BytesIO(), format="png")
    plt.close(fig)
    chart = parse_chart(VLClient(Config.from_env()), buf.getvalue())
    assert chart["series"], "VL 未能提取到数据系列"
    return f"识别 {len(chart['series'])} 条系列"


def main():
    check("Python>=3.10", c_python)
    check("依赖导入", c_deps)
    check("离线链路(校验/代码/渲染)", c_offline_chain)
    check("页面渲染", c_render_pages)
    ollama_ok = False
    try:
        check("Ollama 与模型", c_ollama)
        ollama_ok = RESULTS[-1][0]
    except Exception:  # noqa: BLE001
        print("SKIP Ollama 与模型（不可达）")
    if ollama_ok:
        check("VL 冒烟(单图解析)", c_vl_smoke)
    else:
        print("SKIP VL 冒烟")
    failed = [r for r in RESULTS if not r[0]]
    print(f"\n{len(RESULTS) - len(failed)} 通过 / {len(failed)} 失败")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: 运行自检**

Run: `$py scripts\selfcheck.py`
Expected: 离线项全 PASS；Ollama 在线时含 VL 冒烟 PASS，退出码 0

- [ ] **Step 6: Commit**

```powershell
git add scripts assets/samples
git commit -m "feat: 样例论文（合成+arXiv）与 selfcheck 自检脚本"
```

---

### Task 14: 集成测试与文档收尾

**Files:**
- Create: `tests/integration/test_vl_flow.py`
- Create: `README.md`, `STATUS.md`, `PLAN.md`

- [ ] **Step 1: 写集成测试 tests/integration/test_vl_flow.py**

```python
import json

import pytest

from chart_sdk.config import Config
from chart_sdk.inference.client import VLClient

_cfg = Config.from_env()
_client = VLClient(_cfg)
_OLLAMA_OK = _client.health() and _client.model_available()

pytestmark = pytest.mark.skipif(not _OLLAMA_OK, reason="本地 Ollama/模型不可用")


def _chart_png_bytes():
    import io

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(5, 3.5), dpi=120)
    x = [1, 2, 3, 4]
    ax.plot(x, [10, 20, 15, 30], marker="o", label="m1")
    ax.set_xlabel("step"); ax.set_ylabel("value"); ax.legend()
    fig.savefig(buf := io.BytesIO(), format="png")
    plt.close(fig)
    return buf.getvalue()


def test_single_full_flow(tmp_path):
    from PIL import Image
    from chart_sdk.pipeline.single import run_single
    img = tmp_path / "chart.png"
    Image.open(__import__("io").BytesIO(_chart_png_bytes())).save(img)
    cfg = Config.from_env()
    cfg.cache_dir = str(tmp_path / "cache")
    r = run_single(cfg, _client, img)
    assert r["status"] == "done", r.get("error")
    assert (tmp_path / "cache" / "singles" / r["image_hash"] / "render.png").exists()


def test_paper_detect_and_parse(tmp_path):
    from chart_sdk.pipeline.paper import PaperPipeline
    sample = Path(__file__).resolve().parents[2] / "assets" / "samples" / "synthetic-demo.pdf"
    cfg = Config.from_env()
    cfg.cache_dir = str(tmp_path / "cache")
    session = PaperPipeline(cfg, _client).run(sample)
    assert session["stage"] == "done"
    target = [f for f in session["figures"] if f["type"] in ("line", "bar", "heatmap")]
    assert target, "合成样例中至少应检出 1 张目标类型图表"
```

- [ ] **Step 2: 运行（有 Ollama 时应通过，无则 skip）**

Run: `$py -m pytest tests/integration -v`
Expected: 2 passed（或 2 skipped）

- [ ] **Step 3: 写 README.md**

```markdown
# 论文图表复刻系统（Paper Chart Replica）

完全本地运行：上传论文 PDF 或单张图表图片 → 提取折线/柱状/热力图数据 → 展示数据表、Matplotlib 复刻图与可复制代码。模型经 Ollama 本地量化推理，PDF 与图片不上传公网。

## 快速开始

1. 安装 Python ≥3.10，`python -m venv .venv` 后安装依赖：
   `.venv\Scripts\python.exe -m pip install -r requirements.txt`
2. 安装并启动 [Ollama](https://ollama.com)，拉取模型：`ollama pull qwen2.5vl:7b`（显存不足可 `ollama pull qwen2.5vl:3b` 并设 `CHART_SDK_MODEL=qwen2.5vl:3b`）
3. 生成样例论文（可选）：`.venv\Scripts\python.exe scripts\make_synthetic_sample.py`；联网时 `.venv\Scripts\python.exe scripts\download_samples.py` 下载 arXiv 真实论文
4. 自检：`.venv\Scripts\python.exe scripts\selfcheck.py`
5. 启动：`.venv\Scripts\python.exe app\gradio_app.py`，浏览器打开 http://127.0.0.1:7860

## 使用

- **论文模式**：上传 PDF → 系统渲染页面并高亮图表（红框）→ 点击图表或从列表选择 → 右侧查看原图 / 数据表 / 复刻图 / 代码
- **单图模式**：上传一张图表图片 → 一键解析 → 同样四栏输出
- 同一文件重复上传直接命中缓存（`data/cache/`，删除即清空）

## 配置（环境变量）

| 变量 | 默认 | 说明 |
|---|---|---|
| `CHART_SDK_BASE_URL` | `http://localhost:11434/v1` | Ollama OpenAI 兼容端点 |
| `CHART_SDK_MODEL` | `qwen2.5vl:7b` | 模型名 |
| `CHART_SDK_DPI` | `150` | 页面渲染 DPI |
| `CHART_SDK_MAX_PAGES` | `30` | 最大处理页数 |
| `CHART_SDK_EXEC_TIMEOUT` | `30` | 代码执行超时（秒） |
| `CHART_SDK_VL_TIMEOUT` | `120` | VL 调用超时（秒） |

## 目录

```
chart_sdk/            SDK（inference/pdf/vision/codegen/cache/pipeline）
app/gradio_app.py     前端入口
scripts/              样例生成/下载与自检
assets/samples/       测试论文样例
tests/                单元+集成测试（pytest tests -v）
docs/superpowers/     设计文档与实施计划
STATUS.md / PLAN.md   验收记录与计划
```

## 开发

设计文档：`docs/superpowers/specs/2026-10-19-paper-chart-replication-design.md`；实施计划：`docs/superpowers/plans/2026-10-19-paper-chart-replication.md`。运行测试：`.venv\Scripts\python.exe -m pytest tests\unit -v`（集成测试在 Ollama 不可用时自动跳过）。
```

- [ ] **Step 4: 写 STATUS.md**

```markdown
# STATUS

实际验证记录、当前限制与下一步。

## 0.1.0（2026-10-19 MVP）

- [x] 单图解析链路：VL 结构化解析 → 校验 → 代码生成 → 子进程渲染（含重试与超时保护）
- [x] PDF 论文解析：页面渲染、VL grounding 检测（位图提取降级）、批量预解析
- [x] 内容寻址缓存与断点续跑；单图失败不阻塞整体
- [x] Gradio 双模式前端：页面高亮、点击联动、实时进度
- [x] 单元测试 + 集成测试（Ollama 不可用自动跳过）+ selfcheck 脚本

## 已知限制

- 量化 7B 模型 grounding bbox 存在偏差：已用归一化坐标、钳制与最小面积阈值缓解，复杂双栏版式可能漏检/偏移
- 只支持折线/柱状/热力图；流程图、饼图、照片类被过滤
- 页数上限 30（可配）；正文不解析
- 数据提取为像素级估计，数值可能有小幅偏差（warnings 字段有提示）

## 下一步

- 评测数据集与指标测试（图表类型分类准确率、数据提取保真度）
- 表格与更多图类型；bbox 后处理精修（投影分析）
```

- [ ] **Step 5: 写 PLAN.md**

```markdown
# PLAN

范围与阶段计划（对应用户开发顺序，MVP=1→4）：

1. [x] 单图解析 SDK（验证 VL 识别+代码生成可用）
2. [x] PDF 解析模块（抽取图片+记录坐标）
3. [x] 批量预解析 + 全量缓存
4. [x] Gradio 前端（页面渲染、点击联动、代码展示）
5. [ ] 评测数据集与指标测试（下一轮）

后续候选：更多图表类型、表格解析、bbox 精修、批量论文目录模式。
```

- [ ] **Step 6: 全量测试回归**

Run: `$py -m pytest tests -v`
Expected: 单元全部通过；集成 passed 或 skipped

- [ ] **Step 7: 最终 Commit**

```powershell
git add tests/integration README.md STATUS.md PLAN.md
git commit -m "docs: 集成测试与 README/STATUS/PLAN 收尾"
```

---

## 自查记录（写计划后已执行）

- **Spec 覆盖**：设计文档 §4 架构→Task 0-12 文件一一对应；§5 数据结构→Task 9（FigureBBox）/5（chart JSON）/10（session）；§6 数据流→Task 11；§6.3 前端→Task 12；§7 错误处理→Task 6（重试）、8（超时）、9（降级）、11（隔离）；§8 测试→各任务+Task 14；§9 配置→Task 0；§12 交付物→Task 13/14。无缺口。
- **占位符扫描**：无 TBD/TODO；所有代码步骤均含完整代码。
- **类型一致性**：`FigureBBox` 字段（Task 1/9/11/12）、`validate_chart` 返回 `(dict, warnings)`（Task 5/6/7/11/12/13）、`parse_chart(client, bytes, mime, config)`（Task 6/9/11）、`generate_code(chart, out_png)`（Task 7/8/11）、`execute_code(code, timeout)`（Task 8/11/13）、`PaperStore.page_png/figure_dir`（Task 10/11/12）、进度回调 `cb(stage, done, total, msg)`（Task 11/12）均已对齐。
- **注意点**：Task 1 Step 4/5 顺序依赖已在计划内说明（提前放置 FigureBBox）；Gradio `gr.Image.select` 的 `evt.index` 按原生像素坐标处理并以 Radio 列表作为兜底交互。
