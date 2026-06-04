/**
 * Layout Loader - 共享页面外壳 JavaScript
 * 为独立页面提供：导航函数、侧边栏管理、认证、用户显示、健康检查、修改密码
 *
 * 使用方式：在页面 <script> 中调用 LayoutLoader.init({ activeNavTab: 'connections' })
 */

// ── 导航路由表 ──────────────────────────────────────────────────────────────
var NAV_ROUTES = {
  'connections':      '/connections',
  'diagnosis-cap':    '/diagnosis-center',
  'task-center':      '/tasks',
  'toolchain-center': '/tasks#toolbox',
  'hotfix':           '/workspace#hotfix',
  'profiler':         '/workspace#profiler',
  'terminal':         '/workspace#terminal',
  'monitor':          '/workspace#monitor',
  'filebrowser':      '/workspace#filebrowser',
  'model-config':     '/workspace#model-config',
  'mcp-center':       '/mcp-config.html',
  'skill-management': '/skill-management.html',
  'user-management':  '/user-management.html',
  'audit-logs':       '/audit-logs.html',
  'alerts':           '/alerts',
};

// ── 导航函数 ────────────────────────────────────────────────────────────────
function navigateTo(tabId) {
  var route = NAV_ROUTES[tabId];
  if (route) {
    window.location.href = route;
  }
}

// ── 侧边栏分组折叠 ──────────────────────────────────────────────────────────
function toggleSideNavGroup(btn) {
  var group = btn.closest('.side-nav-group');
  if (!group) return;
  group.classList.toggle('collapsed');
}

// ── 认证工具 ─────────────────────────────────────────────────────────────────
// AUTH_KEY / AUTH_USER 由 auth.js 定义；独立页面若未加载 auth.js 则在此兜底定义
if (typeof AUTH_KEY === 'undefined') var AUTH_KEY  = 'arthas_auth_token';
if (typeof AUTH_USER === 'undefined') var AUTH_USER = 'arthas_auth_user';

function doLogout() {
  fetch('/api/auth/logout', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
    credentials: 'include'
  }).catch(function() {}).then(function() {
    sessionStorage.removeItem(AUTH_KEY);
    sessionStorage.removeItem(AUTH_USER);
    localStorage.removeItem(AUTH_KEY);
    localStorage.removeItem(AUTH_USER);
    localStorage.removeItem('arthas_remember');
    window.location.href = '/login.html';
  });
}

function isAdmin() {
  try {
    var userStr = sessionStorage.getItem(AUTH_USER) || localStorage.getItem(AUTH_USER);
    var user = userStr ? JSON.parse(userStr) : null;
    return user && user.role === 'admin';
  } catch (e) { return false; }
}

function initUserDisplay() {
  var user = null, role = 'user', username = '—';
  try {
    var userStr = sessionStorage.getItem(AUTH_USER) || localStorage.getItem(AUTH_USER);
    user = userStr ? JSON.parse(userStr) : null;
  } catch (e) {}
  if (user) {
    username = user.username || '—';
    role = user.role || 'user';
  }
  var el = document.getElementById('loginUser');
  if (el) el.textContent = username;
  // admin-only visibility
  document.querySelectorAll('.admin-only').forEach(function(el) {
    el.style.display = role === 'admin' ? '' : 'none';
  });
}

// ── 健康检查 ─────────────────────────────────────────────────────────────────
function checkServerHealth() {
  fetch('/api/health').then(function(r) { return r.json(); }).then(function(d) {
    var dot = document.getElementById('svDot');
    var lbl = document.getElementById('svLbl');
    if (dot) dot.className = 'dot ok';
    if (lbl) lbl.textContent = '✅ 服务正常';
  }).catch(function() {
    var dot = document.getElementById('svDot');
    var lbl = document.getElementById('svLbl');
    if (dot) dot.className = 'dot err';
    if (lbl) lbl.textContent = '❌ 服务不可达';
  });
}

// ── 修改密码弹窗 ─────────────────────────────────────────────────────────────
function openChangePasswordModal() {
  var modal = document.getElementById('pwdModal');
  if (modal) { modal.style.display = 'flex'; modal.style.alignItems = 'center'; modal.style.justifyContent = 'center'; }
  var errEl = document.getElementById('pwdModalErr');
  if (errEl) errEl.style.display = 'none';
  var oldEl = document.getElementById('pwdOld');
  if (oldEl) oldEl.value = '';
  var newEl = document.getElementById('pwdNew');
  if (newEl) newEl.value = '';
  var confirmEl = document.getElementById('pwdConfirm');
  if (confirmEl) confirmEl.value = '';
}

function closeChangePasswordModal() {
  var modal = document.getElementById('pwdModal');
  if (modal) modal.style.display = 'none';
}

function submitChangePassword() {
  var oldPwd = document.getElementById('pwdOld').value;
  var newPwd = document.getElementById('pwdNew').value;
  var confirmPwd = document.getElementById('pwdConfirm').value;
  var errEl = document.getElementById('pwdModalErr');

  if (!oldPwd || !newPwd) {
    if (errEl) { errEl.textContent = '请填写完整'; errEl.style.display = 'block'; }
    return;
  }
  if (newPwd !== confirmPwd) {
    if (errEl) { errEl.textContent = '两次输入的密码不一致'; errEl.style.display = 'block'; }
    return;
  }
  if (newPwd.length < 6) {
    if (errEl) { errEl.textContent = '密码长度不能少于6位'; errEl.style.display = 'block'; }
    return;
  }

  safePost('/api/auth/change-password', { old_password: oldPwd, new_password: newPwd })
    .then(function() {
      closeChangePasswordModal();
      toast('密码修改成勿，请重新登录', 'ok');
      setTimeout(function() { doLogout(); }, 1500);
    })
    .catch(function(e) {
      if (errEl) { errEl.textContent = e.message || '修改失败'; errEl.style.display = 'block'; }
    });
}

// ── Toast 通知 ────────────────────────────────────────────────────────────────
function toast(msg, type) {
  var container = document.getElementById('toast');
  if (!container) return;
  var div = document.createElement('div');
  div.className = 'toast-item' + (type ? ' toast-' + type : '');
  div.textContent = msg;
  container.appendChild(div);
  setTimeout(function() { div.remove(); }, 3500);
}

// ── 侧边栏激活状态 ───────────────────────────────────────────────────────────
function highlightActiveNav(activeNavTab) {
  document.querySelectorAll('[data-nav-tab]').forEach(function(el) {
    el.classList.toggle('on', el.getAttribute('data-nav-tab') === activeNavTab);
  });
  // Auto-expand the group containing the active item
  var activeItem = document.querySelector('[data-nav-tab="' + activeNavTab + '"]');
  if (activeItem) {
    var group = activeItem.closest('.side-nav-group');
    if (group && group.classList.contains('collapsed')) {
      group.classList.remove('collapsed');
    }
  }
}

// ── 页面初始化 ────────────────────────────────────────────────────────────────
var LayoutLoader = {
  init: function(options) {
    options = options || {};
    var activeNavTab = options.activeNavTab || '';

    // Auth guard
    (async function() {
      try {
        var resp = await fetch('/api/auth/current', { credentials: 'include' });
        var data = await resp.json();
        if (!data || !data.authenticated) {
          window.location.replace('/login.html');
          return;
        }
      } catch (e) {
        window.location.replace('/login.html');
        return;
      }
      // After auth confirmed, init UI
      initUserDisplay();
      checkServerHealth();
      highlightActiveNav(activeNavTab);
      // Load external links if available
      if (typeof loadExternalLinks === 'function') loadExternalLinks();
      // Callback
      if (typeof options.onReady === 'function') options.onReady();
    })();
  }
};
