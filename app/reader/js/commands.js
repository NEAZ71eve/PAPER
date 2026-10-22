// 命令注册表：按钮只声明 data-cmd="name"，行为在这里集中绑定。
// 命令结构：{ run(...args), enabled(), title? }；enabled 未提供时默认 true。
// 按钮元素上会同步 .disabled 类（用于额外样式，与原生 disabled 并存）。

const commands = new Map();
const listeners = new Set();

export function register(name, def) {
  if (!name || !def || typeof def.run !== 'function') {
    console.warn('[commands] register 缺少 run:', name);
    return;
  }
  commands.set(name, { enabled: () => true, ...def });
}

export function run(name, ...args) {
  const def = commands.get(name);
  if (!def) {
    console.warn('[commands] 未注册:', name);
    return false;
  }
  def.run(...args);
  return true;
}

export function enabled(name) {
  const def = commands.get(name);
  if (!def) return false;
  try { return !!def.enabled(); } catch { return false; }
}

export function refreshStates() {
  document.querySelectorAll('[data-cmd]').forEach((el) => {
    const ok = enabled(el.dataset.cmd);
    el.disabled = !ok;
    el.classList.toggle('disabled', !ok);
  });
  listeners.forEach((fn) => { try { fn(); } catch (e) { console.error(e); } });
}

export function onStateChange(fn) { listeners.add(fn); return () => listeners.delete(fn); }
