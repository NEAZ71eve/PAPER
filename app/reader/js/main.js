import { on } from './state.js';
import { initViewer } from './viewer.js';

function switchSideTab(name) {
  document.querySelectorAll('.side-tab').forEach((b) => b.classList.toggle('active', b.dataset.side === name));
  document.querySelectorAll('.side-panel').forEach((p) => p.classList.toggle('active', p.dataset.panel === name));
}

window.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.side-tab').forEach((b) => b.addEventListener('click', () => switchSideTab(b.dataset.side)));
  on('switch-side-tab', switchSideTab);
  initViewer();
});
