// 阅读画布：导入 / 页面渲染 / 翻页 / 缩放 / 缩略图导航（设计文档 4.1、4.2）
import { state, emit, toast } from './state.js';
import { uploadPaper } from './api.js';
import { loadAnnotations, saveNow } from './annotate.js';

const $ = (id) => document.getElementById(id);

export function initViewer() {
  $('btn-import').addEventListener('click', () => $('file-input').click());
  $('file-input').addEventListener('change', (e) => {
    if (e.target.files[0]) importFile(e.target.files[0]);
    e.target.value = '';
  });
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
  if (state.paper) { await saveNow(); }
  let info;
  try {
    info = await uploadPaper(file, $('chk-detect').checked);
  } catch (e) {
    toast(`导入失败: ${e.message}`);
    return;
  }
  state.paper = info;
  state.page = 1;
  loadedPage = 0;
  state.zoom = 1;
  state.fitMode = 'width';
  state.figures = [];
  $('tb-filename').textContent = info.file_name || '未命名论文';
  buildThumbs(info.n_pages);
  $('empty-state').hidden = true;
  $('page-wrap').hidden = false;
  await loadAnnotations();
  renderPage();
  emit('paper-loaded');
  emit('paper-state-changed');
  toast(`已导入 ${info.file_name}（${info.n_pages} 页${info.truncated ? '，超出页数上限已截断' : ''}）`);
}

let loadedPage = 0;

export function renderPage() {
  if (!state.paper) return;
  const img = $('page-img');
  const n = state.page;
  img.onload = () => {
    if (n !== state.page) return;
    loadedPage = n;
    state.pageSize = { w: img.naturalWidth, h: img.naturalHeight };
    applyScale();
    highlightThumb();
    emit('page-changed', n);
    emit('paper-state-changed');
  };
  img.onerror = () => {
    if (n !== state.page) return;
    toast(`第 ${n} 页加载失败`);
  };
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

export function setZoom(z) {
  state.zoom = z;
  state.fitMode = null;
  applyScale();
  // 同步 zoom-select 控件：手动缩放下拉设置的值与 zoom 对齐
  const zs = document.getElementById('zoom-select');
  if (zs) zs.value = String(z);
}
export function setFitMode(mode) {
  state.fitMode = mode;
  applyScale();
  // 同步 zoom-select 控件：适应模式下清空下拉，避免 UI 与实际状态矛盾
  const zs = document.getElementById('zoom-select');
  if (zs) zs.value = '';
}

export function gotoPage(n) {
  if (!state.paper) return;
  const clamped = Math.min(Math.max(1, n), state.paper.n_pages);
  if (clamped === state.page && loadedPage === clamped) return;
  state.page = clamped;
  renderPage();
}

export function prevPage() { gotoPage(state.page - 1); }
export function nextPage() { gotoPage(state.page + 1); }

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

// ---------- window 桥接（供 shell.js 调用）----------
window.__gotoPage = gotoPage;
window.__setZoom = setZoom;
window.__setFitMode = setFitMode;
