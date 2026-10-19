# 设计文档：论文 PDF 导入 + 图文联动图表复刻系统

日期：2026-10-19
状态：待用户审阅

## 1. 背景与目标

构建一个完全本地运行的"论文图表复刻"系统：上传完整论文 PDF 后，自动解析提取论文内全部目标类型图表；前端展示论文页面预览并高亮图表区域，用户点击任意图表，系统直接展示该图表提取的数据、重绘预览图与对应的 Matplotlib 绘图代码。同时保留独立上传单张图片的解析入口。

核心约束：

- 模型本地量化推理（Ollama + Qwen2.5-VL），PDF 与图片不上传公网
- 只解析论文中的折线图、柱状图、热力图；流程图、饼图、照片类图片跳过
- PDF 解析只提取页面与图表，不解析正文长文本
- 所有解析结果预缓存，重复点击零推理延迟

参考项目 PaperDesk（https://github.com/gruTGU/PaperDesk）仅借鉴其**工程实践**：完全本地处理、README 使用/开发手册、STATUS/PLAN 进度验收记录、PASS/FAIL 自检脚本。不借鉴其技术栈（macOS Swift）与功能（图文排版编辑器，与本系统无关）。

## 2. 范围

### 本次交付（MVP）

1. 单图解析 SDK：Qwen2.5-VL 强约束解析 → JSON → 校验 → matplotlib 代码 → 渲染
2. PDF 论文解析模块：页面渲染 + 图表检测（bbox + 类型）+ 裁剪
3. 批量预解析与全量本地缓存
4. Gradio 前端：论文模式（页面预览 + 高亮 + 点击联动）与单图模式双 Tab
5. 2-3 篇 arXiv 样例论文 + 自检脚本 + 单元/集成测试

### 明确不做（下轮迭代）

- 评测数据集构建与指标测试
- 表格、流程图、饼图、照片类图像解析
- 正文文本提取、OCR
- 多用户/并发、云端部署
- 模型微调

## 3. 关键决策记录

| 决策点 | 结论 | 理由 |
|---|---|---|
| 代码基础 | d:\aicomp 从零搭建 | 工作区为空，无可复用代码 |
| 推理环境 | NVIDIA GPU + Ollama，OpenAI 兼容 API | 用户确认；Windows 上部署最简单 |
| 图表检测 | 方案 B 为主（整页渲染 + VL grounding），方案 A（嵌入位图提取）作为降级实现 | B 覆盖矢量图+位图、bbox 天然对应页面坐标、链路最短；A 保证 VL 异常时演示不空转 |
| 检测器形态 | `FigureDetector` 接口 + 两个实现 | 降级与后续扩展（如专用检测模型）不改动上层 |
| 前端实现 | 全服务端（PIL 预画高亮框 + `gr.Image.select` 坐标命中），无自定义 JS | Gradio 兼容性最好，维护成本最低 |
| 样例论文 | 从 arXiv 选取 2-3 篇含典型折线/柱状/热力图的公开论文 | 用户确认 |
| 交付范围 | MVP（开发顺序 1→4），评测数据集留到下轮 | 用户确认 |

## 4. 总体架构

```
app/gradio_app.py              双模式 UI（Tab: 论文模式 / 单图模式）
chart_sdk/
  __init__.py                  版本号与公共导出
  config.py                    全局配置（环境变量可覆盖）
  pipeline/
    paper.py                   论文会话编排：detect → parse → codegen → session.json
    single.py                  单图编排：parse → codegen
  pdf/
    render.py                  PyMuPDF 页面渲染（150 DPI PNG）
    detector.py                FigureDetector 接口 + VLGroundingDetector（主）+ BitmapFallbackDetector（降级）
  vision/
    prompts.py                 检测/解析两套强约束 prompt
    parser.py                  单图结构化解析（调 inference，输出 chart JSON）
    validator.py               JSON 后处理校验与可疑标记
  codegen/
    generator.py               chart JSON → line/bar/heatmap 模板 → matplotlib 代码
    executor.py                子进程（matplotlib Agg）执行代码渲染 PNG，超时杀进程
  inference/
    client.py                  Ollama OpenAI 兼容客户端（chat + 图像 base64，超时/重试）
  cache/
    store.py                   内容寻址缓存：论文会话与单图结果，分阶段状态
assets/samples/                arXiv 样例论文 PDF
scripts/selfcheck.py           自检脚本（逐项 PASS/FAIL）
tests/
  unit/                        validator / generator / cache key / 坐标换算
  integration/                 需本地 Ollama，不可用则自动 skip
data/cache/                    运行时缓存（gitignore）
```

## 5. 数据结构

### 5.1 FigureBBox（检测结果）

```json
{
  "id": "p3-f1",
  "page": 3,
  "bbox_norm": [120, 300, 880, 720],
  "bbox_px": [149, 526, 1091, 1263],
  "type": "line",
  "source": "vl_grounding",
  "caption_hint": "Fig. 3 ..."
}
```

- `bbox_norm`：Qwen2.5-VL 标准的 0-1000 归一化坐标
- `bbox_px`：换算到当前 DPI 页面像素坐标（前端高亮与点击命中都用它）；示例中 A4 150 DPI 页面为 1240×1754 px，换算规则 `bbox_px = bbox_norm / 1000 × [页宽, 页高]`
- `type` ∈ `line | bar | heatmap | other`；`other` 在检测阶段直接丢弃
- `source` ∈ `vl_grounding | bitmap_fallback`
- `caption_hint`：VL 顺带输出的图注片段，可为 null，仅作展示提示，不参与逻辑

### 5.2 chart JSON（单图解析结果，vision 模块输出）

```json
{
  "chart_type": "line",
  "title": "Accuracy vs. Epochs",
  "x_axis": {"label": "Epoch", "unit": null},
  "y_axis": {"label": "Accuracy", "unit": "%"},
  "legend": ["baseline", "ours"],
  "series": [
    {"name": "baseline", "x": [1, 2, 3], "y": [71.2, 74.8, 76.1]},
    {"name": "ours", "x": [1, 2, 3], "y": [73.0, 77.5, 80.3]}
  ],
  "heatmap": null,
  "warnings": []
}
```

- 折线/柱状图填 `series`；热力图填 `heatmap`（`{x_labels, y_labels, matrix, colormap_hint}`），`series` 置空
- `warnings` 由 validator 填写：可疑但保留的字段说明

### 5.3 session.json（论文会话，cache 模块持有）

```json
{
  "pdf_hash": "sha256...",
  "file_name": "sample.pdf",
  "n_pages": 12,
  "dpi": 150,
  "stage": "done",
  "pages": [{"page": 1, "png_path": "pages/page-01.png"}],
  "figures": [
    {
      "id": "p3-f1", "page": 3,
      "bbox_px": [149, 526, 1091, 1263], "type": "line", "source": "vl_grounding",
      "crop_path": "figures/p3-f1/crop.png",
      "parse_status": "done", "chart_json_path": "figures/p3-f1/chart.json",
      "code_path": "figures/p3-f1/code.py",
      "render_status": "done", "render_path": "figures/p3-f1/render.png",
      "error": null
    }
  ]
}
```

- `stage` ∈ `detecting | parsing | done | failed`（failed 记录顶层 error）
- 单图条目状态：`parse_status` ∈ `pending | done | error`；`render_status` ∈ `pending | done | failed`
- 任何单图失败不阻塞其他图表，错误就地记录

## 6. 数据流

### 6.1 论文模式

1. 上传 PDF → 计算 sha256 → 缓存目录 `data/cache/papers/<hash>/`；已有会话则断点续跑（跳过已完成阶段）
2. 页面渲染：PyMuPDF 全页 150 DPI PNG；页数上限 30，超出截断并提示
3. 图表检测：`VLGroundingDetector` 逐页推理，输出 bbox + 类型（一次推理同时完成定位与分类）；任一页 VL 调用异常时，该页降级 `BitmapFallbackDetector`（PyMuPDF `get_image_rects` 取嵌入位图 + VL 分类过滤）
4. 批量预解析（后台线程，前端进度轮询）：每张裁剪图 → `vision.parser` → chart JSON → `validator` 校验（失败重试 1 次）→ `codegen.generator` 模板生成代码 → `executor` 子进程渲染复刻图
5. 全部结果写入 session.json；前端从缓存读取，点击零推理

### 6.2 单图模式

上传图片 → 内容寻址缓存（`data/cache/singles/<hash>/`）→ 同 6.1 第 4 步链路 → 返回四标签结果。

### 6.3 前端交互

- 布局：`gr.Blocks` 双 Tab
- 论文模式左栏：页码选择（`gr.Dropdown`）+ 当前页大图（PIL 预画高亮框与编号）+ 检测到的图表列表
- 点击命中：`gr.Image.select` 返回显示坐标 → 按显示尺寸与实际像素尺寸比例换算 → 后端命中最小包含 bbox → 右栏切换
- 论文模式右栏：`gr.Tabs`（原图 / 数据表 / 复刻图 / 代码 `gr.Code` 一键复制）
- 单图模式：`gr.Image` 上传 → 解析按钮 → 同右栏四标签输出

## 7. 错误处理

| 场景 | 处理 |
|---|---|
| Ollama 不可达 | 启动时健康检查；UI 显示修复指引（`ollama pull qwen2.5vl:7b`、确认 `OLLAMA_BASE_URL`） |
| grounding 某页无结果 | 合法情况，UI 显示"本页未检测到目标类型图表" |
| VL 输出 JSON 解析失败/校验失败 | 重试 1 次 → 仍失败标记 `error`，详情页显示原因，不阻塞其他图表 |
| 代码执行失败/超时 | 30s 杀子进程，标记 `render_failed`，保留原图、数据表与代码 |
| bbox 越界/退化（面积过小） | validator 丢弃并记录 warning |
| 大 PDF | 页数上限 30 页，超出提示截断 |
| 模型输出坐标偏移 | 0-1000 归一化 + 像素换算钳制到页面范围；面积阈值过滤 |

## 8. 测试策略

- **单元测试**（不依赖模型）：validator 数值校验、generator 模板填充、cache key 与目录规则、bbox 归一化/像素双向换算、状态机断点续跑
- **集成测试**（本地 Ollama 可用时执行，否则 `pytest.mark.skip`）：单图全链路（解析 → 代码 → 渲染）、样例 PDF 检测 → 裁剪 → 至少命中 1 张目标类型图表
- **自检脚本** `scripts/selfcheck.py`：环境（Python 版本、依赖、Ollama 探活、模型可用）+ 核心链路冒烟，逐项输出 PASS/FAIL，失败返回非零退出码

## 9. 配置

| 配置项 | 默认值 | 环境变量覆盖 |
|---|---|---|
| 推理端点 | `http://localhost:11434/v1` | `CHART_SDK_BASE_URL` |
| 模型名 | `qwen2.5vl:7b` | `CHART_SDK_MODEL` |
| 页面渲染 DPI | 150 | `CHART_SDK_DPI` |
| 最大页数 | 30 | `CHART_SDK_MAX_PAGES` |
| 代码执行超时 | 30s | `CHART_SDK_EXEC_TIMEOUT` |
| VL 调用超时 | 120s | `CHART_SDK_VL_TIMEOUT` |
| 校验失败重试 | 1 | 常量 |

## 10. 依赖

Python ≥ 3.10：`gradio`、`pymupdf`、`matplotlib`、`pillow`、`openai`（仅作客户端库连 Ollama）、`numpy`、`pandas`、`pytest`。

## 11. 开发顺序（对应用户开发顺序 1→4）

1. SDK 骨架 + inference 客户端 + 单图解析链路（vision → validator → codegen → executor），先验证 VL 识别与代码生成可用
2. PDF 模块：页面渲染 + FigureDetector（VL grounding 主实现 + 位图降级）+ 裁剪
3. pipeline 论文编排 + 批量预解析 + 缓存（断点续跑）
4. Gradio 前端：双 Tab、页面预览高亮、点击联动、进度轮询
5. 样例论文入库 + 测试补齐 + selfcheck 脚本

## 12. 开源交付物

`chart_sdk`（含 PDF 解析子模块）+ `app/gradio_app.py` + `assets/samples/` 样例论文 + 测试 + `README.md`（使用手册 + 开发手册）+ `STATUS.md` / `PLAN.md`（进度与验收记录）。
