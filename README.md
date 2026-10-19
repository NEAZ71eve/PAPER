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
| `CHART_SDK_CACHE_DIR` | `data/cache` | 缓存根目录（页面/图表渲染产物与 session 存放位置） |

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
