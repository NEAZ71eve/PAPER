// 工具箱：单图上传解析（复用四件套渲染；设计文档 4.1）
import { toast } from './state.js';
import { parseSingle } from './api.js';
import { renderChartResult } from './figures.js';

const $ = (id) => document.getElementById(id);

export function initToolbox() {
  $('btn-single-upload').addEventListener('click', () => $('single-input').click());
  $('single-input').addEventListener('change', (e) => {
    if (e.target.files[0]) doParse(e.target.files[0]);
    e.target.value = '';
  });
}

async function doParse(file) {
  const box = $('single-result');
  box.innerHTML = '<p class="dim">解析中…（约 10-20 秒）</p>';
  try {
    const r = await parseSingle(file);
    if (r.status === 'error') {
      box.innerHTML = `<p class="error-text">解析失败: ${r.error || ''}</p>`;
      return;
    }
    renderChartResult(box, { inputUrl: r.input_url, chart: r.chart, renderUrl: r.render_url, codeText: r.code });
    if (r.status === 'render_failed') toast('复刻图渲染失败，已保留数据与代码');
  } catch (e) {
    box.innerHTML = `<p class="error-text">解析失败: ${e.message}</p>`;
  }
}
