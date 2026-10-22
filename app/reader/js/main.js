import { on, toast } from './state.js';
import { refreshStates, onStateChange } from './commands.js';
import { initShell } from './shell.js';
import { importFile, initViewer } from './viewer.js';
import { initFigures } from './figures.js';
import { initInk } from './ink.js';
import { initComments } from './comments.js';
import { initRibbon } from './ribbon.js';
import { initToolbox } from './toolbox.js';

function switchSideTab(name) {
  document.querySelectorAll('.side-tab').forEach((b) => b.classList.toggle('active', b.dataset.side === name));
  document.querySelectorAll('.side-panel').forEach((p) => p.classList.toggle('active', p.dataset.panel === name));
}

window.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.side-tab').forEach((b) => b.addEventListener('click', () => switchSideTab(b.dataset.side)));
  on('switch-side-tab', switchSideTab);
  initViewer();
  initFigures();
  initInk();
  initComments();
  initRibbon();
  initShell();
  refreshStates();
  initToolbox();
  refreshStates();
  const url = new URL(location.href);
  if (url.searchParams.get('demo') === 'synthetic') {
    url.searchParams.delete('demo');
    history.replaceState(null, '', url);
    fetch('/samples/synthetic-demo.pdf')
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.blob();
      })
      .then((blob) => importFile(new File([blob], 'synthetic-demo.pdf', { type: 'application/pdf' })))
      .catch((error) => {
        console.error('无法加载合成测试论文', error);
        toast(`无法加载合成测试论文: ${error.message}`);
      });
  }
});
