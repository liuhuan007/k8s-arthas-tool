/**
 * 通用工具函数模块
 */

// ── 字符串处理 ────────────────────────────────────────────────────────────

/**
 * HTML 转义，防止 XSS
 */
const esc = s => String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

/**
 * 格式化文件大小
 */
const fmtSz = (b) => {
  if (!b) return '—';
  const units = ['B','KB','MB','GB','TB'];
  let i = 0;
  while (b >= 1024 && i < units.length - 1) { b /= 1024; i++; }
  return b.toFixed(i ? 1 : 0) + ' ' + units[i];
};

/**
 * 格式化时间戳（支持 ISO 字符串、Unix 时间戳秒/毫秒）
 */
const fmtTs = (input) => {
  if (!input) return '—';
  try {
    let date;
    const num = Number(input);
    
    if (!isNaN(num)) {
      // 数字类型：判断是秒还是毫秒
      // 秒级时间戳：约 10 亿 ~ 20 亿（2001-2033年）
      // 毫秒级时间戳：约 1 万亿以上
      if (num > 1e12) {
        date = new Date(num);  // 毫秒
      } else if (num > 1e9) {
        date = new Date(num * 1000);  // 秒，转毫秒
      } else {
        // 太小，可能不是时间戳，返回原值
        return String(input);
      }
    } else {
      // 字符串类型：尝试解析 ISO 格式
      date = new Date(input);
    }
    
    // 验证日期是否有效
    if (isNaN(date.getTime())) {
      return String(input);
    }
    
    return date.toLocaleString('zh-CN', {
      hour12: false,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    });
  } catch {
    return String(input);
  }
};

/**
 * 生成时间戳字符串 (格式: 20260322153847)
 * @returns {string}
 */
function fmtNowTs() {
  const n = new Date();
  return n.getFullYear().toString()
    + String(n.getMonth() + 1).padStart(2, '0')
    + String(n.getDate()).padStart(2, '0')
    + String(n.getHours()).padStart(2, '0')
    + String(n.getMinutes()).padStart(2, '0')
    + String(n.getSeconds()).padStart(2, '0');
}

// ── UI 组件 ────────────────────────────────────────────────────────────

/**
 * 创建键值对 HTML 元素
 * @param {string} k - 键
 * @param {string} v - 值
 * @param {boolean} raw - 是否原始 HTML
 * @returns {string}
 */
const mkv = (k, v, raw = false) => `
  <div class="kv">
    <span class="kv-k">${esc(k)}</span>
    <span class="kv-v">${raw ? v : esc(String(v ?? '—'))}</span>
  </div>`;

/**
 * 创建行元素
 * @param {string} k - 键
 * @param {string} v - 值
 * @returns {string}
 */
const gRow = (k, v) => `
  <div class="g-row">
    <span class="g-row-k">${esc(k)}</span>
    <span class="g-row-v">${esc(String(v ?? '—'))}</span>
  </div>`;

/**
 * 通知提示
 * @param {string} msg - 消息
 * @param {string} type - 类型: info/success/error/warning
 */
function toast(msg, type = 'info') {
  const container = document.getElementById('toastContainer') || createToastContainer();
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = msg;
  container.appendChild(toast);
  
  setTimeout(() => {
    toast.classList.add('show');
  }, 10);
  
  setTimeout(() => {
    toast.classList.remove('show');
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}

/**
 * 创建 toast 容器
 */
function createToastContainer() {
  const container = document.createElement('div');
  container.id = 'toastContainer';
  container.className = 'toast-container';
  document.body.appendChild(container);
  return container;
}

/**
 * 获取文件图标
 * @param {string} name - 文件名
 * @returns {string} emoji
 */
function getFileIcon(name) {
  if (!name) return '📄';
  const ext = name.split('.').pop().toLowerCase();
  const icons = {
    // 目录
    dir: '📁',
    // 压缩包
    zip: '📦', tar: '📦', gz: '📦', targz: '📦', tgz: '📦',
    // 图片
    png: '🖼️', jpg: '🖼️', jpeg: '🖼️', gif: '🖼️', svg: '🖼️', ico: '🖼️',
    // 文档
    pdf: '📕', doc: '📘', docx: '📘', xls: '📗', xlsx: '📗', ppt: '📙', pptx: '📙', txt: '📄', md: '📝',
    // 代码
    js: '📜', ts: '📜', py: '🐍', java: '☕', go: '🔷', rs: '🦀', c: '🔧', cpp: '🔧', h: '🔧',
    // 配置
    json: '⚙️', yaml: '⚙️', yml: '⚙️', xml: '⚙️', ini: '⚙️', conf: '⚙️', cfg: '⚙️',
    // 日志
    log: '📋', out: '📋', err: '❌',
    // 其他
    jar: '🫙', war: '🫙', ear: '🫙',
    class: '☕', 'class': '☕'
  };
  return icons[ext] || '📄';
}

// ── DOM 工具 ────────────────────────────────────────────────────────────

/**
 * 防抖
 * @param {Function} fn
 * @param {number} delay
 * @returns {Function}
 */
function debounce(fn, delay = 300) {
  let timer = null;
  return function(...args) {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => fn.apply(this, args), delay);
  };
}

/**
 * 节流
 * @param {Function} fn
 * @param {number} limit
 * @returns {Function}
 */
function throttle(fn, limit = 300) {
  let inThrottle = false;
  return function(...args) {
    if (!inThrottle) {
      fn.apply(this, args);
      inThrottle = true;
      setTimeout(() => inThrottle = false, limit);
    }
  };
}

/**
 * 深度获取对象属性
 * @param {object} obj
 * @param {string} path - 如 'a.b.c'
 * @param {any} defaultVal
 * @returns {any}
 */
function get(obj, path, defaultVal = undefined) {
  return path.split('.').reduce((o, k) => (o && o[k] !== undefined) ? o[k] : defaultVal, obj);
}

/**
 * 格式化数字
 * @param {number} n
 * @returns {string}
 */
function fmtNum(n) {
  if (n === null || n === undefined) return '—';
  return n.toLocaleString('zh-CN');
}

// 导出
if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    esc, fmtSz, fmtTs, fmtNowTs,
    mkv, gRow, toast, getFileIcon,
    debounce, throttle, get, fmtNum
  };
}