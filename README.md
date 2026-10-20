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
