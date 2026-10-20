// 后端 API 封装（设计文档 6）
async function J(r) {
  if (!r.ok) throw new Error(`HTTP ${r.status}: ${(await r.text()).slice(0, 200)}`);
  return r.json();
}

export async function uploadPaper(file, detect) {
  const fd = new FormData();
  fd.append('file', file);
  fd.append('detect', detect ? 'true' : 'false');
  return J(await fetch('/api/papers', { method: 'POST', body: fd }));
}

export const getStatus = (h) => fetch(`/api/papers/${h}/status`).then(J);
export const getFigures = (h) => fetch(`/api/papers/${h}/figures`).then(J);
export const parseFigure = (h, fid) =>
  fetch(`/api/papers/${h}/figures/${fid}/parse`, { method: 'POST' }).then(J);
export const getAnnotations = (h) => fetch(`/api/papers/${h}/annotations`).then(J);
export const putAnnotations = (h, data) =>
  fetch(`/api/papers/${h}/annotations`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
  }).then(J);
export const startDetect = (h) =>
  fetch(`/api/papers/${h}/detect`, { method: 'POST' }).then(J);
export const getHealth = () => fetch('/api/health').then(J);

export async function parseSingle(file) {
  const fd = new FormData();
  fd.append('file', file);
  return J(await fetch('/api/singles/parse', { method: 'POST', body: fd }));
}

export async function exportPaper(h) {
  const r = await fetch(`/api/papers/${h}/export`, { method: 'POST' });
  if (!r.ok) throw new Error((await r.text()).slice(0, 200));
  const blob = await r.blob();
  const dispo = r.headers.get('Content-Disposition') || '';
  const m = dispo.match(/filename\*?=(?:UTF-8''|")?([^";]+)/i);
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = m ? decodeURIComponent(m[1].replace(/"/g, '')) : 'annotated.pdf';
  a.click();
  URL.revokeObjectURL(a.href);
}
