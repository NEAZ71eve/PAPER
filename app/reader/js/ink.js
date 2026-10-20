// 手写墨迹：canvas 笔画采集 / 荧光笔半透明 / 橡皮点选删整条 / 撤销重做双栈 / 清空本页（设计文档 4.3）
import { state, on, uid, toast } from './state.js';
import { pageAnnot, prunePage, scheduleSave } from './annotate.js';

let canvas, ctx, drawing = false, pts = [];

export function initInk() {
  canvas = document.getElementById('ink-canvas');
  ctx = canvas.getContext('2d');
  canvas.addEventListener('pointerdown', onDown);
  canvas.addEventListener('pointermove', onMove);
  window.addEventListener('pointerup', onUp);
  on('page-changed', redrawAll);
  on('scale-changed', redrawAll);
  on('annotations-changed', redrawAll);
}

function pxPerPt() {
  // 自然像素 150 DPI：1pt = 150/72 px；显示再乘 scale
  return (150 / 72) * state.scale;
}

function toNorm(e) {
  const r = canvas.getBoundingClientRect();
  return [(e.clientX - r.left) / canvas.width, (e.clientY - r.top) / canvas.height];
}

function onDown(e) {
  if (state.tool === 'pen' || state.tool === 'highlighter') {
    drawing = true;
    pts = [toNorm(e)];
    canvas.setPointerCapture(e.pointerId);
  } else if (state.tool === 'eraser') {
    eraseAt(toNorm(e));
  }
}

function onMove(e) {
  if (!drawing) return;
  const p = toNorm(e);
  drawSegment(pts[pts.length - 1], p, state.tool, state.inkColor, state.inkWidth);
  pts.push(p);
}

function onUp() {
  if (!drawing) return;
  drawing = false;
  if (pts.length >= 2) {
    const stroke = { id: uid('s'), tool: state.tool, color: state.inkColor, width: state.inkWidth, points: pts };
    pageAnnot(state.page).strokes.push(stroke);
    state.undoStack.push({ op: 'add', page: state.page, stroke });
    state.redoStack = [];
    scheduleSave();
  }
  pts = [];
  redrawAll();
}

function drawSegment(a, b, tool, color, widthPt) {
  ctx.save();
  ctx.globalAlpha = tool === 'highlighter' ? 0.4 : 1;
  ctx.strokeStyle = color;
  ctx.lineWidth = Math.max(1, widthPt * pxPerPt());
  ctx.lineJoin = 'round';
  ctx.lineCap = 'round';
  ctx.beginPath();
  ctx.moveTo(a[0] * canvas.width, a[1] * canvas.height);
  ctx.lineTo(b[0] * canvas.width, b[1] * canvas.height);
  ctx.stroke();
  ctx.restore();
}

export function redrawAll() {
  if (!canvas || !canvas.width) return;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  const entry = state.annotations.pages[String(state.page)];
  if (!entry) return;
  for (const s of entry.strokes) {
    for (let i = 1; i < s.points.length; i++) {
      drawSegment(s.points[i - 1], s.points[i], s.tool, s.color, s.width);
    }
  }
}

// 橡皮：点选命中删除整条笔画（设计文档 4.3）
function eraseAt([nx, ny]) {
  const entry = state.annotations.pages[String(state.page)];
  if (!entry) return;
  const x = nx * canvas.width;
  const y = ny * canvas.height;
  for (let i = entry.strokes.length - 1; i >= 0; i--) {
    const s = entry.strokes[i];
    const tol = 6 + (s.width * pxPerPt()) / 2;
    if (hitStroke(s, x, y, tol)) {
      entry.strokes.splice(i, 1);
      state.undoStack.push({ op: 'remove', page: state.page, stroke: s, index: i });
      state.redoStack = [];
      prunePage(state.page);
      scheduleSave();
      redrawAll();
      return;
    }
  }
}

function hitStroke(s, x, y, tol) {
  for (let i = 1; i < s.points.length; i++) {
    const ax = s.points[i - 1][0] * canvas.width;
    const ay = s.points[i - 1][1] * canvas.height;
    const bx = s.points[i][0] * canvas.width;
    const by = s.points[i][1] * canvas.height;
    if (distToSegment(x, y, ax, ay, bx, by) <= tol) return true;
  }
  return false;
}

function distToSegment(px, py, ax, ay, bx, by) {
  const dx = bx - ax;
  const dy = by - ay;
  const len2 = dx * dx + dy * dy;
  let t = len2 ? ((px - ax) * dx + (py - ay) * dy) / len2 : 0;
  t = Math.max(0, Math.min(1, t));
  return Math.hypot(px - (ax + t * dx), py - (ay + t * dy));
}

export function undoInk() {
  const op = state.undoStack.pop();
  if (!op) { toast('没有可撤销的操作'); return; }
  applyInverse(op);
  state.redoStack.push(op);
  prunePage(op.page);
  scheduleSave();
  redrawAll();
}

export function redoInk() {
  const op = state.redoStack.pop();
  if (!op) { toast('没有可重做的操作'); return; }
  applyOp(op);
  state.undoStack.push(op);
  scheduleSave();
  redrawAll();
}

function applyOp(op) {
  const entry = pageAnnot(op.page);
  if (op.op === 'add') entry.strokes.push(op.stroke);
  if (op.op === 'remove') removeById(entry, op.stroke.id);
  if (op.op === 'clear') entry.strokes = [];
}

function applyInverse(op) {
  const entry = pageAnnot(op.page);
  if (op.op === 'add') removeById(entry, op.stroke.id);
  if (op.op === 'remove') entry.strokes.splice(Math.min(op.index, entry.strokes.length), 0, op.stroke);
  if (op.op === 'clear') entry.strokes = [...op.strokes];
}

function removeById(entry, id) {
  const i = entry.strokes.findIndex((s) => s.id === id);
  if (i >= 0) entry.strokes.splice(i, 1);
}

export function clearPageStrokes() {
  const entry = state.annotations.pages[String(state.page)];
  if (!entry || !entry.strokes.length) { toast('本页没有墨迹'); return; }
  state.undoStack.push({ op: 'clear', page: state.page, strokes: [...entry.strokes] });
  state.redoStack = [];
  entry.strokes = [];
  prunePage(state.page);
  scheduleSave();
  redrawAll();
}
