// ribbon：工具按钮高亮 / 墨迹参数监听 / 健康灯 / legacy 命令注册（direct click 已迁 shell.js）
import { state, on, emit, toast } from './state.js';
import { getHealth, exportPaper } from './api.js';
import { undoInk, redoInk, clearPageStrokes } from './ink.js';
import { redetectFigures } from './figures.js';
import { register } from './commands.js';

const $ = (id) => document.getElementById(id);

export function initRibbon() {
  // 工具按钮高亮 + 墨迹参数（保留）
  document.querySelectorAll('.tool-btn').forEach((btn) => {
    btn.addEventListener('click', () => setTool(btn.dataset.tool));
  });
  $('ink-color').addEventListener('input', (e) => { state.inkColor = e.target.value; });
  $('ink-width').addEventListener('input', (e) => { state.inkWidth = Number(e.target.value); });

  // legacy 命令注册（run/enabled 实现在此，按钮绑定由 shell.js + data-cmd 统一）
  register('undo',        { run: undoInk,                 enabled: () => !!state.paper });
  register('redo',        { run: redoInk,                 enabled: () => !!state.paper });
  register('clear-page',  { run: () => clearPageStrokes(state.page), enabled: () => !!state.paper });
  register('fit-width',   { run: () => { if (typeof window.__setFitMode === 'function') window.__setFitMode('width'); $('zoom-select').value = ''; }, enabled: () => !!state.paper });
  register('fit-page',    { run: () => { if (typeof window.__setFitMode === 'function') window.__setFitMode('page');  $('zoom-select').value = ''; }, enabled: () => !!state.paper });
  register('export',      { run: onExport,                enabled: () => !!state.paper });
  register('redetect',    { run: redetectFigures,         enabled: () => !!state.paper });
  register('open-toolbox',{ run: () => emit('switch-side-tab', 'toolbox'), enabled: () => true });

  // zoom-select 直接绑定（非 data-cmd，因为是 input 控件值）
  $('zoom-select').addEventListener('change', (e) => {
    if (typeof window.__setZoom === 'function') window.__setZoom(Number(e.target.value));
  });

  // 健康灯 + 检测后状态回调（保留）
  on('paper-loaded', () => {
    refreshHealth();
  });
  refreshHealth();
  setInterval(refreshHealth, 30000);
}

function setTool(tool) {
  state.tool = state.tool === tool ? 'read' : tool;
  document.querySelectorAll('.tool-btn').forEach((b) => b.classList.toggle('active', b.dataset.tool === state.tool));
  const stage = $('page-stage');
  if (['pen', 'highlighter', 'eraser'].includes(state.tool)) stage.dataset.mode = 'ink';
  else if (state.tool === 'comment') stage.dataset.mode = 'comment';
  else stage.dataset.mode = 'read';
  emit('tool-changed');
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
    $('btn-redetect').disabled = !ok || !state.paper;
  } catch (e) {
    light.classList.remove('ok');
    light.classList.add('bad');
    light.title = '后端不可达';
    $('btn-redetect').disabled = true;
  }
}
