// Word 外壳控制器：页签 / Backstage / 折叠 / 窗格 / 状态栏 / localStorage 持久化。
// 命令注册到 commands.js；业务函数通过 window.__ 桥接 viewer.js。
import { register, run, enabled, refreshStates } from './commands.js';
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

// ---------- 页签 & Backstage ----------
export function switchTab(name) {
  if (name === 'file') { openBackstage(); return; }
  document.querySelectorAll('.ribbon-tab').forEach((t) =>
    t.classList.toggle('active', t.dataset.tab === name));
  document.querySelectorAll('.ribbon-panel').forEach((p) =>
    p.classList.toggle('active', p.dataset.panel === name));
  savePref(LS.ACTIVE_TAB, name);
}

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
export function toggleCollapse() {
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
export function setThumbsVisible(show) {
  const el = document.getElementById('thumbs');
  el.classList.toggle('hidden', !show);
  savePref(LS.THUMBS_VISIBLE, show);
}
export function setSidebarVisible(show) {
  const el = document.getElementById('sidebar');
  el.classList.toggle('hidden', !show);
  savePref(LS.SIDEBAR_VISIBLE, show);
}

// ---------- 状态栏 ----------
export function updateStatus() {
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
  // Ribbon 折叠
  register('ribbon-collapse', { run: toggleCollapse, enabled: () => true });
  document.getElementById('btn-ribbon-collapse').addEventListener('click', toggleCollapse);
  doubleClickCollapse();

  // 页签
  document.querySelectorAll('.ribbon-tab').forEach((btn) => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  });

  // Backstage 导入按钮（不走 data-cmd）
  const fileInput = document.getElementById('file-input');
  document.getElementById('btn-import').addEventListener('click', () => fileInput && fileInput.click());
  if (fileInput) fileInput.addEventListener('change', () => setTimeout(closeBackstage, 400));

  // 窗格开关
  register('toggle-thumbs', {
    run: () => setThumbsVisible(document.getElementById('thumbs').classList.contains('hidden')),
    enabled: () => !!state.paper,
  });
  register('toggle-comments', {
    run: () => setSidebarVisible(document.getElementById('sidebar').classList.contains('hidden')),
    enabled: () => !!state.paper,
  });

  // 翻页（通过 window 桥接 viewer.js）
  register('prev', { run: () => runGoto(state.page - 1), enabled: () => !!state.paper && state.page > 1 });
  register('next', { run: () => runGoto(state.page + 1), enabled: () => !!state.paper && state.page < (state.paper?.n_pages || 1) });
  function runGoto(n) { if (typeof window.__gotoPage === 'function') window.__gotoPage(n); }

  // 缩放 / 适应
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

  // data-cmd 委托（全局 click 监听）
  document.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-cmd]');
    if (!btn) return;
    const name = btn.dataset.cmd;
    if (!enabled(name)) return;
    run(name);
  });

  // 订阅事件刷新状态栏与命令可用态
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

  // 绑定现有按钮（带 id 的那些）到命令（覆盖 ribbon.js 原有监听）
  const bindCmd = (id, name) => {
    const el = document.getElementById(id);
    if (el) el.addEventListener('click', () => run(name));
  };
  bindCmd('btn-export', 'export');
  bindCmd('btn-redetect', 'redetect');
  bindCmd('btn-clear-page', 'clear-page');
  bindCmd('btn-prev', 'prev');
  bindCmd('btn-next', 'next');

  updateStatus();
  refreshStates();
}

// 运行期对接 ribbon.js 留下的 legacy 命令（run/enabled 实现由 ribbon.js 注册）
export function registerLegacy(name, fn, { enabled } = {}) {
  register(name, { run: fn, enabled: enabled || (() => true) });
}
