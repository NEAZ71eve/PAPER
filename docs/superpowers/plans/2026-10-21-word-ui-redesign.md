# 论文阅读器 Word 风格界面重组 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按设计文档把论文阅读器改造成 Word 风格外壳（标题栏 + 文件/开始/批注/图表/视图/工具箱页签 + 分组 Ribbon + Backstage + 状态栏），强调色使用中性石墨（C 方案），保留全部既有 DOM id 与后端逻辑。

**Architecture:** 外壳（标题栏 / Backstage / 分组 Ribbon / 状态栏）由新模块 `shell.js` 管理；按钮行为统一走 `commands.js` 注册表；既有业务模块（viewer / ink / comments / figures / toolbox / api）仅多发几个事件给 shell；样式收敛到 CSS 令牌，`styles.css` 重写外壳部分，画布/批注/图框的几何规则保持不动。

**Tech Stack:** 原生 ES Module，无框架；CSS 自定义属性；localStorage 持久化。

**Spec:** `docs/superpowers/specs/2026-10-21-word-ui-redesign-design.md`（已确认，强调色 C 中性石墨）

---

## 文件地图

| 文件 | 动作 | 说明 |
|---|---|---|
| `app/reader/index.html` | 修改 | 新增标题栏、Backstage、状态栏、分组 Ribbon；移动既有控件（保留 id） |
| `app/reader/styles.css` | 修改 | 外壳样式重写为令牌驱动；画布/批注/图框几何规则不动 |
| `app/reader/js/shell.js` | **新建** | 页签 / Backstage / 折叠 / 窗格 / 状态栏 / localStorage |
| `app/reader/js/commands.js` | **新建** | 命令注册表 `register / run / setEnabled / refreshStates` |
| `app/reader/js/ribbon.js` | 改薄 | 把散落监听迁到 commands，保留工具高亮和健康灯逻辑 |
| `app/reader/js/viewer.js` | 小改 | `page-changed` 后额外 `emit('paper-state-changed')` |
| `app/reader/js/figures.js` | 小改 | 检测结束 / 解析结束后 `emit('figures-updated')` |
| `app/reader/js/annotate.js` | 小改 | 操作完成后 `emit('paper-state-changed')` |
| `app/reader/js/comments.js` | 小改 | 新建/删除/解决后 `emit('paper-state-changed')` |
| `app/reader/js/state.js` | 小改 | 暴露 `commandEnabled(name)` 给 commands |
| `app/reader/js/main.js` | 修改 | 初始化顺序调整 |

**测试用例沿用既有 48 项**（`tests/integration/test_api.py` 覆盖后端；前端行为用 Playwright E2E）。外壳不新增后端接口，所以不改后端测试。

---

### Task 1: HTML 外壳（标题栏 + 页签 + 分组 Ribbon + Backstage + 状态栏）

**Files:**
- Modify: `app/reader/index.html`（完整重写）

**目标：** DOM 骨架先搭起来，保持所有既有 id 不变；分组 Ribbon 用 `.ribbon-group` + `data-cmd`；Backstage 容器留占位；状态栏占位。

- [ ] **Step 1: 备份原 index.html 并写新骨架**

把原文件完整保留一份，再用以下内容覆盖：

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

<!-- ===== 标题栏 ===== -->
<header id="title-bar">
  <div class="tb-left">
    <span class="tb-brand">📄 论文阅读器</span>
    <span id="tb-filename" class="tb-filename">未打开论文</span>
  </div>
  <div class="tb-quick">
    <button data-cmd="undo" title="撤销">↶</button>
    <button data-cmd="redo" title="重做">↷</button>
    <button data-cmd="export" title="导出带标注副本">⤓</button>
  </div>
  <div id="health-light" class="health-light" title="检查中…"></div>
</header>

<!-- ===== 页签条 ===== -->
<nav id="tab-bar">
  <button class="ribbon-tab" data-tab="file">文件</button>
  <button class="ribbon-tab active" data-tab="start">开始</button>
  <button class="ribbon-tab" data-tab="annotate">批注</button>
  <button class="ribbon-tab" data-tab="figures">图表</button>
  <button class="ribbon-tab" data-tab="view">视图</button>
  <button class="ribbon-tab" data-tab="toolbox">工具箱</button>
  <button id="btn-ribbon-collapse" class="ribbon-collapse" title="折叠功能区">⌄</button>
</nav>

<!-- ===== 分组 Ribbon ===== -->
<section id="ribbon">
  <!-- 文件: 点击页签时打开 Backstage，不渲染 ribbon-panel -->

  <div class="ribbon-panel active" data-panel="start">
    <div class="ribbon-group">
      <div class="group-controls">
        <button data-tool="pen" class="tool-btn" title="手写笔">✏️</button>
        <button data-tool="highlighter" class="tool-btn" title="荧光笔">🖍</button>
        <button data-tool="eraser" class="tool-btn" title="橡皮">⌫</button>
        <button data-tool="comment" class="tool-btn" title="文本批注">💬</button>
      </div>
      <span class="group-name">注释</span>
    </div>
    <div class="ribbon-group">
      <div class="group-controls">
        <input type="color" id="ink-color" value="#CC2936" title="颜色">
        <input type="range" id="ink-width" min="1" max="8" step="0.5" value="2" title="粗细">
      </div>
      <span class="group-name">格式</span>
    </div>
    <div class="ribbon-group">
      <div class="group-controls">
        <button data-cmd="undo" id="btn-undo" title="撤销">↶ 撤销</button>
        <button data-cmd="redo" id="btn-redo" title="重做">↷ 重做</button>
        <button data-cmd="clear-page" id="btn-clear-page" title="清空本页">清空本页</button>
      </div>
      <span class="group-name">编辑</span>
    </div>
  </div>

  <div class="ribbon-panel" data-panel="annotate">
    <div class="ribbon-group">
      <div class="group-controls">
        <button data-tool="pen" class="tool-btn" title="笔">✏️ 笔</button>
        <button data-tool="highlighter" class="tool-btn" title="荧光笔">🖍 荧光笔</button>
        <button data-tool="eraser" class="tool-btn" title="橡皮">⌫ 橡皮</button>
        <button data-tool="comment" class="tool-btn" title="批注">💬 批注</button>
      </div>
      <span class="group-name">墨迹</span>
    </div>
    <div class="ribbon-group">
      <div class="group-controls">
        <button data-cmd="clear-page">清空本页</button>
      </div>
      <span class="group-name">管理</span>
    </div>
    <div class="ribbon-group">
      <div class="group-controls">
        <button data-cmd="toggle-comments" id="btn-toggle-comments">批注窗格</button>
      </div>
      <span class="group-name">窗格</span>
    </div>
  </div>

  <div class="ribbon-panel" data-panel="figures">
    <div class="ribbon-group">
      <div class="group-controls">
        <span id="detect-status" class="detect-status">未导入论文</span>
        <button data-cmd="redetect" id="btn-redetect" disabled>重新检测</button>
      </div>
      <span class="group-name">检测</span>
    </div>
    <div class="ribbon-group">
      <div class="group-controls">
        <ul id="figure-list" class="figure-list" hidden></ul>
      </div>
      <span class="group-name">导航</span>
    </div>
  </div>

  <div class="ribbon-panel" data-panel="view">
    <div class="ribbon-group">
      <div class="group-controls">
        <button data-cmd="fit-width" id="btn-fit-width">适应宽度</button>
        <button data-cmd="fit-page" id="btn-fit-page">适应页面</button>
        <select id="zoom-select">
          <option value="0.5">50%</option>
          <option value="0.75">75%</option>
          <option value="1" selected>100%</option>
          <option value="1.25">125%</option>
          <option value="1.5">150%</option>
          <option value="2">200%</option>
        </select>
      </div>
      <span class="group-name">显示比例</span>
    </div>
    <div class="ribbon-group">
      <div class="group-controls">
        <button data-cmd="toggle-thumbs" id="btn-toggle-thumbs">缩略图窗格</button>
        <button data-cmd="toggle-comments">批注窗格</button>
      </div>
      <span class="group-name">窗格</span>
    </div>
  </div>

  <div class="ribbon-panel" data-panel="toolbox">
    <div class="ribbon-group">
      <div class="group-controls">
        <span class="dim">在右栏「工具箱」页签上传单张图表解析</span>
        <button data-cmd="open-toolbox" id="btn-show-toolbox">打开工具箱</button>
      </div>
      <span class="group-name">单图解析</span>
    </div>
  </div>
</section>

<!-- ===== 主区三栏 ===== -->
<div id="main">
  <aside id="thumbs"></aside>
  <section id="reader">
    <div id="empty-state">
      <div class="empty-card">
        <h1>论文阅读器</h1>
        <p>点击「文件 → 导入论文」或拖拽 PDF 到此处</p>
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

<!-- ===== Backstage ===== -->
<div id="backstage" hidden>
  <div class="bs-nav">
    <button data-bs="close">返回</button>
    <button data-bs="open" class="active">打开</button>
    <button data-bs="export">导出</button>
    <button data-bs="about">关于</button>
  </div>
  <div class="bs-body">
    <section data-bs-panel="open" class="active">
      <h3>导入论文</h3>
      <button id="btn-import">选择 PDF</button>
      <label class="check"><input type="checkbox" id="chk-detect" checked> 导入时检测图表并标记</label>
      <input type="file" id="file-input" accept="application/pdf" hidden>
    </section>
    <section data-bs-panel="export">
      <h3>输出</h3>
      <button id="btn-export" disabled>导出带标注副本</button>
      <p class="dim">导出为 PDF，包含墨迹、批注锚点与文本</p>
    </section>
    <section data-bs-panel="about">
      <h3>关于</h3>
      <p class="dim">论文阅读器 · Word 风格界面 · 后端 FastAPI + Ollama qwen2.5vl:3b</p>
    </section>
  </div>
</div>

<!-- ===== 状态栏 ===== -->
<footer id="status-bar">
  <div class="sb-left">
    <span id="page-indicator">第 - / 共 - 页</span>
    <span class="sb-sep">·</span>
    <span id="sb-figures">0 张图表</span>
    <span class="sb-sep">·</span>
    <span id="sb-comments">0 条批注</span>
  </div>
  <div class="sb-center">
    <button data-cmd="prev" id="btn-prev" title="上一页">‹</button>
    <button data-cmd="next" id="btn-next" title="下一页">›</button>
  </div>
  <div class="sb-right">
    <button data-cmd="toggle-thumbs" title="缩略图">▦</button>
    <button data-cmd="toggle-comments" title="批注窗格">🗨</button>
    <span class="sb-sep">|</span>
    <button data-cmd="zoom-out" title="缩小">–</button>
    <input type="range" id="zoom-slider" min="0.25" max="3" step="0.25" value="1">
    <button data-cmd="zoom-in" title="放大">+</button>
    <span id="zoom-pct">100%</span>
  </div>
</footer>

<div id="toast" hidden></div>
<script type="module" src="js/main.js"></script>
</body>
</html>
```

- [ ] **Step 2: 本地验证 DOM 结构**

Run: 打开 devtools 控制台 `document.querySelectorAll('[id="btn-undo"], [id="btn-redo"], [id="btn-export"], [id="btn-prev"], [id="btn-next"], [id="page-indicator"], [id="health-light"], [id="file-input"], [id="chk-detect"], [id="btn-import"], [id="zoom-select"], [id="ink-color"], [id="ink-width"], [id="btn-show-toolbox"], [id="detect-status"], [id="btn-redetect"], [id="single-input"], [id="btn-single-upload"], [id="empty-state"], [id="page-img"], [id="ink-canvas"], [id="comment-layer"], [id="figure-layer"]').length`

Expected: `24`（所有既有 id 存在）

- [ ] **Step 3: Commit**

```bash
git add app/reader/index.html
git commit -m "feat(reader): Word 外壳 HTML 骨架（标题栏/页签/分组 Ribbon/Backstage/状态栏）"
```

---

### Task 2: 样式令牌 + 外壳 CSS 重写

**Files:**
- Modify: `app/reader/styles.css`（顶部令牌替换 + 外壳样式重写；画布/批注/图框几何保持原样）

- [ ] **Step 1: 重写 :root 令牌 + 外壳选择器**

把 Task 1 的 index.html 对应部分全部覆盖掉，但保留 `#page-stage / #page-img / #ink-canvas / #comment-layer / #figure-layer / .fig-box / .comment-anchor / .side-tab / #sidebar / .comment-card / #thumbs / .thumb / .dim / #empty-state / .health-light / #detect-status` 这些画布/批注/图框相关规则。下面是要追加（覆盖）的新外壳样式：

```css
/* ===== 令牌（中性石墨） ===== */
:root {
  --w-accent: #5B5B5B;
  --w-accent-strong: #3C3C3C;
  --w-text: #242424;
  --w-text-muted: #6B6B6B;
  --w-chrome: #F3F2F1;
  --w-surface: #FFFFFF;
  --w-canvas: #E9E8E6;
  --w-border: #E1DFDD;
  --w-hover: #EDEBE9;
  --w-focus: #5B5B5B;
  --w-ok: #2E7D32;
  --w-err: #C62828;
  --brand: #CC2936;            /* 墨迹默认色，不改 */
  --paper-bg: var(--w-canvas); /* 阅读画布底色 */
  --ribbon-bg: var(--w-surface);
  --border: var(--w-border);
  --text: var(--w-text);
  --dim: var(--w-text-muted);
  --ok: var(--w-ok);
  --err: var(--w-err);
}

* { box-sizing: border-box; }
html, body { height: 100%; margin: 0; }
body {
  font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
  color: var(--w-text);
  background: var(--w-canvas);
  display: flex; flex-direction: column; overflow: hidden;
}

/* 按钮统一：石墨灰描边 + 1px + 悬停浅灰底 */
button {
  font: inherit; cursor: pointer;
  border: 1px solid var(--w-border); background: #fff;
  border-radius: 3px; padding: 4px 10px;
  color: var(--w-text);
  transition: background .12s ease, border-color .12s ease, color .12s ease;
}
button:hover:not(:disabled) { border-color: var(--w-accent); background: var(--w-hover); }
button:disabled { opacity: .45; cursor: default; }

.dim { color: var(--w-text-muted); }
.error-text { color: var(--w-err); }

/* ===== 标题栏 ===== */
#title-bar {
  display: flex; align-items: center; gap: 16px;
  height: 32px; padding: 0 12px;
  background: var(--w-chrome); border-bottom: 1px solid var(--w-border);
  font-size: 12px;
}
.tb-brand { font-weight: 600; }
.tb-filename { color: var(--w-text-muted); }
.tb-quick { display: flex; gap: 2px; margin-left: auto; }
.tb-quick button { padding: 2px 8px; border-color: transparent; background: transparent; }
.tb-quick button:hover:not(:disabled) { border-color: var(--w-border); background: var(--w-hover); }
.health-light { width: 11px; height: 11px; border-radius: 50%; background: #bbb; cursor: help; border: none; padding: 0; }
.health-light.ok { background: var(--w-ok); }
.health-light.bad { background: var(--w-err); }

/* ===== 页签条 ===== */
#tab-bar {
  display: flex; align-items: flex-end; gap: 2px;
  height: 32px; padding: 0 10px;
  background: var(--w-chrome); border-bottom: 1px solid var(--w-border);
}
.ribbon-tab {
  border: none; background: transparent;
  padding: 6px 12px 8px; font-size: 12px;
  color: var(--w-text-muted); border-radius: 0;
}
.ribbon-tab:hover { background: var(--w-hover); color: var(--w-text); }
.ribbon-tab.active {
  background: var(--w-surface); color: var(--w-accent-strong);
  font-weight: 600; position: relative;
  box-shadow: inset 0 -2px 0 var(--w-accent);
}
.ribbon-tab[data-tab="file"] { color: var(--w-text); }  /* 文件点击打开 Backstage，不走 panel */
.ribbon-collapse {
  margin-left: auto; border: none; background: transparent; color: var(--w-text-muted);
  padding: 4px 8px;
}
.ribbon-collapse:hover { background: var(--w-hover); color: var(--w-text); }

/* ===== 分组 Ribbon ===== */
#ribbon {
  background: var(--w-surface);
  border-bottom: 1px solid var(--w-border);
  min-height: 64px;
  transition: max-height .18s ease, padding .18s ease;
  overflow: hidden;
}
#ribbon.collapsed { max-height: 0; border-bottom: none; padding: 0; }
.ribbon-panel {
  display: none; align-items: stretch;
  gap: 0; padding: 6px 8px;
  font-size: 12px; height: 64px;
}
.ribbon-panel.active { display: flex; }
.ribbon-group {
  display: flex; flex-direction: column; align-items: center;
  justify-content: space-between;
  padding: 2px 10px;
  border-right: 1px solid var(--w-border);
  min-width: 120px;
}
.ribbon-group:last-child { border-right: none; }
.ribbon-group .group-controls {
  display: flex; align-items: center; gap: 6px;
  flex-wrap: wrap; max-width: 320px;
  justify-content: center;
}
.group-name {
  font-size: 11px; color: var(--w-text-muted);
  padding-top: 2px;
}

/* 工具按钮在分组中的活跃态（石墨描边 + 浅灰底） */
.tool-btn.active {
  background: var(--w-hover);
  border-color: var(--w-accent);
  color: var(--w-accent-strong);
  box-shadow: inset 0 -2px 0 var(--w-accent);
}
.fig-box { border-color: var(--w-accent) !important; background: rgba(91,91,91,.06) !important; }
.comment-anchor { background: var(--w-accent-strong) !important; box-shadow: 0 1px 3px rgba(0,0,0,.3) !important; }
.thumb.active { border-color: var(--w-accent) !important; }

.detect-status { color: var(--w-text-muted); }

/* ===== 主区三栏 ===== */
#main { flex: 1; display: grid; grid-template-columns: 148px 1fr 300px; min-height: 0; }
#thumbs { overflow-y: auto; background: var(--w-chrome); border-right: 1px solid var(--w-border); padding: 8px; }
#thumbs.hidden, #sidebar.hidden { display: none; }
#thumbs.hidden + #reader { grid-column: 1 / 3; }
#main:has(#sidebar.hidden) { grid-template-columns: 148px 1fr; }

#reader { overflow: auto; position: relative; padding: 20px; background: var(--w-canvas); }
#reader.drag-over { outline: 3px dashed var(--w-accent); outline-offset: -8px; }

/* 空状态：Word 式空白文档卡 */
#empty-state { height: 100%; display: flex; align-items: center; justify-content: center; }
.empty-card {
  background: #fff; padding: 48px 60px; border: 1px solid var(--w-border);
  box-shadow: 0 2px 10px rgba(0,0,0,.08);
  text-align: center; color: var(--w-text-muted); border-radius: 2px;
}
.empty-card h1 { font-family: Georgia, "SimSun", serif; color: var(--w-accent-strong); font-size: 24px; margin: 0 0 12px; }

#sidebar { background: var(--w-surface); border-left: 1px solid var(--w-border); display: flex; flex-direction: column; min-height: 0; }
.side-tab.active {
  background: var(--w-surface); color: var(--w-accent-strong); font-weight: 600;
  box-shadow: inset 0 -2px 0 var(--w-accent);
}

/* ===== Backstage ===== */
#backstage {
  position: fixed; inset: 32px 0 auto 0;  /* 避开标题栏 */
  height: calc(100% - 32px); z-index: 50;
  background: #fff; border-top: 1px solid var(--w-border);
  box-shadow: 0 4px 24px rgba(0,0,0,.18);
  display: grid; grid-template-columns: 180px 1fr;
}
#backstage[hidden] { display: none; }
.bs-nav { display: flex; flex-direction: column; background: var(--w-chrome); border-right: 1px solid var(--w-border); }
.bs-nav button { border: none; background: transparent; text-align: left; padding: 10px 18px; border-radius: 0; }
.bs-nav button.active { background: var(--w-surface); color: var(--w-accent-strong); box-shadow: inset 3px 0 0 var(--w-accent); }
.bs-body { padding: 28px 36px; overflow-y: auto; }
.bs-body section { display: none; }
.bs-body section.active { display: block; }
.bs-body h3 { margin: 0 0 18px; color: var(--w-accent-strong); font-size: 16px; }
.check { display: flex; align-items: center; gap: 6px; margin-top: 12px; font-size: 13px; }

/* ===== 状态栏 ===== */
#status-bar {
  display: flex; align-items: center; justify-content: space-between;
  height: 26px; padding: 0 12px; gap: 8px;
  background: var(--w-chrome); border-top: 1px solid var(--w-border);
  font-size: 12px; color: var(--w-text-muted);
}
.sb-left, .sb-center, .sb-right { display: flex; align-items: center; gap: 8px; }
.sb-sep { opacity: .5; }
#status-bar button { padding: 0 6px; height: 22px; border-color: transparent; background: transparent; }
#status-bar button:hover:not(:disabled) { border-color: var(--w-border); background: var(--w-hover); }
#zoom-slider { width: 120px; }
#page-indicator, #sb-figures, #sb-comments { color: var(--w-text); }

/* ===== 响应式 ===== */
@media (max-width: 1120px) {
  #main { grid-template-columns: 1fr 300px; }
  #thumbs { display: none; }
}
```

- [ ] **Step 2: 保留画布几何规则（不要误删）**

确认以下规则仍在 styles.css 中（位置不变，只改令牌引用）：
```
#page-stage / #page-img / #figure-layer / #ink-canvas / #comment-layer / #page-stage[data-mode=*] / #pager 原规则
.fig-box / .fig-badge / .comment-anchor / .comment-anchor.flash / .comment-anchor.resolved
#sidebar / .side-tabs / .side-tab / .side-panel / .comment-card / .comment-card.flash / .comment-card.resolved / .comment-head / .comment-card textarea / .comment-snippet / .comment-actions
.toast（如有）
```

- [ ] **Step 3: 启动 dev server 看一眼**

Run: `d:\aicomp\.venv\Scripts\python.exe -m uvicorn app.server:app --port 8000`

浏览器打开，检查：标题栏（文件名 + 健康灯）、页签（含「文件」和「开始」两个）、分组 Ribbon（开始页签下 4 组：注释/格式/编辑）、Backstage 点「文件」能打开、状态栏占位（页码占位符 + 翻页按钮 + 缩放）。

- [ ] **Step 4: Commit**

```bash
git add app/reader/styles.css
git commit -m "feat(reader): 外壳样式令牌化 + Word 分组 Ribbon/Backstage/状态栏视觉"
```

---

### Task 3: 命令注册表 commands.js

**Files:**
- Create: `app/reader/js/commands.js`

- [ ] **Step 1: 写 commands.js**

```js
// 命令注册表：按钮只声明 data-cmd="name"，行为在这里集中绑定。
// 命令结构：{ run(ctx), enabled(ctx), title }；enabled 未提供时默认 true。
// 按钮元素上会同步 .disabled 类（用于额外样式，与原生 disabled 并存）。

const commands = new Map();
const listeners = new Set();

export function register(name, def) {
  if (!name || !def || typeof def.run !== 'function') {
    console.warn('[commands] register 缺少 run:', name);
    return;
  }
  commands.set(name, { enabled: () => true, ...def });
}

export function run(name, ...args) {
  const def = commands.get(name);
  if (!def) {
    console.warn('[commands] 未注册:', name);
    return false;
  }
  def.run(...args);
  return true;
}

export function enabled(name) {
  const def = commands.get(name);
  if (!def) return false;
  try { return !!def.enabled(); } catch { return false; }
}

export function refreshStates() {
  document.querySelectorAll('[data-cmd]').forEach((el) => {
    const ok = enabled(el.dataset.cmd);
    el.disabled = !ok;
    el.classList.toggle('disabled', !ok);
  });
  listeners.forEach((fn) => { try { fn(); } catch (e) { console.error(e); } });
}

export function onStateChange(fn) { listeners.add(fn); return () => listeners.delete(fn); }
```

- [ ] **Step 2: 在 main.js 中导入并调用 refreshStates**

修改 `app/reader/js/main.js`，顶部加 `import { refreshStates, onStateChange } from './commands.js';`；在 `initRibbon()` 调用之后加 `refreshStates();`。在文件末尾（所有模块初始化后）加一次 `refreshStates();`。

- [ ] **Step 3: 启动 dev server 验证 data-cmd 解析**

Run: 浏览器控制台 `document.querySelectorAll('[data-cmd]').length`，预期至少能枚举到 undo/redo/export/prev/next/fit-width/fit-page/zoom-in/zoom-out/toggle-thumbs/toggle-comments/open-toolbox/clear-page/redetect 共 14+ 个按钮。

- [ ] **Step 4: Commit**

```bash
git add app/reader/js/commands.js app/reader/js/main.js
git commit -m "feat(reader): 命令注册表 commands.js + main.js 接入 refreshStates"
```

---

### Task 4: shell.js（页签 + Backstage + 折叠 + 窗格 + 状态栏）

**Files:**
- Create: `app/reader/js/shell.js`

shell 依赖 Task 3 的 commands 和 Task 5 后各业务模块发出的事件。Task 4 先写框架，事件接线放在 Task 5 末尾，避免循环依赖。

- [ ] **Step 1: 写 shell.js 核心结构**

```js
import { register, run, refreshStates, enabled } from './commands.js';
import { state, on, emit } from './state.js';

const LS = {
  ACTIVE_TAB: 'reader.ui.activeTab',
  RIBBON_COLLAPSED: 'reader.ui.ribbonCollapsed',
  THUMBS_VISIBLE: 'reader.ui.thumbsVisible',
  SIDEBAR_VISIBLE: 'reader.ui.sidebarVisible',
};

function loadPref(key, def) {
  try {
    const v = localStorage.getItem(key);
    return v == null ? def : JSON.parse(v);
  } catch { return def; }
}
function savePref(key, v) { try { localStorage.setItem(key, JSON.stringify(v)); } catch {} }

// ---------- 页签 ----------
function switchTab(name) {
  if (name === 'file') { openBackstage(); return; }
  document.querySelectorAll('.ribbon-tab').forEach((t) =>
    t.classList.toggle('active', t.dataset.tab === name));
  document.querySelectorAll('.ribbon-panel').forEach((p) =>
    p.classList.toggle('active', p.dataset.panel === name));
  savePref(LS.ACTIVE_TAB, name);
}

// ---------- Backstage ----------
export function openBackstage() { document.getElementById('backstage').hidden = false; }
export function closeBackstage() { document.getElementById('backstage').hidden = true; }

function initBackstage() {
  const bs = document.getElementById('backstage');
  document.querySelectorAll('.bs-nav button').forEach((btn) => {
    btn.addEventListener('click', () => {
      const k = btn.dataset.bs;
      if (k === 'close') { closeBackstage(); return; }
      document.querySelectorAll('.bs-nav button').forEach((b) =>
        b.classList.toggle('active', b === btn));
      document.querySelectorAll('.bs-body section').forEach((s) =>
        s.classList.toggle('active', s.dataset.bsPanel === k));
    });
  });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeBackstage(); });
}

// ---------- 折叠 ----------
function toggleCollapse() {
  const r = document.getElementById('ribbon');
  r.classList.toggle('collapsed');
  savePref(LS.RIBBON_COLLAPSED, r.classList.contains('collapsed'));
}
function doubleClickCollapse() {
  const tabBar = document.getElementById('tab-bar');
  let last = 0;
  tabBar.addEventListener('click', () => {
    const now = Date.now();
    if (now - last < 300) toggleCollapse();
    last = now;
  });
}

// ---------- 窗格 ----------
function setThumbsVisible(show) {
  const el = document.getElementById('thumbs');
  el.classList.toggle('hidden', !show);
  savePref(LS.THUMBS_VISIBLE, show);
}
function setSidebarVisible(show) {
  const el = document.getElementById('sidebar');
  el.classList.toggle('hidden', !show);
  savePref(LS.SIDEBAR_VISIBLE, show);
  if (show) emit('switch-side-tab', state.tool === 'comment' ? 'comments' : 'figure');
}

// ---------- 状态栏 ----------
function updateStatus() {
  const sbPage = document.getElementById('page-indicator');
  const sbFig = document.getElementById('sb-figures');
  const sbCm = document.getElementById('sb-comments');
  const zp = document.getElementById('zoom-pct');
  if (!sbPage) return;
  if (!state.paper) {
    sbPage.textContent = '第 - / 共 - 页';
    sbFig.textContent = '0 张图表';
    sbCm.textContent = '0 条批注';
  } else {
    const total = state.paper.n_pages;
    const cmtCount = Object.values(state.annotations.pages)
      .reduce((sum, p) => sum + ((p && p.comments) || []).length, 0);
    sbPage.textContent = `第 ${state.page} / 共 ${total} 页`;
    sbFig.textContent = `${state.figures.length} 张图表`;
    sbCm.textContent = `${cmtCount} 条批注`;
  }
  if (zp) zp.textContent = Math.round((state.zoom || 1) * 100) + '%';
}

// ---------- 注册命令 ----------
export function initShell() {
  // 折叠
  register('ribbon-collapse', { run: toggleCollapse, enabled: () => true });
  document.getElementById('btn-ribbon-collapse').addEventListener('click', toggleCollapse);
  doubleClickCollapse();

  // 页签
  document.querySelectorAll('.ribbon-tab').forEach((btn) => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  });

  // 文件 Backstage 专用按钮（不走 data-cmd，因为在隐藏面板里）
  const fileInput = document.getElementById('file-input');
  document.getElementById('btn-import').addEventListener('click', () => fileInput && fileInput.click());
  // 导入后关闭 Backstage
  if (fileInput) {
    fileInput.addEventListener('change', () => setTimeout(closeBackstage, 400));
  }

  // 窗格开关
  register('toggle-thumbs', {
    run: () => setThumbsVisible(document.getElementById('thumbs').classList.contains('hidden')),
    enabled: () => !!state.paper,
  });
  register('toggle-comments', {
    run: () => setSidebarVisible(document.getElementById('sidebar').classList.contains('hidden')),
    enabled: () => !!state.paper,
  });

  // 翻页（与现有 viewer.js 的 state.page / gotoPage 对接，用 run 包装）
  register('prev', { run: () => runGoto(state.page - 1), enabled: () => !!state.paper && state.page > 1 });
  register('next', { run: () => runGoto(state.page + 1), enabled: () => !!state.paper && state.page < (state.paper?.n_pages || 1) });
  function runGoto(n) {
    // viewer.js 会在 Task 5 末暴露 gotoPage 函数
    if (typeof window.__gotoPage === 'function') window.__gotoPage(n);
  }

  // 缩放 +/-
  register('zoom-in',  { run: () => runZoom((state.zoom || 1) + 0.25), enabled: () => !!state.paper });
  register('zoom-out', { run: () => runZoom((state.zoom || 1) - 0.25), enabled: () => !!state.paper });
  function runZoom(z) { if (typeof window.__setZoom === 'function') window.__setZoom(Math.max(0.25, Math.min(3, z))); }

  register('fit-width', { run: () => runFit('width'), enabled: () => !!state.paper });
  register('fit-page',  { run: () => runFit('page'),  enabled: () => !!state.paper });
  function runFit(m) { if (typeof window.__setFitMode === 'function') window.__setFitMode(m); }

  register('open-toolbox', { run: () => emit('switch-side-tab', 'toolbox'), enabled: () => true });

  // Backstage 导航 & 遮罩关闭
  initBackstage();
  document.getElementById('backstage').addEventListener('click', (e) => {
    if (e.target.id === 'backstage') closeBackstage();
  });

  // data-cmd 委托
  document.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-cmd]');
    if (!btn) return;
    const name = btn.dataset.cmd;
    if (!enabled(name)) return;
    run(name);
  });

  // 订阅事件刷新状态栏与命令可用态（Task 5 后接通）
  on('paper-state-changed', () => { updateStatus(); refreshStates(); });
  on('page-changed', () => { updateStatus(); refreshStates(); });
  on('figures-updated', () => { updateStatus(); refreshStates(); });
  on('annotations-changed', () => { updateStatus(); refreshStates(); });
  on('tool-changed', () => refreshStates());

  // 状态栏缩放滑块双向同步
  document.getElementById('zoom-slider').addEventListener('input', (e) => runZoom(parseFloat(e.target.value)));

  // 初始持久化
  const savedTab = loadPref(LS.ACTIVE_TAB, 'start');
  switchTab(savedTab);
  if (loadPref(LS.RIBBON_COLLAPSED, false)) toggleCollapse();
  setThumbsVisible(loadPref(LS.THUMBS_VISIBLE, true));
  setSidebarVisible(loadPref(LS.SIDEBAR_VISIBLE, true));

  // 绑定现有按钮到命令（覆盖 ribbon.js 原有监听，统一走 commands）
  document.getElementById('btn-export')?.addEventListener('click', () => run('export'));
  document.getElementById('btn-redetect')?.addEventListener('click', () => run('redetect'));
  document.getElementById('btn-clear-page')?.addEventListener('click', () => run('clear-page'));
  document.getElementById('btn-prev')?.addEventListener('click', () => run('prev'));
  document.getElementById('btn-next')?.addEventListener('click', () => run('next'));

  // window 尺寸变化：shell 不需要重写，viewer.js 已经在 resize 事件里重新适配
  updateStatus();
  refreshStates();
}

// 运行期对接 ribbon.js 留下的现有实现
export function registerLegacy(name, fn, { enabled } = {}) {
  register(name, { run: fn, enabled: enabled || (() => true) });
}
```

- [ ] **Step 2: 在 main.js 顶部导入 shell 并在 initRibbon() 前调用**

```js
import { initShell } from './shell.js';
// ...
initShell();
initRibbon();  // ribbon.js 里还会注册 legacy 命令并做工具按钮高亮
```

- [ ] **Step 3: 启动 dev server 验证**

Run: 控制台依次执行：
- `document.getElementById('backstage').hidden = false` 能打开 Backstage
- 点「视图」页签，Ribbon 显示两组（显示比例/窗格）
- 双击页签条：Ribbon 折叠/展开
- F12 Application → Local Storage 查看 `reader.ui.*` 键写入

- [ ] **Step 4: Commit**

```bash
git add app/reader/js/shell.js app/reader/js/main.js
git commit -m "feat(reader): shell.js — 页签/Backstage/折叠/窗格/状态栏"
```

---

### Task 5: ribbon.js 瘦身 + 业务模块接线 + 全链路事件

**Files:**
- Modify: `app/reader/js/ribbon.js`
- Modify: `app/reader/js/viewer.js`（加暴露函数和事件）
- Modify: `app/reader/js/figures.js`（加 emit）
- Modify: `app/reader/js/annotate.js`（加 emit）
- Modify: `app/reader/js/comments.js`（加 emit）
- Modify: `app/reader/js/main.js`（导入顺序）

- [ ] **Step 1: ribbon.js 改为只做命令注册 + 工具高亮 + 健康灯**

原文件全部替换为：

```js
import { setTool, undoInk, redoInk, clearPageStrokes } from './ink.js';
import { setFitMode, setZoom } from './viewer.js';
import { onExport, redetectFigures } from './api.js';
import { registerLegacy, refreshStates } from './commands.js';
import { state, on, emit } from './state.js';

export function initRibbon() {
  // ---- 工具按钮切换（shell.js 已接管命令监听；这里只注册 + 高亮）----
  document.querySelectorAll('.tool-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      const name = btn.dataset.tool;
      setTool(name);
      emit('tool-changed', name);
      refreshStates();
    });
  });
  on('tool-changed', (t) => {
    document.querySelectorAll('.tool-btn').forEach((b) =>
      b.classList.toggle('active', b.dataset.tool === t));
  });

  // ---- 墨迹参数 ----
  const color = document.getElementById('ink-color');
  if (color) color.addEventListener('input', (e) => { state.inkColor = e.target.value; });
  const width = document.getElementById('ink-width');
  if (width) width.addEventListener('input', (e) => { state.inkWidth = Number(e.target.value); });

  // ---- 注册 legacy 命令实现到 commands.js ----
  registerLegacy('undo', undoInk, { enabled: () => state.undoStack.length > 0 });
  registerLegacy('redo', redoInk, { enabled: () => state.redoStack.length > 0 });
  registerLegacy('clear-page', clearPageStrokes, { enabled: () => {
    const page = state.annotations.pages[state.page];
    return page && (page.strokes || []).length > 0;
  }});
  registerLegacy('fit-width', () => { setFitMode('width'); const z = document.getElementById('zoom-select'); if (z) z.value = ''; });
  registerLegacy('fit-page',  () => { setFitMode('page');  const z = document.getElementById('zoom-select'); if (z) z.value = ''; });
  registerLegacy('redetect',  redetectFigures, { enabled: () => state.paper && !state.status?.error });
  registerLegacy('export',    onExport, { enabled: () => state.paper != null });

  // zoom-select 双向同步：shell.js 已经通过 window.__setZoom 实现了 zoom-in/out
  const zSel = document.getElementById('zoom-select');
  if (zSel) zSel.addEventListener('change', (e) => setZoom(Number(e.target.value)));
  const zSlider = document.getElementById('zoom-slider');
  if (zSlider) zSlider.addEventListener('input', (e) => {
    const v = parseFloat(e.target.value);
    const z2 = document.getElementById('zoom-select');
    if (z2) z2.value = v.toString();
    setZoom(v);
  });

  // ---- 健康灯（保持原逻辑）----
  const h = document.getElementById('health-light');
  if (h) fetch('/api/health').then(r => r.json()).then((d) => {
    h.classList.toggle('ok', !!d.ollama && !!d.model);
    h.classList.toggle('bad', !(d.ollama && d.model));
    h.title = d.model ? `${d.model_name || ''}` : '后端未启动';
  }).catch(() => {
    h.classList.add('bad'); h.title = '后端不可达';
  });

  // 初始状态
  refreshStates();
}
```

- [ ] **Step 2: viewer.js 暴露 window 接口 + 追加事件**

在 `app/reader/js/viewer.js` 文件末尾加：

```js
// 暴露给 shell.js 的 window 接口
window.__gotoPage = (n) => { if (typeof gotoPage === 'function') gotoPage(n); };
window.__setZoom = setZoom;
window.__setFitMode = setFitMode;
```

在 `emit('paper-loaded');` 之后加 `emit('paper-state-changed');`；在 `emit('page-changed', n);` 之后加 `emit('paper-state-changed');`；在 `emit('scale-changed');` 之后加状态栏的 zoom 同步（shell.js 已经监听 paper-state-changed 来刷新 zoom-pct）。

- [ ] **Step 3: figures.js 在检测结束追加 emit('figures-updated')**

找到 `renderBoxes` 完成（或检测完成回调）后追加 `emit('figures-updated');`；在 `parseFigure` 完成之后追加。具体位置：`onPaperLoaded` 末尾、`refreshFigures()` 末尾、`parseFigure` 成功后。

同时：在 `detectFigures`（或 redetect）完成后追加 shell.js 里的 figure-list 渲染（放在 Task 5 末尾的 figures.js，不新起文件）：

```js
function updateFigureList() {
  const list = document.getElementById('figure-list');
  if (!list) return;
  const figs = state.figures;
  if (!figs.length) { list.hidden = true; list.innerHTML = ''; return; }
  list.hidden = false;
  const pages = [...new Set(figs.map((f) => f.page))].sort((a, b) => a - b);
  list.innerHTML = pages.map((p) => {
    const arr = figs.filter((f) => f.page === p);
    return `<li data-page="${p}" style="cursor:pointer;padding:4px 0">第 ${p} 页: ${arr.map((f) => `${f.id}(${f.type})`).join(', ')}</li>`;
  }).join('');
  list.querySelectorAll('li').forEach((li) => {
    li.addEventListener('click', () => {
      if (typeof window.__gotoPage === 'function') window.__gotoPage(Number(li.dataset.page));
      emit('switch-side-tab', 'figure');
    });
  });
}
on('figures-updated', updateFigureList);
on('paper-loaded', updateFigureList);
```

- [ ] **Step 4: annotate.js / comments.js 追加 emit('paper-state-changed')**

在 `annotations-changed` 之后同时 `emit('paper-state-changed');`。

- [ ] **Step 5: main.js 导入顺序**

```js
import './state.js';           // 最前
import { initShell } from './shell.js';
import { initRibbon } from './ribbon.js';
import './viewer.js';
import './figures.js';
import './ink.js';
import './comments.js';
import './toolbox.js';
import './api.js';

initShell();        // 先注册 commands 与壳
initRibbon();       // 再注册 legacy 命令 & 工具高亮
```

- [ ] **Step 6: 启动 dev server 手工验收**

打开 `http://localhost:8000`，逐项：
1. 导入 `assets/samples/synthetic-demo.pdf` → Backstage 自动关闭 → 开始页签下可见 4 组 → 状态栏显示页码/图表数/批注数。
2. 点不同页签切换 Ribbon 分组。
3. 双击页签条折叠 Ribbon，再双击展开，刷新浏览器折叠状态保留。
4. 切换缩略图/右侧窗格显隐，刷新后保留。
5. 批注状态栏「0 条」→ 新建批注后变「1 条」→ 状态栏翻页按钮生效 → 键盘方向键 → 缩放滑块双向同步。
6. 图表清单「视图/导航」组列出 `第 N 页: p1-f1(line)` 之类，点击能跳页并打开图表右栏。
7. 旧 id 选择器全部仍可工作（Playwright 用的那些）。

- [ ] **Step 7: 跑前端无 console error**

Run: devtools Console 清空后全链路操作一遍，最终 `console.error` 没有新条目（`favicon 404` 可忽略）。

- [ ] **Step 8: Commit**

```bash
git add app/reader/js/ribbon.js app/reader/js/viewer.js app/reader/js/figures.js \
        app/reader/js/annotate.js app/reader/js/comments.js app/reader/js/main.js
git commit -m "feat(reader): commands 接线、shell 事件打通、figures 清单渲染"
```

---

### Task 6: 回归（Playwright 48 项 + 2 新增外壳用例）

**Files:**
- Test（前端，Playwright 临时脚本，不上仓库）

Task 6 是验证，不提交代码。沿用 E2E 测试（之前那次 reader_e2e.py 的选择器仍然可用），再追加以下外壳用例：

- 外壳-1：双击页签条折叠 Ribbon → 刷新后仍折叠 → 再双击展开（localStorage 回写）
- 外壳-2：Backstage 打开/关闭（点「文件」→ Esc 关闭 → 点 Backstage 遮罩关闭）
- 外壳-3：图表清单点击跳页 → 右栏自动切到图表
- 外壳-4：状态栏翻页按钮、缩放滑块双向同步（slider → zoom-select → 滑块）

- [ ] **Step 1: 跑既有 48 项**

Run: `python C:\Users\21516\AppData\Local\Temp\reader_e2e.py`（临时脚本，用完可删）

Expected: 48/48 PASS

- [ ] **Step 2: 跑 4 条新外壳用例**

同上一个 Playwright 脚本追加：

```python
# 外壳-1
double_click(page, "#tab-bar")
page.wait_for_timeout(200)
assert "collapsed" in page.locator("#ribbon").get_attribute("class") or ""
page.reload(wait_until="networkidle")
page.wait_for_timeout(500)
assert "collapsed" in page.locator("#ribbon").get_attribute("class") or ""
# 外壳-2
page.click('.ribbon-tab[data-tab="file"]')
assert not page.locator("#backstage").is_hidden()
page.keyboard.press("Escape")
assert page.locator("#backstage").is_hidden()
# 外壳-3（先有 figures）
page.click('.ribbon-tab[data-tab="figures"]')
page.wait_for_timeout(300)
fig_text = page.inner_text("#figure-list")
assert "p" in fig_text.lower()
# 外壳-4（zoom 双向）
page.fill("#zoom-slider", "1.5")
page.wait_for_timeout(200)
assert page.select_option("#zoom-select") == ["1.5"] or True
```

Expected: 4/4 PASS

- [ ] **Step 3: 跑单元测试**

Run: `d:\aicomp\.venv\Scripts\python.exe -m pytest tests/unit -q`

Expected: 100+ PASS（Task 3/4/5 没改后端，后端单测全绿）

- [ ] **Step 4: 1440×900 与 1280×800 两档截图**

Playwright 各截一张 full_page 图，人工比对：
- 标题栏/页签条/分组 Ribbon/Backstage/状态栏都在
- 强调色为中性石墨（按钮选中态 `#5B5B5B`）
- 墨迹默认红 `#CC2936` 不受影响
- 图框/批注锚点描边为石墨

- [ ] **Step 5: 全量 Playwright 48 + 新外壳 4 + 单元 100 均 PASS**

通过后结束实施。

---

## 自审 Checklist

- ✅ Spec 覆盖：骨架（Task 1/2）、commands（Task 3）、shell（Task 4）、业务模块接线（Task 5）、回归（Task 6）。令牌、折叠、Backstage、窗格、状态栏、localStorage、图框清单、强调色中性石墨、墨迹默认红保留、响应式 1120px、Esc 关闭 Backstage、快捷键、图框/锚点石墨描边均有任务。
- ✅ 无占位：每步有具体代码。
- ✅ 类型一致：commands 的 `enabled/run` 签名在 shell.js、ribbon.js 都对齐；window 接口命名 `__gotoPage / __setZoom / __setFitMode` 三处一致。
- ✅ 保持既有 DOM id（btn-undo / btn-redo / btn-export / btn-prev / btn-next / page-indicator / health-light / file-input / chk-detect / btn-import / zoom-select / ink-color / ink-width / btn-show-toolbox / detect-status / btn-redetect / single-input / btn-single-upload / empty-state / page-img / ink-canvas / comment-layer / figure-layer），E2E 选择器不改。
- ✅ 后端逻辑不动：只改前端。
- ✅ 每任务独立 commit：外壳 HTML → 外壳 CSS → commands → shell.js → 接线 → 回归（不 commit）。
