// 文本批注：画布放置锚点 / 右栏卡片编辑 / 删除 / 已解决置灰 / 双向定位（设计文档 4.3）
import { state, on, emit, uid } from './state.js';
import { pageAnnot, prunePage, scheduleSave } from './annotate.js';

const $ = (id) => document.getElementById(id);

export function initComments() {
  const catcher = document.createElement('div');
  catcher.id = 'comment-catcher';
  $('comment-layer').appendChild(catcher);
  catcher.addEventListener('click', onPlace);
  on('page-changed', renderAll);
  on('scale-changed', renderAnchors);
  on('annotations-changed', renderAll);
}

function comments() {
  const entry = state.annotations.pages[String(state.page)];
  return entry ? entry.comments : [];
}

function onPlace(e) {
  const r = $('comment-layer').getBoundingClientRect();
  const x = (e.clientX - r.left) / r.width;
  const y = (e.clientY - r.top) / r.height;
  const now = new Date().toISOString();
  const c = { id: uid('c'), x, y, text: '', resolved: false, created_at: now, updated_at: now };
  pageAnnot(state.page).comments.push(c);
  scheduleSave();
  renderAll();
  emit('switch-side-tab', 'comments');
  requestAnimationFrame(() => {
    const ta = document.querySelector(`#card-${c.id} textarea`);
    if (ta) ta.focus();
  });
}

function renderAll() { renderAnchors(); renderCards(); }

function renderAnchors() {
  const layer = $('comment-layer');
  layer.querySelectorAll('.comment-anchor').forEach((el) => el.remove());
  comments().forEach((c, i) => {
    const a = document.createElement('div');
    a.className = 'comment-anchor' + (c.resolved ? ' resolved' : '');
    a.textContent = i + 1;
    a.style.left = `${c.x * 100}%`;
    a.style.top = `${c.y * 100}%`;
    a.title = c.text || '（空批注）';
    a.addEventListener('click', (ev) => {
      ev.stopPropagation();
      emit('switch-side-tab', 'comments');
      flashCard(c.id);
    });
    layer.appendChild(a);
  });
}

function renderCards() {
  const panel = $('comments-panel');
  if (!state.paper) { panel.innerHTML = '<p class="dim">导入论文后可添加批注</p>'; return; }
  const list = comments();
  if (!list.length) {
    panel.innerHTML = '<p class="dim">本页暂无批注。在 ribbon「批注」页签选择 💬 后点击页面放置。</p>';
    return;
  }
  panel.innerHTML = '';
  list.forEach((c, i) => {
    const card = document.createElement('div');
    card.className = 'comment-card' + (c.resolved ? ' resolved' : '');
    card.id = `card-${c.id}`;
    const head = document.createElement('div');
    head.className = 'comment-head';
    head.textContent = `#${i + 1} · 第 ${state.page} 页` + (c.resolved ? ' · 已解决' : '');
    card.appendChild(head);
    if (c.resolved) {
      const snippet = document.createElement('p');
      snippet.className = 'comment-snippet';
      snippet.textContent = c.text || '（空批注）';
      card.appendChild(snippet);
    } else {
      const ta = document.createElement('textarea');
      ta.value = c.text;
      ta.placeholder = '输入批注…';
      ta.rows = 3;
      ta.addEventListener('input', () => {
        c.text = ta.value;
        c.updated_at = new Date().toISOString();
        scheduleSave();  // 不触发重渲染，避免打断输入
      });
      card.appendChild(ta);
    }
    const row = document.createElement('div');
    row.className = 'comment-actions';
    const locate = document.createElement('button');
    locate.textContent = '定位';
    locate.addEventListener('click', () => flashAnchor(c.id));
    const toggle = document.createElement('button');
    toggle.textContent = c.resolved ? '重新打开' : '标记已解决';
    toggle.addEventListener('click', () => {
      c.resolved = !c.resolved;
      c.updated_at = new Date().toISOString();
      scheduleSave();
      renderAll();
    });
    const del = document.createElement('button');
    del.textContent = '删除';
    del.className = 'danger';
    del.addEventListener('click', () => {
      const entry = pageAnnot(state.page);
      entry.comments = entry.comments.filter((x) => x.id !== c.id);
      prunePage(state.page);
      scheduleSave();
      renderAll();
    });
    row.appendChild(locate);
    row.appendChild(toggle);
    row.appendChild(del);
    card.appendChild(row);
    panel.appendChild(card);
  });
}

function flashCard(id) {
  const el = document.getElementById(`card-${id}`);
  if (!el) return;
  el.scrollIntoView({ block: 'nearest' });
  el.classList.add('flash');
  setTimeout(() => el.classList.remove('flash'), 900);
}

function flashAnchor(id) {
  const idx = comments().findIndex((c) => c.id === id);
  if (idx < 0) return;
  const el = document.querySelectorAll('.comment-anchor')[idx];
  if (!el) return;
  el.classList.add('flash');
  setTimeout(() => el.classList.remove('flash'), 900);
}
