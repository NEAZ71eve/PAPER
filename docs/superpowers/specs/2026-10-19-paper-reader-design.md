# 设计文档：论文阅读器（Word 风格编排 + 墨迹批注 + 按需图表解析）

日期：2026-10-19
状态：已经用户口头批准，待书面审阅
前置：在已交付的"论文图表复刻系统"（chart_sdk + Gradio 前端）基础上做产品形态升级

## 1. 背景与目标

将现有"上传即全量解析"的工具形态，升级为 **Word 风格的论文阅读器**：

- 打开界面是**空白阅读器**；导入论文时可选择是否检测图表（默认勾选检测）
- 导入 = 渲染页面 + VL 轻量检测画框；**不批量解析数据**
- 阅读中点击图表框才**按需解析**（VL 提取 + 代码生成 + 渲染复刻图）
- 提供**手写墨迹**（自由圈画/写字/√×）与**文本批注**两类标注，论文本体永远只读
- 标注**侧车 JSON 自动保存**，重开同一论文自动恢复；可导出叠加标注的**新 PDF 副本**

核心约束沿用：完全本地运行（Ollama + Qwen2.5-VL）、只解析折线/柱状/热力图、不解析正文。

## 2. 关键决策记录

| 决策点 | 结论 | 理由 |
|---|---|---|
| 标注能力 | 手写墨迹 + 文本批注两者都要；"修改"仅针对标注，论文只读 | 用户确认（方案 C） |
| 按需解析触发 | 导入时 VL grounding 检测画框；阅读时点击图框解析 | 用户确认（方案 A）：用户一眼看到可解析图表，点击精准 |
| 导入勾选项 | "检测图表并标记"复选框**默认勾选**；不勾=纯阅读，可用 ribbon 随时开启 | 用户确认 |
| 标注持久化 | 侧车 annotations.json + 重开恢复 + 可导出新 PDF 副本 | 用户确认（方案 A），与"论文不可修改"原则一致 |
| 技术栈 | FastAPI 后端 + 纯 Web SPA 前端（无构建步骤） | 手写 canvas 墨迹/文本气泡/Word ribbon 超出 Gradio 原生能力；chart_sdk 100% 复用 |
| 单图模式 | 保留为右栏"工具箱"页签 | 用户确认 |
| Gradio 前端 | `app/gradio_app.py` 保留为旧版入口，不再维护，README 标注 legacy | 保留既有工作，避免混淆 |
| 导出批注形态 | 墨迹叠加为图像层；文本批注写为 PDF 标准 text annotation（便签） | PDF 页面无"页边"可写，标准注释在各查看器中通用 |

## 3. 总体架构

```
浏览器 SPA（app/reader/：index.html + styles.css + 原生 JS 模块，无框架无构建）
  ├─ ribbon 工具栏 / 左栏缩略图导航 / 中间阅读画布 / 右栏上下文面板
  └─ fetch 调用后端 API
FastAPI 服务（app/server.py，默认端口 8000）
  ├─ 托管前端静态文件（/）与缓存图片（/cache/...）
  └─ reader API（见第 6 节）
chart_sdk（小改）
  ├─ pipeline/paper.py：新增 render_and_detect() 与 parse_figure() 两个细粒度入口；
  │  旧 run() 全量方法保留不动（legacy gradio 仍可用）
  ├─ annotate/store.py（新增）：AnnotationStore，annotations.json 读写
  └─ annotate/export.py（新增）：叠加标注导出 PDF 副本
data/cache/papers/<hash>/
  ├─ session.json（stage 语义扩展，见 5.3）
  ├─ annotations.json（新增）
  ├─ pages/ figures/（现有）
  └─ exports/（导出副本输出目录）
```

## 4. 前端布局与交互（Word 风格编排）

### 4.1 布局

- **顶部 ribbon**（选项卡式，纯 HTML/CSS）：
  - `文件`：导入论文（含"检测图表并标记"复选框，默认勾选）/ 导出带标注副本
  - `批注`：手写笔 / 荧光笔 / 橡皮 / 撤销 / 重做 / 清空本页 / 颜色 / 粗细 / 文本批注模式
  - `图表`：检测状态指示 / 重新检测
  - `视图`：适应宽度 / 适应页面 / 缩放百分比（50–200%）
  - `工具箱`：切换右栏工具箱页签
  - ribbon 最右：Ollama 状态灯（绿/红 + hover 提示）
- **左栏**：页面缩略图导航（约 150px 宽，当前页高亮，点击跳页）
- **中间**：阅读画布，单页模式 + 翻页按钮 + 键盘 ←/→
- **右栏**：三页签——`批注`（当前页批注卡片列表）｜`图表`（解析结果四件套：原图/数据表/复刻图/代码，代码一键复制）｜`工具箱`（单图上传解析，同四件套展示）
- **空白初始态**：未导入时中间显示空阅读器引导页（点击/拖拽导入）

### 4.2 阅读画布三层叠加（坐标均以归一化 0-1 存储，渲染时乘当前显示尺寸）

1. **图表高亮框 DOM 层**：半透明边框 + 编号角标；hover 提示"点击解析"；按状态着色——未解析虚线 / 已解析实线 / 失败红框
2. **墨迹 canvas 层**：透明叠加，接收绘制事件
3. **批注锚点 DOM 层**：数字小圆标，点击定位到右侧对应批注卡

### 4.3 标注交互

- **手写墨迹**：mousedown/mousemove/mouseup 采集点列，实时描画（lineJoin/lineCap round）；抬笔生成 stroke 对象 `{id, tool: pen|highlighter, color, width, points:[[x,y]...]}`；每笔画入栈后整层重绘。荧光笔 = globalAlpha 0.4。橡皮 = 点选命中删除整条笔画（不做像素擦除）。撤销/重做 = 双栈。清空 = 清当前页 strokes。
- **文本批注**：批注模式下点击画布放置锚点，右栏自动新建批注卡进入编辑；支持编辑、删除、标记已解决（置灰折叠）；锚点与卡片双向定位。
- 每次标注变更后 **1s 防抖自动保存**（PUT annotations），无手动保存按钮。

### 4.4 图表按需解析流程

- 导入上传完成（页面渲染秒级）→ 立即进入阅读器；检测在**后台线程**执行，前端轮询 `status`，图框逐批浮现
- 点击图框 → `POST parse`（同步 10–20s，面板 loading）→ 右侧"图表"页签展示四件套；失败显示错误与**重试**按钮
- 已解析图表重点击：直接读缓存展示，零推理

## 5. 数据结构

### 5.1 annotations.json（侧车，与 session.json 并列）

```json
{
  "version": 1,
  "pages": {
    "3": {
      "strokes": [
        {"id": "s-8f3a", "tool": "pen", "color": "#CC2936", "width": 2.0,
         "points": [[0.12, 0.30], [0.13, 0.31]]}
      ],
      "comments": [
        {"id": "c-21b7", "x": 0.52, "y": 0.18, "text": "这个基线数据存疑",
         "resolved": false, "created_at": "2026-10-19T22:40:00", "updated_at": "2026-10-19T22:41:00"}
      ]
    }
  }
}
```

- 坐标归一化 0-1（相对页面宽/高），缩放与 DPI 变化稳健
- 无标注页面不写条目；全空时文件为 `{"version":1,"pages":{}}`

### 5.2 pipeline 新入口签名

```python
PaperPipeline.render_and_detect(pdf_path, progress=None) -> PaperStore
    # 渲染页面 → VL grounding 检测（页级降级位图）→ 裁剪 → 写 session.json
    # figures 全部 parse_status="pending"，不做数据解析
PaperPipeline.parse_figure(store, figure_id) -> dict
    # 单张：vision.parser → validator（重试1次）→ generator → executor → 更新 session.json
    # 返回该 figure 条目的完整结果（chart/code_path/render_path/error）
```

旧 `run()` 保留原行为与 stage 语义（供 legacy gradio），内部可复用新方法。

### 5.3 session.json stage 语义扩展

`detecting | ready | parsing | done | failed`——`ready` 为新增：检测完成、等待按需解析。`parsing/done` 仅旧 run() 全量路径使用。figure 条目字段不变（parse_status ∈ pending|done|error；render_status ∈ pending|done|failed）。

## 6. 后端 API（FastAPI）

| 方法/路径 | 说明 |
|---|---|
| `POST /api/papers` | multipart `file` + `detect:bool=true` → `{pdf_hash, file_name, n_pages, truncated}`；detect=true 时后台线程启动检测 |
| `GET /api/papers/{h}/status` | `{stage, detect_done, detect_total, n_figures}`（前端轮询） |
| `GET /api/papers/{h}/pages/{n}.png` | 页面 PNG（150 DPI） |
| `GET /api/papers/{h}/figures` | figure 条目列表（含 bbox_px/type/parse_status/error） |
| `POST /api/papers/{h}/figures/{fid}/parse` | 按需解析 → `{parse_status, chart, code_path, render_path, error}` |
| `GET /api/papers/{h}/annotations` | 读 annotations.json（不存在返回空骨架） |
| `PUT /api/papers/{h}/annotations` | 全量写入（前端防抖自动保存），原子写 |
| `POST /api/papers/{h}/export` | 导出叠加标注 PDF 副本 → 文件下载（exports/annotated-<name>.pdf） |
| `POST /api/singles/parse` | 工具箱单图：multipart `file` → 四件套（复用 run_single） |
| `GET /api/health` | `{ollama: bool, model: bool, model_name}` |

静态挂载：`/` → app/reader/index.html；`/static/*` → 前端资源；`/cache/*` → data/cache（页面图/裁剪图/复刻图/代码直接引用）。

## 7. 导出实现

PyMuPDF 打开原 PDF；逐页把该页 strokes 用 PIL 按归一化坐标重绘到透明 RGBA 图层（尺寸=页面渲染像素），`page.insert_image` 叠加；comments 用 `page.add_text_annot` 写为 PDF 标准便签注释（图标位于锚点，内容为批注文本）；保存到 `exports/annotated-<原名>.pdf`。原 PDF 与 annotations.json 不受影响。

## 8. 错误处理

| 场景 | 处理 |
|---|---|
| Ollama 不可达/模型缺失 | ribbon 状态灯红；检测与解析按钮禁用，提示 `ollama pull qwen2.5vl:3b` 与 CHART_SDK_MODEL |
| 检测某页失败 | 仅该页无图框，状态接口记录，不阻塞其他页 |
| 单张解析失败 | 图框红、面板错误信息 + 重试按钮；不影响其他图表与标注 |
| 标注保存失败 | toast 提示；内存标注保留，下次变更重试保存 |
| 导出失败 | toast 提示原因，论文与标注不受影响 |
| 大 PDF | 沿用 30 页上限，超出截断并提示 |

## 9. 测试策略

- **SDK 单测**：render_and_detect/parse_figure 拆分行为（mock VL）；AnnotationStore 读写/空骨架/原子写；export 合成 PDF+假标注 → 输出页数一致、含 annotation
- **API 集成测试**（FastAPI TestClient，VL 走 mock，Ollama 不可用项 skip）：上传合成 PDF → status 轮询 → figures → parse → annotations 读写往返 → export 下载
- **selfcheck 扩展**：新增"API 冒烟"项（子进程起 server → GET /api/health 返回 200）
- **前端**：README 手动验收清单（导入/画框/墨迹四工具/批注增删改/自动保存刷新恢复/按需解析/导出/工具箱）

## 10. 配置与依赖

新增配置：`CHART_SDK_API_PORT`（默认 8000）。新增依赖：`fastapi`、`uvicorn`、`python-multipart`。前端零依赖（原生 HTML/CSS/JS）。

## 11. 范围边界（YAGNI）

不做：正文提取/OCR、PDF 文本层选择与复制、多用户/并发、压感、批注嵌套回复、云端同步、移动端适配、评测数据集（仍留后续迭代）。

## 12. 交付物

`app/server.py` + `app/reader/` 前端 + `chart_sdk/annotate/` + pipeline 拆分 + 测试 + selfcheck 扩展 + README 更新（阅读器使用手册/手动验收清单/legacy 说明）。
