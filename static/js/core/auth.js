/**
 * 认证工具模块
 * 处理登录/登出/用户状态
 */

// 使用 var 声明以便与其他脚本中的声明兼容
var AUTH_KEY = 'arthas_auth_token';
var AUTH_USER = 'arthas_auth_user';

/**
 * 获取当前登录用户信息
 * @returns {object|null}
 */
function getCurrentUser() {
  const userStr = sessionStorage.getItem(AUTH_USER) || localStorage.getItem(AUTH_USER);
  if (!userStr) return null;
  try {
    return JSON.parse(userStr);
  } catch {
    return null;
  }
}

/**
 * 检查用户是否已认证
 * @returns {boolean}
 */
function isAuthenticated() {
  return !!getCurrentUser();
}

/**
 * 检查当前用户是否是管理员
 * @returns {boolean}
 */
function isAdmin() {
  const user = getCurrentUser();
  return user && user.role === 'admin';
}

/**
 * 执行登出操作
 */
async function doLogout() {
  const REMEMBER_KEY = 'arthas_remember';
  
  // 用原生 fetch 调用后端登出，避免 safePost 的 401 自动跳转副作用
  try {
    await fetch(`${API}/auth/logout`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
      credentials: 'include'
    });
  } catch (e) {
    console.log('Logout API error (ignore):', e.message);
  }
  
  // 清除本地存储
  sessionStorage.removeItem(AUTH_KEY);
  sessionStorage.removeItem(AUTH_USER);
  localStorage.removeItem(AUTH_KEY);
  localStorage.removeItem(AUTH_USER);
  localStorage.removeItem(REMEMBER_KEY);
  
  // 跳转到登录页
  window.location.href = window.location.protocol.startsWith('http') ? '/login.html' : 'login.html';
}

/**
 * 初始化用户显示（顶部用户名）
 */
function initUserDisplay() {
  const user = getCurrentUser();
  const displayName = user ? user.username : '游客';
  const el = document.getElementById('loginUser');
  if (el) el.textContent = displayName;
}

/**
 * 检查认证状态（AJAX）
 * @returns {Promise<object>}
 */
async function checkAuthStatus() {
  return safeGet('/auth/current');
}

/**
 * 登录
 * @param {string} username
 * @param {string} password
 * @returns {Promise<object>}
 */
async function login(username, password) {
  return safePost('/auth/login', { username, password });
}

/**
 * 登出
 * @returns {Promise<object>}
 */
async function logout() {
  return safePost('/auth/logout', {});
}

// 导出
if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    AUTH_KEY,
    AUTH_USER,
    getCurrentUser,
    isAuthenticated,
    isAdmin,
    doLogout,
    initUserDisplay,
    checkAuthStatus,
    login,
    logout
  };
}