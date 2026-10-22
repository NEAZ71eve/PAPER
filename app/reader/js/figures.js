// 图表：检测状态轮询 / 图框 DOM 层 / 点击按需解析 / 右栏四件套（设计文档 4.2、4.4）
import { state, on, emit, toast } from './state.js';
import { getStatus, getFigures, parseFigure, startDetect } from './api.js';

const $ = (id) => document.getElementById(id);
let pollTimer = null;
let gen = 0;                          // 论文代际：切论文后丢弃陈旧异步回调
const MAX_POLL_FAILS = 5;             // 连续状态请求失败上限
const MAX_POLL_MS = 15 * 60 * 1000;   // 兜底逃生：避免卡死时无限轮询（远大于正常最长检测时长，不误杀）
let pollFails = 0;
let pollStart = 0;

export function initFigures() {
  on('paper-loaded', onPaperLoaded);
  on('page-changed', renderBoxes);
  on('scale-changed', renderBoxes);
  on('figures-updated', updateFigureList);
  on('paper-loaded', updateFigureList);
}

const hash = () => state.paper.pdf_hash;

async function onPaperLoaded() {
  state.figures = [];
  resetFigurePanel();
  stopPolling();
  const g = ++gen, h = hash();
  try {
    const st = await getStatus(h);
    if (g !== gen) return;
    updateDetectStatus(st);
    if (st.stage === 'detecting') startPolling();
    else await refreshFigures(h, g);
  } catch (e) {
    if (g !== gen) return;
    $('detect-status').textContent = '状态获取失败';
  }
}

function startPolling() {
  stopPolling();
  pollFails = 0;
  pollStart = Date.now();
  pollTimer = setInterval(async () => {
    const g = gen, h = hash();
    try {
      const st = await getStatus(h);
      if (g !== gen) return;
      pollFails = 0;
      updateDetectStatus(st);
      if (st.stage !== 'detecting') {
        stopPolling();
        await refreshFigures(h, g);
        if (st.stage === 'ready') toast(`检测完成，标记 ${st.n_figures} 张图表`);
      } else if (Date.now() - pollStart > MAX_POLL_MS) {
        stopPolling();
        $('detect-status').textContent = '检测超时，可点「重新检测」';
      }
    } catch (e) {
      if (g !== gen) return;
      if (++pollFails >= MAX_POLL_FAILS) {
        stopPolling();
        $('detect-status').textContent = '状态获取失败，可点「重新检测」';
      }
    }
  }, 1000);
}

function stopPolling() { if (pollTimer) { clearInterval(pollTimer); pollTimer = null; } }

export async function redetectFigures() {
  if (!state.paper) return;
  const g = ++gen, h = hash();
  try {
    await startDetect(h);
    if (g !== gen) return;
    $('detect-status').textContent = '检测中…';
    state.figures = [];
    renderBoxes();
    startPolling();
  } catch (e) { if (g === gen) toast(`重新检测失败: ${e.message}`); }
  emit('figures-updated');
}

async function refreshFigures(h = hash(), g = gen) {
  try {
    const data = await getFigures(h);
    if (g !== gen) return;
    state.figures = data.figures;
    renderBoxes();
    emit('figures-updated');
  } catch (e) { if (g === gen) toast('图表列表获取失败'); }
}

function updateDetectStatus(st) {
  const el = $('detect-status');
  if (st.stage === 'detecting') el.textContent = `检测中 ${st.detect_done}/${st.detect_total || '?'} · 已标记 ${st.n_figures} 张`;
  else if (st.stage === 'failed') el.textContent = `检测失败: ${st.error || ''}`;
  else if (st.n_figures > 0) el.textContent = `已标记 ${st.n_figures} 张图表`;
  else el.textContent = '未检测到图表';
}

// 图表清单（「图表」页签「导航」组）：按页分组列出，点击跳页并切到图表右栏
function updateFigureList() {
  const list = $('figure-list');
  if (!list) return;
  const figs = state.figures;
  if (!figs.length) { list.hidden = true; list.innerHTML = ''; return; }
  list.hidden = false;
  const pages = [...new Set(figs.map((f) => f.page))].sort((a, b) => a - b);
  list.innerHTML = pages.map((p) => {
    const arr = figs.filter((f) => f.page === p);
    return `<li data-page="${p}">第 ${p} 页: ${arr.map((f) => `${f.id}(${f.type})`).join(', ')}</li>`;
  }).join('');
  list.querySelectorAll('li').forEach((li) => {
    li.addEventListener('click', () => {
      if (typeof window.__gotoPage === 'function') window.__gotoPage(Number(li.dataset.page));
      emit('switch-side-tab', 'figure');
    });
  });
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
  const g = gen, h = hash();
  if (fig.parse_status !== 'done') panel.innerHTML = '<p class="dim">解析中…（约 10-20 秒）</p>';
  try {
    const r = await parseFigure(h, fig.id);
    if (g !== gen) return;
    fig.parse_status = r.parse_status;
    renderBoxes();
    emit('figures-updated');
    if (r.parse_status === 'error') {
      showPanelError(panel, r.error || '解析失败', () => onBoxClick(fig));
      return;
    }
    renderChartResult(panel, {
      inputUrl: r.crop_path ? `/cache/papers/${h}/${r.crop_path}` : null,
      chart: r.chart,
      renderUrl: r.render_path ? `/cache/papers/${h}/${r.render_path}` : null,
      codeUrl: r.code_path ? `/cache/papers/${h}/${r.code_path}` : null,
    });
  } catch (e) {
    if (g !== gen) return;
    fig.parse_status = 'error';
    renderBoxes();
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
  for (const warning of chart.warnings || []) {
    const notice = document.createElement('p');
    notice.className = 'warning-text';
    notice.textContent = warning;
    pane.appendChild(notice);
  }
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
  series.forEach((s) => {
    const axisLabel = s.axis === 'right' ? '（右轴）' : '';
    head.appendChild(th(`${s.name || 'y'}${axisLabel}`));
  });
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
