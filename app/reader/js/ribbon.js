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
