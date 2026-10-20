// 全局状态 + 简易事件总线 + 工具函数
export const state = {
  paper: null,          // {pdf_hash, file_name, n_pages, truncated}
  page: 1,
  pageSize: { w: 0, h: 0 },  // 页面自然像素（150 DPI PNG）
  zoom: 1,              // 100% = 自然尺寸
  fitMode: 'width',     // 'width' | 'page' | null
  scale: 1,             // 显示像素 / 自然像素
  tool: 'read',         // read | pen | highlighter | eraser | comment
  inkColor: '#CC2936',
  inkWidth: 2,          // 单位 PDF point
  figures: [],
  annotations: { version: 1, pages: {} },
  undoStack: [],
  redoStack: [],
  status: null,
};

const listeners = {};
export function on(evt, fn) { (listeners[evt] ||= []).push(fn); }
export function emit(evt, ...args) { (listeners[evt] || []).forEach((fn) => fn(...args)); }

export const uid = (prefix) =>
  `${prefix}-${Math.random().toString(16).slice(2, 6)}${Date.now().toString(16).slice(-4)}`;

export function toast(msg, ms = 3200) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(t._tm);
  t._tm = setTimeout(() => { t.hidden = true; }, ms);
}
