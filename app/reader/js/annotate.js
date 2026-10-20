// 标注侧车：加载 / 1s 防抖自动保存 / 页条目工具（设计文档 4.3、5.1）
import { state, emit, toast } from './state.js';
import { getAnnotations, putAnnotations } from './api.js';

let timer = null;

export async function loadAnnotations() {
  clearTimeout(timer);
  timer = null;
  try {
    state.annotations = await getAnnotations(state.paper.pdf_hash);
  } catch (e) {
    state.annotations = { version: 1, pages: {} };
    toast(`标注读取失败: ${e.message}`);
  }
  state.undoStack = [];
  state.redoStack = [];
  emit('annotations-changed');
}

export function scheduleSave() {
  clearTimeout(timer);
  timer = setTimeout(saveNow, 1000);
}

export async function saveNow() {
  if (!state.paper) return;
  try {
    await putAnnotations(state.paper.pdf_hash, state.annotations);
  } catch (e) {
    toast('标注保存失败，下次变更将自动重试');
  }
}

export function pageAnnot(n) {
  const pages = state.annotations.pages;
  const key = String(n);
  if (!pages[key]) pages[key] = { strokes: [], comments: [] };
  return pages[key];
}

export function prunePage(n) {
  // 无标注页面不写条目（设计文档 5.1）
  const key = String(n);
  const p = state.annotations.pages[key];
  if (p && p.strokes.length === 0 && p.comments.length === 0) delete state.annotations.pages[key];
}
