/**
 * API 请求封装
 * 统一处理请求/响应/错误
 */

// 自动检测 API 地址
const API = (() => {
  if (typeof window !== 'undefined' && window.location.protocol.startsWith('http')) {
    return `${window.location.protocol}//${window.location.host}/api`;
  }
  return 'http://127.0.0.1:5005/api';
})();

/**
 * 安全 POST 请求
 * @param {string} url - 请求 URL（相对路径，会自动添加 API 前缀）
 * @param {object} body - 请求体
 * @param {number} timeoutMs - 超时时间（毫秒）
 * @returns {Promise<object>}
 */
async function safePost(url, body, timeoutMs = 15000) {
  const fullUrl = url.startsWith('http') ? url : `${API}${url}`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  
  try {
    const r = await fetch(fullUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: controller.signal,
      credentials: 'include'  // 包含 cookie
    });
    clearTimeout(timer);

    // 未登录或会话过期，跳转登录页
    if (r.status === 401) {
      window.location.replace('/login.html');
      throw new Error('会话已过期，请重新登录');
    }
    
    const ct = r.headers.get('content-type') || '';
    if (!ct.includes('application/json')) {
      const text = await r.text();
      throw new Error(
        `服务器返回非JSON响应 (HTTP ${r.status})\n` +
        `响应片段: ${text.slice(0, 120)}`
      );
    }
    
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || d.message || `请求失败 (${r.status})`);
    return d;
  } catch (e) {
    clearTimeout(timer);
    if (e.name === 'AbortError') {
      throw new Error(`请求超时 (${timeoutMs / 1000}s)，请确认服务正在运行`);
    }
    throw e;
  }
}

/**
 * 安全 GET 请求
 * @param {string} url - 请求 URL
 * @param {object} params - 查询参数
 * @param {number} timeoutMs - 超时时间
 * @returns {Promise<object>}
 */
async function safeGet(url, params = {}, timeoutMs = 15000) {
  const fullUrl = url.startsWith('http') ? url : `${API}${url}`;
  const queryString = new URLSearchParams(params).toString();
  const finalUrl = queryString ? `${fullUrl}?${queryString}` : fullUrl;
  
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  
  try {
    const r = await fetch(finalUrl, {
      method: 'GET',
      signal: controller.signal,
      credentials: 'include'  // 包含 cookie
    });
    clearTimeout(timer);

    // 未登录或会话过期，跳转登录页
    if (r.status === 401) {
      window.location.replace('/login.html');
      throw new Error('会话已过期，请重新登录');
    }
    
    const ct = r.headers.get('content-type') || '';
    if (!ct.includes('application/json')) {
      throw new Error(`服务器返回非JSON响应 (HTTP ${r.status})`);
    }
    
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || d.message || `请求失败 (${r.status})`);
    return d;
  } catch (e) {
    clearTimeout(timer);
    if (e.name === 'AbortError') {
      throw new Error(`请求超时 (${timeoutMs / 1000}s)`);
    }
    throw e;
  }
}

/**
 * 下载文件
 * @param {string} url - 下载 URL
 * @param {string} filename - 保存文件名
 */
async function downloadFile(url, filename) {
  const fullUrl = url.startsWith('http') ? url : `${API}${url}`;
  const response = await fetch(fullUrl, { credentials: 'same-origin' });
  
  if (!response.ok) {
    throw new Error(`下载失败: ${response.status}`);
  }
  
  const blob = await response.blob();
  const blobUrl = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = blobUrl;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(blobUrl);
}

/**
 * 安全 PUT 请求
 * @param {string} url - 请求 URL
 * @param {object} body - 请求体
 * @param {number} timeoutMs - 超时时间
 */
async function safePut(url, body, timeoutMs = 15000) {
  const fullUrl = url.startsWith('http') ? url : `${API}${url}`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const r = await fetch(fullUrl, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: controller.signal,
      credentials: 'include',
    });
    clearTimeout(timer);
    if (r.status === 401) { window.location.replace('/login.html'); throw new Error('会话已过期'); }
    const ct = r.headers.get('content-type') || '';
    if (!ct.includes('application/json')) throw new Error(`服务器返回非JSON响应 (HTTP ${r.status})`);
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || d.message || `请求失败 (${r.status})`);
    return d;
  } catch (e) {
    clearTimeout(timer);
    if (e.name === 'AbortError') throw new Error(`请求超时 (${timeoutMs / 1000}s)`);
    throw e;
  }
}

/**
 * 安全 DELETE 请求
 * @param {string} url - 请求 URL
 * @param {number} timeoutMs - 超时时间
 */
async function safeDelete(url, timeoutMs = 15000) {
  const fullUrl = url.startsWith('http') ? url : `${API}${url}`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const r = await fetch(fullUrl, {
      method: 'DELETE',
      signal: controller.signal,
      credentials: 'include',
    });
    clearTimeout(timer);
    if (r.status === 401) { window.location.replace('/login.html'); throw new Error('会话已过期'); }
    if (r.status === 204) return {};
    const ct = r.headers.get('content-type') || '';
    if (!ct.includes('application/json')) throw new Error(`服务器返回非JSON响应 (HTTP ${r.status})`);
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || d.message || `请求失败 (${r.status})`);
    return d;
  } catch (e) {
    clearTimeout(timer);
    if (e.name === 'AbortError') throw new Error(`请求超时 (${timeoutMs / 1000}s)`);
    throw e;
  }
}

// 导出浏览器全局变量，供 inline onclick 和非模块脚本使用
if (typeof window !== 'undefined') {
  window.API = API;
  window.safePost = safePost;
  window.safeGet = safeGet;
  window.safePut = safePut;
  window.safeDelete = safeDelete;
  window.downloadFile = downloadFile;
}

// 导出给其他模块使用
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { API, safePost, safeGet, safePut, safeDelete, downloadFile };
}
