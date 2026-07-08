

// ── 工具函数 ──────────────────────────────────────────────────────────────────
function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text || '';
  return div.innerHTML;
}

// ── 认证工具 ──────────────────────────────────────────────────────────────────
// auth.js 已定义 AUTH_KEY, AUTH_USER，不要重复声明

async function doLogout() {
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
  localStorage.removeItem('arthas_remember');
  // HTTP 模式（K8s/Docker）跳到 /login.html，file:// 模式跳到 login.html
  window.location.href = window.location.protocol.startsWith('http') ? '/login.html' : 'login.html';
}

function initUserDisplay() {
  // 解析用户信息
  let user = null, role = 'user', username = '游客';
  try {
    const userStr = sessionStorage.getItem(AUTH_USER) || localStorage.getItem(AUTH_USER);
    user = userStr ? JSON.parse(userStr) : null;
  } catch {}
  if (user) {
    username = user.username || '未知';
    role = user.role || 'user';
  }
  
  const el = document.getElementById('loginUser');
  if(el) el.textContent = username;
  
  // 根据角色控制管理员链接的显示
  document.querySelectorAll('.admin-only').forEach(el => {
    el.style.display = role === 'admin' ? '' : 'none';
  });
}

// ── 统一导航路由 ─────────────────────────────────────────────────────────────
// 从独立页面和 index.html 统一调用；index.html 内使用 switchTab，其他页面跳转 URL
var NAV_ROUTES = {
  'connections':      '/',
  'diagnosis-cap':    '/diagnosis-center',
  'task-center':      '/tasks',
  'toolchain-center': '/tasks#toolbox',
  'hotfix':           '/#hotfix',
  'profiler':         '/#sampling',
  'terminal':         '/#terminal',
  'monitor':          '/#monitor',
  'filebrowser':      '/#files',
  'model-config':     '/#model-config',
  'mcp-center':       '/mcp-config.html',
  'cluster-management': '/cluster-management.html',
  'skill-management': '/skill-management.html',
  'user-management':  '/user-management.html',
  'audit-logs':       '/audit-logs.html',
  'alerts':           '/alerts',
};

const WORKSPACE_DEEP_LINK_ALIAS = {
  workspace: '',
  connections: 'connections',
  profiler: 'sampling',
  sampling: 'sampling',
  console: 'console',
  'arthas-console': 'console',
  terminal: 'terminal',
  monitor: 'monitor',
  filebrowser: 'files',
  files: 'files',
  hotfix: 'hotfix',
  history: 'history',
  diagnose: 'diag',
  diag: 'diag',
  'model-config': 'model-config',
  'task-center': 'task-center',
  'toolchain-center': 'toolchain-center',
  'diagnosis-cap': 'diagnosis-cap',
  alerts: 'alerts',
};

const WORKSPACE_MANAGED_TABS = ['monitor', 'sampling', 'console', 'terminal', 'files', 'history', 'hotfix', 'diag'];

function normalizeWorkspaceDeepLinkTab(rawTab) {
  const key = String(rawTab || '').trim().replace(/^#/, '').toLowerCase();
  return WORKSPACE_DEEP_LINK_ALIAS[key] || key;
}

function readWorkspaceDeepLinkIntent() {
  const params = new URLSearchParams(window.location.search || '');
  const connId = params.get('conn') || params.get('connection_id') || params.get('connectionId') || '';
  const rawTab = params.get('tab') || (window.location.hash || '').replace(/^#/, '');
  return {
    connId,
    rawTab,
    tab: normalizeWorkspaceDeepLinkTab(rawTab),
  };
}

function applyWorkspaceDeepLink() {
  const intent = readWorkspaceDeepLinkIntent();
  if (!intent.connId && !intent.tab) return false;

  const focusId = intent.connId && getConnectionRecordById(intent.connId) ? intent.connId : '';
  if (intent.tab === 'connections') {
    showWorkspace();
    if (focusId && window.ConnectionPool && typeof ConnectionPool.focus === 'function') {
      ConnectionPool.focus(focusId);
    }
    return true;
  }

  if (WORKSPACE_MANAGED_TABS.includes(intent.tab) || focusId) {
    showWorkspace();
    if (focusId) {
      if (window.ConnectionPool && typeof ConnectionPool.focus === 'function') {
        ConnectionPool.focus(focusId);
      } else if (window.ConnectionStore && typeof ConnectionStore.setFocus === 'function') {
        ConnectionStore.setFocus(focusId);
      }
    }
    const focusConn = window.ConnectionStore && typeof ConnectionStore.getFocusConnection === 'function'
      ? ConnectionStore.getFocusConnection()
      : (focusId ? getConnectionRecordById(focusId) : null);
    if (intent.tab && WORKSPACE_MANAGED_TABS.includes(intent.tab) && focusConn && window.ConnectionWorkspace && typeof ConnectionWorkspace.switchTab === 'function') {
      if (window.ConnectionStore && typeof ConnectionStore.updateConnection === 'function') {
        ConnectionStore.updateConnection(focusConn.id, { tab: intent.tab });
      }
      ConnectionWorkspace.switchTab(intent.tab);
    } else if (window.ConnectionWorkspace && typeof ConnectionWorkspace.render === 'function') {
      ConnectionWorkspace.render();
    }
    return true;
  }

  if (intent.tab && typeof switchTab === 'function' && document.getElementById('panel-' + intent.tab)) {
    setMainShellMode('legacy');
    switchTab(intent.tab);
    return true;
  }

  return false;
}

window.applyWorkspaceDeepLink = applyWorkspaceDeepLink;
window.addEventListener('hashchange', applyWorkspaceDeepLink);

function setMainShellMode(mode) {
  var isWorkspace = mode === 'workspace';
  window.__mainShellMode = isWorkspace ? 'workspace' : 'legacy';
  var pool = document.getElementById('connectionPool');
  var workspaceArea = document.getElementById('workspaceArea');
  var legacyPanels = document.getElementById('legacyPanels');
  if (pool) pool.style.display = isWorkspace ? 'flex' : 'none';
  if (workspaceArea) workspaceArea.style.display = isWorkspace ? 'flex' : 'none';
  if (legacyPanels) legacyPanels.style.display = isWorkspace ? 'none' : 'flex';
  if (!isWorkspace && window.ConnectionWorkspace && typeof ConnectionWorkspace.restoreLegacyPanel === 'function') {
    ConnectionWorkspace.restoreLegacyPanel();
  }
}

function navigateTo(tabId) {
  if (typeof switchTab === 'function' && document.getElementById('panel-' + tabId)) {
    setMainShellMode('legacy');
    switchTab(tabId);
  } else {
    var route = NAV_ROUTES[tabId];
    if (route) {
      window.location.href = route;
    }
  }
}

window.showWorkspace = function() {
  setMainShellMode('workspace');
  var tabs = document.getElementById('workspaceTabs');
  if (tabs) tabs.style.display = 'none';
  var oldTabbar = document.querySelector('.tabbar');
  if (oldTabbar) oldTabbar.style.display = 'none';
  if (typeof highlightActiveNav === 'function') highlightActiveNav('workspace');
  if (window.ConnectionWorkspace && typeof ConnectionWorkspace.render === 'function') {
    ConnectionWorkspace.render();
  }
};

window.showToolbox = function() {
  setMainShellMode('legacy');
  var tabs = document.getElementById('workspaceTabs');
  if (tabs) tabs.style.display = 'none';
  var oldTabbar = document.querySelector('.tabbar');
  if (oldTabbar) oldTabbar.style.display = 'none';
  switchTab('toolchain-center');
};

window.switchWorkspaceTab = function(tabId) {
  var tabs = document.getElementById('workspaceTabs');
  if (tabs) tabs.style.display = 'flex';

  var tabPanelMap = {
    'connect':    ['panel-connections'],
    'monitor':    ['panel-monitor'],
    'sampling':   ['panel-profiler'],
    'diagnosis':  ['panel-diag'],
    'history':    ['panel-history'],
  };

  // Hide ALL .panel elements
  document.querySelectorAll('.panel').forEach(function(p) {
    p.style.display = 'none';
    p.classList.remove('on');
  });

  // Show panels for this tab
  var panels = tabPanelMap[tabId] || [];
  panels.forEach(function(panelId) {
    var el = document.getElementById(panelId);
    if (el) {
      el.style.display = 'flex';
      el.classList.add('on');
    }
  });

  // Update tab active state
  document.querySelectorAll('.ws-tab').forEach(function(t) { t.classList.remove('active'); });
  var tab = document.querySelector('[data-ws-tab="' + tabId + '"]');
  if (tab) tab.classList.add('active');

  // Update workspace title
  var titles = {
    connect:    ['Connection', '连接配置'],
    monitor:    ['Monitor', 'Pod 监控'],
    sampling:   ['Sampling', '采样工具'],
    diagnosis:  ['Diagnosis', '诊断中心'],
    history:    ['History', '历史记录'],
  };
  var pair = titles[tabId] || ['', ''];
  var kicker = document.getElementById('workspaceKicker');
  var title = document.getElementById('workspaceTitle');
  if (kicker) kicker.textContent = pair[0];
  if (title) title.textContent = pair[1];

  // Update connection bar visibility
  updateConnectionBarVisibility(tabId === 'connect' ? 'connections' : tabId);

  // Load monitor data when switching to monitor tab
  if (tabId === 'monitor' && typeof loadSnap === 'function') {
    setTimeout(function() { loadSnap(); }, 100);
  }
};

// 任务中心子面板导航
function navigateToTaskCenter(panel) {
  setMainShellMode('legacy');
  if (typeof switchTab === 'function' && document.getElementById('panel-task-center')) {
    switchTab('task-center');
  } else {
    window.location.href = '/tasks#task-center';
  }
  setTimeout(function () {
    if (typeof scSwitchPanel === 'function') scSwitchPanel(panel);
    var navTab = { tasks: 'task-center', schedules: 'task-schedules', runs: 'task-runs' }[panel] || 'task-center';
    if (typeof highlightActiveNav === 'function') highlightActiveNav(navTab);
  }, 100);
}

// 诊断中心子面板导航（侧边栏导航模式）
function navigateToDiagnosis(section) {
  setMainShellMode('legacy');
  if (typeof switchTab === 'function' && document.getElementById('panel-diagnosis-cap')) {
    switchTab('diagnosis-cap');
  } else {
    window.location.href = '/diagnosis-center';
  }
  setTimeout(function () {
    if (typeof dcSwitchSection === 'function') dcSwitchSection(section);
  }, 100);
}

// ── 侧边栏激活高亮（独立页面也用到） ────────────────────────────────────────
function highlightActiveNav(activeNavTab) {
  document.querySelectorAll('[data-nav-tab]').forEach(function(el) {
    el.classList.toggle('on', el.getAttribute('data-nav-tab') === activeNavTab);
  });
  var activeItem = document.querySelector('[data-nav-tab="' + activeNavTab + '"]');
  if (activeItem) {
    var group = activeItem.closest('.side-nav-group');
    if (group && group.classList.contains('collapsed')) {
      group.classList.remove('collapsed');
    }
  }
}

// ── Topbar Global Menu ────────────────────────────────────────────────────────
function openConnectionCenter() {
  navigateTo('connections');
}

const PAGE_SCENE_META = {
  connections: { required: 'none', showConnBar: true },
  profiler: { required: 'arthas', showConnBar: true },
  console: { required: 'arthas', showConnBar: true },
  terminal: { required: 'pod', showConnBar: true },
  monitor: { required: 'pod', showConnBar: true },
  filebrowser: { required: 'pod', showConnBar: true },
  diag: { required: 'pod', showConnBar: true },
  ai: { required: 'none', showConnBar: true },
  history: { required: 'none', showConnBar: true },
  'model-config': { required: 'none', showConnBar: false },
  'mcp-center': { required: 'none', showConnBar: false },
  'task-center': { required: 'none', showConnBar: false },
  'toolchain-center': { required: 'none', showConnBar: false },
  'external-system': { required: 'none', showConnBar: false },
  'user-management': { required: 'none', showConnBar: false },
  'audit-logs': { required: 'none', showConnBar: false },
  'skill-management': { required: 'none', showConnBar: false },
  'cluster-management': { required: 'none', showConnBar: false },
  'alerts': { required: 'none', showConnBar: false },
  'hotfix': { required: 'arthas', showConnBar: true },
  'diagnosis-cap': { required: 'none', showConnBar: true },
};

function updateConnectionBarVisibility(tab) {
  const meta = PAGE_SCENE_META[tab] || { showConnBar: true };
  window.__hideConnStatusBar = meta.showConnBar === false;
  const bar = document.getElementById('connStatusBar');
  if (bar) bar.style.display = window.__hideConnStatusBar ? 'none' : '';
  const head = document.querySelector('#legacyPanels > .workspace-head');
  if (head) head.style.display = window.__hideConnStatusBar ? 'none' : '';
}

function openTaskCenter() {
  switchTab('task-center');
}

function openToolchainCenter() {
  switchTab('toolchain-center');
  loadToolchainCenter();
}

function openModelConfig() {
  switchTab('model-config');
}

function openMcpCenter() {
  switchTab('mcp-center');
}

function syncFrameTheme(frame) {
  if (!frame) return;
  try {
    const theme = (window.OpsTheme && OpsTheme.current && OpsTheme.current()) || localStorage.getItem('ops_ui_theme') || 'apm';
    try {
      if (frame.contentDocument && frame.contentDocument.documentElement) {
        if (theme === 'devops') frame.contentDocument.documentElement.setAttribute('data-ops-theme', 'devops');
        else frame.contentDocument.documentElement.removeAttribute('data-ops-theme');
      }
    } catch (_) {}
    frame.contentWindow?.postMessage({ type: 'ops-ui-theme', theme }, window.location.origin);
  } catch (e) {}
}

function bindFrameThemeSync(frame) {
  if (!frame || frame.dataset.themeSyncBound) return;
  frame.dataset.themeSyncBound = '1';
  frame.addEventListener('load', function() { syncFrameTheme(frame); });
}

function loadAdminFrameIfNeeded(tab) {
  if (!['user-management', 'audit-logs', 'skill-management', 'cluster-management', 'alerts', 'mcp-center'].includes(tab)) return;
  if (['user-management', 'audit-logs', 'skill-management', 'cluster-management', 'alerts'].includes(tab) && !(typeof isAdmin === 'function' && isAdmin())) return;
  const frame = document.querySelector(`#panel-${tab} iframe[data-src], #panel-${tab} iframe`);
  bindFrameThemeSync(frame);
  if (frame && frame.dataset.src && !frame.getAttribute('src')) {
    frame.setAttribute('src', frame.dataset.src);
  } else {
    syncFrameTheme(frame);
  }
}

// ── Toolchain Center ─────────────────────────────────────────────────────────
let _toolPackages = [];
let _toolchainLoading = false;

const ARTHAS_USER_CASE_CAPABILITIES = [
  { name: 'CPU 高负载一键诊断', issue: '#1202/#569', stage: 'M1', cmd: 'thread/profiler/trace', desc: '高 CPU 线程定位、热点方法与采样报告组合。' },
  { name: 'Trace 调用链耗时分析', issue: '#597/#764/#729', stage: 'M1', cmd: 'trace', desc: '方法调用树、慢调用和 Controller/Service/DAO 分层耗时。' },
  { name: 'Watch 方法现场观测', issue: '#764/#772', stage: 'M1', cmd: 'watch/ognl', desc: '观察入参、返回值、异常和对象字段。' },
  { name: 'Controller 请求入口定位', issue: '#729', stage: 'M1', cmd: 'stack/trace', desc: '定位请求进入的 Controller、Interceptor 与 Service。' },
  { name: 'TraceId 上下文提取', issue: '#1244', stage: 'M2', cmd: 'ognl/MDC', desc: '从 MDC、ThreadLocal 或 RPC 上下文提取 traceId。' },
  { name: 'Spring 事务配置生效诊断', issue: '#764', stage: 'M1', cmd: 'sc/trace/watch', desc: '验证事务代理、超时和传播行为是否真的生效。' },
  { name: 'Logger 动态日志级别调整', issue: '#849', stage: 'M1', cmd: 'logger', desc: '在线查看与调整日志级别，排查后恢复。' },
  { name: 'Heapdump 内存快照工具', issue: '#849', stage: 'M1', cmd: 'heapdump', desc: '生成堆快照并配合文件下载服务导出。' },
  { name: 'VMOption 运行时参数查看', issue: '#849', stage: 'M1', cmd: 'vmoption', desc: '查看/调整 HotSpot Diagnostic Options。' },
  { name: 'ClassLoader 类冲突排查', issue: '#763/#1003', stage: 'M1', cmd: 'sc/classloader/jad', desc: '定位类来源、ClassLoader hash 和线上实际字节码。' },
  { name: 'Spectre 热替换工作台', issue: 'spectre', stage: 'M2', cmd: 'jad/mc/retransform', desc: '借鉴 Spectre，把反编译、编辑、编译、热替换做成工作台。' },
];

function renderArthasUserCaseCapabilities() {
  const el = document.getElementById('arthasUserCaseList');
  if (!el) return;
  el.innerHTML = ARTHAS_USER_CASE_CAPABILITIES.map(item => {
    const tpl = _taskTemplates.find(t => t.name === item.name || (item.name === 'Spectre 热替换工作台' && t.name === 'Arthas jad/retransform 热更新工作流'));
    const action = tpl ? `createTaskFromTemplateQuick(${tpl.id})` : 'openTaskCenterFromToolchain()';
    return `<div class="arthas-user-case-item">
      <div class="arthas-user-case-top"><b>${escapeHtml(item.name)}</b><span>${escapeHtml(item.stage)} · ${escapeHtml(item.issue)}</span></div>
      <div class="arthas-user-case-desc">${escapeHtml(item.desc)}</div>
      <div class="arthas-user-case-cmd">${escapeHtml(item.cmd)}</div>
      <button class="btn btn-g" onclick="${action}">${tpl ? '创建工具任务' : '查看任务中心'}</button>
    </div>`;
  }).join('');
}

async function safeUploadToolPackage(url, form, timeoutMs = 300000) {
  const fullUrl = url.startsWith('http') ? url : `${API}${url}`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const r = await fetch(fullUrl, { method: 'POST', body: form, signal: controller.signal, credentials: 'include' });
    clearTimeout(timer);
    if (r.status === 401) {
      window.location.replace('/login.html');
      throw new Error('会话已过期，请重新登录');
    }
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || data.message || `上传失败 (${r.status})`);
    return data;
  } catch (e) {
    clearTimeout(timer);
    if (e.name === 'AbortError') throw new Error(`上传超时 (${timeoutMs / 1000}s)`);
    throw e;
  }
}

function renderToolQuickPlans() {
  const el = document.getElementById('toolQuickPlanList');
  if (!el) return;
  const names = ['Arthas jad/retransform 热更新工作流', 'Arthas 上传源码覆盖并 retransform', 'Pod Python 文件下载服务'];
  el.innerHTML = names.map(name => {
    const tpl = _taskTemplates.find(t => t.name === name);
    const action = tpl ? `createTaskFromTemplateQuick(${tpl.id})` : 'openTaskCenterFromToolchain()';
    return `<div class="tool-quick-plan"><div><b>${escapeHtml(name)}</b><span>${tpl ? escapeHtml(tpl.description || '') : '请先刷新任务中心模板'}</span></div><button class="btn btn-g" onclick="${action}">${tpl ? '创建任务' : '查看模板'}</button></div>`;
  }).join('');
}

async function createTaskFromTemplateQuick(templateId) {
  switchTab('task-center');
  await loadTaskCenter();
  const sel = document.getElementById('taskTemplate');
  if (sel) {
    sel.value = String(templateId);
    syncTaskTemplateRuntime();
  }
  toast('已切换到任务中心，可基于该模板创建任务', 'ok');
}

async function uploadArthasSourceFromForm() {
  const fileEl = document.getElementById('arthasSourceFile');
  const file = fileEl?.files?.[0];
  const target = getToolchainTargetFromForm();
  if (!file) return toast('请选择 .java 源码文件', 'warn');
  if (!target.cluster_name || !target.pod_name) return toast('请填写 Pod 分发目标', 'warn');
  const form = new FormData();
  form.append('file', file);
  form.append('cluster_name', target.cluster_name);
  form.append('namespace', target.namespace);
  form.append('pod_name', target.pod_name);
  form.append('container', target.container);
  form.append('source_dir', document.getElementById('arthasSourceDir')?.value?.trim() || '/tmp/arthas-sources');
  try {
    await safeUploadToolPackage('/tasks/arthas/source-upload', form, 300000);
    toast('Java 源码已上传到 Pod，可执行 mc + retransform', 'ok');
    fileEl.value = '';
  } catch (e) {
    toast(`源码上传失败：${e.message}`, 'err');
  }
}

function toolStatusLabel(status) {
  const map = { active: '可用', inactive: '未就绪', missing: '缺失', disabled: '停用' };
  return map[status] || status || '-';
}

function toolTypeLabel(type) {
  const map = { arthas: 'Arthas', 'async-profiler': 'async-profiler', jattach: 'jattach', generic: '通用工具' };
  return map[type] || type || '通用工具';
}

function renderToolchainSummary() {
  const el = document.getElementById('toolchainSummary');
  if (!el) return;
  const total = _toolPackages.length;
  const active = _toolPackages.filter(p => p.status === 'active').length;
  const arthas = _toolPackages.filter(p => p.tool_type === 'arthas').length;
  const uploaded = _toolPackages.filter(p => p.source_type === 'upload').length;
  const items = [['工具包', total], ['可用', active], ['Arthas', arthas], ['已上传', uploaded]];
  el.innerHTML = items.map(([label, value]) => `<div class="task-stat"><span>${label}</span><b>${value}</b></div>`).join('');
}

function getToolchainTargetFromForm() {
  return {
    cluster_name: document.getElementById('toolTargetCluster')?.value?.trim() || '',
    namespace: document.getElementById('toolTargetNamespace')?.value?.trim() || 'default',
    pod_name: document.getElementById('toolTargetPod')?.value?.trim() || '',
    container: document.getElementById('toolTargetContainer')?.value?.trim() || '',
    install_path: document.getElementById('toolTargetInstallPath')?.value?.trim() || '/tmp/arthas/arthas-boot.jar',
  };
}

function fillToolchainPodTargetFromCurrent() {
  const target = typeof getCurrentPodTarget === 'function' ? getCurrentPodTarget() : {};
  const map = {
    toolTargetCluster: target.cluster_name || '',
    toolTargetNamespace: target.namespace || 'default',
    toolTargetPod: target.pod_name || '',
    toolTargetContainer: target.container || '',
  };
  Object.entries(map).forEach(([id, value]) => {
    const el = document.getElementById(id);
    if (el) el.value = value;
  });
  if (!target.cluster_name || !target.pod_name) toast('当前没有可填充的 Pod 连接，请手动填写目标', 'warn');
}

function renderToolPackages() {
  renderToolchainSummary();
  const list = document.getElementById('toolPackageList');
  if (!list) return;
  if (!_toolPackages.length) {
    list.innerHTML = '<div class="sb-empty">暂无工具包<br>可上传 arthas-boot.jar 或使用内置 Arthas 离线工具。</div>';
    return;
  }
  list.innerHTML = _toolPackages.map(p => {
    const sha = p.sha256 ? `${escapeHtml(p.sha256.slice(0, 12))}…${escapeHtml(p.sha256.slice(-8))}` : '未校验';
    const size = p.file_size ? fmtSz(p.file_size) : '-';
    const active = p.status === 'active';
    return `<div class="toolchain-package-item">
      <div class="toolchain-package-main">
        <div>
          <div class="task-item-name">${escapeHtml(p.file_name || p.name)} ${p.is_builtin ? '<span class="task-status running">内置</span>' : ''}</div>
          <div class="task-item-meta">类型：${toolTypeLabel(p.tool_type)} · 版本：${escapeHtml(p.version || '-')} · 文件：${escapeHtml(p.file_name || p.file_path || '-')} · 大小：${size} · 模板：${p.template_count || 0}</div>
          <div class="toolchain-hash">SHA256 ${sha} · Pod 安装路径 ${escapeHtml(p.install_path || '-')}</div>
        </div>
        <div class="task-item-actions">
          <span class="task-status ${escapeHtml(p.status || '')}">${toolStatusLabel(p.status)}</span>
          <button class="btn btn-g" onclick="verifyToolPackage(${p.id})">校验</button>
          <button class="btn btn-p" onclick="distributeToolPackage(${p.id})">分发到 Pod</button>
          <button class="btn btn-g" onclick="toggleToolPackageStatus(${p.id}, '${active ? 'disabled' : 'active'}')">${active ? '停用' : '启用'}</button>
          ${p.is_builtin ? '' : `<button class="btn btn-g danger-text" onclick="deleteToolPackage(${p.id})">删除</button>`}
        </div>
      </div>
    </div>`;
  }).join('');
}

async function loadToolchainCenter() {
  if (_toolchainLoading) return;
  _toolchainLoading = true;
  try {
    const data = await safeGet('/tasks/tool-packages');
    _toolPackages = data.packages || [];
    renderToolPackages();
    if (!_taskTemplates.length) {
      try {
        const tpl = await safeGet('/tasks/templates');
        _taskTemplates = tpl.templates || [];
      } catch (_) {}
    }
    renderToolQuickPlans();
    renderArthasUserCaseCapabilities();
    
    // ✅ 新增: 渲染工具箱双栏布局
    if (typeof renderToolboxDualLayout === 'function') {
      renderToolboxDualLayout();
    }

    // ✅ 新增：加载分发历史
    await loadDistributionHistory();
  } catch (e) {
    toast(`工具链加载失败：${e.message}`, 'err');
  } finally {
    _toolchainLoading = false;
  }
}

async function createToolPackageFromForm() {
  const body = {
    name: document.getElementById('toolPackageName')?.value?.trim() || '',
    tool_type: document.getElementById('toolPackageType')?.value || 'arthas',
    version: document.getElementById('toolPackageVersion')?.value?.trim() || '',
    install_path: document.getElementById('toolPackageInstallPath')?.value?.trim() || '/tmp/arthas/arthas-boot.jar',
    description: document.getElementById('toolPackageDesc')?.value?.trim() || '',
  };
  if (!body.name) return toast('请填写工具名称', 'warn');
  try {
    await safePost('/tasks/tool-packages', body);
    toast('工具包已创建', 'ok');
    await loadToolchainCenter();
  } catch (e) {
    toast(`创建工具包失败：${e.message}`, 'err');
  }
}

async function uploadToolPackageFromForm() {
  const fileEl = document.getElementById('toolPackageFile');
  const file = fileEl?.files?.[0];
  if (!file) return toast('请选择离线工具文件', 'warn');
  const form = new FormData();
  form.append('file', file);
  form.append('name', document.getElementById('toolPackageName')?.value?.trim() || file.name);
  form.append('tool_type', document.getElementById('toolPackageType')?.value || 'arthas');
  form.append('version', document.getElementById('toolPackageVersion')?.value?.trim() || '');
  form.append('install_path', document.getElementById('toolPackageInstallPath')?.value?.trim() || '/tmp/arthas/arthas-boot.jar');
  form.append('description', document.getElementById('toolPackageDesc')?.value?.trim() || '');
  try {
    await safeUploadToolPackage('/tasks/tool-packages/upload', form, 300000);
    toast('离线工具已上传', 'ok');
    fileEl.value = '';
    await loadToolchainCenter();
  } catch (e) {
    toast(`上传失败：${e.message}`, 'err');
  }
}

async function verifyToolPackage(packageId) {
  try {
    const data = await safePost(`/tasks/tool-packages/${packageId}/verify`, {});
    toast(data.ok ? '工具文件校验通过' : '工具文件不存在或不可用', data.ok ? 'ok' : 'warn');
    await loadToolchainCenter();
  } catch (e) {
    toast(`校验失败：${e.message}`, 'err');
  }
}

async function distributeToolPackage(packageId) {
  const target = getToolchainTargetFromForm();
  if (!target.cluster_name || !target.pod_name) return toast('请填写 Pod 分发目标', 'warn');
  try {
    toast('开始分发离线工具到 Pod...', 'info');
    const result = await safePost(`/tasks/tool-packages/${packageId}/distribute`, target, 300000);
    const data = result.data || result;

    if (data.ok) {
      let msg = '离线工具已分发到 Pod';
      if (data.install_path) {
        msg += `\n安装路径: ${data.install_path}`;
      }
      if (data.pod_check_status === 'verified' && data.sha256_match !== null) {
        msg += data.sha256_match
          ? '\n✓ SHA256 校验一致'
          : `\n⚠ SHA256 不匹配\n本地: ${data.local_sha256}\nPod: ${data.pod_sha256}`;
      }
      toast(msg, 'ok');

      // 显示分发详情
      if (data.stderr) {
        console.warn('分发警告:', data.stderr);
      }
    } else {
      let errMsg = data.error_message || '分发失败';
      if (data.stderr) {
        errMsg += `\n\nPod stderr:\n${data.stderr}`;
      }
      toast(errMsg, 'err');
    }

    await loadToolchainCenter();
    await loadDistributionHistory();
  } catch (e) {
    let errMsg = `分发失败：${e.message}`;
    if (e.response?.data?.stderr) {
      errMsg += `\n\nPod stderr:\n${e.response.data.stderr}`;
    }
    toast(errMsg, 'err');
  }
}

// ── 工具包分发历史 ───────────────────────────────────────────────────────
let _distributionHistory = [];

async function loadDistributionHistory() {
  try {
    const data = await safeGet('/tasks/tool-packages/distributions?limit=20');
    _distributionHistory = data.distributions || [];
    renderDistributionHistory();
  } catch (e) {
    console.warn('加载分发历史失败:', e.message);
    // 不显示 toast，避免干扰用户
  }
}

function renderDistributionHistory() {
  const container = document.getElementById('distributionHistory');
  if (!container) return;

  if (!_distributionHistory.length) {
    container.innerHTML = '<div class="empty-hint">暂无分发记录</div>';
    return;
  }

  container.innerHTML = _distributionHistory.map(d => {
    const statusClass = d.status === 'success' ? 'status-ok' : 'status-err';
    const statusText = d.status === 'success' ? '✓ 成功' : '✗ 失败';
    const time = d.created_at ? new Date(d.created_at).toLocaleString('zh-CN') : '';
    const target = [d.target_cluster, d.target_namespace, d.target_pod]
      .filter(Boolean)
      .join('/');

    let details = '';
    if (d.pod_check_status === 'verified' && d.local_sha256 && d.pod_sha256) {
      const match = d.local_sha256 === d.pod_sha256;
      details += `<div class="dist-detail">`;
      details += `<span>本地 SHA256: <code>${d.local_sha256.substring(0, 16)}...</code></span>`;
      details += `<span>Pod SHA256: <code>${d.pod_sha256.substring(0, 16)}...</code></span>`;
      details += `<span class="${match ? 'text-ok' : 'text-err'}">${match ? '✓ 校验一致' : '⚠ 校验不匹配'}</span>`;
      details += `</div>`;
    }

    if (d.stderr) {
      details += `<div class="dist-stderr"><strong>stderr:</strong><pre>${escapeHtml(d.stderr)}</pre></div>`;
    }

    return `
      <div class="dist-record ${statusClass}">
        <div class="dist-header">
          <span class="dist-status">${statusText}</span>
          <span class="dist-package">${d.package_name || '工具包 #' + d.package_id}</span>
          <span class="dist-target" title="${target}">${target}</span>
          <span class="dist-path">${d.install_path}</span>
          <span class="dist-time">${time}</span>
        </div>
        ${details}
        ${d.error_message ? `<div class="dist-error">${escapeHtml(d.error_message)}</div>` : ''}
      </div>
    `;
  }).join('');
}

function escapeHtml(text) {
  if (!text) return '';
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

async function toggleToolPackageStatus(packageId, status) {
  try {
    await safePut(`/tasks/tool-packages/${packageId}`, { status });
    toast(status === 'active' ? '工具包已启用' : '工具包已停用', 'ok');
    await loadToolchainCenter();
  } catch (e) {
    toast(`操作失败：${e.message}`, 'err');
  }
}

async function deleteToolPackage(packageId) {
  if (!confirm('确认删除此离线工具包？上传文件也会被删除。')) return;
  try {
    await safeDelete(`/tasks/tool-packages/${packageId}`);
    toast('工具包已删除', 'ok');
    await loadToolchainCenter();
  } catch (e) {
    toast(`删除失败：${e.message}`, 'err');
  }
}

function openTaskCenterFromToolchain() {
  switchTab('task-center');
  loadTaskCenter();
}

// ── Task Center ───────────────────────────────────────────────────────────────
let _taskTemplates = [];
let _taskDefinitions = [];
let _taskRuns = [];
let _taskSchedules = [];
let _taskCenterLoading = false;

function taskRuntimeLabel(runtime) {
  return runtime === 'shell' ? 'Shell' : 'Python';
}

function taskExecutionModeLabel(mode) {
  return mode === 'pod' ? 'Pod 内执行' : 'Node 本机';
}

function taskTargetLabel(taskOrRun = {}) {
  const target = taskOrRun.target || {};
  if ((taskOrRun.execution_mode || 'node') !== 'pod') return '';
  const base = [target.cluster_name || target.cluster, target.namespace || 'default', target.pod_name || target.pod]
    .filter(Boolean)
    .join('/');
  return target.container ? `${base}/${target.container}` : base;
}

function getTaskPodTargetFromForm() {
  return {
    cluster_name: document.getElementById('taskCluster')?.value?.trim() || '',
    namespace: document.getElementById('taskNamespace')?.value?.trim() || 'default',
    pod_name: document.getElementById('taskPod')?.value?.trim() || '',
    container: document.getElementById('taskContainer')?.value?.trim() || '',
  };
}

function fillTaskPodTargetFromCurrent() {
  const target = typeof getCurrentPodTarget === 'function' ? getCurrentPodTarget() : {};
  const map = {
    taskCluster: target.cluster_name || '',
    taskNamespace: target.namespace || 'default',
    taskPod: target.pod_name || '',
    taskContainer: target.container || '',
  };
  Object.entries(map).forEach(([id, value]) => {
    const el = document.getElementById(id);
    if (el) el.value = value;
  });
  if (!target.cluster_name || !target.pod_name) toast('当前没有可填充的 Pod 连接，请手动填写目标', 'warn');
}

function toggleTaskTargetFields() {
  const mode = document.getElementById('taskExecutionMode')?.value || 'node';
  const box = document.getElementById('taskPodTargetBox');
  if (box) box.style.display = mode === 'pod' ? '' : 'none';
  if (mode === 'pod') fillTaskPodTargetFromCurrent();
}

function taskStatusLabel(status) {
  const map = { success: '成功', failed: '失败', timeout: '超时', running: '运行中', pending: '等待中' };
  return map[status] || status || '-';
}

function renderTaskSummary(overview = {}) {
  const el = document.getElementById('taskSummary');
  if (!el) return;
  const items = [
    ['模板', overview.templates ?? '-'],
    ['任务', overview.tasks ?? '-'],
    ['执行', overview.runs ?? '-'],
    ['运行中', overview.running ?? '-'],
    ['调度', overview.schedules ?? '-'],
  ];
  el.innerHTML = items.map(([label, value]) => `<div class="task-stat"><span>${label}</span><b>${value}</b></div>`).join('');
}

function renderTaskTemplateOptions() {
  const select = document.getElementById('taskTemplate');
  if (!select) return;
  const current = select.value;
  select.innerHTML = '<option value="">不使用模板 / 使用内联脚本</option>' + _taskTemplates.map(t => {
    const toolPackageName = t.tool_package_name || '未绑定工具包';
    return `<option value="${t.id}" data-runtime="${escapeHtml(t.runtime || 'python')}" data-timeout="${t.default_timeout || 60}">${escapeHtml(t.name)}（${escapeHtml(toolPackageName)} / ${taskRuntimeLabel(t.runtime)}）</option>`;
  }).join('');
  if (current && _taskTemplates.some(t => String(t.id) === String(current))) select.value = current;
}

function syncTaskTemplateRuntime() {
  const select = document.getElementById('taskTemplate');
  const opt = select?.selectedOptions?.[0];
  if (!opt || !opt.value) return;
  const runtime = opt.getAttribute('data-runtime') || 'python';
  const timeout = opt.getAttribute('data-timeout') || '60';
  const runtimeEl = document.getElementById('taskRuntime');
  const timeoutEl = document.getElementById('taskTimeout');
  if (runtimeEl) runtimeEl.value = runtime;
  if (timeoutEl) timeoutEl.value = timeout;
}

function renderTaskDefinitions() {
  const el = document.getElementById('taskDefinitionList');
  if (!el) return;
  if (!_taskDefinitions.length) {
    el.innerHTML = '<div class="sb-empty">暂无任务<br>可先使用内置模板创建一个 Node 本机或 Pod 内任务</div>';
    return;
  }
  el.innerHTML = _taskDefinitions.map(t => `
    <div class="task-item">
      <div class="task-item-main">
        <div>
          <div class="task-item-name">${escapeHtml(t.name)}</div>
          <div class="task-item-meta">执行位置：${taskExecutionModeLabel(t.execution_mode)}${taskTargetLabel(t) ? ' · 目标：' + escapeHtml(taskTargetLabel(t)) : ''} · 运行时：${taskRuntimeLabel(t.runtime)} · 模板：${escapeHtml(t.template_name || '内联脚本')} · 超时：${t.timeout_seconds || 60}s</div>
        </div>
        <div class="task-item-actions">
          <button class="btn btn-p" onclick="runTaskDefinition(${t.id})">执行</button>
          <button class="btn btn-g danger-text" onclick="deleteTaskDefinition(${t.id})">删除</button>
        </div>
      </div>
    </div>
  `).join('');
}

function renderTaskRuns() {
  const el = document.getElementById('taskRunList');
  if (!el) return;
  if (!_taskRuns.length) {
    el.innerHTML = '<div class="sb-empty">暂无执行记录</div>';
    return;
  }
  el.innerHTML = _taskRuns.map(r => `
    <div class="task-run-item" id="task-run-${escapeHtml(r.id)}">
      <div class="task-run-main">
        <div>
          <div class="task-run-name">${escapeHtml(r.task_name || ('任务 #' + (r.task_id || '-')))}</div>
          <div class="task-run-meta">${taskExecutionModeLabel(r.execution_mode)}${taskTargetLabel(r) ? ' · ' + escapeHtml(taskTargetLabel(r)) : ''} · ${escapeHtml(r.started_at || r.created_at || '-')} · 耗时：${r.duration_ms ?? '-'}ms · exit：${r.exit_code ?? '-'}${r.error_message ? ' · ' + escapeHtml(r.error_message) : ''}</div>
        </div>
        <div class="task-run-actions">
          <span class="task-status ${escapeHtml(r.status || '')}">${taskStatusLabel(r.status)}</span>
          <button class="btn btn-g" onclick="toggleTaskRunLog('${escapeHtml(r.id)}')">日志</button>
        </div>
      </div>
      <div class="task-log" id="task-log-${escapeHtml(r.id)}"></div>
    </div>
  `).join('');
}

async function loadTaskCenter() {
  if (_taskCenterLoading) return;
  _taskCenterLoading = true;
  try {
    const [overview, templates, defs, runs, schedules] = await Promise.all([
      safeGet('/tasks/overview'),
      safeGet('/tasks/templates'),
      safeGet('/tasks/definitions'),
      safeGet('/tasks/runs', { limit: 50 }),
      safeGet('/tasks/schedules'),
    ]);
    _taskTemplates = templates.templates || [];
    _taskDefinitions = defs.tasks || [];
    _taskRuns = runs.runs || [];
    _taskSchedules = schedules.schedules || [];
    renderTaskSummary(overview);
    renderTaskTemplateOptions();
    renderTaskDefinitions();
    renderTaskRuns();
    renderTaskSchedules();
  } catch (e) {
    toast(`任务中心加载失败：${e.message}`, 'err');
  } finally {
    _taskCenterLoading = false;
  }
}

async function createTaskDefinitionFromForm() {
  const name = document.getElementById('taskName')?.value?.trim() || '';
  const templateId = document.getElementById('taskTemplate')?.value || '';
  const runtime = document.getElementById('taskRuntime')?.value || 'python';
  const timeout = Number(document.getElementById('taskTimeout')?.value || 60);
  const scriptBody = document.getElementById('taskScript')?.value?.trim() || '';
  const executionMode = document.getElementById('taskExecutionMode')?.value || 'node';
  const target = executionMode === 'pod' ? getTaskPodTargetFromForm() : {};
  if (executionMode === 'pod' && !target.cluster_name) return toast('请填写 Pod 执行目标集群', 'warn');
  if (executionMode === 'pod' && !target.pod_name) return toast('请填写 Pod 名称', 'warn');
  if (!name) return toast('请填写任务名称', 'warn');
  if (!templateId && !scriptBody) return toast('请选择模板或填写内联脚本', 'warn');
  try {
    await safePost('/tasks/definitions', {
      name,
      execution_mode: executionMode,
      target,
      template_id: templateId ? Number(templateId) : null,
      runtime,
      timeout_seconds: timeout,
      script_body: scriptBody,
    });
    toast('任务已创建', 'ok');
    document.getElementById('taskName').value = '';
    document.getElementById('taskScript').value = '';
    await loadTaskCenter();
  } catch (e) {
    toast(`创建任务失败：${e.message}`, 'err');
  }
}

async function runTaskDefinition(taskId) {
  try {
    toast('任务开始执行，请稍候...', 'info');
    const result = await safePost(`/tasks/definitions/${taskId}/run`, {}, 650000);
    toast(result.run?.status === 'success' ? '任务执行成功' : '任务执行完成但存在失败', result.run?.status === 'success' ? 'ok' : 'warn');
    await loadTaskCenter();
    if (result.run?.id) setTimeout(() => toggleTaskRunLog(result.run.id), 80);
  } catch (e) {
    toast(`执行任务失败：${e.message}`, 'err');
  }
}

async function toggleTaskRunLog(runId) {
  const el = document.getElementById(`task-log-${runId}`);
  if (!el) return;
  if (el.classList.contains('open')) {
    el.classList.remove('open');
    return;
  }
  try {
    const data = await safeGet(`/tasks/runs/${runId}/logs`);
    const run = data.run || {};
    el.innerHTML = `
      <div class="task-log-title">stdout</div>
      <pre>${escapeHtml(run.stdout || '') || '无输出'}</pre>
      <div class="task-log-title">stderr</div>
      <pre>${escapeHtml(run.stderr || '') || '无输出'}</pre>
    `;
    el.classList.add('open');
  } catch (e) {
    toast(`加载日志失败：${e.message}`, 'err');
  }
}

// ── 调度管理 ──────────────────────────────────────────────

function scheduleStatusLabel(status) {
  return status === 'active' ? '运行中' : status === 'paused' ? '已暂停' : (status || '-');
}

function renderTaskSchedules() {
  const el = document.getElementById('taskScheduleList');
  if (!el) return;
  if (!_taskSchedules.length) {
    el.innerHTML = '<div class="sb-empty">暂无调度<br>点击「+ 新建调度」为任务绑定 interval 定时调度</div>';
    return;
  }
  el.innerHTML = _taskSchedules.map(s => {
    const isActive = s.status === 'active';
    return `
      <div class="task-item">
        <div class="task-item-main">
          <div>
            <div class="task-item-name">${escapeHtml(s.name)}</div>
            <div class="task-item-meta">
              任务：${escapeHtml(s.task_name || ('#' + s.task_id))} ·
              间隔：${s.interval_seconds}s ·
              上次：${escapeHtml(s.last_run_at || '从未')} ·
              下次：${escapeHtml(s.next_run_at || '-')}
            </div>
          </div>
          <div class="task-item-actions">
            <span class="task-status ${isActive ? 'success' : 'paused'}">${scheduleStatusLabel(s.status)}</span>
            <button class="btn btn-g" onclick="toggleTaskScheduleStatus(${s.id}, '${isActive ? 'paused' : 'active'}')">${isActive ? '暂停' : '恢复'}</button>
            <button class="btn btn-g danger-text" onclick="deleteTaskSchedule(${s.id})">删除</button>
          </div>
        </div>
      </div>
    `;
  }).join('');
}

function openCreateScheduleModal() {
  // 用当前已加载的任务定义填充下拉
  const sel = document.getElementById('scheduleTaskId');
  if (sel) {
    sel.innerHTML = _taskDefinitions.length
      ? _taskDefinitions.map(t => `<option value="${t.id}">${escapeHtml(t.name)}</option>`).join('')
      : '<option value="">暂无可用任务</option>';
  }
  const modal = document.getElementById('modalCreateSchedule');
  if (modal) modal.style.display = 'flex';
}

function closeCreateScheduleModal() {
  const modal = document.getElementById('modalCreateSchedule');
  if (modal) modal.style.display = 'none';
}

async function submitCreateSchedule() {
  const taskId = document.getElementById('scheduleTaskId')?.value;
  const name = document.getElementById('scheduleName')?.value?.trim() || '';
  const interval = Number(document.getElementById('scheduleInterval')?.value || 3600);
  if (!taskId) return toast('请选择绑定任务', 'warn');
  if (!name) return toast('请填写调度名称', 'warn');
  if (interval < 60 || interval > 86400) return toast('间隔需在 60 ~ 86400 秒之间', 'warn');
  try {
    await safePost('/tasks/schedules', { task_id: Number(taskId), name, interval_seconds: interval });
    toast('调度已创建', 'ok');
    closeCreateScheduleModal();
    document.getElementById('scheduleName').value = '';
    document.getElementById('scheduleInterval').value = '3600';
    await loadTaskCenter();
  } catch (e) {
    toast(`创建调度失败：${e.message}`, 'err');
  }
}

async function toggleTaskScheduleStatus(scheduleId, newStatus) {
  try {
    await safePut(`/tasks/schedules/${scheduleId}`, { status: newStatus });
    toast(newStatus === 'active' ? '调度已恢复' : '调度已暂停', 'ok');
    await loadTaskCenter();
  } catch (e) {
    toast(`操作失败：${e.message}`, 'err');
  }
}

async function deleteTaskSchedule(scheduleId) {
  if (!confirm('确认删除此调度？')) return;
  try {
    await safeDelete(`/tasks/schedules/${scheduleId}`);
    toast('调度已删除', 'ok');
    await loadTaskCenter();
  } catch (e) {
    toast(`删除失败：${e.message}`, 'err');
  }
}

async function deleteTaskDefinition(taskId) {
  if (!confirm('确认删除此任务？删除后关联调度将一并清除。')) return;
  try {
    await safeDelete(`/tasks/definitions/${taskId}`);
    toast('任务已删除', 'ok');
    await loadTaskCenter();
  } catch (e) {
    toast(`删除失败：${e.message}`, 'err');
  }
}

function openApiHelp() {

  window.open('/api/health', '_blank');
}

function openChangePasswordModal() {
  const modal = document.getElementById('pwdModal');
  if (!modal) return;
  ['pwdOld', 'pwdNew', 'pwdConfirm'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });
  const err = document.getElementById('pwdModalErr');
  if (err) { err.style.display = 'none'; err.textContent = ''; }
  modal.classList.add('open');
  setTimeout(() => document.getElementById('pwdOld')?.focus(), 50);
}

function closeChangePasswordModal() {
  document.getElementById('pwdModal')?.classList.remove('open');
}

async function submitChangePassword() {
  const oldPassword = document.getElementById('pwdOld')?.value || '';
  const newPassword = document.getElementById('pwdNew')?.value || '';
  const confirmPassword = document.getElementById('pwdConfirm')?.value || '';
  const err = document.getElementById('pwdModalErr');
  const showErr = (msg) => {
    if (err) { err.textContent = msg; err.style.display = ''; }
  };

  if (!oldPassword || !newPassword || !confirmPassword) return showErr('请完整填写当前密码、新密码和确认密码');
  if (newPassword.length < 6) return showErr('新密码至少 6 位');
  if (newPassword !== confirmPassword) return showErr('两次输入的新密码不一致');

  try {
    await safePost('/auth/change-password', { old_password: oldPassword, new_password: newPassword });
    closeChangePasswordModal();
    toast('密码已修改，请使用新密码登录', 'ok');
  } catch (e) {
    showErr(e.message || '修改密码失败');
  }
}


// 生成时间戳字符串 格式: 20260322153847
function fmtNowTs() {
  const n = new Date();
  return n.getFullYear().toString()
    + String(n.getMonth()+1).padStart(2,'0')
    + String(n.getDate()).padStart(2,'0')
    + String(n.getHours()).padStart(2,'0')
    + String(n.getMinutes()).padStart(2,'0')
    + String(n.getSeconds()).padStart(2,'0');
}

function formatProfilerLogTime(timestamp) {
  const d = timestamp ? new Date(String(timestamp).replace(' ', 'T')) : new Date();
  if (Number.isNaN(d.getTime())) return String(timestamp).slice(11, 19) || new Date().toLocaleTimeString('zh-CN', {hour12:false});
  return d.toLocaleTimeString('zh-CN', {hour12:false});
}

function profilerTargetPayload(t) {
  const focusConn = window.ConnectionStore && typeof ConnectionStore.getFocusConnection === 'function'
    ? ConnectionStore.getFocusConnection()
    : null;
  const connectionId = _currentConnId || window._currentConnId || focusConn?.id || t.connection_id || t.conn_id || '';
  const connTarget = focusConn ? normalizeConnTarget(focusConn) : null;
  const payload = {
    ...t,
    cluster_name: connTarget?.cluster_name || t.cluster_name || '',
    namespace: connTarget?.namespace || t.namespace || 'default',
    pod_name: connTarget?.pod_name || t.pod_name || '',
    container: connTarget?.container || t.container || '',
    arthas_jar: connTarget?.arthas_jar || t.arthas_jar || '',
  };
  return connectionId ? {...payload, connection_id: connectionId, conn_id: connectionId} : payload;
}

function sameProfilerConnection(a, b) {
  if (!a || !b) return false;
  return a === b || String(a).split('@u')[0] === String(b).split('@u')[0];
}

function resetProfilerPollTimer() {
  if (_pfPollTimer) {
    clearInterval(_pfPollTimer);
    _pfPollTimer = null;
  }
}

function startProfilerPollTimer(intervalMs) {
  resetProfilerPollTimer();
  pfPoll();
  _pfPollTimer = setInterval(pfPoll, intervalMs);
}

// Safe fetch helper: 使用 api.js 中的 safePost

// ── State ──────────────────────────────────────────────────────────────────────
let _clusters = [], _ac = null;

// ✅ 使用 ConnectionStore 统一管理连接状态 (替代全局变量)
// 旧变量保留为 ConnectionStore 的引用,保证向后兼容
let _connections = [];
let _currentConnId = null;
let _connected = false;
let _ap = null;
let _connHealth = {};
let _connState = 'disconnected';
let _runtimeInfo = null;
let _podConnId = null;
let _podPhase = null;

// ✅ 初始化 ConnectionStore 同步
function _initConnectionStore() {
  if (typeof ConnectionStore === 'undefined') {
    console.warn('[app-ui] ConnectionStore not loaded, using legacy state');
    return;
  }
  
  // 从 ConnectionStore 同步到本地变量
  const state = ConnectionStore.getState();
  _connections = state.connections;
  _currentConnId = state.currentConnId;
  _connState = state.connState;
  _runtimeInfo = state.runtimeInfo;
  _connHealth = state.connHealth || {};
  
  // 订阅状态变化
  ConnectionStore.subscribe((newState, oldState) => {
    // 更新本地变量
    _connections = newState.connections;
    _currentConnId = newState.currentConnId;
    _connState = newState.connState;
    _runtimeInfo = newState.runtimeInfo;
    _connHealth = newState.connHealth || {};
    
    // 更新 UI
    if (newState.currentConnId !== oldState.currentConnId) {
      renderConnList();
      updateConnectionButton();
    }
    if (newState.connState !== oldState.connState) {
      updateFeatureTabs();
    }
  });
  
  console.log('[app-ui] ConnectionStore synced');
}

// 同步模块内部状态到 window，供 ai-chat.js / 外部组件读取
function _mergeExternalConnectionState() {
  // ✅ 优先从 ConnectionStore 获取
  if (typeof ConnectionStore !== 'undefined') {
    const state = ConnectionStore.getState();
    _connections = state.connections;
    _currentConnId = state.currentConnId;
    _connState = state.connState;
    _runtimeInfo = state.runtimeInfo;
    _connHealth = state.connHealth || {};
    return;
  }
  
  // 向后兼容: 从 window 变量合并
  const externalConns = Array.isArray(window._connections) ? window._connections : [];
  if (externalConns.length && externalConns !== _connections) {
    const merged = new Map();
    _connections.forEach(c => { if (c && c.id) merged.set(c.id, c); });
    externalConns.forEach(c => {
      if (!c || !c.id) return;
      const old = merged.get(c.id);
      merged.set(c.id, old ? { ...old, ...c } : c);
    });
    _connections = Array.from(merged.values());
  }

  const externalConnId = window._currentConnId || null;
  if (externalConnId && (!_currentConnId || !_connections.find(c => c.id === _currentConnId))) {
    _currentConnId = externalConnId;
  }
}

function _syncState(options = {}) {
  if (!options.skipMerge) {
    _mergeExternalConnectionState();
  }
  
  // ✅ 优先使用 ConnectionStore
  if (typeof ConnectionStore !== 'undefined') {
    ConnectionStore.setState({
      connections: _connections,
      currentConnId: _currentConnId,
      connState: _connState,
      runtimeInfo: _runtimeInfo,
      connHealth: _connHealth || {},
    });
    return;
  }
  
  // 向后兼容: 同步到 window
  window._connections  = _connections;
  window._currentConnId = _currentConnId;
  window._connHealth   = _connHealth;
  // P0-1: 同步两步连接状态，供 diagnose.js 等外部模块判断连接层级
  if (typeof getConnectionState === 'function') {
    window._connState   = getConnectionState();
  } else if (window._connState) {
    window._connState = window._connState;
  }
  if (typeof _runtimeInfo !== 'undefined') {
    window._runtimeInfo = _runtimeInfo || window._runtimeInfo;
  }
}
let _sid = null, _cid = null, _sidConnId = null, _pollTimer = null, _polling = false;
let _cmdHist = [], _histIdx = -1, _selCmd = null;
let _cmdHistByConn = {}, _cmdDraftByConn = {};
let _pfTaskId = null, _pfPollTimer = null, _pfStart = null, _pfDur = 60, _pfLL = 0;
let _pfPollingForConn = null; // 记录当前轮询是为哪个连接服务
let _pfLastMsg = '';          // 上次后端 message，用于去重
let _pfLastProgressLog = 0;   // 上次输出进度日志的时间戳
let _pfTaskInfo = { type: '-', event: '-', duration: 0, status: '-' }; // 当前任务信息
let _snap = null, _histData = [], _logRaw = '', _logWrap = true;
let _fbSelected = null, _fbCurPath = '/tmp';
// 每个连接的采样任务状态缓存
let _pfTasksByConn = {}; // { connId: { taskId, startTime, duration, logLines, status } }
let _metricsPolling = false, _metricsTimer = null;
let _metricsCache = new Map();

// ✅ 修复: Profiler 任务持久化（切换页签后不丢失）
function _persistPfTask(connId, taskId, meta) {
  if (!connId || !taskId) return;
  try {
    const key = 'pf_tasks_by_conn';
    const store = JSON.parse(localStorage.getItem(key) || '{}');
    store[connId] = { taskId, startTime: Date.now(), ...meta, status: 'running' };
    localStorage.setItem(key, JSON.stringify(store));
  } catch(e) { console.warn('[pf] persist failed:', e); }
}
function _loadPersistedPfTasks() {
  try {
    const key = 'pf_tasks_by_conn';
    const store = JSON.parse(localStorage.getItem(key) || '{}');
    for (const [connId, task] of Object.entries(store)) {
      if (task && task.taskId && !_pfTasksByConn[connId]) {
        _pfTasksByConn[connId] = task;
      }
    }
  } catch(e) { console.warn('[pf] load persisted failed:', e); }
}
function _clearPersistedPfTask(connId) {
  try {
    const key = 'pf_tasks_by_conn';
    const store = JSON.parse(localStorage.getItem(key) || '{}');
    delete store[connId];
    localStorage.setItem(key, JSON.stringify(store));
  } catch(e) {}
}

function activeCommandConnId() {
  return _currentConnId || window._currentConnId || '';
}

function isActiveCommandConnection(connId) {
  return !!connId && connId === activeCommandConnId();
}

function saveCommandConsoleState(connId = activeCommandConnId()) {
  if (!connId) return;
  _cmdHistByConn[connId] = Array.isArray(_cmdHist) ? _cmdHist.slice(-100) : [];
  const ta = document.getElementById('cmdTa');
  if (ta) _cmdDraftByConn[connId] = ta.value || '';
}

function restoreCommandConsoleState(connId = activeCommandConnId()) {
  _cmdHist = (connId && _cmdHistByConn[connId] ? _cmdHistByConn[connId] : []).slice();
  _histIdx = -1;
  const ta = document.getElementById('cmdTa');
  if (ta) {
    ta.value = connId ? (_cmdDraftByConn[connId] || '') : '';
    autoResize(ta);
  }
}

function resetCommandSessionState() {
  _polling = false;
  if (_pollTimer) { clearTimeout(_pollTimer); _pollTimer = null; }
  _sid = null;
  _cid = null;
  _sidConnId = null;
  const stopBtn = document.getElementById('btnStop');
  if (stopBtn) stopBtn.style.display = 'none';
}

// ── Server Health Check ──────────────────────────────────────────────────
async function checkServerHealth() {
  const dot = document.getElementById('svDot');
  const lbl = document.getElementById('svLbl');
  const verTop = document.getElementById('arthasVerTop');
  try {
    const r = await fetch(`${API}/health`, { credentials: 'include' });
    const d = await r.json();
    if (d.ok) {
      if (dot) { dot.className = 'dot live'; }
      if (lbl) { lbl.textContent = '服务在线'; }
      if (verTop && d.version) {
        verTop.textContent = `v${d.version}`;
        verTop.style.display = '';
      }
    } else {
      if (dot) { dot.className = 'dot'; }
      if (lbl) { lbl.textContent = '服务异常'; }
      if (verTop) verTop.style.display = 'none';
    }
  } catch(e) {
    if (dot) { dot.className = 'dot'; }
    if (lbl) { lbl.textContent = '服务离线'; }
    if (verTop) verTop.style.display = 'none';
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────────
// esc, fmtSz, fmtTs, mkv, gRow, toast 已在 utils.js 中定义

// ── Sidebar Pod Target Collapse ──────────────────────────────────────────────
function togglePodTarget() {
  const el = document.getElementById('podTarget');
  const arrow = document.getElementById('ptCollapseArrow');
  if (!el) return;
  el.classList.toggle('collapsed');
  if (arrow) arrow.classList.toggle('up', !el.classList.contains('collapsed'));
}

// ── Sidebar Navigation ───────────────────────────────────────────────────────
function toggleSideNavGroup(el) {
  const group = el?.closest?.('.side-nav-group');
  if (!group) return;
  group.classList.toggle('collapsed');
}

const WORKSPACE_META = {
  connections: { kicker: 'Connection Center', title: '连接中心', sub: '管理 Pod 连接、Arthas 升级与最近连接记录' },
  profiler: { kicker: 'Profiler', title: '采样工具', sub: '启动 async-profiler、JFR、线程和堆转储等采样任务' },
  console: { kicker: 'Arthas Console', title: 'Arthas命令', sub: '执行 Arthas 诊断命令，需要 Arthas-ready 连接' },
  hotfix: { kicker: 'Hotfix Workbench', title: '热修复', sub: 'jad 查看源码 → 在线编辑/上传 → mc 编译 → redefine 热更新 → 验证报告' },
  terminal: { kicker: 'Pod Terminal', title: '终端', sub: '通过 kubectl exec 进入目标 Pod，不依赖 Arthas' },
  monitor: { kicker: 'Pod Monitor', title: 'Pod 监控', sub: '查看 CPU、内存、网络、磁盘和事件等 Pod 级指标' },
  filebrowser: { kicker: 'File Browser', title: '文件下载', sub: '浏览和下载 Pod 内文件，不依赖 Arthas' },
  ai: { kicker: 'AI Assistant', title: 'AI 助手', sub: '结合连接上下文进行诊断分析和命令建议' },
  'model-config': { kicker: 'Model Config', title: '模型配置', sub: '配置大模型供应商、Base URL、模型名称和系统提示词' },
  'mcp-center': { kicker: 'MCP Access', title: 'MCP 接入', sub: '管理 MCP Token 和客户端接入配置，按需加载配置详情' },
  diag: { kicker: 'Diagnosis', title: '性能诊断', sub: '按场景组织 JVM 与 Pod 诊断流程' },
  'diagnosis-cap': { kicker: 'Diagnosis Center', title: '诊断中心', sub: '按场景组织 JVM 与 Pod 诊断，支持快捷工具、场景方案和 AI 诊断' },
  history: { kicker: 'History', title: '历史记录', sub: '查看命令、采样和文件下载记录' },
  'task-center': { kicker: 'Task Center', title: '任务中心', sub: '规划 Pod 定时脚本、执行结果和任务历史' },
  'toolchain-center': { kicker: 'Toolchain', title: '工具链', sub: '管理 Arthas、async-profiler、jattach 与离线缓存' },
  'external-system': { kicker: 'External System', title: '外部系统', sub: '在右侧工作区嵌入展示外部系统页面' },
  'user-management': { kicker: 'System Management', title: '用户管理', sub: '管理账号、角色、状态与集群授权' },
  'skill-management': { kicker: 'Skill Management', title: 'Skill 管理', sub: '管理诊断 Skill 的导入、校验、发布与归档' },
  'audit-logs': { kicker: 'Audit Logs', title: '审计日志', sub: '查看登录、连接、诊断与资源变更操作记录' },
  'alerts': { kicker: 'Alert Center', title: '告警中心', sub: '实时异常检测与告警管理' },
};

function updateWorkspaceHead(tab) {
  if (window.__hideConnStatusBar) return;

  const kicker = document.getElementById('workspaceKicker');
  const title = document.getElementById('workspaceTitle');
  const sub = document.getElementById('workspaceSub');

  const meta = WORKSPACE_META[tab] || WORKSPACE_META.connections;
  // 更新标题内容并显示
  if (kicker) { kicker.textContent = meta.kicker; kicker.style.display = ''; }
  if (title) { title.textContent = meta.title; title.style.display = ''; }
  if (sub) { sub.textContent = meta.sub; sub.style.display = ''; }
}

// ── Connection Management ─────────────────────────────────────────────────────
// 连接层级辅助
function _inferLevel(c) {
  if (!c) return 'pod';
  if (c.level) return c.level;
  if (c.local_port || c.arthas_version || c.java_pid) return 'arthas';
  if (c.runtime_type || c.runtime) return 'pod';
  if (c.status === 'connected') return 'arthas'; // 兼容旧数据
  return 'pod';
}

function _normalizeConnectionRecord(c) {
  const conn = { ...(c || {}) };
  const level = _inferLevel(conn);
  const rawStatus = String(conn.status || '').toLowerCase();
  const hasArthasMeta = !!(conn.local_port || conn.arthas_version || conn.java_pid || conn.arthas_address);
  const connectedLike = ['ready', 'connected', 'running', 'ok', 'healthy', 'degraded'].includes(rawStatus);
  const connectingLike = ['connecting', 'pending', 'starting'].includes(rawStatus);

  conn.cluster = conn.cluster || conn.cluster_name;
  conn.pod = conn.pod || conn.pod_name;
  conn.container = conn.container || conn.container_name;
  conn.level = level;
  conn.state = conn.state || (connectedLike ? 'connected' : connectingLike ? 'connecting' : 'disconnected');
  conn.health = conn.health || (conn.state === 'connected' ? 'ok' : conn.state === 'connecting' ? 'warn' : 'off');

  if (level === 'arthas' && hasArthasMeta) {
    conn.arthas = conn.arthas || { port: conn.local_port, version: conn.arthas_version };
    if (rawStatus === 'ready') conn.status = 'connected';
  }
  return conn;
}
function _getRt(c) {
  if (!c) return null;
  if (c.runtime && typeof c.runtime === 'object') {
    // 后端 RuntimeInfo.__dict__ 字段为 runtime_type/version，前端统一为 type/version
    const rt = c.runtime;
    return { type: rt.type || rt.runtime_type, version: rt.version || rt.runtime_version || '' };
  }
  if (c.runtime_type) return { type: c.runtime_type, version: c.runtime_version || '' };
  return null;
}
function _rtIcon(t) { return {java:'☕',node:'🟢',python:'🐍',go:'🔵',dotnet:'🟣',unknown:'❓'}[t]||'❓'; }
function _canUpgrade(c) { return _inferLevel(c)==='pod' && _getRt(c)?.type==='java'; }

/**
 * 格式化最后活跃时间
 * @param {string} timestamp - ISO 时间戳 (如 "2026-05-03T22:18:28")
 * @returns {string} 相对时间描述 (如 "2分钟前", "1小时前", "3天前")
 */
function _formatLastActive(timestamp) {
  if (!timestamp) return '未知';
  
  try {
    const now = new Date();
    const pingTime = new Date(timestamp);
    const diffMs = now - pingTime;
    const diffSec = Math.floor(diffMs / 1000);
    const diffMin = Math.floor(diffSec / 60);
    const diffHour = Math.floor(diffMin / 60);
    const diffDay = Math.floor(diffHour / 24);
    
    if (diffSec < 60) return '刚刚';
    if (diffMin < 60) return `${diffMin}分钟前`;
    if (diffHour < 24) return `${diffHour}小时前`;
    if (diffDay < 7) return `${diffDay}天前`;
    
    // 超过 7 天显示具体日期
    const month = pingTime.getMonth() + 1;
    const day = pingTime.getDate();
    const hours = pingTime.getHours().toString().padStart(2, '0');
    const minutes = pingTime.getMinutes().toString().padStart(2, '0');
    return `${month}/${day} ${hours}:${minutes}`;
  } catch (e) {
    console.warn('[时间格式化] 失败:', e);
    return timestamp;
  }
}

/**
 * 通过连接 ID 获取当前连接记录
 */
function getConnectionRecordById(connId) {
  if (!connId) return null;
  _mergeExternalConnectionState();
  const sameId = (value) => {
    if (!value) return false;
    const left = String(value);
    const right = String(connId);
    return left === right || left.split('@u')[0] === right || right.split('@u')[0] === left;
  };
  return _connections.find(c => sameId(c.id) || sameId(c.pod_conn_id) || sameId(c.connection_id))
    || (window.ConnectionStore && typeof ConnectionStore.getConnection === 'function' ? ConnectionStore.getConnection(connId) : null)
    || (window.ConnectionStore && typeof ConnectionStore.getConnections === 'function'
      ? ConnectionStore.getConnections().find(c => sameId(c.id) || sameId(c.pod_conn_id) || sameId(c.connection_id))
      : null)
    || null;
}

function hydratePodConnectionForUpgrade(conn) {
  if (!conn) return null;
  const currentConnId = conn.id || conn.connection_id || conn.pod_conn_id;
  const podConnId = conn.pod_conn_id || conn.connection_id || conn.id;
  const runtime = (conn.runtime && typeof conn.runtime === 'object')
    ? conn.runtime
    : {
      runtime_type: conn.runtime_type || (typeof conn.runtime === 'string' ? conn.runtime : 'unknown'),
      type: conn.runtime_type || (typeof conn.runtime === 'string' ? conn.runtime : 'unknown'),
      version: conn.runtime_version || '',
      runtime_version: conn.runtime_version || '',
      pid: conn.pid || conn.java_pid || null,
    };
  _currentConnId = currentConnId;
  window._currentConnId = currentConnId;
  _podConnId = podConnId;
  _runtimeInfo = runtime;
  _podPhase = conn.pod_phase || _podPhase || 'Running';
  _connState = ConnectionState.POD_CONNECTED;
  window._connState = ConnectionState.POD_CONNECTED;
  window._runtimeInfo = runtime;
  _connected = false;
  _ap = syncPodTargetFromConnection(conn) || normalizeConnTarget(conn) || getCurrentPodTarget();
  if (window.ConnectionStore && typeof ConnectionStore.setState === 'function') {
    ConnectionStore.setState({
      currentConnId,
      connState: ConnectionState.POD_CONNECTED,
      runtimeInfo: runtime,
      podConnId,
      connHealth: {
        ...(typeof _connHealth !== 'undefined' ? _connHealth : {}),
        [currentConnId]: { alive: true, pod_exists: true, pod_phase: _podPhase },
      },
    });
  }
  if (typeof updateConnectionButton === 'function') updateConnectionButton();
  if (typeof updateRuntimeDisplay === 'function') updateRuntimeDisplay();
  if (typeof updateFeatureTabs === 'function') updateFeatureTabs();
  return { currentConnId, podConnId, runtime };
}

function updateReconnectConnectionState(connId, updates) {
  if (!connId || !updates) return;
  const localConn = _connections.find(c => c.id === connId);
  if (localConn) Object.assign(localConn, updates);
  if (window.ConnectionStore && typeof ConnectionStore.getConnection === 'function' && ConnectionStore.getConnection(connId)) {
    ConnectionStore.updateConnection(connId, updates);
  }
}

function setConnectionWorkspaceTab(connId, tab) {
  if (!connId || !tab) return;
  const localConn = _connections.find(c => c.id === connId);
  if (localConn) localConn.tab = tab;
  if (window.ConnectionStore && typeof ConnectionStore.getConnection === 'function' && ConnectionStore.getConnection(connId)) {
    ConnectionStore.updateConnection(connId, { tab });
  }
}

function resolveConnectionWorkspaceTab(conn, levelOverride) {
  const candidate = { ...(conn || {}) };
  if (levelOverride) candidate.level = levelOverride;
  if (window.ConnectionWorkspace && typeof ConnectionWorkspace.resolveTab === 'function') {
    return ConnectionWorkspace.resolveTab(candidate);
  }
  const tab = candidate.tab || 'monitor';
  const level = levelOverride || candidate.level || _inferLevel(candidate);
  if (['sampling', 'console', 'hotfix', 'diag'].includes(tab) && level !== 'arthas') return 'monitor';
  return tab;
}

function clearReconnectProfilerState(connId) {
  const hasActivePoll = sameProfilerConnection(_pfPollingForConn, connId);
  const hasPersistedTask = !!_pfTasksByConn[connId];
  const hasCurrentTask = !!_pfTaskId && sameProfilerConnection(_currentConnId || window._currentConnId, connId);
  if (!hasActivePoll && !hasPersistedTask && !hasCurrentTask) return;
  resetProfilerPollTimer();
  _pfTaskId = null;
  _pfPollingForConn = null;
  delete _pfTasksByConn[connId];
  if (typeof _clearPersistedPfTask === 'function') _clearPersistedPfTask(connId);
  if (sameProfilerConnection(_currentConnId || window._currentConnId, connId)) {
    pfClearLog();
    if (typeof renderProfilerStatus === 'function') renderProfilerStatus();
  }
}

async function bestEffortDisconnectRuntime(conn) {
  const connectionId = conn?.pod_conn_id || conn?.id;
  if (!connectionId) return;
  const isArthasLevel = _inferLevel(conn) === 'arthas' || !!(conn.local_port || conn.arthas_version || conn.http_url);
  if (isArthasLevel) {
    try {
      await fetch(`${API}/arthas/disconnect`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ connection_id: connectionId })
      });
    } catch (_) {}
  }
  try {
    await fetch(`${API}/pod/disconnect`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ connection_id: connectionId })
    });
  } catch (_) {}
}

async function reconnectConnectionById(connId, options = {}) {
  const conn = getConnectionRecordById(connId);
  if (!conn) throw new Error('连接不存在');

  const previousLevel = options.previousLevel || _inferLevel(conn);
  const previousTab = resolveConnectionWorkspaceTab({ ...conn, level: previousLevel }, previousLevel);

  if (window.ConnectionStore && typeof ConnectionStore.setFocus === 'function') {
    ConnectionStore.setFocus(conn.id);
  }
  _currentConnId = conn.id;
  window._currentConnId = conn.id;
  _ap = syncPodTargetFromConnection(conn) || normalizeConnTarget(conn) || getCurrentPodTarget();
  window._manualTargetDirty = false;

  clearReconnectProfilerState(conn.id);
  updateReconnectConnectionState(conn.id, {
    state: 'connecting',
    level: 'disconnected',
    health: 'warn',
    arthas: null,
  });
  setConnectionWorkspaceTab(conn.id, 'monitor');

  _connected = false;
  _connState = 'disconnected';
  window._connState = 'disconnected';
  _podConnId = null;
  if (window.ConnectionStore && typeof ConnectionStore.setState === 'function') {
    ConnectionStore.setState({
      currentConnId: conn.id,
      connState: 'disconnected',
      runtimeInfo: null,
      podConnId: null,
    });
  }
  if (typeof updateConnectionButton === 'function') updateConnectionButton();
  if (typeof updateFeatureTabs === 'function') updateFeatureTabs();
  if (typeof ConnectionWorkspace !== 'undefined' && typeof ConnectionWorkspace.render === 'function') {
    ConnectionWorkspace.render();
  }

  setConnStatus('dim', `正在重连 ${conn.pod_name || conn.pod || conn.id} ...`);
  await bestEffortDisconnectRuntime(conn);

  try {
    const podReconnectOk = await podConnect({ silentError: true });
    if (!podReconnectOk) {
      throw new Error(window._lastPodConnectError || 'Pod 不存在或无法访问');
    }

    const activeConn = getConnectionRecordById(_podConnId || _currentConnId || conn.id) || conn;
    const podTab = resolveConnectionWorkspaceTab({ ...activeConn, tab: previousTab, level: 'pod' }, 'pod');
    updateReconnectConnectionState(activeConn.id, {
      state: 'connected',
      level: 'pod',
      health: 'ok',
      lastHb: Date.now(),
    });
    setConnectionWorkspaceTab(activeConn.id, podTab);

    if (previousLevel !== 'arthas') {
      if (typeof saveConnections === 'function') saveConnections();
      if (typeof renderConnList === 'function') renderConnList();
      if (typeof ConnectionWorkspace !== 'undefined' && typeof ConnectionWorkspace.render === 'function') {
        ConnectionWorkspace.render();
      }
      toast('Pod 连接已恢复', 'success');
      return { ok: true, level: 'pod', connectionId: activeConn.id };
    }

    const arthasReconnectOk = await upgradeToArthas({ silentError: true, reconnect: true });
    if (!arthasReconnectOk) {
      setConnectionWorkspaceTab(activeConn.id, 'monitor');
      updateReconnectConnectionState(activeConn.id, {
        state: 'connected',
        level: 'pod',
        health: 'ok',
        lastHb: Date.now(),
      });
      if (typeof saveConnections === 'function') saveConnections();
      if (typeof renderConnList === 'function') renderConnList();
      if (typeof ConnectionWorkspace !== 'undefined' && typeof ConnectionWorkspace.render === 'function') {
        ConnectionWorkspace.render();
      }
      toast(`Arthas 恢复失败，已切回监控页：${window._lastArthasUpgradeError || '请重新启动 Arthas 后再试'}`, 'warn');
      return {
        ok: false,
        partial: true,
        level: 'pod',
        connectionId: activeConn.id,
        message: window._lastArthasUpgradeError || 'Arthas 恢复失败',
      };
    }

    setConnectionWorkspaceTab(activeConn.id, previousTab);
    if (typeof saveConnections === 'function') saveConnections();
    if (typeof renderConnList === 'function') renderConnList();
    if (typeof ConnectionWorkspace !== 'undefined' && typeof ConnectionWorkspace.render === 'function') {
      ConnectionWorkspace.render();
    }
    toast('Arthas 连接已恢复', 'success');
    return { ok: true, level: 'arthas', connectionId: activeConn.id };
  } catch (e) {
    updateReconnectConnectionState(conn.id, {
      state: 'disconnected',
      level: 'disconnected',
      health: 'off',
      arthas: null,
    });
    setConnectionWorkspaceTab(conn.id, 'monitor');
    _connected = false;
    _connState = 'disconnected';
    window._connState = 'disconnected';
    _podConnId = null;
    if (window.ConnectionStore && typeof ConnectionStore.setState === 'function') {
      ConnectionStore.setState({
        currentConnId: conn.id,
        connState: 'disconnected',
        runtimeInfo: null,
        podConnId: null,
      });
    }
    if (typeof updateConnectionButton === 'function') updateConnectionButton();
    if (typeof updateFeatureTabs === 'function') updateFeatureTabs();
    if (typeof saveConnections === 'function') saveConnections();
    if (typeof renderConnList === 'function') renderConnList();
    if (typeof ConnectionWorkspace !== 'undefined' && typeof ConnectionWorkspace.render === 'function') {
      ConnectionWorkspace.render();
    }
    throw e;
  }
}

async function upgradeConnectionById(connId, options = {}) {
  const silentError = !!options.silentError;
  const conn = getConnectionRecordById(connId);
  if (!conn) {
    const error = new Error('连接不存在');
    if (!silentError) toast(`启动 Arthas 失败: ${error.message}`, 'error');
    throw error;
  }

  try {
    _ap = syncPodTargetFromConnection(conn) || normalizeConnTarget(conn) || getCurrentPodTarget();
    window._manualTargetDirty = false;

    if (_inferLevel(conn) === 'arthas' && (conn.local_port || conn.arthas_version || conn.http_url)) {
      if (typeof ConnectionWorkspace !== 'undefined' && typeof ConnectionWorkspace.render === 'function') {
        ConnectionWorkspace.render();
      }
      return { ok: true, level: 'arthas', connectionId: conn.id, reused: true };
    }

    const beforeSwitchConnId = _currentConnId;
    if (beforeSwitchConnId !== conn.id) {
      await switchConnection(conn.id);
    }

    const activeConn = getConnectionRecordById(conn.id) || conn;
    if (window.ConnectionStore && typeof ConnectionStore.setFocus === 'function') {
      ConnectionStore.setFocus(activeConn.id || conn.id);
    }
    if (_inferLevel(activeConn) === 'arthas' && (activeConn.local_port || activeConn.arthas_version || activeConn.http_url)) {
      if (typeof ConnectionWorkspace !== 'undefined' && typeof ConnectionWorkspace.render === 'function') {
        ConnectionWorkspace.render();
      }
      return { ok: true, level: 'arthas', connectionId: activeConn.id || conn.id, reused: true };
    }

    if (typeof upgradeToArthas !== 'function') {
      throw new Error('Arthas 升级入口不可用');
    }

    hydratePodConnectionForUpgrade(activeConn);
    const arthasOk = await upgradeToArthas({ silentError: true });
    if (!arthasOk) {
      throw new Error(window._lastArthasUpgradeError || 'Arthas 启动失败');
    }

    const upgradedConn = getConnectionRecordById(activeConn.id || conn.id) || activeConn || conn;
    if (typeof ConnectionWorkspace !== 'undefined' && typeof ConnectionWorkspace.render === 'function') {
      ConnectionWorkspace.render();
    }
    return { ok: true, level: 'arthas', connectionId: upgradedConn.id || conn.id };
  } catch (e) {
    if (!silentError) toast(`启动 Arthas 失败: ${e.message}`, 'error');
    throw e;
  }
}

/**
 * ✅ 新增: 一键重连当前连接
 */
async function reconnectCurrentConnection() {
  const connId = _currentConnId;
  if (!connId) {
    toast('没有可重连的连接', 'warning');
    return;
  }

  const conn = getConnectionRecordById(connId);
  if (!conn) {
    toast('连接不存在', 'error');
    return;
  }

  toast(`正在重连 ${conn.pod_name || conn.pod}...`, 'info');

  try {
    const result = await reconnectConnectionById(connId, { source: 'current-connection' });
    if (result && result.partial) return;
  } catch (e) {
    console.error('[Reconnect] Error:', e);
    toast(`重连失败: ${e.message}`, 'error');
  }
}

/**
 * ✅ 新增: 查看 Arthas 启动日志
 */
async function viewArthasStartLog() {
  const conn = _connections.find(c => c.id === _currentConnId);
  if (!conn) {
    toast('请先选择连接', 'warning');
    return;
  }
  
  const connId = _currentConnId;
  const clusterName = conn.cluster_name || conn.cluster;
  const namespace = conn.namespace;
  const podName = conn.pod_name || conn.pod;
  
  if (!clusterName || !namespace || !podName) {
    toast('连接信息不完整', 'error');
    return;
  }
  
  toast('正在获取 Arthas 启动日志...', 'info');
  
  try {
    const res = await fetch(`${API}/pod/exec`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      credentials: 'include',
      body: JSON.stringify({
        cluster_name: clusterName,
        namespace: namespace,
        pod_name: podName,
        command: 'tail -100 /tmp/arthas_start.log 2>&1 || echo "日志文件不存在"'
      })
    });
    
    const data = await res.json();
    if (data.ok) {
      // 显示日志
      const output = data.stdout || data.message || '无输出';
      showArthasLogModal(output);
    } else {
      toast(`获取日志失败: ${data.message}`, 'error');
    }
  } catch (e) {
    console.error('[ArthasLog] Error:', e);
    toast(`获取日志失败: ${e.message}`, 'error');
  }
}

/**
 * 显示 Arthas 日志模态框
 */
function showArthasLogModal(logContent) {
  const modal = document.createElement('div');
  modal.style.cssText = `
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: rgba(0, 0, 0, 0.85);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 10000;
  `;
  
  const content = document.createElement('div');
  content.style.cssText = `
    background: var(--bg-2);
    border: 1px solid var(--br);
    border-radius: 8px;
    width: 80%;
    max-width: 900px;
    max-height: 80%;
    display: flex;
    flex-direction: column;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.6);
  `;
  
  content.innerHTML = `
    <div style="padding: 16px; border-bottom: 1px solid var(--br); display: flex; justify-content: space-between; align-items: center;">
      <h3 style="margin: 0; color: var(--tx);">Arthas 启动日志</h3>
      <button onclick="this.closest('div').parentElement.parentElement.remove()" style="background: none; border: none; color: var(--tx-2); cursor: pointer; font-size: 20px; padding: 4px 8px;">&times;</button>
    </div>
    <pre style="flex: 1; overflow-y: auto; padding: 16px; margin: 0; background: var(--bg-3); color: var(--tx-2); font-family: monospace; font-size: 12px; white-space: pre-wrap; word-break: break-all;">${logContent}</pre>
  `;
  
  modal.appendChild(content);
  document.body.appendChild(modal);
  
  // 点击背景关闭
  modal.addEventListener('click', (e) => {
    if (e.target === modal) {
      modal.remove();
    }
  });
}

function renderConnList() {
  _mergeExternalConnectionState();
  _connHealth = _connHealth || {};
  const el = document.getElementById('connList');
  if (!el) return;
  if (_connections.length === 0) {
    el.innerHTML = '<div class="sb-empty">暂无连接<br>使用左侧连接配置创建连接</div>';
    return;
  }
  let html = '';
  _connections.forEach(c => {
    const isActive = c.id === _currentConnId;
    const level = _inferLevel(c);
    const rt = _getRt(c);
    const h = _connHealth[c.id];

    // 层级标识
    const levelIcon = level === 'arthas' ? '⚡' : '🔵';
    const levelBadge = `<span class="conn-level ${level}">${level === 'arthas' ? 'Arthas连接' : 'Pod连接'}</span>`;

    // ✅ 最后活跃时间
    let lastActiveLine = '';
    if (c.last_ping_at) {
      const timeStr = _formatLastActive(c.last_ping_at);
      lastActiveLine = `<div class="conn-last-active" title="最后活跃: ${c.last_ping_at}">🕒 ${timeStr}</div>`;
    }

    // 运行时信息行（补充：从当前连接状态获取，以防旧缓存中缺失）
    let runtimeLine = '';
    if (rt) {
      runtimeLine = `<div class="conn-runtime">${_rtIcon(rt.type)} ${rt.type}${rt.version ? ' ' + rt.version : ''}${c.java_pid ? ' · PID ' + c.java_pid : ''}</div>`;
    } else if (isActive && window._runtimeInfo) {
      // 旧连接缓存中无运行时，但从当前连接状态补充
      const ri = window._runtimeInfo;
      if (ri.runtime_type || ri.type) {
        const rt2type = ri.type || ri.runtime_type;
        const rt2ver = ri.version || ri.runtime_version || '';
        const rt2pid = ri.java_pid || '';
        runtimeLine = `<div class="conn-runtime">${_rtIcon(rt2type)} ${rt2type}${rt2ver ? ' ' + rt2ver : ''}${rt2pid ? ' · PID ' + rt2pid : ''}</div>`;
      }
    }

    // 升级按钮
    let upgradeBtn = '';
    if (_canUpgrade(c)) {
      upgradeBtn = `<div class="conn-upgrade-btn" onclick="event.stopPropagation();upgradeConnectionFromList('${esc(c.id)}')">⚡ 启动 Arthas</div>`;
    }

    // 健康状态图标与样式
    let statusIcon = '', statusStyle = '', statusHint = '';
    if (h) {
      if (h.pod_exists === false) {
        statusIcon = '⚠'; statusStyle = 'color:var(--a5)'; statusHint = 'Pod 不存在，建议删除';
      } else if (h.reason && h.reason.startsWith('pod_')) {
        statusIcon = '◉'; statusStyle = 'color:#f59e0b'; statusHint = `Pod 状态: ${h.pod_phase || h.reason}`;
      } else if (h.alive === false && level === 'arthas') {
        statusIcon = '◉'; statusStyle = 'color:#f59e0b'; statusHint = 'Arthas 已断开，Pod 连接可能仍可用';
      } else if (h.alive === false) {
        statusIcon = '◈'; statusStyle = 'color:#f59e0b'; statusHint = '连接已断开，点击可重连';
      } else if (h.pod_exists === true && h.alive !== false) {
        statusIcon = '●'; statusStyle = 'color:var(--a3)'; statusHint = '连接正常';
      } else if (h.reason === 'cluster_unavailable') {
        statusIcon = '⊘'; statusStyle = 'color:var(--a5)'; statusHint = '集群不可用';
      }
    }

    html += `
      <div class="conn-itm ${isActive?'on':''}" onclick="switchConnection('${c.id}')" title="集群: ${esc(c.cluster_name)}\n环境: ${c.namespace}\nPod: ${c.pod_name}\n连接类型: ${level === 'arthas' ? 'Arthas连接' : 'Pod连接'}${c.local_port ? '\n端口: ' + c.local_port : ''}${c.arthas_version ? '\nArthas: ' + c.arthas_version : ''}${c.arthas_address ? '\n地址: ' + c.arthas_address : ''}${statusHint ? '\n' + statusHint : ''}">
        <input type="checkbox" class="conn-checkbox" onclick="event.stopPropagation();updateSelectedCount()">
        <div class="conn-info">
          <div class="conn-cluster">${statusIcon ? `<span style="font-size:9px;${statusStyle};margin-right:3px" title="${statusHint}">${statusIcon}</span>` : `<span style="font-size:11px">${levelIcon}</span>`} ${esc(c.cluster_name)}${levelBadge}</div>
          <div class="conn-pod"><span class="conn-ns">${c.namespace}</span><span class="conn-slash">/</span><span class="conn-name">${esc(c.pod_name)}</span></div>
          ${runtimeLine}
          ${lastActiveLine}
          ${upgradeBtn}
        </div>
        <button class="del-conn" onclick="event.stopPropagation();deleteConnection('${c.id}')" title="删除连接">✕</button>
      </div>
    `;
  });
  el.innerHTML = html;
  if (typeof renderConnectionBatchActions === 'function') renderConnectionBatchActions();
}

async function loadConnectionCommands(connId) {
  // 加载连接的命令历史
  try {
    const r = await fetch(`${API}/arthas/commands?connection_id=${connId}&limit=50`);
    const d = await r.json();
    if (!isActiveCommandConnection(connId)) return;
    if (d.ok && d.commands) {
      // 清空当前输出区
      const co = coEl();
      co.innerHTML = '<div class="o-dim">── Arthas K8s 诊断台 ─────────────────────────────────────────────────────</div>';

      // 按时间倒序显示（最新的在上面）
      d.commands.reverse().forEach(cmd => {
        clog(esc(cmd.command), 'cmd');
        if (cmd.error) {
          clog('✗ ' + esc(cmd.error), 'err');
        } else if (cmd.output) {
          clog(esc(cmd.output));
        }
      });
    }
  } catch(e) {
    console.error('Load commands error:', e);
  }
}

async function switchConnection(connId) {
  _mergeExternalConnectionState();
  if (connId === _currentConnId) {
    const currentConn = _connections.find(c => c.id === connId);
    if (currentConn) syncPodTargetFromConnection(currentConn);
    _syncState();
    return;
  }
  const conn = _connections.find(c => c.id === connId);
  if (!conn) return;

  const level = _inferLevel(conn);
  const t = {
    cluster_name: conn.cluster_name,
    namespace: conn.namespace,
    pod_name: conn.pod_name,
    // ✅ 修复: 数据库字段是 container_name
    container: conn.container_name || conn.container,
    arthas_jar: conn.arthas_jar
  };

  // 显示加载状态
  setConnStatus('dim', `正在切换到 ${conn.cluster_name} / ${conn.namespace} / ${conn.pod_name} ...`);

  try {
    // ── 连接复用逻辑 ──
    // level=pod: 尝试复用后端已有 Pod 连接，不存在则重建
    // level=arthas: 尝试复用已有 Arthas 连接，不可用则降级为 pod 或重建

    let d = null;  // 连接响应数据

    if (level === 'pod') {
      // 先检查后端 Pod 连接是否存活
      try {
        const checkR = await fetch(`${API}/pod/connections`, { credentials: 'include' });
        const checkD = await checkR.json();
        const existing = (checkD.connections || []).find(c => c.id === connId && c.alive);
        if (existing) {
          // 后端连接存活，直接复用，不需要重新连接
          d = { ok: true, connection_id: connId, reused: true, runtime: { runtime_type: existing.runtime, version: existing.runtime_version }, pod_phase: existing.pod_phase };
        }
      } catch (e) {
        console.warn('Pod 连接存活检查失败，将重新连接:', e);
      }

      // 后端无存活连接，重新建立 Pod 连接
      if (!d) {
        const r = await fetch(`${API}/pod/connect`, {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          credentials: 'include',
          body: JSON.stringify({
            cluster_name: t.cluster_name,
            namespace: t.namespace,
            pod_name: t.pod_name,
            container: t.container
          })
        });
        d = await r.json();
        if (!d.ok) {
          throw new Error(d.error || 'Pod 连接失败');
        }
        // 同步两步连接状态
        if (typeof _podConnId !== 'undefined') { _podConnId = d.connection_id; }
        if (typeof _runtimeInfo !== 'undefined') { _runtimeInfo = d.runtime; }
        if (typeof _podPhase !== 'undefined') { _podPhase = d.pod_phase; }
      }
    } else {
      // level=arthas: 尝试复用已有 Arthas 连接
      // 先检查 Arthas 端口是否可达
      try {
        const checkR = await fetch(`${API}/arthas/connections/check`, {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          credentials: 'same-origin',
          body: JSON.stringify({connections: [{id: connId, cluster_name: t.cluster_name, namespace: t.namespace, pod_name: t.pod_name}]}),
          signal: AbortSignal.timeout(8000)
        });
        const checkD = await checkR.json();
        const h = checkD.results && checkD.results[connId];

        if (h && h.alive && h.pod_exists !== false) {
          // Arthas 连接存活，直接复用
          d = { ok: true, connection_id: connId, reused: true, local_port: conn.local_port, java_pid: conn.java_pid, arthas_version: conn.arthas_version, arthas_address: conn.arthas_address };
        } else if (h && h.pod_exists === true && h.alive === false) {
          // Arthas 断了但 Pod 还在 → 降级为 pod level
          conn.level = 'pod';
          delete conn.local_port;
          delete conn.java_pid;
          delete conn.arthas_version;
          delete conn.arthas_address;
          saveConnections();
          // 重新走 pod 连接逻辑
          const podR = await fetch(`${API}/pod/connect`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            credentials: 'include',
            body: JSON.stringify({
              cluster_name: t.cluster_name,
              namespace: t.namespace,
              pod_name: t.pod_name,
              container: t.container
            })
          });
          d = await podR.json();
          if (!d.ok) throw new Error(d.error || 'Pod 连接失败');
          toast('Arthas 连接已断开，已降级为 Pod 连接', 'warn');
          if (typeof _podConnId !== 'undefined') { _podConnId = d.connection_id; }
          if (typeof _runtimeInfo !== 'undefined') { _runtimeInfo = d.runtime; }
          if (typeof _podPhase !== 'undefined') { _podPhase = d.pod_phase; }
        } else {
          // Pod 也不在了，需要重建
          d = null;
        }
      } catch (e) {
        console.warn('Arthas 连接检查失败，尝试重建:', e);
      }

      // 无法复用，走原有 arthas/connect 重建
      if (!d) {
        const r = await fetch(`${API}/arthas/connect`, {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({...t, connection_id: connId})
        });
        d = await r.json();
      }
    }

    if (d && d.ok) {
      // 保存旧连接的采样任务状态（必须在设置 _currentConnId 之前）
      const oldConnId = _currentConnId;
      const hadRunningTask = _pfTaskId && _pfPollTimer;
      if (oldConnId && hadRunningTask) {
        _pfTasksByConn[oldConnId] = {
          taskId: _pfTaskId,
          pollTimer: null,
          startTime: _pfStart,
          duration: _pfDur,
          logLines: _pfLL,
          status: 'running',
          type: _pfTaskInfo.type,
          event: _pfTaskInfo.event
        };
      } else if (oldConnId) {
        delete _pfTasksByConn[oldConnId];
      }

      // 设置新的当前连接
      _currentConnId = connId;
      window._currentConnId = connId;  // ✅ 同步到 window,让状态栏能找到
      _connected = true;
      _ap = syncPodTargetFromConnection(conn) || t;

      // 更新连接层级
      const newLevel = _inferLevel(conn);
      _connHealth[connId] = { alive: true, pod_exists: true, pod_phase: d.pod_phase || 'Running' };

      // 更新连接对象状态 + 后端返回的元数据
      conn.status = 'connected';
      if (d.connection_id) conn.pod_conn_id = d.connection_id;
      if (d.runtime) conn.runtime = d.runtime;
      if (d.local_port) conn.local_port = d.local_port;
      if (d.java_pid) conn.java_pid = d.java_pid;
      if (d.arthas_version) conn.arthas_version = d.arthas_version;
      if (d.arthas_address) conn.arthas_address = d.arthas_address;
      if (d.http_url) conn.http_url = d.http_url;

      // 同步两步连接状态
      if (newLevel === 'pod') {
        _connState = ConnectionState.POD_CONNECTED;
        _runtimeInfo = d.runtime || conn.runtime || _getRt(conn);
        window._connState = ConnectionState.POD_CONNECTED;
        window._runtimeInfo = _runtimeInfo;
        if (typeof _podConnId !== 'undefined') _podConnId = d.connection_id || connId;
        if (typeof _podPhase !== 'undefined') _podPhase = d.pod_phase;
        _connected = false; // Pod 连接不代表 Arthas 可用
        
        // ✅ 修复: 同步到 two-step-connection 组件
        if (typeof window.getConnectionState === 'function') {
          // 触发状态更新
          if (typeof window.updateConnectionButton === 'function') {
            window.updateConnectionButton();
          }
          if (typeof window.updateRuntimeDisplay === 'function') {
            window.updateRuntimeDisplay();
          }
        }
      } else {
        _connState = ConnectionState.ARTHAS_READY;
        window._connState = ConnectionState.ARTHAS_READY;
        if (typeof _runtimeInfo !== 'undefined' && d.runtime) _runtimeInfo = d.runtime;
        _connected = true;
        _currentConnId = connId;
        window._currentConnId = connId;  // ✅ 同步到 window,让状态栏能找到
        
        // ✅ 修复: 同步到 two-step-connection 组件
        if (typeof window.getConnectionState === 'function') {
          if (typeof window.updateConnectionButton === 'function') {
            window.updateConnectionButton();
          }
        }
      }

      // 同步状态到 window
      _syncState({ skipMerge: true });
      
      // ✅ 关键修复: 同步到 ConnectionStore
      if (typeof ConnectionStore !== 'undefined') {
        ConnectionStore.setCurrentConnection(connId);
        ConnectionStore.updateConnection(connId, {
          status: 'connected',
          level: newLevel
        });
      }
      
      renderConnList();
      if (typeof aiRefreshConnSelect === 'function') aiRefreshConnSelect();

      // 清理当前会话状态
      // 切换 Pod 前保存命令行草稿和本地历史，避免多个 Arthas 连接共用同一组输入状态。
      saveCommandConsoleState(oldConnId);
      resetCommandSessionState();

      // 停止当前采样轮询
      if (_pfPollTimer) {
        clearInterval(_pfPollTimer);
        _pfPollTimer = null;
      }

      _pfTaskId = null;
      _pfLL = 0;

      // 更新 UI — 根据层级显示不同信息
      if (newLevel === 'arthas' && conn.local_port) {
        const _switchAddr = conn.arthas_address || conn.http_url || `http://127.0.0.1:${conn.local_port}`;
        const _switchRows = [
          conn.java_pid ? `<div class="ct-tip-row"><span class="ct-tip-k">Java PID</span><span class="ct-tip-v">${esc(String(conn.java_pid))}</span></div>` : '',
          `<div class="ct-tip-row"><span class="ct-tip-k">本地端口</span><span class="ct-tip-v">${esc(String(conn.local_port))}</span></div>`,
          `<div class="ct-tip-row"><span class="ct-tip-k">地址</span><span class="ct-tip-v">${esc(_switchAddr)}</span></div>`,
          conn.arthas_version ? `<div class="ct-tip-row"><span class="ct-tip-k">Arthas</span><span class="ct-tip-v">${esc(conn.arthas_version)}</span></div>` : '',
        ].filter(Boolean).join('');
        setConnStatus('ok', `<div class="ct-tip-hd"><div class="ct-tip-icon">⚡</div><div style="flex:1;min-width:0"><div class="ct-tip-pod">${esc(conn.pod_name)}</div><div class="ct-tip-ns">${esc(conn.cluster_name)} / ${esc(conn.namespace)}</div></div></div><div class="ct-tip-body">${_switchRows}</div>`);
        setCpSt('ok', `✓ 已连接  (port:${conn.local_port})`);
      } else {
        // Pod 层级
        const rt = _getRt(conn);
        const rtInfo = rt ? `${_rtIcon(rt.type)} ${rt.type}${rt.version ? ' ' + rt.version : ''}` : 'Pod';
        setConnStatus('ok', `<div class="ct-tip-hd"><div class="ct-tip-icon">🔵</div><div style="flex:1;min-width:0"><div class="ct-tip-pod">${esc(conn.pod_name)}</div><div class="ct-tip-ns">${esc(conn.cluster_name)} / ${esc(conn.namespace)}</div></div></div><div class="ct-tip-body"><div class="ct-tip-row"><span class="ct-tip-k">连接类型</span><span class="ct-tip-v">Pod连接</span></div><div class="ct-tip-row"><span class="ct-tip-k">运行时</span><span class="ct-tip-v">${rtInfo}</span></div></div>`);
        setCpSt('ok', `✓ Pod 已连接 (${rtInfo})`);
      }

      // 切换连接时设置 conTitle（含悬浮 tooltip）
      const _switchConTitle = document.getElementById('conTitle');
      if (_switchConTitle) {
        const _switchTipRows = [
          `<div class="ct-tip-row"><span class="ct-tip-k">集群</span><span class="ct-tip-v">${esc(conn.cluster_name)}</span></div>`,
          `<div class="ct-tip-row"><span class="ct-tip-k">命名空间</span><span class="ct-tip-v">${esc(conn.namespace)}</span></div>`,
          `<div class="ct-tip-row"><span class="ct-tip-k">Pod</span><span class="ct-tip-v">${esc(conn.pod_name)}</span></div>`,
          `<div class="ct-tip-row"><span class="ct-tip-k">连接类型</span><span class="ct-tip-v">${newLevel === 'arthas' ? 'Arthas连接' : 'Pod连接'}</span></div>`,
          conn.java_pid ? `<div class="ct-tip-row"><span class="ct-tip-k">Java PID</span><span class="ct-tip-v">${esc(String(conn.java_pid))}</span></div>` : '',
          conn.local_port ? `<div class="ct-tip-row"><span class="ct-tip-k">本地端口</span><span class="ct-tip-v">${esc(String(conn.local_port))}</span></div>` : '',
          conn.arthas_version ? `<div class="ct-tip-row"><span class="ct-tip-k">Arthas</span><span class="ct-tip-v">${esc(conn.arthas_version)}</span></div>` : '',
        ].filter(Boolean).join('');
        const titleIcon = newLevel === 'arthas' ? '⚡' : '🔵';
        _switchConTitle.innerHTML = `${esc(conn.cluster_name)}/${esc(conn.namespace)}/${esc(conn.pod_name)}<span class="ct-tip"><div class="ct-tip-hd"><div class="ct-tip-icon">${titleIcon}</div><div><div class="ct-tip-pod">${esc(conn.pod_name)}</div><div class="ct-tip-ns">${esc(conn.cluster_name)} / ${esc(conn.namespace)}</div></div></div><div class="ct-tip-body">${_switchTipRows}</div></span>`;
      }

      // 更新 Arthas 版本徽章
      const _verBadgeSwitch = document.getElementById('arthasVerBadge');
      if (_verBadgeSwitch) {
        if (conn.arthas_version) {
          _verBadgeSwitch.textContent = `Arthas v${conn.arthas_version}`;
          _verBadgeSwitch.style.display = '';
        } else {
          _verBadgeSwitch.style.display = 'none';
        }
      }

      // 更新连接按钮状态
      if (typeof updateConnectionButton === 'function') updateConnectionButton();
      if (typeof updateFeatureTabs === 'function') updateFeatureTabs();
      if (typeof updateRuntimeDisplay === 'function') updateRuntimeDisplay();
      // 刷新连接信息提示条
      if (typeof csbRefresh === 'function') csbRefresh();

      document.getElementById('runBtn').disabled = false;
      restoreCommandConsoleState(connId);

      // 更新 Pod 目标选择器
      const ptNs = document.getElementById('ptNs');
      const ptPod = document.getElementById('ptPod');
      if (ptNs && ptPod) {
        ptNs.value = conn.namespace;
        ptPod.value = conn.pod_name;
      }

      // 加载该连接的命令历史
      await loadConnectionCommands(connId);

      // 加载该连接的采样日志
      const profilerTab = document.getElementById('tab-profiler');
      if (profilerTab && profilerTab.classList.contains('on')) {
        loadConnectionProfilerLogs(connId);
      }

      // 恢复该连接的采样任务状态（如果有缓存的 task_id）
      const targetTask = _pfTasksByConn[connId];
      const hasCachedTask = targetTask && targetTask.taskId;

      if (hasCachedTask) {
        // 先从后端查询任务真实状态
        try {
          const statusResp = await fetch(`${API}/profile/${targetTask.taskId}`);
          const statusData = await statusResp.json();

          if (statusData.status === 'running') {
            // 任务仍在运行，恢复轮询
            _pfTaskId = targetTask.taskId;
            // 恢复 _pfStart：优先用缓存的 startTime，否则从 created_at 推算
            if (targetTask.startTime) {
              _pfStart = targetTask.startTime;
            } else if (statusData.created_at) {
              _pfStart = new Date(statusData.created_at).getTime();
            } else {
              _pfStart = Date.now();  // 兜底
            }
            _pfDur = targetTask.duration || statusData.duration || 60;
            _pfLL = 0;
            _pfPollingForConn = connId;

            _pfTaskInfo = {
              taskId: targetTask.taskId,
              type: targetTask.type || statusData.type || 'profiler',
              event: targetTask.event || statusData.event || '-',
              duration: _pfDur,
              status: 'running',
              progress: statusData.progress ? `后端进度 ${Math.round(statusData.progress)}%` : '等待后端进度',
              progressPercent: Math.min(Math.round(statusData.progress || 0), 95),
              outputFile: statusData.output_file
            };
            updatePfTaskInfo();

            startProfilerPollTimer(2000);

            // 加载该连接的采样日志
            await loadConnectionProfilerLogs(connId);

          } else if (statusData.status === 'completed') {
            // 任务已完成，显示完成状态和下载链接
            delete _pfTasksByConn[connId];
            _pfTaskId = null;
            _pfPollingForConn = null;

            _pfTaskInfo = {
              taskId: targetTask.taskId,
              type: targetTask.type || statusData.type || 'profiler',
              event: targetTask.event || statusData.event || '-',
              duration: statusData.duration || targetTask.duration || '-',
              status: 'completed',
              progress: '100%',
              progressPercent: 100,
              outputFile: statusData.output_file
            };
            updatePfTaskInfo();

            // 加载该连接的采样日志和文件列表
            await loadConnectionProfilerLogs(connId);
            loadLocalFiles();

          } else {
            // 任务失败或取消，清理缓存
            delete _pfTasksByConn[connId];
            _pfTaskId = null;
            _pfPollingForConn = null;
            hidePfTaskInfo();

            // 加载该连接的采样日志
            await loadConnectionProfilerLogs(connId);
          }
        } catch (e) {
          // 查询失败，清理缓存
          console.error('Failed to query task status:', e);
          delete _pfTasksByConn[connId];
          _pfPollingForConn = null;
          hidePfTaskInfo();
        }
      } else {
        // 没有缓存的任务，重置 UI
        _pfPollingForConn = null;
        hidePfTaskInfo();
        const pfLogPanel = document.getElementById('pfl-panel-log');
        const pfLogCnt = document.getElementById('pfLogCnt');
        const pfProgFill = document.getElementById('pfProgFill');
        const pfProgPct = document.getElementById('pfProgPct');
        const pfProgLbl = document.getElementById('pfProgLbl');
        if (pfProgFill) pfProgFill.style.width = '0%';
        if (pfProgPct) pfProgPct.textContent = '0%';
        if (pfProgLbl) pfProgLbl.textContent = '等待中...';
        if (pfLogPanel) pfLogPanel.innerHTML = '<div class="o-dim">等待启动...</div>';
        if (pfLogCnt) pfLogCnt.textContent = '0行';
      }

      // 如果当前标签是 Pod 监控，重新加载数据
      const monitorTab = document.getElementById('tab-monitor');
      if (monitorTab && monitorTab.classList.contains('on')) {
        loadSnap();
      }

      // 如果历史面板可见且勾选了连接筛选，刷新
      if (typeof refreshHistoryIfFiltered === 'function') refreshHistoryIfFiltered();

      // 显示切换提示
      const tip = document.createElement('div');
      tip.style.cssText = 'position:fixed;top:60px;right:20px;background:var(--bg1);border:1px solid var(--a);border-radius:6px;padding:12px 16px;font-size:12px;z-index:9999;box-shadow:0 4px 12px rgba(0,0,0,0.3);animation:slideIn 0.3s ease-out';
      tip.innerHTML = `
        <div style="font-weight:600;color:var(--a);margin-bottom:6px">✓ 已切换连接</div>
        <div style="color:var(--tx2);line-height:1.6">
          <div><span style="color:var(--tx3)">集群:</span> ${conn.cluster_name}</div>
          <div><span style="color:var(--tx3)">环境:</span> ${conn.namespace}</div>
          <div><span style="color:var(--tx3)">Pod:</span> ${conn.pod_name}</div>
        </div>
      `;
      document.body.appendChild(tip);

      // 添加动画样式
      if (!document.getElementById('switch-tip-style')) {
        const style = document.createElement('style');
        style.id = 'switch-tip-style';
        style.textContent = `@keyframes slideIn {from{transform:translateX(100px);opacity:0}to{transform:translateX(0);opacity:1}}`;
        document.head.appendChild(style);
      }

      setTimeout(() => {
        tip.style.opacity = '0';
        tip.style.transform = 'translateX(100px)';
        tip.style.transition = 'all 0.3s ease-out';
        setTimeout(() => tip.remove(), 300);
      }, 2500);

      saveConnections();
    } else {
      // 切换失败
      setConnStatus('fail', '✗ 切换失败: ' + d.message);
      toast('切换连接失败: ' + d.message, 'error');
    }
  } catch(e) {
    setConnStatus('fail', '✗ 切换失败: ' + e.message);
    toast('切换连接失败', 'error');
    console.error('Switch connection error:', e);
  }
}

async function deleteConnection(connId) {
  if (!confirm('确定删除此连接吗？')) return;
  // 通知后端断开连接，释放资源
  fetch(`${API}/arthas/disconnect`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    credentials: 'same-origin',
    body: JSON.stringify({conn_id: connId})
  }).catch(() => {});  // 忽略错误，可能后端已无此连接
  _connections = _connections.filter(c => c.id !== connId);
  delete _connHealth[connId];
  if (_currentConnId === connId) {
    _currentConnId = null;
    _connected = false;
    _ap = null;
    setConnStatus('', '');
    setPtStat('', '');
    setCpSt('', '');
    document.getElementById('conTitle').innerHTML = '等待连接...';
    const _verBadgeDel = document.getElementById('arthasVerBadge');
    if (_verBadgeDel) _verBadgeDel.style.display = 'none';
    document.getElementById('runBtn').disabled = true;
  }
  _syncState();  // 【关键修复】同步状态到 window
  renderConnList();
  saveConnections();
  if (typeof aiRefreshConnSelect === 'function') aiRefreshConnSelect();
}

// 批量检查所有连接的健康状态（区分 level）
async function deleteConnectionPersistent(connId) {
  if (!confirm('确定删除此连接吗？')) return;
  try {
    const r = await fetch(`${API}/connections/${encodeURIComponent(connId)}`, {
      method: 'DELETE',
      credentials: 'include',
    });
    let d = {};
    try { d = await r.json(); } catch (_) {}
    if (!r.ok || (d.code && d.code >= 400) || d.ok === false) {
      throw new Error(d.message || d.error || `HTTP ${r.status}`);
    }
  } catch (e) {
    toast(`删除失败: ${e.message}`, 'error');
    return;
  }
  _connections = _connections.filter(c => c.id !== connId);
  delete _connHealth[connId];
  if (_currentConnId === connId) {
    _currentConnId = null;
    _connected = false;
    _ap = null;
    setConnStatus('', '');
    setPtStat('', '');
    setCpSt('', '');
    document.getElementById('conTitle').innerHTML = '等待连接...';
    const verBadge = document.getElementById('arthasVerBadge');
    if (verBadge) verBadge.style.display = 'none';
    document.getElementById('runBtn').disabled = true;
  }
  _syncState();
  renderConnList();
  saveConnections();
  if (window.ConnectionStore && typeof ConnectionStore.removeConnection === 'function') {
    ConnectionStore.removeConnection(connId);
  }
  if (typeof aiRefreshConnSelect === 'function') aiRefreshConnSelect();
  toast('已删除', 'success');
}

async function checkConnectionsHealth() {
  if (_connections.length === 0) return;
  _connHealth = _connHealth || {};
  try {
    const podConns = _connections.filter(c => _inferLevel(c) === 'pod');
    const arthasConns = _connections.filter(c => _inferLevel(c) === 'arthas');

    // Arthas 连接健康检测
    if (arthasConns.length > 0) {
      const r = await fetch(`${API}/arthas/connections/check`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        credentials: 'same-origin',
        body: JSON.stringify({connections: arthasConns.map(c => ({
          id: c.id, cluster_name: c.cluster_name, namespace: c.namespace, pod_name: c.pod_name
        }))}),
        signal: AbortSignal.timeout(15000)
      });
      const d = await r.json();
      if (d.results) {
        Object.assign(_connHealth, d.results);
        // Arthas 短暂不可达时保留 Arthas 层，避免刷新/健康检查把可恢复连接误降级成 Pod。
        for (const c of arthasConns) {
          const h = d.results[c.id];
          if (h && h.alive === false && h.pod_exists === true) {
            c.status = 'degraded';
            c.state = 'degraded';
            c.health = 'warn';
            if (c.id === _currentConnId) {
              window._connState = 'arthas_ready';
              if (typeof updateConnectionButton === 'function') updateConnectionButton();
              if (typeof updateFeatureTabs === 'function') updateFeatureTabs();
              if (typeof updateRuntimeDisplay === 'function') updateRuntimeDisplay();
              if (typeof csbRefresh === 'function') csbRefresh();
              toast('Arthas 连接暂时不可达，请稍后重试或手动重连', 'warn');
            }
          }
        }
      }
    }

    // Pod 连接存活检测（轻量级）
    if (podConns.length > 0) {
      try {
        const podCheckR = await fetch(`${API}/pod/connections`, { credentials: 'include' });
        const podCheckD = await podCheckR.json();
        const aliveIds = new Set((podCheckD.connections || []).filter(c => c.alive).map(c => c.id));
        for (const c of podConns) {
          const isAlive = aliveIds.has(c.id);
          _connHealth[c.id] = { alive: isAlive, pod_exists: isAlive };
        }
      } catch (e) {
        console.warn('Pod 连接健康检测失败:', e);
      }
    }

    // 同步健康状态到连接对象的 status 字段
    for (const c of _connections) {
      const h = _connHealth[c.id];
      if (h) {
        if (h.pod_exists === false) {
          c.status = 'disconnected';
          c.state = 'disconnected';
          c.health = 'off';
        } else if (h.alive) {
          c.status = 'connected';
          c.state = 'connected';
          c.health = 'ok';
        } else if (_inferLevel(c) === 'arthas') {
          c.status = c.status === 'disconnected' ? 'degraded' : (c.status || 'degraded');
          c.state = c.state === 'disconnected' ? 'degraded' : (c.state || 'degraded');
          c.health = 'warn';
        } else {
          c.status = 'disconnected';
          c.state = 'disconnected';
          c.health = 'off';
        }
      }
    }
    renderConnList();
    _syncState();
    if (typeof aiUpdateConnIndicator === 'function') aiUpdateConnIndicator();
    if (typeof csbRefresh === 'function') csbRefresh();
  } catch(e) {
    console.warn('连接健康检查失败:', e);
  }
}

// 刷新连接列表：从后端数据库重新获取
async function refreshConnectionList() {
  toast('正在刷新连接列表...', 'info');
  try {
    const r = await fetch(`${API}/arthas/connections`, { credentials: 'include' });
    const d = await r.json();
    if (!r.ok || d.ok === false) throw new Error(d.error || '获取失败');
    
    // ✅ 使用 ConnectionStore 统一管理状态
    if (typeof ConnectionStore !== 'undefined') {
      const connections = (d.connections || []).map(_normalizeConnectionRecord);
      ConnectionStore.setConnections(connections);
      ConnectionStore._persist();
      console.log('[refreshConnectionList] Updated ConnectionStore with', connections.length, 'connections');
    } else {
      // 降级: 使用旧逻辑
      _connections = d.connections || [];
      const user = getCurrentUser();
      const key = user ? `arthas_connections_${user.username}` : 'arthas_connections';
      localStorage.setItem(key, JSON.stringify(_connections));
    }
    
    // 重新渲染
    renderConnList();
    toast(`已刷新，${d.connections ? d.connections.length : 0} 个连接`, 'ok');
  } catch (e) {
    console.error('刷新连接列表失败:', e);
    toast('刷新失败: ' + e.message, 'error');
    // 降级：从 ConnectionStore 加载
    if (typeof ConnectionStore !== 'undefined') {
      ConnectionStore.init();
      renderConnList();
    } else {
      loadConnections();
    }
  }
}

// 一键清理所有失效连接（Pod 不存在 或 集群不可用）
async function cleanupStaleConnections() {
  _connHealth = _connHealth || {};
  const staleIds = [];
  for (const c of _connections) {
    const h = _connHealth[c.id];
    if (h && (h.pod_exists === false || h.reason === 'cluster_unavailable')) {
      staleIds.push(c.id);
    }
  }
  if (staleIds.length === 0) {
    toast('没有需要清理的失效连接', 'info');
    return;
  }
  if (!confirm(`发现 ${staleIds.length} 个失效连接（Pod 不存在或集群不可用），是否清理？`)) return;
  try {
    const resp = await fetch(`${API}/arthas/connections/cleanup-stale`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      credentials: 'include',
      body: JSON.stringify({connection_ids: staleIds})
    });
    const data = await resp.json();
    if (!resp.ok || data.ok === false) throw new Error(data.error || '清理失败');
  } catch (e) {
    toast('清理失败: ' + e.message, 'error');
    return;
  }
  _connections = _connections.filter(c => !staleIds.includes(c.id));
  staleIds.forEach(id => delete _connHealth[id]);
  if (staleIds.includes(_currentConnId)) {
    console.log('[清理] 当前连接被清理,重置状态');
    _currentConnId = null;
    _connected = false;
    _ap = null;
    setConnStatus('', '');
    document.getElementById('conTitle').innerHTML = '等待连接...';
    const _verBadgeStale = document.getElementById('arthasVerBadge');
    if (_verBadgeStale) _verBadgeStale.style.display = 'none';
    document.getElementById('runBtn').disabled = true;
  }
  
  // 保存到 localStorage
  saveConnections();
  
  // 同步状态到 window (关键!)
  _syncState();
  
  console.log('[清理] 清理后状态:', {
    connections_count: _connections.length,
    current_conn_id: _currentConnId,
    window_connections: window._connections?.length
  });
  
  // 刷新连接列表
  renderConnList();
  
  // 刷新连接状态条
  if (typeof csbRefresh === 'function') csbRefresh();
  
  // 更新功能 Tab 状态
  if (typeof updateFeatureTabs === 'function') updateFeatureTabs();
  
  // 更新连接按钮
  if (typeof updateConnectionButton === 'function') updateConnectionButton();
  
  toast(`已清理 ${staleIds.length} 个失效连接`, 'success');
}

function saveConnections() {
  // 按用户隔离连接数据，不同用户看不到彼此的连接
  const user = getCurrentUser();
  const key = user ? `arthas_connections_${user.username}` : 'arthas_connections';
  localStorage.setItem(key, JSON.stringify(_connections));
  
  // 保存当前活跃连接 ID 和层级，刷新后自动恢复
  const activeKey = user ? `arthas_active_conn_${user.username}` : 'arthas_active_conn';
  const levelKey = user ? `arthas_active_level_${user.username}` : 'arthas_active_level';
  
  if (_currentConnId) {
    localStorage.setItem(activeKey, _currentConnId);
    // ✅ 修复: 直接用 _connState 推断 level，不依赖连接对象字段完整性
    // _connState 是连接成功时显式设置的，比 _inferLevel() 更可靠
    const level = _connState === 'arthas_ready' ? 'arthas' : 'pod';
    localStorage.setItem(levelKey, level);
  } else {
    localStorage.removeItem(activeKey);
    localStorage.removeItem(levelKey);
  }
  
  // 【关键修复】同步到 window
  _syncState({ skipMerge: true });
}

function loadConnections() {
  try {
    // ✅ 使用 ConnectionStore 统一管理状态
    if (typeof ConnectionStore !== 'undefined') {
      // ConnectionStore 已经在 DOM Ready 时初始化
      const state = ConnectionStore.getState();
      _connections = state.connections || [];
      console.log('[loadConnections] Loaded', _connections.length, 'connections from ConnectionStore');
    } else {
      // 降级: 使用旧逻辑
      const user = getCurrentUser();
      const key = user ? `arthas_connections_${user.username}` : 'arthas_connections';
      const data = localStorage.getItem(key);
      if (data) {
        _connections = JSON.parse(data);
      } else {
        _connections = [];
      }
    }
    
    renderConnList();

    // 自动恢复上次活跃连接（延迟执行，不阻塞页面初始化）
    const user = getCurrentUser();
    const activeKey = user ? `arthas_active_conn_${user.username}` : 'arthas_active_conn';
    const levelKey = user ? `arthas_active_level_${user.username}` : 'arthas_active_level';
    const savedConnId = localStorage.getItem(activeKey);
    const savedLevel = localStorage.getItem(levelKey);  // ✅ 读取保存的层级
    
    if (savedConnId && _connections.find(c => c.id === savedConnId)) {
      const conn = _connections.find(c => c.id === savedConnId);
      if (conn) {
        // ✅ 修复: 去掉 800ms 延迟，立即开始恢复
        _restoreActiveConnection(conn, savedLevel).catch(e => {
          console.warn('自动恢复连接失败:', e);
          _currentConnId = null;
          _syncState();
          renderConnList();
          localStorage.removeItem(activeKey);
          localStorage.removeItem(levelKey);
          if (typeof ConnectionStore !== 'undefined') {
            ConnectionStore.setState({ isRestoring: false, connState: 'disconnected' });
          }
        });
      }
    }
  } catch(e) {
    console.error('加载连接失败:', e);
    _connections = [];
    _syncState();
  }
}

/**
 * 安全恢复上次活跃连接
 * 不走 switchConnection（会被 connId===_currentConnId 短路跳过），
 * 而是直接发起后端 connect 请求重建 Arthas 通道。
 * 
 * @param {Object} conn - 连接对象
 * @param {string} savedLevel - 保存的连接层级 ('arthas' 或 'pod')
 */
async function _restoreActiveConnection(conn, savedLevel) {
  const t = {
    cluster_name: conn.cluster_name,
    namespace: conn.namespace,
    pod_name: conn.pod_name,
    container: conn.container,
    arthas_jar: conn.arthas_jar
  };

  setConnStatus('dim', `正在恢复连接 ${conn.cluster_name} / ${conn.namespace} / ${conn.pod_name} ...`);

  // P0-3: Pod-first 恢复流程 — 先尝试 Pod 连接，再按需升级 Arthas
  // Step 1: 尝试 Pod 连接
  let podOk = false;
  try {
    const podR = await fetch(`${API}/pod/connect`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      credentials: 'include',
      body: JSON.stringify({
        cluster_name: t.cluster_name,
        namespace: t.namespace,
        pod_name: t.pod_name,
        container: t.container
      })
    });
    const podD = await podR.json();
    if (podD.ok) {
      podOk = true;
      // 同步连接状态到局部变量和 ConnectionStore
      _connState = 'pod_connected';
      window._connState = _connState;
      window._runtimeInfo = podD.runtime;
      _runtimeInfo = podD.runtime;
      _podConnId = conn.id;  // ✅ 关键：设置 Pod 连接 ID，upgradeToArthas 依赖它
      window._podConnId = conn.id;
      // 同步到 ConnectionStore，触发 two-step-connection 的订阅回调
      if (typeof ConnectionStore !== 'undefined') {
        ConnectionStore.setState({
          connState: 'pod_connected',
          runtimeInfo: podD.runtime,
          podPhase: podD.pod_phase || 'Running',
          podConnId: conn.id,
        });
      }
      // 同步到全局状态
      _currentConnId = conn.id;
      window._currentConnId = conn.id;
      _connected = false; // Pod 连接不算 _connected（这是 Arthas 标志）
      _ap = syncPodTargetFromConnection(conn) || t;
      _connHealth[conn.id] = { alive: true, pod_exists: true, pod_phase: podD.pod_phase || 'Running' };
      conn.status = 'connected';
      conn.level = 'pod';
      _syncState();
      saveConnections();
      renderConnList();
      // 显式更新 two-step-connection 按钮状态（不依赖订阅回调）
      if (typeof updateConnectionButton === 'function') updateConnectionButton();
      if (typeof updateRuntimeDisplay === 'function') updateRuntimeDisplay();
      if (typeof updateFeatureTabs === 'function') updateFeatureTabs();

      setConnStatus('ok', `✓ Pod 连接已恢复 (${podD.runtime?.runtime_type || 'unknown'})`);
      toast(`Pod 连接已恢复 (${podD.runtime?.runtime_type || 'unknown'})`, 'success');

      // 确保 namespace 下拉正确回填（预加载可能尚未完成）
      const _ptNs = document.getElementById('ptNs');
      if (_ptNs && conn.namespace) {
        const _hasNs = Array.from(_ptNs.options).some(o => o.value === conn.namespace);
        if (!_hasNs) _ptNs.add(new Option(conn.namespace, conn.namespace));
        _ptNs.value = conn.namespace;
      }

      // Step 2: 根据保存的层级判断是否需要升级 Arthas
      // 信任 localStorage 中保存的层级：如果之前是 Arthas 连接，直接尝试升级
      // 运行时检测可能因 kubectl 超时返回 unknown，不能依赖它来决定是否升级
      const shouldUpgradeToArthas = savedLevel === 'arthas';

      if (!shouldUpgradeToArthas) {
        // 不需要升级 Arthas，清除恢复标志
        if (typeof ConnectionStore !== 'undefined') {
          ConnectionStore.setState({ isRestoring: false });
        }
      }

      if (shouldUpgradeToArthas) {
        console.log('[恢复] 检测到之前是 Arthas 连接, 开始自动升级');
        setConnStatus('dim', `正在恢复 Arthas 诊断环境...`);
        try {
          const arthasR = await fetch(`${API}/pod/upgrade-to-arthas`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            credentials: 'include',
            body: JSON.stringify({
              connection_id: conn.id,
              java_pid: conn.java_pid || null,
              force: true
            })
          });
          const arthasD = await arthasR.json();
          if (arthasD.ok) {
            // Arthas 升级成功 — 同步状态到局部变量和 ConnectionStore
            _connState = 'arthas_ready';
            window._connState = _connState;
            _connected = true;
            _currentConnId = conn.id;
            window._currentConnId = conn.id;
            conn.local_port = arthasD.local_port;
            conn.java_pid = arthasD.java_pid;
            conn.arthas_version = arthasD.arthas_version;
            conn.arthas_address = arthasD.arthas_address;
            conn.http_url = arthasD.http_url;
            conn.level = 'arthas';
            if (typeof ConnectionStore !== 'undefined') {
              ConnectionStore.setState({
                connState: 'arthas_ready',
                currentConnId: conn.id,
                isRestoring: false,
              });
              ConnectionStore.setCurrentConnection(conn.id);
              ConnectionStore.updateConnection(conn.id, {
                level: 'arthas',
                local_port: arthasD.local_port,
                java_pid: arthasD.java_pid,
                arthas_version: arthasD.arthas_version,
                arthas_address: arthasD.arthas_address,
                status: 'connected',
              });
            }
            _syncState();
            saveConnections();
            renderConnList();
            // 显式更新 two-step-connection 按钮状态
            if (typeof updateConnectionButton === 'function') updateConnectionButton();
            if (typeof updateFeatureTabs === 'function') updateFeatureTabs();

            const _addr = conn.arthas_address || conn.http_url || `http://127.0.0.1:${conn.local_port}`;
            setConnStatus('ok', `<div class="ct-tip-hd"><div class="ct-tip-icon">⚡</div><div style="flex:1;min-width:0"><div class="ct-tip-pod">${esc(conn.pod_name)}</div><div class="ct-tip-ns">${esc(conn.cluster_name)} / ${esc(conn.namespace)}</div></div></div><div class="ct-tip-body"><div class="ct-tip-row"><span class="ct-tip-k">本地端口</span><span class="ct-tip-v">${esc(String(conn.local_port))}</span></div><div class="ct-tip-row"><span class="ct-tip-k">地址</span><span class="ct-tip-v">${esc(_addr)}</span></div>${conn.arthas_version ? `<div class="ct-tip-row"><span class="ct-tip-k">Arthas</span><span class="ct-tip-v">${esc(conn.arthas_version)}</span></div>` : ''}</div>`);
            setCpSt('ok', `✓ Arthas 已恢复 (port:${conn.local_port})`);
            toast('Arthas 诊断环境已恢复', 'success');
            return;
          }
        } catch (e) {
          console.warn('Arthas 恢复失败，保持 Pod 连接:', e.message);
          // ✅ 修复: 用户可见的错误提示 + 重试入口
          toast(`Arthas 自动恢复失败: ${e.message}（当前为 Pod 连接，可在连接中心重试升级）`, 'warning', 6000);
          setConnStatus('fail', `⚠ Arthas 恢复失败 — ${e.message} <a href="#" onclick="upgradeToArthas();return false" style="color:var(--a);text-decoration:underline">重试</a>`);
          // 清除 isRestoring 标志
          if (typeof ConnectionStore !== 'undefined') {
            ConnectionStore.setState({ isRestoring: false });
          }
        }
      } else {
        console.log(`[恢复] savedLevel=${savedLevel}, runtime=${podD.runtime?.runtime_type}, 不需要升级`);
      }
      return; // Pod 连接成功即返回
    }
  } catch (e) {
    console.warn('Pod 连接恢复失败，尝试直接 Arthas 连接:', e.message);
  }

  // Step 3: 回退到原有 Arthas 直接连接（兼容旧流程）
  const r = await fetch(`${API}/arthas/connect`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    credentials: 'include',
    body: JSON.stringify({...t, connection_id: conn.id})
  });
  const d = await r.json();

  if (!d.ok) {
    throw new Error(d.message || '连接失败');
  }

  // 连接成功，更新状态（复用 switchConnection 中的成功逻辑，但不走 switchConnection 本身）
  _connState = 'arthas_ready';
  window._connState = _connState;
  _currentConnId = conn.id;
  window._currentConnId = conn.id;
  _connected = true;
  _ap = syncPodTargetFromConnection(conn) || t;
  _connHealth[conn.id] = { alive: true, pod_exists: true, pod_phase: 'Running' };
  conn.status = 'connected';
  conn.level = 'arthas';
  conn.local_port = d.local_port;
  if (d.java_pid) conn.java_pid = d.java_pid;
  if (d.arthas_version) conn.arthas_version = d.arthas_version;
  if (d.arthas_address) conn.arthas_address = d.arthas_address;
  if (d.http_url) conn.http_url = d.http_url;
  if (typeof ConnectionStore !== 'undefined') {
    ConnectionStore.setState({
      connState: 'arthas_ready',
      currentConnId: conn.id,
      isRestoring: false,
    });
    ConnectionStore.setCurrentConnection(conn.id);
    ConnectionStore.updateConnection(conn.id, {
      level: 'arthas',
      local_port: d.local_port,
      java_pid: d.java_pid,
      status: 'connected',
    });
  }
  _syncState();
  saveConnections();
  renderConnList();
  // ✅ 显式更新 two-step-connection 按钮状态（ConnectionStore 订阅可能不触发 updateConnectionButton）
  if (typeof updateConnectionButton === 'function') updateConnectionButton();
  if (typeof updateFeatureTabs === 'function') updateFeatureTabs();

  // 更新 UI
  const _addr = conn.arthas_address || conn.http_url || `http://127.0.0.1:${conn.local_port}`;
  setConnStatus('ok', `<div class="ct-tip-hd"><div class="ct-tip-icon">⚡</div><div style="flex:1;min-width:0"><div class="ct-tip-pod">${esc(conn.pod_name)}</div><div class="ct-tip-ns">${esc(conn.cluster_name)} / ${esc(conn.namespace)}</div></div></div><div class="ct-tip-body"><div class="ct-tip-row"><span class="ct-tip-k">本地端口</span><span class="ct-tip-v">${esc(String(conn.local_port))}</span></div><div class="ct-tip-row"><span class="ct-tip-k">地址</span><span class="ct-tip-v">${esc(_addr)}</span></div>${conn.arthas_version ? `<div class="ct-tip-row"><span class="ct-tip-k">Arthas</span><span class="ct-tip-v">${esc(conn.arthas_version)}</span></div>` : ''}</div>`);
  setCpSt('ok', `✓ 已恢复连接  (port:${conn.local_port})`);

  // 更新 conTitle
  const conTitle = document.getElementById('conTitle');
  if (conTitle) {
    conTitle.innerHTML = `${esc(conn.cluster_name)}/${esc(conn.namespace)}/${esc(conn.pod_name)}<span class="ct-tip"><div class="ct-tip-hd"><div class="ct-tip-icon">⚡</div><div><div class="ct-tip-pod">${esc(conn.pod_name)}</div><div class="ct-tip-ns">${esc(conn.cluster_name)} / ${esc(conn.namespace)}</div></div></div><div class="ct-tip-body"><div class="ct-tip-row"><span class="ct-tip-k">集群</span><span class="ct-tip-v">${esc(conn.cluster_name)}</span></div><div class="ct-tip-row"><span class="ct-tip-k">命名空间</span><span class="ct-tip-v">${esc(conn.namespace)}</span></div><div class="ct-tip-row"><span class="ct-tip-k">Pod</span><span class="ct-tip-v">${esc(conn.pod_name)}</span></div>${conn.java_pid ? `<div class="ct-tip-row"><span class="ct-tip-k">Java PID</span><span class="ct-tip-v">${esc(String(conn.java_pid))}</span></div>` : ''}<div class="ct-tip-row"><span class="ct-tip-k">本地端口</span><span class="ct-tip-v">${esc(String(conn.local_port))}</span></div><div class="ct-tip-row"><span class="ct-tip-k">地址</span><span class="ct-tip-v">${esc(_addr)}</span></div>${conn.arthas_version ? `<div class="ct-tip-row"><span class="ct-tip-k">Arthas</span><span class="ct-tip-v">${esc(conn.arthas_version)}</span></div>` : ''}</div></span>`;
  }

  // 更新 Arthas 版本徽章
  const verBadge = document.getElementById('arthasVerBadge');
  if (verBadge) {
    if (conn.arthas_version) {
      verBadge.textContent = `Arthas v${conn.arthas_version}`;
      verBadge.style.display = '';
    } else {
      verBadge.style.display = 'none';
    }
  }

  document.getElementById('runBtn').disabled = false;

  // 更新 Pod 目标选择器
  syncPodTargetFromConnection(conn);

  if (typeof aiRefreshConnSelect === 'function') aiRefreshConnSelect();
}

function switchTab(n) {
  const tabMap = {0:'connections', 1:'profiler', 2:'console', 3:'hotfix', 4:'terminal', 5:'monitor', 6:'filebrowser', 7:'ai', 8:'model-config', 9:'mcp-center', 10:'task-center', 11:'toolchain-center', 12:'history', 13:'diag', 14:'skill-management', 15:'cluster-management', 16:'user-management', 17:'audit-logs', 18:'alerts'};
  const tab = typeof n === 'number' ? tabMap[n] : n;
  const previousShellMode = window.__mainShellMode || 'workspace';
  setMainShellMode('legacy');

  var workspaceTabs = document.getElementById('workspaceTabs');
  var isWorkspaceTab = ['connections','profiler','console','hotfix','ai','diag','diagnosis-cap','history'].includes(tab);
  if (workspaceTabs) {
    workspaceTabs.style.display = isWorkspaceTab ? 'flex' : 'none';
  }

  // Record previous tab for history panel "back" button
  if (tab === 'history') {
    if (previousShellMode !== 'legacy') {
      _historyReturnMode = 'workspace';
      _historyReturnTo = 'workspace';
    } else {
      var currentTab = document.querySelector('.panel.on');
      if (currentTab) {
        var currentId = currentTab.id.replace('panel-', '');
        if (currentId !== 'history') {
          _historyReturnTo = currentId === 'connections' ? 'workspace' : currentId;
          _historyReturnMode = currentId === 'connections' ? 'workspace' : 'legacy';
        }
      }
    }
  }

  // 先切 Tab（允许切换到任何 Tab）
  const allTabs = ['connections','console','profiler','hotfix','monitor','filebrowser','terminal','ai','model-config','mcp-center','task-center','toolchain-center','external-system','history','diag','diagnosis-cap','skill-management','cluster-management','user-management','audit-logs','alerts'];
  
  allTabs.forEach(x => {
    document.getElementById('tab-'+x)?.classList.toggle('on', x===tab);
    var pnl = document.getElementById('panel-'+x);
    if (pnl) {
      pnl.style.display = '';
      pnl.classList.toggle('on', x===tab);
    }
    document.querySelectorAll(`[data-nav-tab="${x}"]`).forEach(el => el.classList.toggle('on', x === tab));
    if (x !== tab) {
      document.getElementById('panel-'+x)?.classList.remove('panel-locked');
    }
  });
  // 清除任务中心子面板的高亮（不在 allTabs 中）
  if (tab !== 'task-center') {
    ['task-schedules', 'task-runs', 'task-scripts'].forEach(function (subTab) {
      document.querySelectorAll('[data-nav-tab="' + subTab + '"]').forEach(function (el) {
        el.classList.remove('on');
      });
    });
  }
  
  // ✅ 第13章: 连接切换时通知 DiagnosisContext
  if (tab === 'connections' && window.DiagnosisContext && window.currentConnection) {
    DiagnosisContext.onConnectionChange(window.currentConnection);
  }

  updateWorkspaceHead(tab);
  updateConnectionBarVisibility(tab);
  loadAdminFrameIfNeeded(tab);

  // ✅ 新增: 诊断能力面板初始化
  if (tab === 'diagnosis-cap') {
    if (typeof dcInit === 'function') {
      dcInit();
    } else if (typeof diagCapInit === 'function') {
      diagCapInit();
    }
  }
  
  // ✅ 新增: 任务中心面板初始化
  if (tab === 'task-center') {
    if (typeof initTaskCenterV2 === 'function') {
      initTaskCenterV2();  // task-center.js
    }
  }
  
  // ✅ 新增: 工具箱面板初始化
  if (tab === 'toolchain-center') {
    if (typeof renderToolbox === 'function') {
      renderToolbox();
    } else {
      loadToolchainCenter();
    }
  }

  // 连接引导检查：允许切 Tab，但不满足要求时显示引导面板 + 禁用操作区
  if (window.ConnectionGuard) {
    const result = ConnectionGuard.check(tab);
    if (!result.ok) {
      // 显示引导面板，禁用面板内的操作
      ConnectionGuard.showGuide(tab, result.current, result.required);
      // 给面板加禁用遮罩（引导面板在遮罩上层，可点击引导按钮）
      const panel = document.getElementById('panel-'+tab);
      if (panel) panel.classList.add('panel-locked');
    } else {
      // 满足要求，隐藏引导 + 移除禁用
      ConnectionGuard.hideGuide();
      const panel = document.getElementById('panel-'+tab);
      if (panel) panel.classList.remove('panel-locked');
    }
  } else {
    // 降级：兼容旧逻辑
    const cs = window._connState;
    const hasPod = cs === 'pod_connected' || cs === 'arthas_ready';
    const hasArthas = cs === 'arthas_ready';
    const arthasOnlyTabs = ['console', 'profiler'];
    if (arthasOnlyTabs.includes(tab) && !hasArthas) {
      if (hasPod) { toast('此功能需要启动 Arthas 诊断环境', 'warn'); }
      else { toast('请先建立 Pod 连接', 'warn'); }
    }
    if (['monitor','filebrowser','terminal'].includes(tab) && !hasPod) {
      toast('请先建立 Pod 连接', 'warn');
    }
  }

  // Show Arthas JAR path only for Arthas/JProfiler tabs
  const needsArthas = ['console','profiler'].includes(tab);
  const jarWrap = document.getElementById('ptArthasWrap');
  if(jarWrap) jarWrap.style.display = needsArthas ? 'block' : 'none';

  // Adapt connect button — delegate to two-step-connection's updateConnectionButton
  // which correctly manages ptConnBtn (step 3) and ptUpgradeBtn (step 4) independently
  if (typeof updateConnectionButton === 'function') updateConnectionButton();

  // Terminal tab overrides ptConnBtn for terminal-specific connect
  if(tab === 'terminal') {
    const connBtn = document.getElementById('ptConnBtn');
    if(connBtn) {
      connBtn.textContent = '🖥️ 终端连接';
      connBtn.onclick = () => { termInit(); };
    }
  }

  if(tab==='history') loadHistory();
  // 刷新连接信息提示条
  if(typeof csbRefresh === 'function') csbRefresh();
  // 离开监控 tab 时清理 history 轮询
  if(tab!=='monitor') {
    clearInterval(window._histTimer);
    window._histTimer = null;
    stopMonitorBackendPolling();
  }
  if(tab==='profiler') {
    setTimeout(() => {
      // 加载当前连接的采样日志
      if (_currentConnId) {
        loadConnectionProfilerLogs(_currentConnId);
      }
    }, 100);
  }
  if(tab==='terminal') {
    setTimeout(()=>{
      if (typeof syncTerminalFromFocusedConnection === 'function') syncTerminalFromFocusedConnection({ silent: true, autoConnect: false });
      document.getElementById('termInput')?.focus();
    },100);
  }
  if(tab==='console') { setTimeout(hardenCommandSearchAutofill, 100); setTimeout(hardenCommandSearchAutofill, 350); }
  if(tab==='ai') { setTimeout(()=>{ aiRefreshConnSelect(); document.getElementById('aiInput')?.focus(); },100); }
  if(tab==='model-config') { setTimeout(()=>{ document.querySelector('#panel-model-config button')?.focus(); },100); }
  if(tab==='mcp-center') { setTimeout(()=>{ document.querySelector('#panel-mcp-center iframe')?.contentWindow?.focus?.(); },100); }
  if(tab==='task-center') { /* loadTaskCenter() replaced by initTaskCenterV2 */ }
  if(tab==='toolchain-center') { loadToolchainCenter(); }
  if(tab==='diag') { setTimeout(()=>{ if(typeof diagRefreshConn==='function') diagRefreshConn(); },100); }

  if(tab==='monitor') {
    loadSnap();
  }
}

const HISTORY_VIEW_SELECTORS = {
  'filter-label': '[data-history-role="filter-label"], #histFilterLabel',
  'filter-checkbox': '[data-history-role="filter-checkbox"], #histFilterConn',
  'filter-pod': '[data-history-role="filter-pod"], #histFilterPod',
  'tab-profiler': '[data-history-role="tab-profiler"], #hist-profiler',
  'tab-files': '[data-history-role="tab-files"], #hist-files',
  'panel-profiler': '[data-history-role="panel-profiler"], #hist-panel-profiler',
  'panel-files': '[data-history-role="panel-files"], #hist-panel-files',
  'count-profiler': '[data-history-role="count-profiler"], #cntPfTasks',
  'count-files': '[data-history-role="count-files"], #cntDlFiles',
};

window.__workspaceHistoryHost = window.__workspaceHistoryHost || null;

function setWorkspaceHistoryHost(root) {
  window.__workspaceHistoryHost = root || null;
}

function clearWorkspaceHistoryHost(root) {
  if (root && window.__workspaceHistoryHost && window.__workspaceHistoryHost !== root) return;
  window.__workspaceHistoryHost = null;
}

function getHistoryViewRoot() {
  const workspaceRoot = window.__workspaceHistoryHost;
  if (workspaceRoot && document.body.contains(workspaceRoot)) return workspaceRoot;
  if (workspaceRoot) window.__workspaceHistoryHost = null;
  return document.getElementById('panel-history');
}

function isHistoryViewVisible(root) {
  if (!root) return false;
  if (root.dataset && root.dataset.historyHost === 'workspace') return true;
  return root.classList.contains('on');
}

function getHistoryViewElement(role) {
  const root = getHistoryViewRoot();
  const selector = HISTORY_VIEW_SELECTORS[role];
  if (!root || !selector) return null;
  return root.querySelector(selector);
}

function updateHistoryCounts() {
  const pfCnt = parseInt(getHistoryViewElement('count-profiler')?.textContent) || 0;
  const fileCnt = parseInt(getHistoryViewElement('count-files')?.textContent) || 0;
  const totalEl = document.getElementById('cntHistory');
  if (totalEl) totalEl.textContent = pfCnt + fileCnt;
}

window.setWorkspaceHistoryHost = setWorkspaceHistoryHost;
window.clearWorkspaceHistoryHost = clearWorkspaceHistoryHost;
window.updateHistoryCounts = updateHistoryCounts;

function switchHistTab(name) {
  ['profiler','files'].forEach(n => {
    const tab = getHistoryViewElement('tab-' + n);
    if (tab) {
      tab.classList.toggle('active', n===name);
      tab.classList.toggle('on', n===name); // legacy compat
    }
    const p = getHistoryViewElement('panel-' + n);
    if (p) {
      p.classList.toggle('active', n===name);
      p.style.display = n===name ? 'block' : 'none';
    }
  });
}



function switchPm(n) {
  const tabs = ['ov','mt','pr','nw','dk','ev','lg','cf','fb'];
  tabs.forEach(x => {
    document.getElementById('pms-'+x)?.classList.toggle('on', x===n);
    const p = document.getElementById('pmp-'+x);
    if(p) { p.style.display = x===n ? 'block' : 'none'; p.classList.toggle('on', x===n); }
  });
  // Fix logs panel flex
  const lg = document.getElementById('pmp-lg');
  if(lg && n==='lg') lg.style.display = 'flex'; // override block
  if(n==='mt' && _snap) renderMetrics(_snap);
  if(n==='dk' && _snap) renderDisk(_snap);
}

// ── Server health ──────────────────────────────────────────────────────────────
async function checkHealth() {
  try {
    const r = await fetch(`${API}/health`, {signal: AbortSignal.timeout(2000)});
    const ok = r.ok;
    document.getElementById('svDot').className = 'dot' + (ok ? ' live' : '');
    document.getElementById('svLbl').textContent = ok ? '服务在线' : '服务离线';
    return ok;
  } catch {
    document.getElementById('svDot').className = 'dot';
    document.getElementById('svLbl').textContent = '服务离线';
    return false;
  }
}

// ── Target helpers ─────────────────────────────────────────────────────────────
function normalizeConnTarget(conn) {
  if (!conn) return null;
  return {
    cluster_name: conn.cluster_name || conn.cluster || '',
    namespace: conn.namespace || 'default',
    pod_name: conn.pod_name || conn.pod || '',
    // ✅ 修复: 数据库字段是 container_name,不是 container
    container: conn.container_name || conn.container || '',
    arthas_jar: conn.arthas_jar || document.getElementById('ptArthas')?.value || '/app/arthas/arthas-boot.jar',
  };
}

function syncPodTargetFromConnection(conn) {
  const t = normalizeConnTarget(conn);
  if (!t) return null;
  _ac = t.cluster_name || _ac;
  const ptNs = document.getElementById('ptNs');
  const ptPod = document.getElementById('ptPod');
  const ptCtr = document.getElementById('ptCtr');
  const ptArthas = document.getElementById('ptArthas');
  if (ptNs) {
    // 确保目标 namespace 在下拉列表中（切换集群时选项可能未加载）
    const ns = t.namespace || 'default';
    const exists = Array.from(ptNs.options || []).some(opt => opt.value === ns);
    if (ns && !exists) ptNs.add(new Option(ns, ns));
    ptNs.value = ns;
    // 异步加载该集群的完整 namespace 列表，刷新下拉选项
    const cached = window._clusterNs && window._clusterNs[t.cluster_name];
    if (cached) { populateNsList(cached); }
    else if (t.cluster_name) { autoLoadNs(t.cluster_name); }
  }
  if (ptPod) ptPod.value = t.pod_name || '';
  if (ptCtr) {
    const value = t.container || '';
    const exists = Array.from(ptCtr.options || []).some(opt => opt.value === value);
    if (value && !exists) ptCtr.add(new Option(value, value));
    ptCtr.value = value;
  }
  if (ptArthas && t.arthas_jar) ptArthas.value = t.arthas_jar;
  _ap = t;
  return t;
}

function syncArthasConsoleFromFocus() {
  if (window.ConnectionStore && typeof ConnectionStore.getFocusConnection === 'function') {
    const conn = ConnectionStore.getFocusConnection();
    const level = conn && (conn.level || conn.connection_level || '').toLowerCase();
    const hasArthas = conn && (level === 'arthas' || conn.local_port || conn.arthas_version || conn.arthas?.port);
    if (hasArthas) {
      _currentConnId = conn.id;
      window._currentConnId = conn.id;
      _connState = 'arthas_ready';
      window._connState = _connState;
      _connected = true;
      _ap = syncPodTargetFromConnection(conn) || _ap;
      const runBtn = document.getElementById('runBtn');
      if (runBtn) runBtn.disabled = false;
      if (typeof setCpSt === 'function') setCpSt('ok', conn.local_port ? `✓ 已连接 (port:${conn.local_port})` : '✓ 已连接');
      return true;
    }
  }
  return _connected;
}

function getCurrentPodTarget() {
  _mergeExternalConnectionState();
  const formTarget = getT();
  if (window._manualTargetDirty) {
    return formTarget;
  }
  const currentId = _currentConnId || window._currentConnId || null;
  const conn = _connections.find(c => c.id === currentId) || (window._connections || []).find(c => c.id === currentId);
  const connTarget = syncPodTargetFromConnection(conn);
  return {
    cluster_name: connTarget?.cluster_name || formTarget.cluster_name || '',
    namespace: connTarget?.namespace || formTarget.namespace || 'default',
    pod_name: connTarget?.pod_name || formTarget.pod_name || '',
    container: connTarget?.container || formTarget.container || '',
    arthas_jar: connTarget?.arthas_jar || formTarget.arthas_jar || '',
  };
}

function resetConnectionFlowForTargetChange() {
  window._manualTargetDirty = true;
  _currentConnId = null;
  window._currentConnId = null;
  _connected = false;
  _ap = null;
  window._selectedJavaPid = null;
  window._lastCheckResult = null;
  if (typeof resetTwoStepConnectionState === 'function') resetTwoStepConnectionState();
  else window._connState = 'disconnected';
  const runtimeEl = document.getElementById('runtimeInfo');
  if (runtimeEl) runtimeEl.style.display = 'none';
  setPtStat('', '');
  setConnStatus('', '');
  // 展开 Pod 目标区，让用户能看到连接按钮
  const podTarget = document.getElementById('podTarget');
  if (podTarget && podTarget.classList.contains('collapsed')) {
    podTarget.classList.remove('collapsed');
    const arrow = document.getElementById('ptCollapseArrow');
    if (arrow) arrow.classList.remove('up');
  }
  const conTitle = document.getElementById('conTitle');
  if (conTitle) conTitle.innerHTML = '等待连接...';
  const verBadge = document.getElementById('arthasVerBadge');
  if (verBadge) verBadge.style.display = 'none';
  const runBtn = document.getElementById('runBtn');
  if (runBtn) runBtn.disabled = true;
  if (typeof updateConnectionButton === 'function') updateConnectionButton();
  if (typeof updateFeatureTabs === 'function') updateFeatureTabs();
  if (typeof csbRefresh === 'function') csbRefresh();
  _syncState();
}

function getT() {
  return {
    cluster_name: _ac || '',
    namespace: document.getElementById('ptNs').value || 'default',
    pod_name: document.getElementById('ptPod').value.trim(),
    container: document.getElementById('ptCtr').value,
    arthas_jar: document.getElementById('ptArthas').value,
  };
}

function setPtStat(type, msg) {
  const el = document.getElementById('ptStat');
  el.style.display = msg ? 'block' : 'none';
  el.className = 'pt-stat' + (type ? ' ' + type : '');
  el.textContent = msg;
}

async function loadPods() {
  if(!_ac) { toast('请先选择集群','warn'); return; }
  if(!validateSelectedNamespace()) return;
  const ns = document.getElementById('ptNs').value || 'default';
  try {
    const r = await fetch(`${API}/clusters/${encodeURIComponent(_ac)}/pods?namespace=${ns}`, { credentials: 'include' });
    if (r.status === 401) { window.location.replace('/login.html'); return; }
    const d = await r.json();
    const pods = d.pods || [];
    const sel = document.getElementById('ptPodSel');
    sel.innerHTML = '<option value="">— 选择 Pod —</option>' +
      pods.map(p => `<option value="${p.name}" data-c="${p.containers.join(',')}">${p.name} [${p.phase}]</option>`).join('');
    sel.style.display = 'block';
    toast(`找到 ${pods.length} 个 Pod`);
  } catch(e) { toast('加载失败: ' + e.message, 'error'); }
}

function onPodSel(name) {
  document.getElementById('ptPod').value = name;
  const sel = document.getElementById('ptPodSel');
  const opt = sel.options[sel.selectedIndex];
  const ctrs = (opt?.dataset.c || '').split(',').filter(Boolean);
  const csel = document.getElementById('ptCtr');
  csel.innerHTML = '<option value="">默认容器</option>' + ctrs.map(c => `<option value="${c}">${c}</option>`).join('');
  csel.value = ctrs[0] || '';
  const lcsel = document.getElementById('logCtr');
  if(lcsel) lcsel.innerHTML = ctrs.map(c => `<option value="${c}">${c}</option>`).join('');
  resetConnectionFlowForTargetChange();
}

async function checkPod() {
  const t = getT();
  if(!t.cluster_name) { toast('请选择集群','warn'); return; }
  if(!t.pod_name) { toast('请填写 Pod 名称','warn'); return; }
  setPtStat('info', '检查中...');
  try {
    const r = await fetch(`${API}/check`, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(t)});
    const d = await r.json();
    if(d.error) setPtStat('fail', `✗ ${d.error}`);
    else if(d.java_processes && d.java_processes.length > 0) {
      // 存储检测结果供后续使用
      window._lastCheckResult = d;
      
      if(d.has_multiple_jvms) {
        // 多个 Java 进程，提示用户选择
        setPtStat('warn', `检测到 ${d.java_processes.length} 个 Java 进程，请选择`);
        showPidSelector(d.java_processes);
      } else {
        setPtStat('ok', `✓ 检测到 Java PID: ${d.java_pid} (${d.java_processes[0].description})`);
        window._selectedJavaPid = d.java_pid;
      }
    }
    else setPtStat('warn', '未检测到 Java 进程');
  } catch(e) { setPtStat('fail', '失败: ' + e.message); }
}

// 显示 PID 选择弹窗
function showPidSelector(processes) {
  // 移除已存在的弹窗
  const existing = document.getElementById('pidSelectorModal');
  if(existing) existing.remove();
  
  const options = processes.map(p => 
    `<option value="${p.pid}">${p.pid} - ${escapeHtml(p.description)}</option>`
  ).join('');
  
  const modal = document.createElement('div');
  modal.id = 'pidSelectorModal';
  modal.innerHTML = `
    <div style="position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.6);z-index:9999;display:flex;align-items:center;justify-content:center;">
      <div style="background:var(--bg2);border-radius:8px;padding:24px;min-width:400px;max-width:600px;box-shadow:0 4px 20px rgba(0,0,0,0.5);">
        <h3 style="margin:0 0 16px 0;color:var(--fg);">选择要连接的 Java 进程</h3>
        <p style="margin:0 0 12px 0;color:var(--muted);font-size:13px;">检测到多个 Java 进程，请选择 Arthas 要附加的目标进程：</p>
        <select id="pidSelect" style="width:100%;padding:10px;border-radius:4px;background:var(--bg);color:var(--fg);border:1px solid var(--border);font-size:14px;">
          ${options}
        </select>
        <div style="margin-top:20px;display:flex;gap:12px;justify-content:flex-end;">
          <button id="pidCancelBtn" style="padding:8px 20px;border-radius:4px;border:1px solid var(--border);background:transparent;color:var(--fg);cursor:pointer;">取消</button>
          <button id="pidConfirmBtn" style="padding:8px 20px;border-radius:4px;border:none;background:var(--accent);color:#fff;cursor:pointer;font-weight:500;">确认</button>
        </div>
      </div>
    </div>
  `;
  document.body.appendChild(modal);
  
  document.getElementById('pidCancelBtn').onclick = () => modal.remove();
  document.getElementById('pidConfirmBtn').onclick = () => {
    const selectedPid = document.getElementById('pidSelect').value;
    const selectedProcess = processes.find(p => p.pid === selectedPid);
    window._selectedJavaPid = selectedPid;
    setPtStat('ok', `✓ 已选择 Java PID: ${selectedPid} (${selectedProcess?.description || ''})`);
    modal.remove();
  };
  
  // 点击背景关闭
  modal.querySelector('div > div').parentElement.onclick = (e) => {
    if(e.target === modal.querySelector('div > div').parentElement) modal.remove();
  };
}

// ── Arthas Connect ─────────────────────────────────────────────────────────────
async function arthasConnect() {
  const t = getT();
  if(!t.cluster_name || !t.pod_name) { toast('请先配置集群和 Pod','warn'); return; }
  
  // 检查是否需要选择 Java PID
  if(window._lastCheckResult && window._lastCheckResult.has_multiple_jvms && !window._selectedJavaPid) {
    showPidSelector(window._lastCheckResult.java_processes);
    return;
  }
  
      // 添加用户选择的 Java PID 到请求参数
      if(window._selectedJavaPid) {
        t.java_pid = window._selectedJavaPid;
      }

      const ptBtn = document.getElementById('ptConnBtn');
      ptBtn.disabled = true; ptBtn.textContent = '连接中...';
      setCpSt('', ''); setConnStatus('dim', `正在连接 ${t.cluster_name} / ${t.namespace} / ${t.pod_name} ...`);
      try {
        const r = await fetch(`${API}/arthas/connect`, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(t)});
        const d = await r.json();
        if(d.ok) {
          // 使用后端返回的 connection_id
          const connId = d.connection_id || d.conn_id;
          const nowIso = new Date().toISOString();
          const newConn = {
            id: connId,
            cluster_name: t.cluster_name,
            namespace: t.namespace,
            pod_name: t.pod_name,
            container: t.container,
            arthas_jar: t.arthas_jar,
            level: 'arthas',
            local_port: d.local_port,
            java_pid: d.java_pid || null,
            arthas_version: d.arthas_version || '',
            arthas_address: d.arthas_address || d.http_url || '',
            http_url: d.http_url || '',
            status: 'connected',
            message: d.message,
            last_ping_at: nowIso,
            last_active_at: nowIso,
            created_at: nowIso
          };

          // 检查是否已存在相同的 Pod 连接
          const existingIndex = _connections.findIndex(c =>
            c.cluster_name === t.cluster_name && c.namespace === t.namespace && c.pod_name === t.pod_name
          );

          if (existingIndex >= 0) {
            // 更新现有连接
            _connections[existingIndex] = newConn;
            _currentConnId = newConn.id;
          } else {
            // 添加新连接
            _connections.push(newConn);
            _currentConnId = newConn.id;
          }

          _connected = true;
          _ap = t;
          ptBtn.textContent = '⚡ 连接'; ptBtn.className = 'pt-btn'; ptBtn.disabled = false;

          // 连接成功后，立即标记为健康状态
          _connHealth[connId] = { alive: true, pod_exists: true, pod_phase: 'Running' };

          // 【关键修复】同步状态到 window
          _syncState();
          renderConnList();
          if (typeof aiRefreshConnSelect === 'function') aiRefreshConnSelect();
      setCpSt('ok', `✓ ${d.message}  (port:${d.local_port})`);
      document.getElementById('runBtn').disabled = false;
      const _verSuffix = d.arthas_version ? `  Arthas ${d.arthas_version}` : '';
      const _addrInfo = d.arthas_address || d.http_url || `http://127.0.0.1:${d.local_port}`;
      // conTitle 悬浮 tooltip 展示完整连接信息
      const _conTitleEl = document.getElementById('conTitle');
      if (_conTitleEl) {
        const _tipRows = [
          `<div class="ct-tip-row"><span class="ct-tip-k">集群</span><span class="ct-tip-v">${esc(t.cluster_name)}</span></div>`,
          `<div class="ct-tip-row"><span class="ct-tip-k">命名空间</span><span class="ct-tip-v">${esc(t.namespace)}</span></div>`,
          `<div class="ct-tip-row"><span class="ct-tip-k">Pod</span><span class="ct-tip-v">${esc(t.pod_name)}</span></div>`,
          d.java_pid ? `<div class="ct-tip-row"><span class="ct-tip-k">Java PID</span><span class="ct-tip-v">${esc(String(d.java_pid))}</span></div>` : '',
          `<div class="ct-tip-row"><span class="ct-tip-k">本地端口</span><span class="ct-tip-v">${esc(String(d.local_port))}</span></div>`,
          `<div class="ct-tip-row"><span class="ct-tip-k">地址</span><span class="ct-tip-v">${esc(_addrInfo)}</span></div>`,
          d.arthas_version ? `<div class="ct-tip-row"><span class="ct-tip-k">Arthas</span><span class="ct-tip-v">${esc(d.arthas_version)}</span></div>` : '',
        ].filter(Boolean).join('');
        _conTitleEl.innerHTML = `${esc(t.cluster_name)}/${esc(t.namespace)}/${esc(t.pod_name)}<span class="ct-tip"><div class="ct-tip-hd"><div class="ct-tip-icon">⚡</div><div><div class="ct-tip-pod">${esc(t.pod_name)}</div><div class="ct-tip-ns">${esc(t.cluster_name)} / ${esc(t.namespace)}</div></div></div><div class="ct-tip-body">${_tipRows}</div></span>`;
      }
      // 在 conTitle 旁显示 Arthas 版本徽章
      const _verBadge = document.getElementById('arthasVerBadge');
      if (_verBadge) {
        if (d.arthas_version) {
          _verBadge.textContent = `Arthas v${d.arthas_version}`;
          _verBadge.style.display = '';
        } else {
          _verBadge.style.display = 'none';
        }
      }
      setPtStat('ok', d.java_pid ? `Arthas 已连接 (PID: ${d.java_pid})${_verSuffix}` : `Arthas 已连接${_verSuffix}`);
      const _connRows = [
        d.java_pid ? `<div class="ct-tip-row"><span class="ct-tip-k">Java PID</span><span class="ct-tip-v">${esc(String(d.java_pid))}</span></div>` : '',
        `<div class="ct-tip-row"><span class="ct-tip-k">本地端口</span><span class="ct-tip-v">${esc(String(d.local_port))}</span></div>`,
        `<div class="ct-tip-row"><span class="ct-tip-k">地址</span><span class="ct-tip-v">${esc(_addrInfo)}</span></div>`,
        d.arthas_version ? `<div class="ct-tip-row"><span class="ct-tip-k">Arthas</span><span class="ct-tip-v">${esc(d.arthas_version)}</span></div>` : '',
      ].filter(Boolean).join('');
      setConnStatus('ok', `<div class="ct-tip-hd"><div class="ct-tip-icon">⚡</div><div style="flex:1;min-width:0"><div class="ct-tip-pod">${esc(t.pod_name)}</div><div class="ct-tip-ns">${esc(t.cluster_name)} / ${esc(t.namespace)}</div></div></div><div class="ct-tip-body">${_connRows}</div>`);
      // 在控制台输出区显示连接信息
      clog(`── Arthas 已连接 ──`, 'dim');
      clog(`PID: ${d.java_pid || '?'}   Port: ${d.local_port}`, 'dim');
      if (d.arthas_version) clog(`Arthas Version: ${d.arthas_version}`, 'ok');
      saveConnections();
      toast('连接成功', 'success');
      // 连接成功后自动折叠 Pod 目标区，节省侧边栏空间
      const podTarget = document.getElementById('podTarget');
      const ptArrow = document.getElementById('ptCollapseArrow');
      if (podTarget && !podTarget.classList.contains('collapsed')) {
        podTarget.classList.add('collapsed');
        if (ptArrow) ptArrow.classList.add('up');
      }
    } else {
      setCpSt('fail', '✗ ' + d.message); setPtStat('fail', d.message);
      clog('✗ ' + d.message, 'err'); toast('连接失败','error');
      ptBtn.disabled = false; ptBtn.textContent = '⚡ 连接'; ptBtn.className = 'pt-btn';
    }
  } catch(e) {
    clog('✗ ' + e.message, 'err');
    ptBtn.disabled = false; ptBtn.textContent = '⚡ 连接'; ptBtn.className = 'pt-btn';
  }
}

async function arthasDC() {
  _polling = false; if(_pollTimer) { clearTimeout(_pollTimer); _pollTimer = null; }
  if(_sid && _ap) try { await fetch(`${API}/arthas/session/close`, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({..._ap, session_id: _sid})}); } catch {}
  if(_ap) try { await fetch(`${API}/arthas/disconnect`, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(_ap)}); } catch {}
  
  // 更新新连接池状态
  if (typeof ConnectionStore !== 'undefined' && _currentConnId) {
    ConnectionStore.updateConnection(_currentConnId, {
      state: ConnectionState.DISCONNECTED, level: 'disconnected', arthas: null, health: 'off'
    });
    if (typeof ConnectionPool !== 'undefined') ConnectionPool.render();
    if (typeof ConnectionWorkspace !== 'undefined') ConnectionWorkspace.render();
  }
  
  saveCommandConsoleState(_currentConnId);
  _connected = false; _ap = null; resetCommandSessionState();
  window._selectedJavaPid = null;  // 清除选中的 PID
  const ptBtn = document.getElementById('ptConnBtn');
  ptBtn.disabled = false; ptBtn.textContent = '⚡ 连接'; ptBtn.className = 'pt-btn';
  document.getElementById('runBtn').disabled = true;
  setCpSt('', ''); setPtStat('', ''); setConnStatus('', '');
  document.getElementById('btnStop').style.display = 'none';
  document.getElementById('conTitle').innerHTML = '等待连接...';
  const _verBadgeDisc = document.getElementById('arthasVerBadge');
  if (_verBadgeDisc) _verBadgeDisc.style.display = 'none';
  clog('── 已断开连接 ──', 'dim'); toast('已断开','info');
}

function setConnStatus(type, msg) {
  const el = document.getElementById('connStatus');
  if (!el) return;
  if (!msg) { el.style.display = 'none'; el.innerHTML = ''; return; }
  el.style.display = 'block';
  el.className = type === 'ok' ? 'conn-status ok' : type === 'dim' ? 'conn-status dim' : type === 'fail' ? 'conn-status fail' : 'conn-status';
  el.innerHTML = msg;
}

function setCpSt(type, msg) {
  const el = document.getElementById('cpSt');
  el.style.display = msg ? 'block' : 'none';
  el.className = 'cp-cst' + (type ? ' ' + type : '');
  el.textContent = msg;
}

// ── Console output ─────────────────────────────────────────────────────────────
const coEl = () => document.getElementById('conOut');

// ── 高性能输出：批量写入 + RAF 滚动，避免每次 DOM 操作触发 reflow ──────────
const _logCls = {line:'o-line',dim:'o-dim',ok:'o-ok',err:'o-err',warn:'o-warn',cmd:'o-cmd'};
let   _logRaf = null;   // requestAnimationFrame handle
let   _logFrag = null;  // pending DocumentFragment

function clog(msg, cls='line') {
  if(!_logFrag) _logFrag = document.createDocumentFragment();
  const d = document.createElement('div');
  d.className = _logCls[cls] || 'o-line';
  d.innerHTML = msg;
  _logFrag.appendChild(d);
  // Flush at most once per animation frame
  if(!_logRaf) {
    _logRaf = requestAnimationFrame(() => {
      const el = coEl();
      if(_logFrag && el) {
        el.appendChild(_logFrag);
        // Only scroll if user is near bottom (within 120px)
        if(el.scrollHeight - el.scrollTop - el.clientHeight < 120) {
          el.scrollTop = el.scrollHeight;
        }
      }
      _logFrag = null;
      _logRaf  = null;
    });
  }
}

function _flushLog() {
  // Force-flush pending log entries immediately (e.g. before clearing)
  if(_logRaf) { cancelAnimationFrame(_logRaf); _logRaf = null; }
  const el = coEl();
  if(_logFrag && el) { el.appendChild(_logFrag); _logFrag = null; }
}

function clearConOut() { _flushLog(); coEl().innerHTML = ''; }
function oSep() {
  const d = document.createElement('div'); d.className = 'o-sep';
  if(!_logFrag) _logFrag = document.createDocumentFragment();
  _logFrag.appendChild(d);
  if(!_logRaf) {
    _logRaf = requestAnimationFrame(() => {
      const el = coEl(); if(_logFrag && el) el.appendChild(_logFrag);
      _logFrag = null; _logRaf = null;
    });
  }
}

// ── Arthas Command Catalogue ───────────────────────────────────────────────────
// 命令数据结构:
//   id       — 唯一标识
//   name     — 实际执行的命令名
//   icon     — 面板图标
//   type     — once(一次性) | stream(持续输出Session) | profiler(采样)
//   desc     — 简短描述（面板列表展示）
//   tip      — 详细说明 + 典型场景（选中命令时展示）
//   example  — 典型用法示例（选中命令时展示）
//   params   — 参数构建器字段
//   doc      — 官方文档链接
// 参考: https://arthas.aliyun.com/en/doc/commands.md
// ─────────────────────────────────────────────────────────────────────────────
const CMDS = [

  { cat: '🖥️ JVM 基础信息', cmds: [
    { id:'dashboard', name:'dashboard', icon:'📊', type:'stream',
      desc:'实时仪表板 — 线程/内存/GC/系统资源一览',
      tip:`每隔5秒刷新，展示线程状态/内存用量/GC频次/CPU负载。\n适用：快速定位 CPU 飙高、内存告警、线程阻塞的第一步。`,
      example:`dashboard\ndashboard -i 2000  # 2s刷新\ndashboard -n 5     # 输出5次退出`,
      doc:`https://arthas.aliyun.com/en/doc/dashboard.html`,
      params:[] },
    { id:'jvm', name:'jvm', icon:'☕', type:'once',
      desc:'JVM 详细信息（版本/编译器/GC/ClassPath）',
      tip:`输出 JVM 运行时信息：JDK版本、JVM参数、GC算法、编译器状态、ClassPath。\n适用：确认生产环境 JVM 配置是否符合预期。`,
      example:`jvm`,
      doc:`https://arthas.aliyun.com/en/doc/jvm.html`,
      params:[] },
    { id:'memory', name:'memory', icon:'🧠', type:'once',
      desc:'内存各区域用量（heap/metaspace/direct...）',
      tip:`详细展示各内存区域的 used/total/max：heap(eden/survivor/old)、non-heap(metaspace)、direct buffer。\n适用：定位内存泄漏区域，判断是堆内还是堆外内存问题。`,
      example:`memory`,
      doc:`https://arthas.aliyun.com/en/doc/memory.html`,
      params:[] },
    { id:'sysprop', name:'sysprop', icon:'📋', type:'once',
      desc:'系统属性 System.getProperties()',
      tip:`读取/设置 Java System.properties。可单独查询某个属性，也可动态修改（如修改日志路径）。\n注意：修改仅影响当前 JVM 实例，重启后失效。`,
      example:`sysprop                    # 列出所有\nsysprop file.encoding      # 查指定属性\nsysprop user.timezone UTC  # 动态修改`,
      doc:`https://arthas.aliyun.com/en/doc/sysprop.html`,
      params:[{k:'key', ph:'属性名（可选，留空=全部）', def:''}] },
    { id:'sysenv', name:'sysenv', icon:'🌍', type:'once',
      desc:'环境变量 System.getenv()',
      tip:`只读，仅查看。适用于确认容器环境变量是否正确注入（K8s ConfigMap/Secret）。`,
      example:`sysenv\nsysenv JAVA_OPTS`,
      doc:`https://arthas.aliyun.com/en/doc/sysenv.html`,
      params:[{k:'key', ph:'变量名（可选，留空=全部）', def:''}] },
    { id:'vmoption', name:'vmoption', icon:'⚙️', type:'once',
      desc:'查看/修改 JVM 运行期参数（如 HeapDumpOnOOM）',
      tip:`查看或动态修改 JVM flag（DiagnosticOptions）。\n常用：开启 OOM 自动 dump、修改 GC 日志。\n注意：并非所有参数支持运行时修改。`,
      example:`vmoption\nvmoption HeapDumpOnOutOfMemoryError\nvmoption HeapDumpOnOutOfMemoryError true`,
      doc:`https://arthas.aliyun.com/en/doc/vmoption.html`,
      params:[{k:'name', ph:'参数名（留空=列出所有）', def:''},{k:'value', ph:'新值（留空=仅查看）', def:''}] },
    { id:'perfcounter', name:'perfcounter', icon:'⚡', type:'once',
      desc:'JVM PerfCounter 计数器（GC次数/编译次数等）',
      tip:`输出 JVM 内部 PerfData 计数器，包含 GC 次数/时间、JIT 编译次数、类加载数量等底层指标。\n适用：metrics-server 不可用时的轻量指标查看。`,
      example:`perfcounter\nperfcounter -d sun.gc`,
      doc:`https://arthas.aliyun.com/en/doc/perfcounter.html`,
      params:[] },
    { id:'version', name:'version', icon:'🏷️', type:'once',
      desc:'Arthas 版本信息',
      tip:`输出当前 Arthas 版本号，用于确认版本兼容性。`,
      example:`version`,
      doc:`https://arthas.aliyun.com/en/doc/version.html`,
      params:[] },
    { id:'session', name:'session', icon:'🔌', type:'once',
      desc:'查看当前 Arthas Session 信息',
      tip:`查看当前 Session 的 sessionId、consumerId、目标 PID 等。`,
      example:`session`,
      doc:`https://arthas.aliyun.com/en/doc/session.html`,
      params:[] },
  ]},

  { cat: '🧵 线程分析', cmds: [
    { id:'thread', name:'thread', icon:'🧵', type:'once',
      desc:'线程列表 + CPU 占用（-n 最忙N个，-b 检测死锁）',
      tip:`输出所有线程或指定线程的状态和 CPU 占用。\n-n N：输出 CPU 最高的前N个线程及堆栈，排查 CPU 飙高的核心命令。\n-b：检测处于 BLOCKED 的线程，定位死锁。\ntid：指定线程ID查看完整调用栈。`,
      example:`thread
thread -n 3
thread 12
thread -b
thread --state BLOCKED`,
      doc:`https://arthas.aliyun.com/en/doc/thread.html`,
      params:[
        {k:'-n', ph:'最忙前N个线程', def:''},
        {k:'tid', ph:'线程 ID（查看具体堆栈）', def:''},
        {k:'--state', ph:'BLOCKED/WAITING/TIMED_WAITING', def:''},
        {k:'-b', ph:'检测死锁', def:'-b', toggle:true},
      ] },
    { id:'thread_all', name:'thread -all', icon:'📋', type:'once',
      desc:'输出所有线程完整堆栈（等同于 jstack）',
      tip:`输出所有线程的完整调用栈，等价于 jstack。\n也可用「🔥 JProfiler → 💾 Dump → 线程 Dump」一键导出并下载。`,
      example:`thread -all`,
      doc:`https://arthas.aliyun.com/en/doc/thread.html`,
      params:[] },
    { id:'thread_block', name:'thread -b', icon:'🔒', type:'once',
      desc:'专项检测死锁/阻塞线程',
      tip:`查找处于 BLOCKED 状态且持有或等待锁的线程，直接定位死锁根因。\n输出格式：阻塞线程 → 持锁线程 的调用链路。`,
      example:`thread -b`,
      doc:`https://arthas.aliyun.com/en/doc/thread.html`,
      params:[] },
  ]},

  { cat: '🔍 类与类加载器', cmds: [
    { id:'sc', name:'sc', icon:'🔍', type:'once',
      desc:'搜索已加载的类（Search Class）',
      tip:`搜索 JVM 中已加载的类，支持通配符。\n-d 显示类的详细信息（继承关系/ClassLoader/字节码来源JAR）。\n适用：确认某个类是否被加载、排查 ClassNotFound / 类冲突。`,
      example:`sc *UserService*\nsc -d com.example.Demo\nsc -d -f com.example.Demo`,
      doc:`https://arthas.aliyun.com/en/doc/sc.html`,
      params:[
        {k:'pattern', ph:'类名，支持通配符 *Service*', def:'', req:true},
        {k:'-d', ph:'显示类详情', def:'-d', toggle:true},
        {k:'-f', ph:'显示字段信息', def:'', toggle:true},
        {k:'-x', ph:'字段展开层级', def:'2'},
      ] },
    { id:'sm', name:'sm', icon:'🔎', type:'once',
      desc:'搜索类的方法（Search Method）',
      tip:`搜索已加载类中的方法。-d 显示方法签名/返回类型/参数类型/注解。\n适用：watch/trace 之前确认方法名和签名，避免拼写错误导致监控无效。`,
      example:`sm com.example.UserService\nsm com.example.UserService get*\nsm -d com.example.UserService login`,
      doc:`https://arthas.aliyun.com/en/doc/sm.html`,
      params:[
        {k:'class', ph:'类名', def:'', req:true},
        {k:'method', ph:'方法名（支持通配符）', def:''},
        {k:'-d', ph:'显示方法详情', def:'-d', toggle:true},
      ] },
    { id:'classloader', name:'classloader', icon:'📦', type:'once',
      desc:'类加载器统计（层级/数量/加载类数）',
      tip:`列出所有 ClassLoader 的层级关系、已加载类的数量。\n-c hash 可查看指定 ClassLoader 加载的类。\n适用：Spring Boot fat jar、热部署框架的类加载问题排查。`,
      example:`classloader\nclassloader -t\nclassloader -c 3d4eac69`,
      doc:`https://arthas.aliyun.com/en/doc/classloader.html`,
      params:[
        {k:'-t', ph:'树形展示继承关系', def:'-t', toggle:true},
        {k:'-l', ph:'列出所有 ClassLoader', def:'', toggle:true},
        {k:'-c', ph:'指定 ClassLoader hash', def:''},
      ] },
    { id:'jad', name:'jad', icon:'📄', type:'once',
      desc:'反编译类源码（可指定方法）',
      tip:`将运行中字节码反编译为 Java 源码，是确认代码是否正确部署的利器。\n可指定方法名，只反编译某个方法。`,
      example:`jad com.example.UserService\njad com.example.UserService login\njad --source-only com.example.UserService`,
      doc:`https://arthas.aliyun.com/en/doc/jad.html`,
      params:[
        {k:'class', ph:'全限定类名', def:'', req:true},
        {k:'method', ph:'方法名（可选，留空=整个类）', def:''},
      ] },
    { id:'dump', name:'dump', icon:'💾', type:'once',
      desc:'导出类字节码 .class 文件',
      tip:`将 JVM 中运行的类字节码 dump 到本地文件，可用于反编译分析或与源码比对。\n提示：dump 后的 .class 可用「📂 文件下载」标签下载到本地。`,
      example:`dump com.example.UserService\ndump -d /tmp com.example.Demo.*`,
      doc:`https://arthas.aliyun.com/en/doc/dump.html`,
      params:[
        {k:'class', ph:'全限定类名，支持通配符', def:'', req:true},
        {k:'-d', ph:'输出目录', def:'/tmp'},
      ] },
    { id:'mc', name:'mc', icon:'🔨', type:'once',
      desc:'内存编译 .java 为 .class（配合 retransform）',
      tip:`在 JVM 内存中直接编译 .java 文件，无需在 Pod 外安装 JDK。\n热修复工作流：jad 反编译 → 修改源码 → mc 编译 → retransform 热加载。`,
      example:`mc /tmp/UserService.java\nmc -d /tmp /tmp/UserService.java`,
      doc:`https://arthas.aliyun.com/en/doc/mc.html`,
      params:[
        {k:'file', ph:'/tmp/YourClass.java', def:'', req:true},
        {k:'-d', ph:'输出目录', def:'/tmp'},
      ] },
    { id:'retransform', name:'retransform', icon:'♻️', type:'once',
      desc:'热重载 .class 文件（生产热修复首选）',
      tip:`将 .class 文件热加载到 JVM 中，替换正在运行的类实现，无需重启。\n注意：不能新增/删除方法，不能修改字段类型。`,
      example:`retransform /tmp/UserService.class`,
      doc:`https://arthas.aliyun.com/en/doc/retransform.html`,
      params:[{k:'file', ph:'/tmp/YourClass.class', def:'', req:true}] },
    { id:'redefine', name:'redefine', icon:'🔧', type:'once',
      desc:'重新定义类（旧版热修复，推荐用 retransform）',
      tip:`旧版热修复命令，推荐优先使用 retransform（更安全，不能与 retransform 混用）。`,
      example:`redefine /tmp/UserService.class`,
      doc:`https://arthas.aliyun.com/en/doc/redefine.html`,
      params:[{k:'file', ph:'/tmp/YourClass.class', def:'', req:true}] },
  ]},

  { cat: '👁 方法监控与追踪', cmds: [
    { id:'watch', name:'watch', icon:'👁', type:'stream',
      desc:'观察方法调用：入参/返回值/异常（每次调用实时输出）',
      tip:`最常用的诊断命令，每次方法被调用时实时输出入参/返回值/异常。\nOGNL表达式：{params}参数 {returnObj}返回值 {throwExp}异常 params[0]第一个参数\n-b 调用前观察，-e 仅在异常时输出，-x 展开层级（建议2~3）`,
      example:`watch com.example.UserService login "{params,returnObj,throwExp}" -x 2 -n 5\nwatch com.example.OrderService * "{params[0]}" -b\nwatch com.example.Demo * "{params}" -e`,
      doc:`https://arthas.aliyun.com/en/doc/watch.html`,
      params:[
        {k:'class', ph:'类名（全限定或通配符）', def:'', req:true},
        {k:'method', ph:'方法名', def:'', req:true},
        {k:'expr', ph:'OGNL表达式', def:'"{params,returnObj,throwExp}"'},
        {k:'-x', ph:'对象展开层级', def:'2'},
        {k:'-n', ph:'最多观察次数', def:'5'},
        {k:'-b', ph:'方法调用前观察', def:'', toggle:true},
        {k:'-e', ph:'方法异常时观察', def:'', toggle:true},
      ] },
    { id:'trace', name:'trace', icon:'🔬', type:'stream',
      desc:'追踪方法调用树及各节点耗时（找性能瓶颈）',
      tip:`输出方法调用的完整调用树，每个子调用的耗时一目了然，快速定位性能瓶颈。\n--skipJDKMethod false 包含 JDK 内部方法调用。\n注意：对被追踪方法有一定性能影响，建议限制 -n 次数。`,
      example:`trace com.example.UserService login -n 5\ntrace com.example.OrderService processOrder --skipJDKMethod false`,
      doc:`https://arthas.aliyun.com/en/doc/trace.html`,
      params:[
        {k:'class', ph:'类名', def:'', req:true},
        {k:'method', ph:'方法名', def:'', req:true},
        {k:'-n', ph:'追踪次数', def:'5'},
        {k:'--skipJDKMethod', ph:'跳过 JDK 方法', def:'', toggle:true},
      ] },
    { id:'monitor', name:'monitor', icon:'📈', type:'stream',
      desc:'统计方法 QPS/RT/成功率（持续监控，按周期输出）',
      tip:`按统计周期输出方法的调用次数(QPS)/平均耗时(RT)/成功率/失败次数。\n不侵入方法内部，性能影响极低，适合长时间挂载监控。\n适用：接口调用量异常、响应时间波动分析。`,
      example:`monitor com.example.UserService login -c 5\nmonitor com.example.OrderService * -c 10 -n 6`,
      doc:`https://arthas.aliyun.com/en/doc/monitor.html`,
      params:[
        {k:'class', ph:'类名', def:'', req:true},
        {k:'method', ph:'方法名', def:'', req:true},
        {k:'-c', ph:'统计周期（秒）', def:'5'},
        {k:'-n', ph:'统计轮次', def:'10'},
      ] },
    { id:'stack', name:'stack', icon:'📚', type:'stream',
      desc:'打印方法被调用时的调用栈（谁调了我？）',
      tip:`每次目标方法被调用时，打印完整的调用链（从哪里调用的）。\n与 trace 的区别：trace 向下追踪被调方法，stack 向上追踪调用者。\n适用：定位某个方法的触发来源，如接口从哪条链路进来的。`,
      example:`stack com.example.UserService login -n 5\nstack java.lang.Thread sleep`,
      doc:`https://arthas.aliyun.com/en/doc/stack.html`,
      params:[
        {k:'class', ph:'类名', def:'', req:true},
        {k:'method', ph:'方法名', def:'', req:true},
        {k:'-n', ph:'最多打印次数', def:'5'},
      ] },
    { id:'tt', name:'tt', icon:'⏱', type:'stream',
      desc:'时间隧道：记录方法调用历史，可重放/对比入参',
      tip:`记录方法每次调用的入参/返回值/异常/耗时，可事后查看和重放。\n-t 开始记录，-l 列出历史，-i index 查看详情，-p -i index 重放。\n适用：偶发性错误复现、参数对比分析。`,
      example:`tt -t com.example.UserService login -n 10\ntt -l\ntt -i 1000\ntt -p -i 1000`,
      doc:`https://arthas.aliyun.com/en/doc/tt.html`,
      params:[
        {k:'action', ph:'-t class method（记录）/ -l（列表）/ -i N（详情）/ -p -i N（重放）', def:''},
        {k:'class', ph:'类名（-t 时用）', def:''},
        {k:'method', ph:'方法名（-t 时用）', def:''},
        {k:'-n', ph:'最大记录次数', def:'5'},
      ] },
  ]},

  { cat: '🧮 OGNL & 变量操作', cmds: [
    { id:'ognl', name:'ognl', icon:'🧮', type:'once',
      desc:'执行任意 OGNL 表达式（读写静态变量/调用方法）',
      tip:`在运行中的 JVM 执行 OGNL 表达式，可读取/修改静态变量、调用任意方法。\n语法：@Class@field 读取静态字段，@Class@method(args) 调用静态方法。\n-c 指定 ClassLoader hash（多 ClassLoader 环境必须指定）。`,
      example:`ognl "@java.lang.System@currentTimeMillis()"\nognl "@com.example.Config@instance.timeout"\nognl "#conf=@com.example.Config@instance, #conf.timeout=3000"`,
      doc:`https://arthas.aliyun.com/en/doc/ognl.html`,
      params:[
        {k:'expr', ph:'"@java.lang.System@currentTimeMillis()"', def:'', req:true},
        {k:'-x', ph:'结果展开层级', def:'3'},
        {k:'-c', ph:'指定 ClassLoader hash', def:''},
      ] },
    { id:'getstatic', name:'getstatic', icon:'📌', type:'once',
      desc:'获取静态字段值（快捷方式）',
      tip:`getstatic 是 ognl 读取静态字段的快捷命令。\n适用：快速查看单例对象的状态、配置值等。`,
      example:`getstatic com.example.Config timeout\ngetstatic -x 2 com.example.Config instance`,
      doc:`https://arthas.aliyun.com/en/doc/getstatic.html`,
      params:[
        {k:'class', ph:'全限定类名', def:'', req:true},
        {k:'field', ph:'字段名', def:'', req:true},
        {k:'-x', ph:'展开层级', def:'2'},
      ] },
    { id:'vmtool', name:'vmtool', icon:'🛠', type:'once',
      desc:'获取 JVM 堆中对象实例（-a getInstances）',
      tip:`直接从堆内存中获取指定类的所有实例对象，无需 heapdump。还支持强制触发 GC。\n适用：检查单例是否真的单例、查看缓存内容、强制 GC 后观察内存变化。\n注意：对象数量大时可能有性能影响，建议用 -l 限制数量。`,
      example:`vmtool --action getInstances --className com.example.UserService -x 2\nvmtool --action getInstances --className com.example.Cache -l 5 -x 3\nvmtool --action forceGc`,
      doc:`https://arthas.aliyun.com/en/doc/vmtool.html`,
      params:[
        {k:'--action', ph:'getInstances / forceGc', def:'getInstances', req:true},
        {k:'--className', ph:'全限定类名', def:''},
        {k:'-x', ph:'结果展开层级', def:'2'},
        {k:'-l', ph:'最大实例数', def:'10'},
      ] },
    { id:'logger', name:'logger', icon:'📝', type:'once',
      desc:'查看/动态修改 Logger 日志级别（无需重启）',
      tip:`无需重启 JVM，动态修改 Logback/Log4j 的日志级别。\n生产排查时临时开启 DEBUG 日志，排查完后改回 INFO，不影响服务运行。`,
      example:`logger\nlogger --name ROOT\nlogger --name com.example --level DEBUG\nlogger --name com.example --level INFO`,
      doc:`https://arthas.aliyun.com/en/doc/logger.html`,
      params:[
        {k:'--name', ph:'Logger 名称（如 com.example）', def:''},
        {k:'--level', ph:'新日志级别：DEBUG/INFO/WARN/ERROR', def:''},
      ] },
  ]},

  { cat: '🔥 性能分析', cmds: [
    { id:'p_start', name:'profiler start', icon:'▶️', type:'profiler',
      desc:'async-profiler: 开始采样（支持 cpu/alloc/lock/wall）',
      tip:`async-profiler 低开销采样，所有 JDK 版本可用。\n推荐使用右侧「🔥 JProfiler」面板操作，支持可视化配置和一键下载。\n直接命令适合在 Arthas 终端快速操作。`,
      example:`profiler start\nprofiler start --event alloc\nprofiler start --event lock`,
      doc:`https://arthas.aliyun.com/en/doc/profiler.html`,
      params:[{k:'--event', ph:'事件：cpu/alloc/lock/wall/itimer', def:'cpu'}] },
    { id:'p_status', name:'profiler status', icon:'📊', type:'once',
      desc:'查看当前 async-profiler 采样状态',
      tip:`查看当前采样事件类型和已运行时长。`,
      example:`profiler status`,
      doc:`https://arthas.aliyun.com/en/doc/profiler.html`,
      params:[] },
    { id:'p_getSamples', name:'profiler getSamples', icon:'🔢', type:'once',
      desc:'获取已采集的样本数量',
      tip:`查看当前已采集的样本数，判断采样是否正常进行。`,
      example:`profiler getSamples`,
      doc:`https://arthas.aliyun.com/en/doc/profiler.html`,
      params:[] },
    { id:'p_list', name:'profiler list', icon:'📋', type:'once',
      desc:'列出当前平台支持的所有采样事件',
      tip:`不同 OS/内核版本支持的事件不同，先用此命令确认可用事件。`,
      example:`profiler list`,
      doc:`https://arthas.aliyun.com/en/doc/profiler.html`,
      params:[] },
    { id:'p_stop_html', name:'profiler stop', icon:'⏹', type:'profiler',
      desc:'停止采样 → 生成 HTML 火焰图',
      tip:`停止采样并生成报告文件。推荐使用「🔥 JProfiler」面板操作，支持自动下载。`,
      example:`profiler stop\nprofiler stop --format html --file /tmp/profiler.html\nprofiler stop --format jfr  --file /tmp/profiler.jfr`,
      doc:`https://arthas.aliyun.com/en/doc/profiler.html`,
      params:[
        {k:'--format', ph:'html/jfr/collapsed/md', def:'html'},
        {k:'--file', ph:'输出路径', def:'/tmp/profiler.html'},
      ] },
    { id:'jfr_start', name:'jfr start', icon:'📊', type:'once',
      desc:'JDK JFR 录制启动（需 JDK 8u262+ 或 JDK 11+）',
      tip:`JDK 原生 Flight Recorder，需要 JDK 8u262+ 或 JDK 11+。推荐使用右侧「🔥 JProfiler → 📊 JDK JFR」面板操作。\n-d 指定录制时长后自动停止，-s 选择录制配置。`,
      example:`jfr start -n myRec -s default -d 60s -f /tmp/my.jfr\njfr status -n myRec\njfr stop -n myRec`,
      doc:`https://arthas.aliyun.com/en/doc/jfr.html`,
      params:[
        {k:'-n', ph:'录制名称', def:'arthas-jfr'},
        {k:'-s', ph:'配置: default / profile', def:'default'},
        {k:'-d', ph:'录制时长，如 60s', def:'60s'},
        {k:'-f', ph:'输出文件路径', def:'/tmp/arthas.jfr'},
      ] },
    { id:'jfr_status', name:'jfr status', icon:'ℹ️', type:'once',
      desc:'查看 JFR 录制状态',
      tip:`查看指定录制任务的状态（running/stopped）。`,
      example:`jfr status -n arthas-jfr`,
      doc:`https://arthas.aliyun.com/en/doc/jfr.html`,
      params:[{k:'-n', ph:'录制名称', def:'arthas-jfr'}] },
    { id:'jfr_stop', name:'jfr stop', icon:'⏹', type:'once',
      desc:'停止 JFR 录制（文件自动保存）',
      tip:`停止录制，文件写入启动时指定的路径。`,
      example:`jfr stop -n arthas-jfr`,
      doc:`https://arthas.aliyun.com/en/doc/jfr.html`,
      params:[
        {k:'-n', ph:'录制名称', def:'arthas-jfr'},
        {k:'-f', ph:'另存路径（可选）', def:''},
      ] },
    { id:'jfr_dump', name:'jfr dump', icon:'💾', type:'once',
      desc:'导出 JFR 录制（录制继续运行）',
      tip:`在录制运行期间导出当前数据，录制本身不停止。`,
      example:`jfr dump -n arthas-jfr -f /tmp/dump.jfr`,
      doc:`https://arthas.aliyun.com/en/doc/jfr.html`,
      params:[
        {k:'-n', ph:'录制名称', def:'arthas-jfr'},
        {k:'-f', ph:'输出文件路径', def:'/tmp/dump.jfr'},
      ] },
    { id:'heapdump', name:'heapdump', icon:'🗂', type:'once',
      desc:'导出 Heap Dump（OOM/内存泄漏分析，会触发 STW）',
      tip:`导出堆内存快照，用于 MAT/JVisualVM 分析。\n--live 只导出存活对象，可大幅减小文件体积。\n警告：会触发 Full GC 并暂停 JVM（STW），大堆可能需要数分钟，生产环境慎用。\n推荐使用右侧「💾 Dump」面板操作，支持自动下载。`,
      example:`heapdump /tmp/heap.hprof\nheapdump --live /tmp/heap-live.hprof`,
      doc:`https://arthas.aliyun.com/en/doc/heapdump.html`,
      params:[
        {k:'file', ph:'输出路径', def:'/tmp/heap.hprof'},
        {k:'--live', ph:'仅 live 对象（减小文件体积）', def:'--live', toggle:true},
      ] },
  ]},

  { cat: '🔧 工具命令', cmds: [
    { id:'mbean', name:'mbean', icon:'🔧', type:'once',
      desc:'查看/订阅 JMX MBean 属性（线程池/连接池等）',
      tip:`通过 JMX 查看或订阅 MBean 属性，适合监控连接池/线程池/GC 等标准 JMX 指标。\n-i ms 按毫秒间隔持续输出。\n常用：java.lang:type=Memory  java.lang:type=Threading  Catalina:type=ThreadPool`,
      example:`mbean java.lang:type=Memory\nmbean java.lang:type=Threading\nmbean -i 1000 java.lang:type=GarbageCollector,*`,
      doc:`https://arthas.aliyun.com/en/doc/mbean.html`,
      params:[
        {k:'mbean-pattern', ph:'java.lang:type=Memory', def:'java.lang:type=Memory'},
        {k:'attribute-pattern', ph:'属性名（留空=全部）', def:''},
        {k:'-i', ph:'订阅间隔 ms（持续监控）', def:''},
      ] },
    { id:'options', name:'options', icon:'⚙️', type:'once',
      desc:'查看/修改 Arthas 全局开关（如 save-result）',
      tip:`查看或修改 Arthas 全局配置开关，如是否保存命令结果到文件。`,
      example:`options\noptions save-result true`,
      doc:`https://arthas.aliyun.com/en/doc/options.html`,
      params:[
        {k:'name', ph:'选项名（留空=列出全部）', def:''},
        {k:'value', ph:'新值（留空=仅查看）', def:''},
      ] },
    { id:'echo', name:'echo', icon:'📢', type:'once',
      desc:'打印文本（调试脚本用）',
      tip:`在控制台打印字符串，用于批量脚本中添加分隔符/注释。`,
      example:`echo hello arthas`,
      doc:`https://arthas.aliyun.com/en/doc/echo.html`,
      params:[{k:'text', ph:'要打印的内容', def:'hello arthas', req:true}] },
    { id:'cat', name:'cat', icon:'📖', type:'once',
      desc:'打印文件内容（如配置文件）',
      tip:`在 Arthas 会话中读取 Pod 内文件内容，也可用「📂 文件下载」标签浏览下载。`,
      example:`cat /proc/version\ncat /app/config/application.yml`,
      doc:`https://arthas.aliyun.com/en/doc/cat.html`,
      params:[{k:'file', ph:'文件路径', def:'', req:true}] },
    { id:'pwd', name:'pwd', icon:'📂', type:'once',
      desc:'打印 Arthas 当前工作目录',
      tip:`输出 Arthas 进程的当前工作目录（通常是 JVM 启动目录）。`,
      example:`pwd`,
      doc:`https://arthas.aliyun.com/en/doc/pwd.html`,
      params:[] },
    { id:'history', name:'history', icon:'🕐', type:'once',
      desc:'打印命令执行历史',
      tip:`输出最近执行的命令历史，方便回顾和重复执行。`,
      example:`history\nhistory 20`,
      doc:`https://arthas.aliyun.com/en/doc/history.html`,
      params:[{k:'n', ph:'最近 N 条', def:'20'}] },
  ]},
];

// 记录各分组折叠状态（默认全展开）
const _catCollapsed = {};

function renderCmdPal(filter='') {
  const el = document.getElementById('cmdPal');
  const fl = filter.toLowerCase();
  let html = '';
  for(let gi = 0; gi < CMDS.length; gi++) {
    const cat  = CMDS[gi];
    const gid  = `cg${gi}`;
    const cmds = fl
      ? cat.cmds.filter(c => c.name.includes(fl) || c.desc.toLowerCase().includes(fl))
      : cat.cmds;
    if(!cmds.length) continue;
    const collapsed = !fl && _catCollapsed[gid];  // 搜索时强制展开
    const arrow = collapsed ? '▶' : '▼';
    html += `<div class="cp-cat-hd" data-gid="${gid}" onclick="toggleCmdCat('${gid}')">
      <span class="cp-cat-arrow">${arrow}</span>${cat.cat}
      <span class="cp-cat-cnt">${cmds.length}</span>
    </div>`;
    if(!collapsed) {
      html += `<div class="cp-cat-body" id="${gid}">`;
      for(const cmd of cmds) {
        const bt = cmd.type==='stream'?'badge-stream':cmd.type==='profiler'?'badge-prof':'badge-once';
        const bl = cmd.type==='stream'?'持续':cmd.type==='profiler'?'prof':'once';
        html += `<div class="cp-cmd" data-id="${cmd.id}" onclick="selCmd('${cmd.id}')">
          <span class="cp-ci">${cmd.icon}</span>
          <div><div class="cp-cn">${esc(cmd.name)}<span class="cp-badge ${bt}">${bl}</span></div>
          <div class="cp-cd">${esc(cmd.desc)}</div></div>
        </div>`;
      }
      html += `</div>`;
    }
  }
  el.innerHTML = html || '<div style="color:var(--tx3);padding:10px;font-size:11px">无匹配命令</div>';
}

function toggleCmdCat(gid) {
  _catCollapsed[gid] = !_catCollapsed[gid];
  // Toggle DOM directly — no full rebuild needed
  const body = document.getElementById(gid);
  const hdr  = document.querySelector(`[data-gid="${gid}"]`);
  if(body) body.style.display = _catCollapsed[gid] ? 'none' : 'block';
  if(hdr) {
    const arrow = hdr.querySelector('.cp-cat-arrow');
    if(arrow) arrow.textContent = _catCollapsed[gid] ? '▶' : '▼';
  }
}

let _filterTimer = null;
function filterCmds(v) {
  clearTimeout(_filterTimer);
  _filterTimer = setTimeout(() => renderCmdPal(v), 150);
}

function hardenCommandFieldAutofill(el, onClear, strictSearch) {
  const clearIfUnexpected = (el, onClear, strictSearch) => {
    const v = (el.value || '').trim();
    const low = v.toLowerCase();
    const looksLikeLogin = low === 'admin' || low === 'administrator' || (strictSearch && v.includes('@'));
    if (looksLikeLogin) {
      el.value = '';
      if (typeof onClear === 'function') onClear(el);
    }
  };
  if (!el) return;
  el.setAttribute('autocomplete', 'off');
  el.setAttribute('autocorrect', 'off');
  el.setAttribute('autocapitalize', 'off');
  el.setAttribute('spellcheck', 'false');
  el.setAttribute('data-lpignore', 'true');
  el.setAttribute('data-1p-ignore', 'true');
  el.setAttribute('data-bwignore', 'true');
  el.setAttribute('data-form-type', 'other');
  el.removeAttribute('name');
  clearIfUnexpected(el, onClear, strictSearch);
  [120, 350, 800].forEach(delay => setTimeout(() => clearIfUnexpected(el, onClear, strictSearch), delay));
  if (el.dataset.noAutofillReady) return;
  el.dataset.noAutofillReady = '1';
  el.readOnly = true;
  let ready = false;
  const enable = () => { if (!ready) { ready = true; el.readOnly = false; } };
  const guard = setInterval(() => {
    clearIfUnexpected(el, onClear, strictSearch);
    if (ready) clearInterval(guard);
  }, 200);
  setTimeout(enable, 3000);
  el.addEventListener('focus', enable, { once: true });
  el.addEventListener('mousedown', enable, { once: true });
}
function hardenCommandSearchAutofill() {
  hardenCommandFieldAutofill(document.getElementById('cmdSearch'), () => filterCmds(''), true);
  hardenCommandFieldAutofill(document.getElementById('cmdTa'), (el) => autoResize(el), false);
}
function findCmd(id) { for(const c of CMDS) { const f=c.cmds.find(x=>x.id===id); if(f) return f; } return null; }

function selCmd(id) {
  document.querySelectorAll('.cp-cmd').forEach(e => e.classList.toggle('active', e.dataset.id===id));
  _selCmd = findCmd(id); if(!_selCmd) return;
  const bldr = document.getElementById('cmdBldr');

  // Build tip/example section
  let infoHtml = '';
  if(_selCmd.tip || _selCmd.example) {
    infoHtml = `<div class="bldr-tip">`;
    if(_selCmd.tip) {
      infoHtml += `<div class="bldr-tip-text">${esc(_selCmd.tip).replace(/\\n/g,'<br>')}</div>`;
    }
    if(_selCmd.example) {
      infoHtml += `<div class="bldr-tip-ex"><span class="bldr-tip-exlbl">示例</span><pre class="bldr-tip-code">${esc(_selCmd.example)}</pre></div>`;
    }
    if(_selCmd.doc) {
      infoHtml += `<a class="bldr-tip-doc" href="${esc(_selCmd.doc)}" target="_blank">📖 官方文档 ↗</a>`;
    }
    infoHtml += `</div>`;
  }

  if(_selCmd.params && _selCmd.params.length) {
    bldr.style.display = 'block';
    document.getElementById('bldrLbl').textContent = `${_selCmd.icon} ${_selCmd.name}`;
    document.getElementById('bldrFlds').innerHTML =
      infoHtml +
      _selCmd.params.map((p,i) => `<div class="bldr-f"><label>${esc(p.k)}${p.req?' *':''}</label>
        ${p.toggle
          ? `<select id="bf${i}"><option value="">${p.k} 关</option><option value="${esc(p.def)}" selected>${p.k} 开</option></select>`
          : `<input id="bf${i}" type="text" value="${esc(p.def||'')}" placeholder="${esc(p.ph||'')}" autocomplete="off" autocorrect="off" autocapitalize="off" spellcheck="false" data-lpignore="true" data-1p-ignore="true" data-bwignore="true" data-form-type="other">`
        }</div>`).join('') +
      `<button class="bldr-send" onclick="buildAndRun()">▶ 执行</button>`;
    _selCmd.params.forEach((p,i) => {
      if (!p.toggle) hardenCommandFieldAutofill(document.getElementById(`bf${i}`), null, false);
    });
  } else {
    bldr.style.display = infoHtml ? 'block' : 'none';
    if(infoHtml) {
      document.getElementById('bldrLbl').textContent = `${_selCmd.icon} ${_selCmd.name}`;
      document.getElementById('bldrFlds').innerHTML = infoHtml +
        `<button class="bldr-send" onclick="buildAndRun()">▶ 执行</button>`;
    }
    document.getElementById('cmdTa').value = _selCmd.name;
    autoResize(document.getElementById('cmdTa'));
  }
  const runBtn = document.getElementById('runBtn');
  if (runBtn) runBtn.disabled = !syncArthasConsoleFromFocus();
}

function buildAndRun() {
  if(!_selCmd) return;
  let parts = [_selCmd.name];
  _selCmd.params.forEach((p,i) => {
    const v = (document.getElementById(`bf${i}`)?.value||'').trim();
    if(!v) return;
    if(p.toggle) { parts.push(v); return; }
    const pos = ['class','method','pattern','expr','mbean','file','key','action'];
    if(pos.includes(p.k)) parts.push(v); else parts.push(`${p.k} ${v}`);
  });
  document.getElementById('cmdTa').value = parts.join(' ');
  autoResize(document.getElementById('cmdTa'));
  runCmd();
}

function handleKey(e) {
  if(e.key==='Enter' && !e.shiftKey) { e.preventDefault(); runCmd(); return; }
  if(e.key==='ArrowUp') { e.preventDefault(); navHist(-1); }
  if(e.key==='ArrowDown') { e.preventDefault(); navHist(1); }
}
function navHist(d) {
  _histIdx = Math.max(-1, Math.min(_cmdHist.length-1, _histIdx+d));
  const ta = document.getElementById('cmdTa');
  ta.value = _histIdx>=0 ? _cmdHist[_cmdHist.length-1-_histIdx] : '';
  autoResize(ta);
}
let _resizeTimer = null;
function autoResize(ta) {
  // Debounce: only measure scrollHeight after typing pauses
  clearTimeout(_resizeTimer);
  _resizeTimer = setTimeout(() => {
    ta.style.height = 'auto';
    ta.style.height = Math.min(ta.scrollHeight, 96) + 'px';
  }, 50);
}

async function runCmd() {
  if(window.ConnectionGuard && !ConnectionGuard.guard('console')) return;
  if(!syncArthasConsoleFromFocus()) { toast('请先连接 Arthas','warn'); return; }
  const ta = document.getElementById('cmdTa'); const command = ta.value.trim(); if(!command) return;
  ta.value=''; autoResize(ta); _cmdHist.push(command); _histIdx=-1;
  saveCommandConsoleState(_currentConnId);
  oSep(); clog(esc(command), 'cmd');
  // 根据命令类型选择执行方式：stream 命令实时输出，once 命令一次性返回
  const streamCmds = ['dashboard','watch','trace','monitor','stack','tt'];
  const cmdBase = command.trim().split(/\s+/)[0];
  if(streamCmds.includes(cmdBase)) {
    await runStream(command);
  } else {
    await runOnce(command);
  }
}

async function runOnce(command) {
  const runConnId = activeCommandConnId();
  const runTarget = { ..._ap };
  document.getElementById('runBtn').disabled = true;
  try {
    const r = await fetch(`${API}/arthas/exec`, {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({...runTarget, command, connection_id: runConnId, timeout_ms: 60000})});
    const d = await r.json();
    if (!isActiveCommandConnection(runConnId)) return;
    if(!d.state && d.error) { clog('✗ ' + esc(d.error), 'err'); }
    else { renderRes(d); }
  } catch(e) {
    if (isActiveCommandConnection(runConnId)) clog('✗ ' + esc(e.message), 'err');
  } finally {
    if (isActiveCommandConnection(runConnId)) document.getElementById('runBtn').disabled = false;
  }
}

async function runStream(command) {
  const runConnId = activeCommandConnId();
  const runTarget = { ..._ap };
  document.getElementById('runBtn').disabled = true;
  document.getElementById('btnStop').style.display = 'inline-flex';
  if(!_sid || _sidConnId !== runConnId) {
    try {
      const r = await fetch(`${API}/arthas/session/create`, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(runTarget)});
      const d = await r.json();
      if (!isActiveCommandConnection(runConnId)) return;
      if(d.state !== 'SUCCEEDED') { clog('✗ Session 创建失败: ' + esc(JSON.stringify(d)), 'err'); stopPoll(); return; }
      _sid = d.sessionId; _cid = d.consumerId; _sidConnId = runConnId;
      clog(`Session: ${d.sessionId}`, 'dim');
    } catch(e) {
      if (isActiveCommandConnection(runConnId)) clog('✗ ' + esc(e.message), 'err');
      stopPoll();
      return;
    }
  }
  try {
    const r = await fetch(`${API}/arthas/session/exec`, {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({...runTarget, command, session_id: _sid})});
    const d = await r.json();
    if (!isActiveCommandConnection(runConnId)) return;
    if(d.state === 'FAILED') { clog('✗ ' + esc(d.message), 'err'); stopPoll(); return; }
  } catch(e) {
    if (isActiveCommandConnection(runConnId)) clog('✗ ' + esc(e.message), 'err');
    stopPoll();
    return;
  }
  _polling = true; let empty = 0;
  const poll = async () => {
    if(!_polling || !isActiveCommandConnection(runConnId)) return;
    try {
      const r = await fetch(`${API}/arthas/session/pull`, {method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({...runTarget, session_id: _sid, consumer_id: _cid})});
      if (!isActiveCommandConnection(runConnId)) return;
      const d = await r.json(); let has = false;
      for(const res of d.body?.results||[]) {
        if(['input_status','welcome','message'].includes(res.type)) continue;
        renderRes({state:'SUCCEEDED', body:{results:[res]}}); has = true;
      }
      if(!has) empty++;
      if(empty < 60 && _polling) _pollTimer = setTimeout(poll, 1500); else stopPoll();
    } catch { stopPoll(); }
  };
  _pollTimer = setTimeout(poll, 1000);
}

function stopPoll() {
  _polling = false; if(_pollTimer) { clearTimeout(_pollTimer); _pollTimer = null; }
  _sidConnId = null;
  document.getElementById('runBtn').disabled = false;
  document.getElementById('btnStop').style.display = 'none';
}

async function interruptCmd() {
  _polling = false; if(_pollTimer) { clearTimeout(_pollTimer); _pollTimer = null; }
  if(_sid && _ap) try {
    await fetch(`${API}/arthas/session/interrupt`, {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({..._ap, session_id: _sid})});
  } catch {}
  stopPoll(); clog('── 命令已中断 ──', 'dim');
}

// ── Arthas result rendering ────────────────────────────────────────────────────
// ─────────────────────────────────────────────────────────────────────────────
// Arthas 命令结果渲染器
// 每种 result type 对应官方文档的字段结构，渲染为可读的 HTML
// ─────────────────────────────────────────────────────────────────────────────

/** 通用工具 */
function toggleResultCollapse(id) {
  const wrap = document.getElementById(id);
  if (!wrap) return;
  const open = wrap.classList.toggle('open');
  const head = wrap.querySelector('.r-coll-h');
  if (head) head.setAttribute('aria-expanded', open ? 'true' : 'false');
}

const R = {
  // key-value 行
  kv: (k, v, vCls='') =>
    `<div class="r-kv"><span class="r-k">${esc(k)}</span><span class="r-v ${vCls}">${v}</span></div>`,
  // 表格
  table: (cols, rows) => {
    const ths = cols.map(c => `<th>${esc(c)}</th>`).join('');
    const trs = rows.map(row =>
      `<tr>${row.map(c => `<td>${c}</td>`).join('')}</tr>`
    ).join('');
    return `<table class="r-tbl"><thead><tr>${ths}</tr></thead><tbody>${trs}</tbody></table>`;
  },
  // 代码块
  code: (text, lang='java') =>
    `<pre class="o-code r-code">${esc(String(text||''))}</pre>`,
  // 标签
  badge: (txt, color='#4ade80') =>
    `<span style="background:${color}22;color:${color};border:1px solid ${color}44;border-radius:3px;padding:1px 6px;font-size:10px;font-weight:600">${esc(String(txt))}</span>`,
  // 状态颜色
  stateColor: s => ({
    RUNNABLE:'#4ade80', BLOCKED:'#f87171', WAITING:'#fb923c',
    TIMED_WAITING:'#fbbf24', NEW:'#94a3b8', TERMINATED:'#94a3b8'
  }[s] || '#94a3b8'),
  // 用量 bar
  bar: (used, total, max) => {
    const pct = total > 0 ? Math.round(used/total*100) : 0;
    const color = pct > 90 ? '#f87171' : pct > 75 ? '#fb923c' : '#4ade80';
    const usedStr = R.fmtBytes(used), totalStr = R.fmtBytes(total);
    return `<div class="r-bar-wrap">
      <div class="r-bar" style="width:${pct}%;background:${color}"></div>
      <span class="r-bar-lbl">${usedStr} / ${totalStr} (${pct}%)</span>
    </div>`;
  },
  fmtBytes: b => {
    if(!b || b < 0) return '—';
    if(b < 1024) return b + 'B';
    if(b < 1048576) return (b/1024).toFixed(1) + 'K';
    if(b < 1073741824) return (b/1048576).toFixed(1) + 'M';
    return (b/1073741824).toFixed(2) + 'G';
  },
  fmtMs: ms => ms > 1000 ? (ms/1000).toFixed(2)+'s' : ms+'ms',
  // 折叠块
  collapsible: (header, body, open=false) => {
    const id = 'rc_' + Math.random().toString(36).slice(2);
    const bodyId = `${id}_body`;
    return `<div class="r-coll ${open?'open':''}" id="${id}">
      <div class="r-coll-h" role="button" tabindex="0" aria-expanded="${open?'true':'false'}" aria-controls="${bodyId}" onclick="toggleResultCollapse('${id}')" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();toggleResultCollapse('${id}')}">
        <span class="r-coll-arr">▶</span>${header}</div>
      <div class="r-coll-b" id="${bodyId}">${body}</div>
    </div>`;
  },
};

/** 各命令专属渲染函数 */
const RENDERERS = {

  // ── dashboard ────────────────────────────────────────────────────────────
  dashboard(r) {
    let html = '';
    // Threads table
    const threads = r.threads || r.busyThreads || [];
    if(threads.length) {
      const rows = threads.map(t => [
        `<span style="color:#c0caf5">${esc(t.name||'')}</span>`,
        `<span style="color:${R.stateColor(t.state)}">${esc(t.state||'')}</span>`,
        t.cpu != null ? `<span style="color:#4ade80">${t.cpu}%</span>` : '—',
        t.deltaTime != null ? `${t.deltaTime}ms` : '—',
        `<span style="color:#565f89">${t.id||''}</span>`,
        t.daemon ? '<span style="color:#565f89">D</span>' : '',
      ]);
      html += `<div class="r-sec-lbl">🧵 Threads</div>`;
      html += R.table(['Name','State','CPU%','ΔTime','Id','D'], rows);
    }
    // Memory
    const mem = r.memoryInfo || r.memory || {};
    if(Object.keys(mem).length) {
      html += `<div class="r-sec-lbl" style="margin-top:10px">🧠 Memory</div>`;
      for(const [zone, info] of Object.entries(mem)) {
        if(!info || typeof info !== 'object') continue;
        const used = info.used ?? info.usedBytes ?? 0;
        const total= info.total ?? info.totalBytes ?? info.committed ?? 0;
        const max  = info.max ?? info.maxBytes ?? 0;
        html += `<div style="margin:3px 0">${R.kv(zone, R.bar(used,total,max), '')}`;
        html += `</div>`;
      }
    }
    // Runtime info
    const rt = r.runtimeInfo || {};
    if(Object.keys(rt).length) {
      const rows = Object.entries(rt).map(([k,v]) => [
        `<span style="color:#7aa2f7">${esc(k)}</span>`,
        `<span style="color:#a9b1d6">${esc(String(v??''))}</span>`
      ]);
      html += `<div class="r-sec-lbl" style="margin-top:10px">⚙️ Runtime</div>`;
      html += R.table(['Key','Value'], rows);
    }
    return html || RENDERERS._fallback(r);
  },

  // ── thread ────────────────────────────────────────────────────────────────
  thread(r) {
    const threads = r.busyThreads || r.threads || [];
    if(!threads.length) return RENDERERS._fallback(r);
    let html = `<div class="r-sec-lbl">🧵 Threads (${threads.length})</div>`;
    for(const t of threads) {
      const sc = t.state==='BLOCKED'?'#f87171':t.state==='RUNNABLE'?'#4ade80':t.state==='WAITING'||t.state==='TIMED_WAITING'?'#fb923c':'#94a3b8';
      const cpu_s = t.cpu != null ? ` <span style="color:#4ade80;font-size:10px">cpu=${t.cpu}%</span>` : '';
      const dt_s  = t.deltaTime != null && t.deltaTime > 0 ? ` <span style="color:#fb923c;font-size:10px">+${t.deltaTime}ms</span>` : '';
      const head  = `<span style="color:#c0caf5;font-weight:600">${esc(t.name||'')}</span>
        <span style="color:#565f89;font-size:11px"> Id=${t.id}</span>${cpu_s}${dt_s}
        <span style="color:${sc};font-size:10px;margin-left:6px">${esc(t.state||'')}</span>`;
      const frames = (t.stackTrace||[]).map(f => {
        const loc = f.lineNumber===-2 ? 'Native Method' : (f.fileName ? `${f.fileName}:${f.lineNumber}` : 'Unknown');
        const parts = (f.className||'').split('.');
        const cls = parts.pop(); const pkg = parts.join('.');
        return `<div style="font-size:12px;color:#565f89;padding:1px 0">
          <span style="color:#3b4261">${esc(pkg?pkg+'.':'')}</span><span style="color:#7dcfff">${esc(cls)}</span>.<span style="color:#73daca">${esc(f.methodName||'')}</span>(<span style="color:#e0af68">${esc(loc)}</span>)
        </div>`;
      }).join('');
      const lock = t.lockName ? `<div style="color:#f7768e;font-size:11px">⏸ waiting on ${esc(t.lockName)}</div>` : '';
      html += R.collapsible(head, lock + frames, t.state==='BLOCKED');
    }
    return html;
  },

  // ── jvm ───────────────────────────────────────────────────────────────────
  jvm(r) {
    // result is the whole r object — each key is a JVM category
    const skip = new Set(['type','jobId','statusCode']);
    let html = '';
    for(const [cat, entries] of Object.entries(r)) {
      if(skip.has(cat) || !entries) continue;
      let body = '';

      // 格式化值，处理嵌套对象
      const formatValue = (v) => {
        if (v === null || v === undefined) return '';
        if (typeof v === 'string') return v;
        if (typeof v === 'number' || typeof v === 'boolean') return String(v);
        if (typeof v === 'object') {
          return JSON.stringify(v, null, 2);
        }
        return String(v);
      };

      if(Array.isArray(entries)) {
        body = R.table(['Name','Value'], entries.map(e => [
          `<span style="color:#7aa2f7">${esc(e.name||e.key||'')}</span>`,
          `<span style="color:#a9b1d6;white-space:pre-wrap;font-family:monospace;font-size:11px">${esc(formatValue(e.value??e.val??''))}</span>`
        ]));
      } else if(typeof entries === 'object') {
        body = R.table(['Key','Value'], Object.entries(entries).map(([k,v]) => [
          `<span style="color:#7aa2f7">${esc(k)}</span>`,
          `<span style="color:#a9b1d6;white-space:pre-wrap;font-family:monospace;font-size:11px">${esc(formatValue(v))}</span>`
        ]));
      } else {
        body = `<span style="color:#a9b1d6">${esc(String(entries))}</span>`;
      }
      html += R.collapsible(`<span style="color:#c0caf5;font-weight:600">${esc(cat)}</span>`, body, true);
    }
    return html || RENDERERS._fallback(r);
  },

  // ── memory ────────────────────────────────────────────────────────────────
  memory(r) {
    const zones = r.heap || r.heapMemory || [];
    const nonheap = r.nonHeap || r.nonheap || [];
    const buffers = r.buffer || r.bufferPool || [];
    let html = '';
    const renderZones = (label, arr) => {
      if(!arr || !arr.length) return '';
      let s = `<div class="r-sec-lbl">${label}</div>`;
      for(const z of arr) {
        const used = z.used ?? z.usedBytes ?? 0;
        const total= z.total ?? z.totalBytes ?? z.committed ?? 0;
        const max  = z.max ?? z.maxBytes ?? 0;
        s += `<div style="margin:4px 0">
          <span style="color:#7aa2f7;font-size:11px">${esc(z.name||z.type||'')}</span>
          ${R.bar(used, total, max)}
        </div>`;
      }
      return s;
    };
    html += renderZones('Heap', zones);
    html += renderZones('Non-Heap', nonheap);
    html += renderZones('Buffer', buffers);
    return html || RENDERERS._fallback(r);
  },

  // ── sysprop / sysenv ──────────────────────────────────────────────────────
  sysprop(r) {
    const props = r.props || r.sysprops || r;
    const skip = new Set(['type','jobId','statusCode']);
    const entries = Object.entries(props).filter(([k]) => !skip.has(k));
    if(!entries.length) return RENDERERS._fallback(r);
    const rows = entries.map(([k,v]) => [
      `<span style="color:#7aa2f7">${esc(k)}</span>`,
      `<span style="color:#a9b1d6;word-break:break-all">${esc(String(v??''))}</span>`
    ]);
    return R.table(['Property','Value'], rows);
  },
  sysenv(r) {
    const env = r.env || r;
    const skip = new Set(['type','jobId','statusCode']);
    const entries = Object.entries(env).filter(([k]) => !skip.has(k));
    if(!entries.length) return RENDERERS._fallback(r);
    const rows = entries.map(([k,v]) => [
      `<span style="color:#7aa2f7">${esc(k)}</span>`,
      `<span style="color:#a9b1d6;word-break:break-all">${esc(String(v??''))}</span>`
    ]);
    return R.table(['Variable','Value'], rows);
  },

  // ── vmoption ──────────────────────────────────────────────────────────────
  vmoption(r) {
    const opts = r.vmOptions || r.vmOption ? [r.vmOption].filter(Boolean) : [];
    const list = opts.length ? opts : (r.vmOptions || []);
    if(!list.length) return RENDERERS._fallback(r);
    const rows = list.map(o => [
      `<span style="color:#7aa2f7">${esc(o.name||'')}</span>`,
      `<span style="color:#4ade80">${esc(String(o.value??''))}</span>`,
      o.writeable ? '<span style="color:#4ade80">✓</span>' : '<span style="color:#565f89">✗</span>'
    ]);
    return R.table(['Name','Value','Writeable'], rows);
  },

  // ── perfcounter ───────────────────────────────────────────────────────────
  perfcounter(r) {
    const counters = r.perfCounters || r.counters || r.content || [];
    if(!Array.isArray(counters) || !counters.length) return RENDERERS._fallback(r);
    const rows = counters.map(c => [
      `<span style="color:#7aa2f7">${esc(c.name||c.key||'')}</span>`,
      `<span style="color:#4ade80">${esc(String(c.value??''))}</span>`,
      `<span style="color:#565f89">${esc(c.units||c.unit||'')}</span>`
    ]);
    return R.table(['Counter','Value','Unit'], rows);
  },

  // ── sc ────────────────────────────────────────────────────────────────────
  sc(r) {
    const items = r.classInfo || r.classes || [];
    if(!items.length) { clog(`<span style="color:#565f89">No classes found</span>`, 'line'); return ''; }
    return items.map(c => {
      const name = c.name || c.className || '';
      const cl   = c.classLoader || c.classLoaderHash || '';
      const src  = c.codeSource || c.location || '';
      const isI  = c.isInterface;
      const body = [
        cl  ? R.kv('ClassLoader', `<span style="color:#7aa2f7">${esc(cl)}</span>`) : '',
        src ? R.kv('CodeSource',  `<span style="color:#565f89">${esc(src)}</span>`) : '',
        c.superClass ? R.kv('Super', `<span style="color:#7aa2f7">${esc(c.superClass)}</span>`) : '',
        c.interfaces?.length ? R.kv('Implements', c.interfaces.map(i=>`<span style="color:#7dcfff">${esc(i)}</span>`).join(', ')) : '',
      ].filter(Boolean).join('');
      const hdr = `<span style="color:${isI?'#bb9af7':'#7dcfff'};font-weight:600">${esc(name)}</span>
        ${isI ? R.badge('interface','#bb9af7') : ''}`;
      return R.collapsible(hdr, body || '<span style="color:#565f89">No details</span>', false);
    }).join('');
  },

  // ── sm ────────────────────────────────────────────────────────────────────
  sm(r) {
    const items = r.methodInfo || r.methods || [];
    if(!items.length) return `<span style="color:#565f89">No methods found</span>`;
    const rows = items.map(m => [
      `<span style="color:#7aa2f7">${esc(m.declaringClass||m.className||'')}</span>`,
      `<span style="color:#73daca;font-weight:600">${esc(m.methodName||m.name||'')}</span>`,
      `<span style="color:#a9b1d6;font-size:11px">${esc((m.paramTypes||m.params||[]).join(', '))}</span>`,
      `<span style="color:#e0af68">${esc(m.returnType||m.returnTypeName||'')}</span>`,
      `<span style="color:#565f89">${esc(m.modifier||m.modifiers||'')}</span>`,
    ]);
    return R.table(['Class','Method','Params','Return','Modifier'], rows);
  },

  // ── jad ───────────────────────────────────────────────────────────────────
  jad(r) {
    let html = '';
    if(r.location) html += `<div style="color:#565f89;font-size:11px;margin-bottom:4px">📍 ${esc(r.location)}</div>`;
    if(r.classInfo) html += `<div style="color:#7aa2f7;font-size:11px;margin-bottom:4px">${esc(r.classInfo)}</div>`;
    html += R.code(r.source || JSON.stringify(r, null, 2));
    return html;
  },

  // ── classloader ───────────────────────────────────────────────────────────
  classloader(r) {
    const cls = r.classLoaders || r.classloaders || [];
    if(!cls.length) return RENDERERS._fallback(r);
    const rows = cls.map(c => [
      `<span style="color:#7dcfff">${esc(c.name||c.className||'')}</span>`,
      `<span style="color:#4ade80">${c.loadedCount ?? c.classCount ?? '—'}</span>`,
      `<span style="color:#565f89">${esc(c.hash||c.hashCode||'')}</span>`,
      `<span style="color:#a9b1d6;font-size:11px">${esc(c.parent||'')}</span>`,
    ]);
    return R.table(['ClassLoader','Loaded','Hash','Parent'], rows);
  },

  // ── watch / getstatic / ognl ──────────────────────────────────────────────
  watch(r) {
    let html = '';
    const cost = r.cost ?? r.ts;
    if(cost != null) html += `<div style="color:#e0af68;font-size:11px;margin-bottom:4px">⏱ cost=${R.fmtMs(cost)}</div>`;
    if(r.isThrow) html += `<div style="color:#f7768e;font-size:11px;margin-bottom:4px">💥 Exception thrown</div>`;
    const val = r.object ?? r.value ?? r.returnValue ?? r.result;
    if(val !== undefined) html += R.code(typeof val === 'string' ? val : JSON.stringify(val, null, 2));
    else html += RENDERERS._fallback(r);
    return html;
  },
  ognl(r)      { return RENDERERS.watch(r); },
  getstatic(r) { return RENDERERS.watch(r); },

  // ── trace ─────────────────────────────────────────────────────────────────
  trace(r) {
    const root = r.threadTrace || r.traceTree || r;
    const renderNode = (node, depth=0) => {
      if(!node || typeof node !== 'object') return '';
      const cls  = node.className  || '';
      const mth  = node.methodName || '';
      const cost = node.cost ?? node.duration;
      const color = cost > 500 ? '#f87171' : cost > 100 ? '#fb923c' : '#4ade80';
      const costStr = cost != null ? `<span style="color:${color};font-size:11px"> [${R.fmtMs(cost)}]</span>` : '';
      const indent = depth * 16;
      let html = `<div style="padding-left:${indent}px;font-size:12px;line-height:1.8">
        <span style="color:#7dcfff">${esc(cls)}</span>.<span style="color:#73daca;font-weight:600">${esc(mth)}</span>()${costStr}
      </div>`;
      for(const child of (node.children || [])) {
        html += renderNode(child, depth + 1);
      }
      return html;
    };
    return `<div style="font-family:var(--mono)">${renderNode(root)}</div>`;
  },
  stack(r)     { return RENDERERS.trace(r); },

  // ── monitor ───────────────────────────────────────────────────────────────
  monitor(r) {
    const stats = r.monitorStatistics || r.statistics || r.data || [];
    if(!Array.isArray(stats) || !stats.length) return RENDERERS._fallback(r);
    const rows = stats.map(s => [
      `<span style="color:#7aa2f7">${esc(s.className||s.clazz||'')}</span>`,
      `<span style="color:#73daca">${esc(s.methodName||s.method||'')}</span>`,
      `<span style="color:#4ade80">${s.total??'—'}</span>`,
      `<span style="color:#4ade80">${s.success??'—'}</span>`,
      `<span style="color:#f87171">${s.failed??s.fail??'—'}</span>`,
      s.avgRt!=null ? `<span style="color:#e0af68">${R.fmtMs(s.avgRt)}</span>` : (s.avg!=null ? `<span style="color:#e0af68">${R.fmtMs(s.avg)}</span>` : '—'),
      s.maxRt!=null ? `<span style="color:#fb923c">${R.fmtMs(s.maxRt)}</span>` : '—',
      s.failureRate!=null ? `<span style="color:${s.failureRate>0?'#f87171':'#4ade80'}">${(s.failureRate*100).toFixed(1)}%</span>` : '—',
    ]);
    return R.table(['Class','Method','Total','Success','Fail','Avg RT','Max RT','Fail%'], rows);
  },

  // ── tt ────────────────────────────────────────────────────────────────────
  tt(r) {
    const idx = r.index ?? r.indexNum;
    const cost = r.cost;
    const isRet = r.isReturn; const isThr = r.isThrow;
    let html = '<div class="r-tt-card">';
    if(idx != null) html += R.kv('Index', `<span style="color:#7aa2f7">${idx}</span>`);
    if(cost != null) html += R.kv('Cost',  `<span style="color:#e0af68">${R.fmtMs(cost)}</span>`);
    if(isRet != null) html += R.kv('Return', isRet ? '<span style="color:#4ade80">true</span>' : '<span style="color:#565f89">false</span>');
    if(isThr != null) html += R.kv('Throw',  isThr ? '<span style="color:#f87171">true</span>'  : '<span style="color:#565f89">false</span>');
    const params = r.params ?? r.args;
    if(params != null) html += R.kv('Params', '') + R.code(JSON.stringify(params, null, 2));
    const ret = r.returnValue ?? r.returnObj;
    if(ret != null) html += R.kv('Return Value', '') + R.code(JSON.stringify(ret, null, 2));
    html += '</div>';
    return html;
  },

  // ── vmtool ────────────────────────────────────────────────────────────────
  vmtool(r) {
    if(r.action === 'forceGc' || r.forceGc) {
      return `<span style="color:#4ade80">✓ Force GC completed</span>`;
    }
    const instances = r.instances || r.objects || r.result || [];
    if(!Array.isArray(instances)) return RENDERERS._fallback(r);
    let html = `<div style="color:#565f89;font-size:11px;margin-bottom:6px">${instances.length} instance(s)</div>`;
    instances.forEach((obj, i) => {
      const preview = typeof obj === 'string' ? obj : JSON.stringify(obj, null, 2);
      html += R.collapsible(
        `<span style="color:#7dcfff">Instance [${i}]</span>`,
        R.code(preview), i === 0
      );
    });
    return html;
  },

  // ── logger ────────────────────────────────────────────────────────────────
  logger(r) {
    const loggers = r.loggers || r.loggerInfos || [];
    if(!Array.isArray(loggers) || !loggers.length) return RENDERERS._fallback(r);
    const levelColor = l => ({
      ERROR:'#f87171', WARN:'#fb923c', INFO:'#4ade80',
      DEBUG:'#7aa2f7', TRACE:'#94a3b8'
    }[l?.toUpperCase()] || '#9aa5ce');
    const rows = loggers.map(lg => [
      `<span style="color:#c0caf5">${esc(lg.name||lg.loggerName||'')}</span>`,
      `<span style="color:${levelColor(lg.level)};font-weight:600">${esc(lg.level||'')}</span>`,
      `<span style="color:${levelColor(lg.effectiveLevel||lg.configLevel)}">${esc(lg.effectiveLevel||lg.configLevel||'')}</span>`,
      `<span style="color:#565f89;font-size:11px">${(lg.appenders||[]).map(a=>esc(a.name||a)).join(', ')}</span>`,
    ]);
    return R.table(['Logger','Level','Effective','Appenders'], rows);
  },

  // ── mbean ─────────────────────────────────────────────────────────────────
  mbean(r) {
    const beans = r.mBeanInfo || r.mbeanInfo || [];
    if(!Array.isArray(beans)) return RENDERERS._fallback(r);
    return beans.map(b => {
      const name = esc(b.objectName || b.name || '');
      const attrs = (b.attributes || []).map(a =>
        R.kv(a.name || a.key || '', `<span style="color:#a9b1d6">${esc(String(a.value ?? ''))}</span>`)
      ).join('');
      return R.collapsible(
        `<span style="color:#7aa2f7;font-weight:600">${name}</span>`,
        attrs || '<span style="color:#565f89">No attributes</span>',
        false
      );
    }).join('');
  },

  // ── profiler ──────────────────────────────────────────────────────────────
  profiler(r) {
    const action = r.action || '';
    const file   = r.outputFile || r.file || '';
    const event  = r.event || '';
    let html = '';
    if(action) html += R.kv('Action', `<span style="color:#7aa2f7">${esc(action)}</span>`);
    if(event)  html += R.kv('Event',  `<span style="color:#4ade80">${esc(event)}</span>`);
    if(file)   html += R.kv('Output', `<span style="color:#e0af68">${esc(file)}</span>`);
    const result = r.executeResult || r.result || '';
    if(result) html += `<div style="color:#a9b1d6;font-size:12px;margin-top:4px">${esc(String(result))}</div>`;
    return html || RENDERERS._fallback(r);
  },

  // ── heapdump ──────────────────────────────────────────────────────────────
  heapdump(r) {
    const loc = r.location || r.file || r.outputFile || '';
    return `<div>${R.kv('File', `<span style="color:#e0af68">${esc(loc)}</span>`)}</div>`;
  },

  // ── jfr ───────────────────────────────────────────────────────────────────
  jfr(r) {
    const out = r.jfrOutput || r.output || r.result || '';
    return `<div style="color:#a9b1d6;font-size:12px;white-space:pre-wrap">${esc(String(out))}</div>`;
  },

  // ── version ───────────────────────────────────────────────────────────────
  version(r) {
    return R.kv('Arthas Version', `<span style="color:#4ade80;font-weight:700">${esc(r.version||'')}</span>`);
  },

  // ── pwd ───────────────────────────────────────────────────────────────────
  pwd(r) {
    const path = r.workingDir || r.dir || r.path || '';
    return R.kv('Working Dir', `<span style="color:#e0af68">${esc(path)}</span>`);
  },

  // ── history ───────────────────────────────────────────────────────────────
  history(r) {
    const cmds = r.commands || r.history || r.entries || [];
    if(!Array.isArray(cmds) || !cmds.length) return RENDERERS._fallback(r);
    const rows = cmds.map((c, i) => [
      `<span style="color:#565f89">${i+1}</span>`,
      `<span style="color:#a9b1d6">${esc(c.command||c.cmd||String(c))}</span>`
    ]);
    return R.table(['#','Command'], rows);
  },

  // ── echo / cat / grep / tee ───────────────────────────────────────────────
  echo(r) {
    return `<div style="color:#a9b1d6;white-space:pre-wrap">${esc(r.text||r.content||r.output||'')}</div>`;
  },
  cat(r)  { return RENDERERS.echo(r); },

  // ── fallback: pretty JSON ─────────────────────────────────────────────────
  _fallback(r) {
    const skip = new Set(['type','jobId','statusCode']);
    const filtered = Object.fromEntries(Object.entries(r).filter(([k]) => !skip.has(k)));
    return R.code(JSON.stringify(filtered, null, 2));
  },
};

/** 主渲染入口 */
function renderRes(resp) {
  if(!resp) return;
  if(resp.state==='FAILED' || resp.state==='REFUSED') {
    clog('✗ ' + esc(resp.message || JSON.stringify(resp)), 'err');
    return;
  }
  // 兼容旧格式 {error: "..."} 或 {ok: false}
  if(resp.error && !resp.body) {
    clog('✗ ' + esc(resp.error), 'err');
    return;
  }
  const results = resp.body?.results || [];
  if(!results.length && resp.body) {
    clog(`<pre class="o-code">${esc(JSON.stringify(resp.body, null, 2))}</pre>`, 'line');
    return;
  }
  if(!results.length) {
    // SUCCEEDED 但无 results，输出完整响应用于调试
    clog(`<pre class="o-code">${esc(JSON.stringify(resp, null, 2))}</pre>`, 'line');
    return;
  }
  // Collect ALL result HTML into one string → one clog call → one DOM insert
  const parts = [];
  for(const r of results) {
    const t = r.type || '';
    if(['status','message','welcome','input_status'].includes(t)) continue;
    const renderer = RENDERERS[t];
    const html = renderer ? renderer(r) : RENDERERS._fallback(r);
    if(html) parts.push(html);
  }
  if(parts.length) clog(parts.join('<hr class="r-hr">'), 'line');
}

// ── 性能分析 & Dump ───────────────────────────────────────────────────────────
let _pfMode = 'profiler'; // 'profiler' | 'jfr' | 'dump'

const PF_MODE_DESC = {
  profiler: 'async-profiler: 低开销采样分析，支持 CPU/内存/锁等事件，生成火焰图。适用所有 JDK 版本。',
  jfr:      'JDK JFR (Java Flight Recorder): JDK 内置事件录制，需要 JDK 11+。通过 Arthas jfr 命令控制，生成 .jfr 文件，用 JDK Mission Control 分析。',
  dump:     '快照导出: 线程 Dump 分析死锁/卡顿；Heap Dump 分析内存泄漏/OOM。文件自动下载到本地。',
  gclog:    'GC 日志分析: 自动探测 JVM 的 GC 日志配置（-Xloggc / -Xlog:gc），读取日志内容，支持下载。无 GC 日志配置时给出启用建议。',
};

function pfSetMode(mode) {
  _pfMode = mode;
  ['profiler','jfr','dump','gclog'].forEach(m => {
    const btn = document.getElementById(`pfMode-${m}`);
    if (btn) {
      btn.classList.toggle('active', m === mode);
      btn.classList.toggle('on', m === mode); // legacy compat
    }
    const cfg = document.getElementById(`pfCfg-${m}`);
    if(cfg) cfg.style.display = m === mode ? 'block' : 'none';
  });
  const desc = document.getElementById('pfModeDesc');
  if(desc) desc.textContent = PF_MODE_DESC[mode] || '';
  // Update start button text with SVG icons
  const btn = document.getElementById('pfBtn');
  if(btn) {
    const icons = {
      gclog: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.35-4.35"/></svg> 探测 GC 日志',
      dump: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><polygon points="5 3 19 12 5 21 5 3"/></svg> 导出',
      default: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><polygon points="5 3 19 12 5 21 5 3"/></svg> 开始采样'
    };
    btn.innerHTML = icons[mode] || icons.default;
  }
  // Show/hide dump sub-options
  pfUpdateDumpOpts();
}

function pfUpdateDumpOpts() {
  const heapOpts = document.getElementById('dumpHeapOpts');
  const dumpSel  = document.getElementById('dumpType');
  if(heapOpts && dumpSel) {
    heapOpts.style.display = dumpSel.value === 'heap' ? 'block' : 'none';
  }
}

function pfDurSync(val, from) {
  const v = Math.max(30, Math.min(7200, parseInt(val)||60));
  if(from !== 'num') { const n = document.getElementById('pfDurNum'); if(n) n.value = v; }
  const slider = document.getElementById('pfDur');
  if(slider) slider.value = Math.min(v, parseInt(slider.max));
}
function pfSetDur(s) {
  const sl = document.getElementById('pfDur');     if(sl) sl.value = Math.min(s, 1800);
  const nm = document.getElementById('pfDurNum');  if(nm) nm.value = s;
}

async function pfStart() {
  if(window.ConnectionGuard && !ConnectionGuard.guard('profiler')) {
    // ConnectionGuard 已经显示了引导面板，这里添加额外的 toast 提示
    const level = ConnectionGuard.getCurrentLevel();
    if (level === 'none') {
      toast('请先建立 Pod 连接，再使用采样工具', 'warn');
    } else if (level === 'pod') {
      toast('请先启动 Arthas 诊断环境，再使用采样工具', 'warn');
    }
    return;
  }
  const t = profilerTargetPayload(getCurrentPodTarget());
  if(!t.cluster_name || !t.pod_name) { toast('请先配置集群和 Pod','warn'); return; }

  if(_pfMode === 'dump')  { await pfRunDump(t);  return; }
  if(_pfMode === 'jfr')   { await pfRunJfr(t);   return; }
  if(_pfMode === 'gclog') { await pfRunGcLog(t); return; }

  // ── async-profiler (profiler start/stop) ──────────────────────────────────
  _pfDur   = Math.max(30, parseInt(document.getElementById('pfDurNum')?.value || document.getElementById('pfDur')?.value) || 60);
  _pfStart = Date.now();
  const event  = document.getElementById('pfEvent')?.value  || 'cpu';
  const fmt    = document.getElementById('pfFmt')?.value    || 'html';

  // 更新任务信息面板
  _pfTaskInfo = { type: 'async-profiler', event: event, duration: _pfDur, status: 'starting', progressPercent: 0 };
  updatePfTaskInfo();

  pfClearLog();
  _pfLastMsg = '';
  _pfLastProgressLog = 0;
  pfLog(`提交任务... 事件=${event} 格式=${fmt} 时长=${_pfDur}s`, 'dim');
  try {
    const r = await fetch(`${API}/profile/start`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({...profilerTargetPayload(t), duration: _pfDur, format: fmt, event}),
    });
    const d = await r.json(); 
    if(!r.ok) {
      // 409 = 已有运行中任务，恢复按钮并提示
      if (r.status === 409) {
        toast(d.message || '该连接已有运行中的任务', 'warn');
        pfLog('⚠ ' + (d.message || '已有运行中的任务'), 'warn');
        hidePfTaskInfo();
        return;
      }
      throw new Error(d.error || d.message || '失败');
    }
    if(d.error) throw new Error(d.error);
    _pfTaskId = d.task_id;
    const profilerConnId = d.connection_id || _currentConnId;
    _pfTaskInfo.taskId = d.task_id;
    _pfTaskInfo.status = 'running';
    updatePfTaskInfo();
    _persistPfTask(profilerConnId, d.task_id, { type: 'async-profiler', event, duration: _pfDur });
    pfLog(`任务已创建: ${d.task_id}`, 'ok');
    _pfPollingForConn = profilerConnId;
    startProfilerPollTimer(2000);
  } catch(e) { pfLog('失败: '+e.message, 'err'); hidePfTaskInfo(); }
}

async function pfRunJfr(t) {
  // ── JDK JFR via Arthas jfr command ──────────────────────────────────────
  // 正确用法: jfr start [name] [settings] → jfr stop [name] [filename]
  // 注意: JFR 需要 JDK 11+，不同于 async-profiler 的 "profiler stop --format jfr"
  const name     = document.getElementById('jfrName')?.value.trim() || 'arthas-jfr';
  const dur      = Math.max(10, parseInt(document.getElementById('jfrDurNum')?.value) || 60);
  const settings = document.getElementById('jfrSettings')?.value || 'default';
  const _jts    = fmtNowTs();
  const jfrFile  = `/tmp/jfr-${name}-${_jts}.jfr`;

  _pfStart = Date.now(); _pfDur = dur;

  // 更新任务信息面板
  _pfTaskInfo = { type: 'JDK JFR', event: settings, duration: dur, status: 'starting', progressPercent: 0 };
  updatePfTaskInfo();

  pfClearLog();
  _pfLastMsg = '';
  _pfLastProgressLog = 0;
  pfLog(`JFR 录制: name=${name} settings=${settings} duration=${dur}s`, 'dim');
  pfLog('注意: JFR 需要 JDK 8u262+ 或 JDK 11+', 'warn');

  try {
    const r = await fetch(`${API}/profile/start`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({...profilerTargetPayload(t), mode: 'jfr', jfr_name: name,
                            jfr_settings: settings, jfr_file: jfrFile,
                            duration: dur, format: 'jfr', event: settings}),
    });
    const d = await r.json(); 
    if(!r.ok) {
      if (r.status === 409) {
        toast(d.message || '该连接已有运行中的任务', 'warn');
        pfLog('⚠ ' + (d.message || '已有运行中的任务'), 'warn');
        hidePfTaskInfo();
        return;
      }
      throw new Error(d.error || d.message || '失败');
    }
    if(d.error) throw new Error(d.error);
    _pfTaskId = d.task_id;
    const profilerConnId = d.connection_id || _currentConnId;
    _pfTaskInfo.taskId = d.task_id;
    _pfTaskInfo.status = 'running';
    updatePfTaskInfo();
    pfLog(`JFR 任务已创建: ${d.task_id}`, 'ok');
    _pfPollingForConn = profilerConnId;
    startProfilerPollTimer(2000);
  } catch(e) { pfLog('失败: '+e.message, 'err'); hidePfTaskInfo(); }
}

async function pfRunDump(t) {
  // ── Dump: thread dump or heap dump ────────────────────────────────────────
  const dumpType = document.getElementById('dumpType')?.value || 'thread';

  // 更新任务信息面板
  _pfTaskInfo = { type: dumpType === 'thread' ? 'Thread Dump' : 'Heap Dump', event: '-', duration: '-', status: 'starting', progressPercent: 0 };
  updatePfTaskInfo();

  pfClearLog();
  _pfLastMsg = '';
  _pfLastProgressLog = 0;

  if(dumpType === 'thread') {
    pfLog('导出线程 Dump...', 'dim');
    try {
      const r = await fetch(`${API}/profile/start`, {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({...profilerTargetPayload(t), mode: 'threaddump', duration: 0, format: 'html'}),
      });
      const d = await r.json(); 
      if(!r.ok) {
        if (r.status === 409) {
          toast(d.message || '该连接已有运行中的任务', 'warn');
          pfLog('⚠ ' + (d.message || '已有运行中的任务'), 'warn');
          hidePfTaskInfo();
          return;
        }
        throw new Error(d.error || d.message || '失败');
      }
      if(d.error) throw new Error(d.error);
      _pfTaskId = d.task_id;
      const profilerConnId = d.connection_id || _currentConnId;
      _pfTaskInfo.taskId = d.task_id;
      _pfTaskInfo.status = 'running';
      _pfStart = Date.now();
      _pfDur = 0;
      updatePfTaskInfo();
      pfLog(`线程 Dump 任务: ${d.task_id}`, 'ok');
      pfLog('正在采集，通常 5~10 秒完成...', 'dim');
      _pfPollingForConn = profilerConnId;
      startProfilerPollTimer(1500);
    } catch(e) { pfLog('失败: '+e.message, 'err'); hidePfTaskInfo(); }
  } else {
    // heap dump
    const file    = '';
    const _hfEl = document.getElementById('dumpHeapFile');
    if(_hfEl) _hfEl.value = file;
    const liveOnly = document.getElementById('dumpHeapLive')?.checked ?? true;
    pfLog(`导出 Heap Dump → ${file}`, 'dim');
    pfLog('警告: Heap Dump 会暂停 JVM（STW），大堆可能需要数分钟', 'warn');
    try {
      const r = await fetch(`${API}/profile/start`, {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({...profilerTargetPayload(t), mode: 'heapdump', heap_file: file,
                              heap_live: liveOnly, duration: 0, format: 'hprof'}),
      });
      const d = await r.json(); 
      if(!r.ok) {
        if (r.status === 409) {
          toast(d.message || '该连接已有运行中的任务', 'warn');
          pfLog('⚠ ' + (d.message || '已有运行中的任务'), 'warn');
          hidePfTaskInfo();
          return;
        }
        throw new Error(d.error || d.message || '失败');
      }
      if(d.error) throw new Error(d.error);
      _pfTaskId = d.task_id;
      const profilerConnId = d.connection_id || _currentConnId;
      _pfTaskInfo.taskId = d.task_id;
      _pfTaskInfo.status = 'running';
      _pfStart = Date.now();
      _pfDur = 0;
      updatePfTaskInfo();
      pfLog(`Heap Dump 任务: ${d.task_id}`, 'ok');
      pfLog('采集中，请等待...', 'dim');
      _pfPollingForConn = profilerConnId;
      startProfilerPollTimer(2000);
    } catch(e) { pfLog('失败: '+e.message, 'err'); hidePfTaskInfo(); }
  }
}

async function pfRunGcLog(t) {
  // 更新任务信息面板
  _pfTaskInfo = { type: 'GC日志', event: 'gc探测', duration: '-', status: 'starting', progressPercent: 0 };
  updatePfTaskInfo();

  pfClearLog();
  _pfLastMsg = '';
  _pfLastProgressLog = 0;
  pfLog('探测 GC 日志配置...', 'dim');

  const gcInfo = document.getElementById('gcLogInfo');
  const gcHint = document.getElementById('gcHint');
  if(gcInfo) gcInfo.style.display = 'none';
  if(gcHint) gcHint.style.display = 'none';

  try {
    const r = await fetch(`${API}/gc/info`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify(t),
    });
    const d = await r.json();
    if(!r.ok || d.error) throw new Error(d.error || '探测失败');

    pfLog(`进程 PID: ${d.pid}`, 'dim');

    if(d.gc_enabled) {
      // ── 左侧：显示 GC 参数 + 文件路径列表 ─────────────────────────────
      const flagsEl = document.getElementById('gcFlagsDisplay');
      if(flagsEl) flagsEl.textContent = d.gc_flags?.join('\n') || '（未发现具名 GC 参数）';

      // 构建路径列表（支持多个路径 + stdout）
      const pathListEl = document.getElementById('gcPathList');
      if(pathListEl) {
        const paths = d.stdout_gc ? ['stdout'] : (d.log_paths || []);
        if(paths.length === 0 && d.log_path_used) paths.push(d.log_path_used);

        pathListEl.innerHTML = paths.map(p => `
          <div style="display:flex;gap:5px;align-items:center">
            <input class="fi" value="${esc(p)}" readonly
              style="flex:1;font-size:11px;color:var(--a);font-family:var(--mono)">
            ${p !== 'stdout' ? `
              <button class="ib" onclick="gcDownloadPath('${esc(p)}')"
                style="font-size:11px;padding:3px 8px;white-space:nowrap">↓ 下载</button>
              <button class="ib" onclick="gcPreviewPath('${esc(p)}')"
                style="font-size:11px;padding:3px 8px;white-space:nowrap">👁 预览</button>
            ` : `<span style="font-size:11px;color:var(--a4)">→ Pod监控日志</span>`}
          </div>`).join('');
      }
      if(gcInfo) gcInfo.style.display = 'block';

      // ── 右侧日志面板：显示探测结果 ──────────────────────────────────────
      if(d.gc_flags?.length) {
        pfLog(`GC 参数 (${d.gc_flags.length}个):`, 'ok');
        d.gc_flags.forEach(f => pfLog(`  ${f}`, 'info'));
      }
      if(d.stdout_gc) {
        pfLog('GC 输出到 stdout → 请在「Pod 监控 → 日志」查看', 'warn');
      } else if(d.log_path_used) {
        pfLog(`✓ 日志文件: ${d.log_path_used}`, 'ok');
        if(d.log_content && !d.log_content.startsWith('文件不可读')) {
          const lines = d.log_content.split('\n').filter(l => l.trim());
          pfLog(`最后 ${Math.min(lines.length, 30)} 行:`, 'dim');
          lines.slice(-30).forEach(l => pfLog(l, 'info'));
        } else {
          pfLog(d.log_content || '无法读取内容', 'warn');
        }
      }
    } else {
      pfLog('⚠ 未检测到 GC 日志配置', 'warn');
      if(gcHint) { gcHint.textContent = d.hint || ''; gcHint.style.display = 'block'; }
      pfLog('启用 GC 日志需要重启 JVM，添加启动参数（见左侧提示框）', 'dim');
    }

    if(d.cmdline_snippet) {
      pfLog(`cmdline: ${d.cmdline_snippet.slice(0, 200)}`, 'dim');
    }

  } catch(e) {
    pfLog('探测失败: ' + e.message, 'err');
  } finally {
    // Re-enable start button
    const startBtn = document.getElementById('pfBtn');
    if (startBtn) {
      startBtn.disabled = false;
      startBtn.classList.remove('running');
    }
  }
}

async function gcDownloadPath(path) {
  const t = getT();
  if(!t.pod_name) { toast('请先配置 Pod', 'warn'); return; }
  pfLog(`下载: ${path}`, 'dim');
  try {
    const r = await fetch(`${API}/gc/download`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({...t, log_path: path}),
    });
    if(!r.ok) { const e = await r.json(); throw new Error(e.error||'下载失败'); }
    const blob = await r.blob();
    const ts   = new Date().toISOString().replace(/[:.]/g,'-').slice(0,19);
    const fname = `gc-${t.pod_name}-${fmtNowTs()}.log`;
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href=url; a.download=fname; a.click();
    URL.revokeObjectURL(url);
    toast('GC 日志已下载', 'success');
    pfLog(`✓ 已下载: ${fname}`, 'ok');
  } catch(e) { toast(e.message, 'error'); pfLog('下载失败: '+e.message, 'err'); }
}

async function gcPreviewPath(path) {
  const t = getT();
  if(!t.pod_name) { toast('请先配置 Pod', 'warn'); return; }
  pfLog(`预览: ${path}`, 'dim');
  try {
    const d = await safePost(`${API}/pod/files/tail`, {...t, path, lines: 100});
    if(d.error) { pfLog('预览失败: '+d.error, 'err'); return; }
    const lines = (d.content||'').split('\n');
    pfLog(`── GC 日志末尾 ${lines.length} 行 ──────────────────────────`, 'dim');
    lines.forEach(l => {
      const cls = /pause|stop-the-world|full gc|gc overhead/i.test(l) ? 'err'
                : /young|minor/i.test(l) ? 'ok' : 'info';
      pfLog(l || ' ', cls);
    });
  } catch(e) { pfLog('预览失败: '+e.message, 'err'); }
}

// 兼容旧版 gcDownload 调用
async function gcDownload() {
  const path = document.getElementById('gcLogPath')?.value;
  if(path) { await gcDownloadPath(path); }
  else { toast('未检测到 GC 日志路径', 'warn'); }
}

// 更新任务信息面板
function updatePfTaskInfo() {
  const panel = document.getElementById('pfStatusPanel');
  if (!panel) return;
  panel.style.display = 'block';
  const info = _pfTaskInfo || {};

  // Status dot
  const dot = document.getElementById('pfStatusDot');
  if (dot) {
    dot.className = 'pf-status-dot ' + (info.status || 'starting');
  }

  // Status text
  const statusText = document.getElementById('pfStatusText');
  if (statusText) {
    const statusLabels = { starting: '启动中...', running: '采样中', completed: '已完成', failed: '失败', stopped: '已停止' };
    statusText.textContent = statusLabels[info.status] || info.status || '准备中...';
  }

  // Status time
  const statusTime = document.getElementById('pfStatusTime');
  if (statusTime && info.status === 'running' && _pfStart) {
    const elapsed = Math.floor((Date.now() - _pfStart) / 1000);
    const dur = info.duration || 0;
    statusTime.textContent = dur > 0 ? `${elapsed}s / ${dur}s` : `${elapsed}s`;
  } else if (statusTime) {
    statusTime.textContent = '';
  }

  // 友好的类型/事件名称
  const typeLabels = {
    'Thread Dump': '线程转储',
    'Heap Dump': '堆转储',
    'async-profiler': 'async-profiler',
    'JDK JFR': 'JDK JFR'
  };
  const eventLabels = {
    'threaddump': '线程转储',
    'heapdump': '堆转储',
    'cpu': 'CPU 采样',
    'alloc': '内存分配',
    'lock': '锁竞争',
    'wall': 'Wall 时间',
    'default': '默认配置',
    'profile': 'Profile 配置'
  };
  document.getElementById('pfInfoTaskId').textContent = info.taskId || '-';
  document.getElementById('pfInfoType').textContent = typeLabels[info.type] || info.type || '-';
  document.getElementById('pfInfoEvent').textContent = eventLabels[info.event] || info.event || '-';

  const isDump = info.type === 'Thread Dump' || info.type === 'Heap Dump' || info.event === 'threaddump' || info.event === 'heapdump';
  const durDisplay = isDump || !info.duration || info.duration === '-' || info.duration === 0 ? '-' : `${info.duration}s`;
  document.getElementById('pfInfoDur').textContent = durDisplay;

  // Progress bar
  const fill = document.getElementById('pfProgFill');
  const lbl = document.getElementById('pfProgLbl');
  const pct = document.getElementById('pfProgPct');
  if (fill) fill.style.width = (info.progressPercent || 0) + '%';
  if (lbl) lbl.textContent = info.progress || '等待中...';
  if (pct) pct.textContent = (info.progressPercent || 0) + '%';

  // Stop button
  const stopBtn = document.getElementById('pfStopBtn');
  if (stopBtn) {
    stopBtn.style.display = (info.status === 'running' || info.status === 'starting') ? 'inline-flex' : 'none';
  }

  // Start button state
  const startBtn = document.getElementById('pfBtn');
  if (startBtn) {
    const isRunning = info.status === 'running' || info.status === 'starting';
    startBtn.disabled = isRunning;
    startBtn.classList.toggle('running', isRunning);
  }

  // Download button
  const downloadWrap = document.getElementById('pfInfoDownloadWrap');
  const downloadBtn = document.getElementById('pfInfoDownloadBtn');
  if (downloadWrap && downloadBtn) {
    if (info.status === 'completed') {
      downloadWrap.style.display = 'inline';
      if (info.taskId) {
        const fname = info.outputFile || `profiler-${info.taskId}.html`;
        downloadBtn.onclick = () => downloadProfilerTask(info.taskId, fname);
      } else if (info.outputFile) {
        downloadBtn.onclick = () => downloadOutputFile(info.outputFile);
      } else {
        downloadWrap.style.display = 'none';
      }
    } else {
      downloadWrap.style.display = 'none';
    }
  }
}

// 隐藏任务信息面板
function hidePfTaskInfo() {
  const panel = document.getElementById('pfStatusPanel');
  if (panel) panel.style.display = 'none';
  _pfTaskInfo = { type: '-', event: '-', duration: 0, status: '-' };
  // Re-enable start button
  const startBtn = document.getElementById('pfBtn');
  if (startBtn) {
    startBtn.disabled = false;
    startBtn.classList.remove('running');
  }
}

// 安全下载文件（带认证）
async function safeDownload(url, filename) {
  try {
    const fullUrl = url.startsWith('http') ? url : `${API}${url}`;
    const r = await fetch(fullUrl, { credentials: 'include' });
    
    if (r.status === 401) {
      toast('登录已过期，请刷新页面重新登录', 'error');
      return;
    }
    if (!r.ok) {
      const errData = await r.json().catch(() => ({}));
      toast(errData.error || `下载失败 (${r.status})`, 'error');
      return;
    }
    
    const blob = await r.blob();
    const blobUrl = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = blobUrl;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(blobUrl);
    toast(`已下载: ${filename}`, 'success');
  } catch (e) {
    toast('下载失败: ' + e.message, 'error');
  }
}

// 下载采样任务结果
async function downloadProfilerTask(taskId, filename) {
  await safeDownload(`/profile/${taskId}/download`, filename || `profiler-${taskId}.html`);
}

// ✅ 停止当前采样任务（从状态面板调用）
function pfStop() {
  if (_pfTaskId) {
    cancelProfilerTask(_pfTaskId);
  }
}

// ✅ 中断运行中的 Profiler 任务
async function cancelProfilerTask(taskId) {
  if (!taskId) return;
  if (!confirm('确定要中断此任务吗？')) return;
  try {
    const r = await fetch(`${API}/profile/${taskId}/cancel`, { method: 'POST', credentials: 'include' });
    const d = await r.json();
    if (d.ok) {
      toast('任务已中断', 'success');
      // 如果是当前正在轮询的任务，也停止轮询
      if (_pfTaskId === taskId) {
        if (_pfPollTimer) { clearInterval(_pfPollTimer); _pfPollTimer = null; }
        _pfTaskId = null;
        _pfPollingForConn = null;
        document.getElementById('pfBtn').disabled = false;
        hidePfTaskInfo();
      }
      // 刷新历史列表（如果历史面板可见且筛选激活）
      if (typeof refreshHistoryIfFiltered === 'function') refreshHistoryIfFiltered();
    } else {
      toast(d.msg || '中断失败', 'error');
    }
  } catch (e) {
    toast('中断失败: ' + e.message, 'error');
  }
}

// 下载本地输出文件
async function downloadOutputFile(filename) {
  await safeDownload(`/files/${encodeURIComponent(filename)}`, filename);
}

async function pfPoll() {
  if(!_pfTaskId) return;
  try {
    const r = await fetch(`${API}/profile/${_pfTaskId}`); const d = await r.json();

    // 只为当前连接输出日志和更新 UI
    if (sameProfilerConnection(_pfPollingForConn, _currentConnId || window._currentConnId)) {
      // ── 后端 message 变化时输出新日志 ──
      const curMsg = d.message || '';
      if (curMsg && curMsg !== _pfLastMsg) {
        let lv = 'info';
        if (/失败|error|异常/i.test(curMsg)) lv = 'err';
        else if (/完成|success|done/i.test(curMsg)) lv = 'ok';
        else if (/warn|警告/i.test(curMsg)) lv = 'warn';
        await pfLog(curMsg, lv, d.updated_at);
        _pfLastMsg = curMsg;
      }

      // ── 后端 logs 数组（兼容旧格式） ──
      for (const l of (d.logs||[]).slice(_pfLL)) {
        if (l.message === curMsg) continue;
        await pfLog(l.message, l.level, l.timestamp);
      }
      _pfLL = d.logs?.length||0;

      const el = (Date.now()-_pfStart)/1000;
      const totalDur = _pfDur || 30;
      const serverProgress = Number.isFinite(Number(d.progress)) ? Math.max(0, Math.min(100, Number(d.progress))) : 0;
      const overtime = d.status === 'running' && totalDur > 0 && el > totalDur;
      const pct = d.status === 'completed' ? 100 : d.status === 'running' ? Math.min(95, serverProgress) : serverProgress;
      const pfFill = document.getElementById('pfProgFill');
      const pfPct = document.getElementById('pfProgPct');
      const pfLbl = document.getElementById('pfProgLbl');
      if(pfFill) pfFill.style.width = pct+'%';
      if(pfPct) pfPct.textContent = Math.round(pct)+'%';

      if (d.status === 'running') {
        if (overtime) {
          if(pfLbl) { pfLbl.textContent = `后端仍在执行 (${Math.round(el)}s)`; pfLbl.style.color = 'var(--a3)'; }
        } else if (serverProgress > 0) {
          if(pfLbl) { pfLbl.textContent = `后端进度 ${Math.round(serverProgress)}%`; pfLbl.style.color = 'var(--tx2)'; }
        } else {
          if(pfLbl) { pfLbl.textContent = `等待后端进度 (${Math.round(el)}s)`; pfLbl.style.color = 'var(--tx2)'; }
        }
      } else {
        if(pfLbl) pfLbl.textContent = d.status;
      }

      const clientTimeout = Math.max(totalDur * 3, 180);
      if (d.status === 'running' && el > clientTimeout) {
        clearInterval(_pfPollTimer); _pfPollTimer = null; _pfLL = 0;
        _pfPollingForConn = null;
        _pfTaskInfo.status = 'timeout';
        _pfTaskInfo.progress = `超时（已运行 ${Math.round(el)}s）`;
        updatePfTaskInfo();
        await pfLog(`✗ 任务超时：已运行 ${Math.round(el)}s，超过上限 ${clientTimeout}s`, 'err');
        toast('采样超时，请检查后端日志', 'error');
        return;
      }

      // 更新任务信息面板
      _pfTaskInfo.status = d.status || 'running';
      if (d.type) _pfTaskInfo.type = d.type;
      if (d.event) _pfTaskInfo.event = d.event;
      if (overtime && d.status === 'running') {
        _pfTaskInfo.progress = `后端仍在执行 (${Math.round(el)}s)`;
        _pfTaskInfo.progressPercent = Math.round(pct);
      } else if (d.status === 'running' && serverProgress > 0) {
        _pfTaskInfo.progress = `后端进度 ${Math.round(serverProgress)}%`;
        _pfTaskInfo.progressPercent = Math.round(pct);
      } else {
        _pfTaskInfo.progress = d.status === 'running' ? `等待后端进度 (${Math.round(el)}s)` : (d.status || '-');
        _pfTaskInfo.progressPercent = Math.round(pct);
      }
      updatePfTaskInfo();

      if(d.status==='completed'||d.status==='failed') {
        clearInterval(_pfPollTimer); _pfPollTimer = null; _pfLL = 0;
        _pfPollingForConn = null;
        if(d.status==='completed') {
          if(pfFill) pfFill.style.width='100%';
          if(pfPct) pfPct.textContent='100%';
          _pfTaskInfo.progress = '100%';
          _pfTaskInfo.progressPercent = 100;
          _pfTaskInfo.status = 'completed';
          _pfTaskInfo.outputFile = d.output_file;
          updatePfTaskInfo();
          const dur = Math.round((Date.now() - _pfStart) / 1000);
          await pfLog(`✓ 采样完成（前端观察耗时 ${dur}s）`, 'ok', d.updated_at);
          if (d.output_file) {
            await pfLog(`📄 输出文件: ${d.output_file}`, 'info');
          }
          toast('完成！','success'); loadLocalFiles(); loadPfHistory();
        } else {
          _pfTaskInfo.status = 'failed';
          updatePfTaskInfo();
          await pfLog('✗ 任务失败: ' + (d.message || '未知错误'), 'err');
          toast('失败','error');
        }

        if (_currentConnId && _pfTasksByConn[_currentConnId]) {
          delete _pfTasksByConn[_currentConnId];
        }
        if (typeof _clearPersistedPfTask === 'function' && _currentConnId) {
          _clearPersistedPfTask(_currentConnId);
        }
        _pfTaskId = null;
        _pfLastMsg = '';
        _pfLastProgressLog = 0;
      }
    } else {
      _pfLL = d.logs?.length||0;
    }
  } catch(e) { console.error('[pfPoll] error:', e); }
}

function _isQuickTask() {
  // Dump 类任务（thread/heap）不需要周期进度日志
  return _pfMode === 'dump' || (_pfDur && _pfDur <= 15);
}

async function pfLog(msg, lv='info', timestamp=null) {
  const el = document.getElementById('pfl-panel-log');
  if (!el) return;  // 面板不存在时静默跳过
  if(el.children.length===1 && el.children[0].textContent==='等待启动...') el.innerHTML='';
  const cls = {info:'o-line',dim:'o-dim',ok:'o-ok',error:'o-err',warn:'o-warn',success:'o-ok'}[lv]||'o-line';
  const ts = timestamp ? formatProfilerLogTime(timestamp) : new Date().toLocaleTimeString('zh-CN', {hour12:false});
  const d = document.createElement('div');
  d.className = cls;
  d.innerHTML = '<span style="color:var(--tx3);margin-right:6px">[' + ts + ']</span>' + msg.replace(/\n/g, '<br>');
  el.appendChild(d);
  el.scrollTop = el.scrollHeight;

  const _cntEl = document.getElementById('pfLogCnt');
  if(_cntEl) _cntEl.textContent = (el?.children.length||0) + '行';
}
function pfClearLog() {
  const el = document.getElementById('pfl-panel-log');
  if(el) el.innerHTML='<div class="o-dim">等待启动...</div>';
  const c = document.getElementById('pfLogCnt'); if(c) c.textContent='0行';

  // 注意：不再删除数据库中的历史任务记录
  // 之前 pfClearLog() 会调用 DELETE /api/profile/logs/{conn_id}，
  // 导致该连接下所有 profiler_tasks 被删除，重复采集时历史数据丢失

  // 清空当前连接的任务状态缓存（如果任务已完成或被取消）
  if (_currentConnId && _pfTasksByConn[_currentConnId] && !_pfTaskId) {
    delete _pfTasksByConn[_currentConnId];
  }
}

// ── Profiler History (handled by SamplingHistory component) ──────────────
// Legacy pagination functions kept as no-ops for backwards compatibility
function pfHistPrevPage() {}
function pfHistNextPage() {}
function pfHistJumpToPage() {}
function pfHistChangePageSize() {}
function renderPfHistoryPage() {}

// ── Unified History Panel ──────────────────────────────────────────────────
var _historyReturnTo = 'workspace';  // which tab to return to when pressing "back"
var _historyReturnMode = 'workspace';
var _historyReturnWorkspaceTab = 'monitor';

function rememberWorkspaceHistoryReturn(tabId) {
  if (tabId && tabId !== 'history') {
    _historyReturnWorkspaceTab = tabId;
  }
  _historyReturnMode = 'workspace';
  _historyReturnTo = 'workspace';
}

function historyGoBack() {
  var target = _historyReturnTo || 'workspace';
  if (_historyReturnMode === 'workspace' || target === 'workspace' || target === 'connections') {
    // 历史记录可从新工作台进入，返回时必须回到新工作台，避免露出过渡期的旧连接中心。
    if (typeof window.showWorkspace === 'function') {
      window.showWorkspace();
    } else {
      setMainShellMode('workspace');
    }
    var workspaceTab = _historyReturnWorkspaceTab || 'monitor';
    if (workspaceTab !== 'history' && window.ConnectionWorkspace && typeof ConnectionWorkspace.switchTab === 'function') {
      ConnectionWorkspace.switchTab(workspaceTab);
    }
    return;
  }
  switchTab(target);
}

function openSamplingHistory() {
  if (window.__mainShellMode !== 'legacy' && window.ConnectionWorkspace && typeof ConnectionWorkspace.switchTab === 'function') {
    var focusConn = window.ConnectionStore && typeof ConnectionStore.getFocusConnection === 'function'
      ? ConnectionStore.getFocusConnection()
      : null;
    rememberWorkspaceHistoryReturn((focusConn && focusConn.tab && focusConn.tab !== 'history') ? focusConn.tab : 'sampling');
    ConnectionWorkspace.switchTab('history');
    setTimeout(function() {
      if (typeof loadHistory === 'function') loadHistory();
    }, 0);
    return;
  }
  switchTab('history');
}

function toggleHistoryConnFilter() {
  var checkbox = getHistoryViewElement('filter-checkbox');
  if (!checkbox) return;
  var container = getHistoryViewElement('panel-profiler');
  if (!container || typeof SamplingHistory === 'undefined') return;

  if (checkbox.checked && _currentConnId) {
    SamplingHistory.mount(container, { mode: 'global', connectionId: _currentConnId });
  } else {
    checkbox.checked = false;
    SamplingHistory.mount(container, { mode: 'global' });
  }
}

function updateHistoryFilterLabel() {
  var label = getHistoryViewElement('filter-label');
  var podSpan = getHistoryViewElement('filter-pod');
  if (!label) return;

  if (_currentConnId && window._connections) {
    var conn = _connections.find(function(c) { return c.id === _currentConnId; });
    if (conn) {
      label.style.display = 'flex';
      if (podSpan) podSpan.textContent = conn.pod_name || '';
      return;
    }
  }
  label.style.display = 'none';
}

async function loadConnectionProfilerLogs(connId) {
  // 从数据库加载连接的采样日志
  const el = document.getElementById('pfl-panel-log');
  if (!el) return;

  try {
    const r = await fetch(`${API}/profile/logs/${connId}`);
    const d = await r.json();
    const logs = d.logs || [];

    if (logs.length === 0) {
      el.innerHTML = '<div class="o-dim">暂无采样日志</div>';
      const c = document.getElementById('pfLogCnt');
      if (c) c.textContent = '0行';
      return;
    }

    el.innerHTML = '';
    logs.forEach(log => {
      const cls = {info:'o-line',dim:'o-dim',ok:'o-ok',error:'o-err',warn:'o-warn',success:'o-ok'}[log.level]||'o-line';
      const d = document.createElement('div');
      d.className = cls;
      // 使用 innerHTML 保留换行符
      d.innerHTML = log.message.replace(/\n/g, '<br>');
      el.appendChild(d);
    });
    el.scrollTop = el.scrollHeight;

    const c = document.getElementById('pfLogCnt');
    if (c) c.textContent = logs.length + '行';
  } catch(e) {
    console.error('Failed to load profiler logs:', e);
    el.innerHTML = '<div class="o-dim">加载日志失败</div>';
  }
}

// ── Pod Monitor ───────────────────────────────────────────────────────────────
window._monitorSnapshotInflight = window._monitorSnapshotInflight || null;
window._monitorSnapshotLast = window._monitorSnapshotLast || { key: '', at: 0 };
window._monitorPollingKey = window._monitorPollingKey || '';
window._monitorPollingPayload = window._monitorPollingPayload || null;

function renderMonitorMessage(message, type = 'info') {
  const color = type === 'error' ? 'var(--a5)' : type === 'warn' ? 'var(--a4)' : 'var(--tx3)';
  const html = `<div style="color:${color};padding:30px;text-align:center;line-height:1.8"><div style="font-size:14px;margin-bottom:8px">${esc(message)}</div><div style="font-size:11px;color:var(--tx3)">请在连接中心确认当前 Pod 连接后重试</div></div>`;
  ['pmp-ov','pmp-dk','pmp-pr','pmp-nw','pmp-ev','pmp-cf'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.innerHTML = html;
  });
}

function stopMonitorBackendPolling() {
  const payload = window._monitorPollingPayload;
  if (!payload) return;
  fetch(`${API}/monitor/stop-polling`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload),
  }).catch(() => {});
  window._monitorPollingPayload = null;
  window._monitorPollingKey = '';
}

async function loadSnap(silent = false) {
  if (!silent) _syncState();
  if(window.ConnectionGuard && !ConnectionGuard.guard('monitor')) return;
  const t = getCurrentPodTarget();
  if(!t.cluster_name || !t.pod_name) {
    const msg = '请先在连接中心建立或选择一个 Pod 连接';
    if(!silent) toast(msg, 'warn');
    renderMonitorMessage(msg, 'warn');
    return;
  }
  const snapKey = `${t.cluster_name}/${t.namespace}/${t.pod_name}/${t.container || ''}`;
  const now = Date.now();
  if (silent && window._monitorSnapshotInflight?.key === snapKey) return window._monitorSnapshotInflight.promise;
  if (silent && window._monitorSnapshotLast.key === snapKey && now - window._monitorSnapshotLast.at < 5000) return _snap;
  // 静默刷新时不显示 loading，避免闪烁
  if (!silent) {
    const loadingHtml = `<div style="color:var(--tx3);padding:30px;text-align:center"><div style="font-size:14px;margin-bottom:8px">⏳ 加载监控数据中...</div><div style="font-size:11px">${esc(t.cluster_name)} / ${esc(t.namespace)} / ${esc(t.pod_name)}，首次加载可能需要 10-20 秒（kubectl 采集）</div></div>`;
    document.getElementById('pmp-ov').innerHTML = loadingHtml;
    document.getElementById('pmp-dk').innerHTML = loadingHtml;
    document.getElementById('pmp-pr').innerHTML = loadingHtml;
    document.getElementById('pmp-nw').innerHTML = loadingHtml;
  }
  const requestPromise = safePost(`${API}/monitor/snapshot`, t, 60000);
  window._monitorSnapshotInflight = { key: snapKey, promise: requestPromise };
  try {
    // snapshot 接口涉及多次 kubectl 调用，超时设为 60 秒
    _snap = await requestPromise;
    window._monitorSnapshotLast = { key: snapKey, at: Date.now() };
    if(_snap.error) {
      if(!silent) toast(_snap.error, 'error');
      renderMonitorMessage(_snap.error, 'error');
      return;
    }
    document.getElementById('pmTs').textContent = new Date().toLocaleTimeString('zh-CN',{hour12:false});
    renderOverview(_snap); renderProcs(_snap); renderNetwork(_snap); renderDisk(_snap); renderEvents(_snap); renderConfig(_snap);
    const ctrs = _snap.pod_info?.containers||[];
    const lcsel = document.getElementById('logCtr');
    if(lcsel) lcsel.innerHTML = ctrs.map(c => `<option value="${esc(c.name)}">${esc(c.name)}</option>`).join('');
    // start history polling
    if (window._monitorPollingKey !== snapKey) {
      stopMonitorBackendPolling();
      fetch(`${API}/monitor/start-polling`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(t)}).catch(()=>{});
      window._monitorPollingKey = snapKey;
      window._monitorPollingPayload = t;
    }
    clearInterval(window._histTimer);
    window._histTimer = setInterval(async () => {
      // 只在监控 tab 激活且指标子 tab 可见时才请求
      const monitorTab = document.getElementById('tab-monitor');
      if (!monitorTab || !monitorTab.classList.contains('on')) return;
      const r2 = await fetch(`${API}/monitor/history`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(t)}).catch(()=>null);
      if(r2) { _histData = await r2.json(); if(document.getElementById('pms-mt')?.classList.contains('on')) renderMetrics(_snap); }
    }, 16000);
  } catch(e) {
    const msg = '加载失败: '+e.message;
    if(!silent) toast(msg, 'error');
    renderMonitorMessage(msg, 'error');
  } finally {
    if (window._monitorSnapshotInflight?.promise === requestPromise) {
      window._monitorSnapshotInflight = null;
    }
  }
}

// ── 监控面板自动刷新 ─────────────────────────────────────────────────────────────
window._monitorAutoTimer = null;

function toggleAutoRefresh(seconds) {
  seconds = parseInt(seconds) || 0;
  if (window._monitorAutoTimer) {
    clearInterval(window._monitorAutoTimer);
    window._monitorAutoTimer = null;
  }
  if (seconds > 0) {
    // 立即静默刷新一次
    loadSnap(true);
    // 设置定时静默刷新（避免闪烁）
    window._monitorAutoTimer = setInterval(() => {
      const monitorTab = document.getElementById('tab-monitor');
      if (monitorTab && monitorTab.classList.contains('on')) {
        loadSnap(true);
      }
    }, seconds * 1000);
  }
}

function renderOverview(snap) {
  const info = snap.pod_info, top = snap.top_metrics||{}, cm = snap.container_metrics||{};
  const ctrs = info.containers||[];
  const readyN = ctrs.filter(c=>c.ready).length, restN = ctrs.reduce((s,c)=>s+c.restart_count,0);
  const mu = cm.cgroup_mem_usage_bytes||0, ml = cm.cgroup_mem_limit_bytes||0;
  const mp = ml ? Math.round(mu/ml*100) : 0;
  const dp = cm.disk_use_pct ? parseInt(cm.disk_use_pct) : 0;
  const dc = dp>85?'var(--a5)':dp>70?'var(--a4)':'var(--a3)';
  // 获取当前 Arthas 版本
  const curConn = _connections.find(c => c.id === _currentConnId);
  const arthasVer = curConn?.arthas_version || '';
  const arthasVerHtml = arthasVer ? `<div class="sc" style="--sc-ac:var(--a)"><div class="sc-lbl">Arthas</div><div class="sc-val" style="font-size:16px;color:var(--a3)">v${esc(arthasVer)}</div><div class="sc-sub">${curConn?.local_port ? 'port: ' + curConn.local_port : ''}</div></div>` : '';

  let html = `<div class="sg">
    <div class="sc" style="--sc-ac:var(--a)"><div class="sc-lbl">状态</div><div class="sc-val" style="font-size:16px;color:${info.phase==='Running'?'var(--a3)':'var(--a4)'}">${info.phase}</div><div class="sc-sub">${info.namespace}/${info.name}</div></div>
    <div class="sc" style="--sc-ac:var(--a3)"><div class="sc-lbl">容器就绪</div><div class="sc-val">${readyN}<span style="font-size:14px;color:var(--tx2)">/${ctrs.length}</span></div><div class="sc-sub">重启合计: ${restN}</div></div>
    <div class="sc" style="--sc-ac:var(--a4)"><div class="sc-lbl">CPU</div><div class="sc-val" style="font-size:16px">${top.cpu_raw||'—'}</div><div class="sc-sub">毫核 (kubectl top)</div></div>
    <div class="sc" style="--sc-ac:var(--a2)"><div class="sc-lbl">内存</div><div class="sc-val" style="font-size:16px">${mu?fmtSz(mu):(top.memory_raw||'—')}</div><div class="sc-sub">限制: ${ml?fmtSz(ml):'—'}${mp?' · '+mp+'%':''}</div></div>
  </div>
  <div class="sg">
    <div class="sc" style="--sc-ac:var(--a)"><div class="sc-lbl">节点</div><div class="sc-val" style="font-size:13px">${info.node_name||'—'}</div><div class="sc-sub">HostIP: ${info.host_ip||'—'}</div></div>
    <div class="sc" style="--sc-ac:var(--a6)"><div class="sc-lbl">Pod IP</div><div class="sc-val" style="font-size:14px">${info.pod_ip||'—'}</div><div class="sc-sub">QoS: ${info.qos_class||'—'}</div></div>
    <div class="sc" style="--sc-ac:var(--a3)"><div class="sc-lbl">运行时长</div><div class="sc-val">${info.age||'—'}</div><div class="sc-sub">${fmtTs(info.creation_timestamp)}</div></div>
    <div class="sc" style="--sc-ac:${dc}"><div class="sc-lbl">磁盘 /</div><div class="sc-val" style="color:${dc}">${cm.disk_use_pct||'—'}</div><div class="sc-sub">${cm.disk_used||''}/${cm.disk_total||''}${cm.disk_mounts?.length?' · '+cm.disk_mounts.length+'挂载点':''}</div></div>
    ${arthasVerHtml}
  </div>`;

  html += `<div style="margin-bottom:10px"><div style="font-size:10px;color:var(--tx2);text-transform:uppercase;letter-spacing:1px;margin-bottom:7px">Pod 条件</div>
  <div class="conds">${(info.conditions||[]).map(c => `<div class="cond"><div class="cond-t">${c.type}</div><div class="cond-v" style="color:${c.status==='True'?'var(--a3)':'var(--a5)'}">${c.status==='True'?'✓':'✗'} ${c.status}</div></div>`).join('')}</div></div>`;

  html += `<div style="font-size:10px;color:var(--tx2);text-transform:uppercase;letter-spacing:1px;margin-bottom:7px">容器 (${ctrs.length})</div>
  ${ctrs.map((c,i) => {
    const sc = c.state==='running'?'bg':c.state==='waiting'?'by':'br';
    return `<div class="ctr-card">
      <div class="ctr-hd">
        <div><div class="ctr-nm">${esc(c.name)}</div><div class="ctr-img">${esc(c.image)}</div></div>
        <div class="ctr-badges">
          <span class="badge ${sc}">${c.state}</span>
          <span class="badge ${c.ready?'bg':'by'}">${c.ready?'Ready':'NotReady'}</span>
          ${c.restart_count>0?`<span class="badge br">×${c.restart_count}</span>`:''}
          ${c.liveness_probe?'<span class="badge bb">Liveness</span>':''}
          ${c.readiness_probe?'<span class="badge bb">Readiness</span>':''}
        </div>
      </div>
      <div class="ctr-body" id="ctrbd${i}">
        <div class="ctr-res">
          <div class="ctr-ri"><div class="ctr-rl">CPU 请求</div><div class="ctr-rv">${c.requests_cpu||'—'}</div></div>
          <div class="ctr-ri"><div class="ctr-rl">CPU 限制</div><div class="ctr-rv">${c.limits_cpu||'—'}</div></div>
          <div class="ctr-ri"><div class="ctr-rl">内存 请求</div><div class="ctr-rv">${c.requests_mem||'—'}</div></div>
          <div class="ctr-ri"><div class="ctr-rl">内存 限制</div><div class="ctr-rv">${c.limits_mem||'—'}</div></div>
        </div>
        ${c.ports.length?`<div style="font-size:11px;margin-bottom:6px"><b style="color:var(--tx2)">Ports:</b> ${c.ports.map(p=>`<code>${p.containerPort}/${p.protocol||'TCP'}</code>`).join(' ')}</div>`:''}
        ${c.state_reason?`<div style="font-size:11px;color:var(--a4)">原因: ${esc(c.state_reason)}</div>`:''}
        ${c.state_message?`<div style="font-size:10px;color:var(--tx2);margin-top:3px">${esc(c.state_message)}</div>`:''}
      </div>
    </div>`;
  }).join('')}`;

  html += `<div class="two-col">
    <div class="ic"><div class="ic-hd"><span>🏷️</span><span class="ic-tt">Labels</span></div>
    <div class="ic-bd"><div class="tagw">${Object.entries(info.labels||{}).map(([k,v])=>`<div class="ltag"><b>${esc(k)}</b>: ${esc(v)}</div>`).join('')||'<span style="color:var(--tx3)">无</span>'}</div></div></div>
    <div class="ic"><div class="ic-hd"><span>ℹ️</span><span class="ic-tt">基本信息</span></div>
    <div class="ic-bd">${mkv('Service Account',info.service_account||'—')}${mkv('Restart Policy',info.restart_policy)}${mkv('QoS Class',info.qos_class||'—')}${cm.open_fds!=null?mkv('打开 FD 数',cm.open_fds):''}</div></div>
  </div>`;
  document.getElementById('pmp-ov').innerHTML = html;
}
function toggleCtr(i) { const el = document.getElementById(`ctrbd${i}`); if(el) el.classList.toggle('open'); }

function renderMetrics(snap) {
  const cm = snap?.container_metrics||{}, top = snap?.top_metrics||{};
  const mu = cm.cgroup_mem_usage_bytes||0, ml = cm.cgroup_mem_limit_bytes||0, mp = ml?Math.round(mu/ml*100):0;
  const dp = cm.disk_use_pct?parseInt(cm.disk_use_pct):0;
  const lc = snap?.pod_info?.containers?.[0]?.limits_cpu||'';
  let lm = 0; if(lc.endsWith('m')) lm=parseFloat(lc); else if(lc) lm=parseFloat(lc)*1000;
  const cpuM = top.cpu_millicores||0, cp = lm>0?Math.min(100,Math.round(cpuM/lm*100)):0;
  const cc = cp>85?'var(--a5)':cp>70?'var(--a4)':'var(--a)';
  const mc = mp>85?'var(--a5)':mp>70?'var(--a4)':'var(--a2)';
  const dc = dp>85?'var(--a5)':dp>70?'var(--a4)':'var(--a3)';
  const gauge = (pct,color,lbl,unit) => {
    const r=30,cx=38,cy=38,ci=2*Math.PI*r,fill=ci*(1-Math.min(pct,100)/100);
    return `<div class="gauge-ring"><svg viewBox="0 0 76 76"><circle class="gr-bg" cx="${cx}" cy="${cy}" r="${r}"/><circle class="gr-f" cx="${cx}" cy="${cy}" r="${r}" stroke="${color}" stroke-dasharray="${ci}" stroke-dashoffset="${fill}"/></svg><div class="gauge-lbl"><span class="gauge-pct" style="color:${color}">${lbl}</span><span class="gauge-unit">${unit}</span></div></div>`;
  };
  let html = `<div class="ch-grid">
    <div class="gauge-card"><div class="gauge-hd"><div class="gauge-live"></div><span class="gauge-tt">CPU</span><span class="gauge-bv" style="color:${cc}">${top.cpu_raw||'—'}</span></div>
    <div class="gauge-in">${gauge(cp,cc,cp+'%','CPU')}<div class="gauge-rows">${gRow('当前',top.cpu_raw||'—')}${gRow('限制',lc||'未设置')}${gRow('使用率',lm?cp+'%':'—')}${gRow('节流次数',cm.cpu_nr_throttled||'—')}</div></div></div>

    <div class="gauge-card"><div class="gauge-hd"><div class="gauge-live"></div><span class="gauge-tt">内存</span><span class="gauge-bv" style="color:${mc}">${mu?fmtSz(mu):(top.memory_raw||'—')}</span></div>
    <div class="gauge-in">${gauge(mp,mc,mp+'%','MEM')}<div class="gauge-rows">${gRow('cgroup用量',mu?fmtSz(mu):'—')}${gRow('cgroup限制',ml?fmtSz(ml):'—')}${gRow('kubectl top',top.memory_raw||'—')}${gRow('使用率',mp?mp+'%':'—')}</div></div></div>

    <div class="gauge-card"><div class="gauge-hd"><div class="gauge-live"></div><span class="gauge-tt">磁盘 /</span><span class="gauge-bv" style="color:${dc}">${cm.disk_use_pct||'—'}</span></div>
    <div class="gauge-in">${gauge(dp,dc,cm.disk_use_pct||'—','DISK')}<div class="gauge-rows">${gRow('总量',cm.disk_total||'—')}${gRow('已用',cm.disk_used||'—')}${gRow('可用',cm.disk_avail||'—')}</div></div></div>

    <div class="gauge-card"><div class="gauge-hd"><span class="gauge-tt">其他指标</span></div>
    <div class="gauge-in"><div class="gauge-rows" style="width:100%">
      ${gRow('打开 FD 数',cm.open_fds||'—')}
      ${gRow('CPU 节流时间',cm.cpu_throttled_time!=null?(cm.cpu_throttled_time/1e9).toFixed(2)+'s':'—')}
      ${gRow('CPU 节流次数',cm.cpu_nr_throttled||'—')}
      ${gRow('Restart 合计',snap?.pod_info?.containers?.reduce((s,c)=>s+c.restart_count,0)||0)}
      ${gRow('QoS Class',snap?.pod_info?.qos_class||'—')}
    </div></div></div>
  </div>`;

  html += _histData.length>=2
    ? `<div class="ch-grid">
        <div class="ch-card"><div class="ch-hd"><span class="ch-tt">CPU 历史 (毫核)</span><span id="hcv" style="font-size:14px;color:var(--a)"></span></div><div class="ch-body"><canvas id="chCpu" height="70"></canvas></div></div>
        <div class="ch-card"><div class="ch-hd"><span class="ch-tt">内存历史</span><span id="hmv" style="font-size:14px;color:var(--a2)"></span></div><div class="ch-body"><canvas id="chMem" height="70"></canvas></div></div>
      </div>`
    : '<div style="color:var(--tx3);font-size:11px;padding:10px">历史趋势图将在后台采集 15 秒后可用（每 15s 一个采样点）</div>';

  document.getElementById('pmp-mt').innerHTML = html;
  if(_histData.length>=2) {
    const last = _histData[_histData.length-1];
    const cv = document.getElementById('hcv'), mv = document.getElementById('hmv');
    if(cv) cv.textContent = last.cpu_raw||Math.round(last.cpu_m)+'m';
    if(mv) mv.textContent = last.mem_raw||fmtSz(last.mem_bytes||0);
    drawSpark('chCpu', _histData.map(d=>d.cpu_m||0), '#38bdf8');
    drawSpark('chMem', _histData.map(d=>d.mem_bytes||0), '#a78bfa');
  }
}

function drawSpark(id, vals, color) {
  const c = document.getElementById(id); if(!c) return;
  const W = c.parentElement.clientWidth-24, H = 70; c.width=W; c.height=H;
  const ctx = c.getContext('2d'); ctx.clearRect(0,0,W,H);
  const max = Math.max(...vals,1), rng = max||1;
  ctx.strokeStyle='rgba(255,255,255,.05)'; ctx.lineWidth=1;
  for(let i=1;i<4;i++){const y=H*i/4;ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(W,y);ctx.stroke();}
  const pts = vals.map((v,i)=>({x:i/(vals.length-1)*W, y:H-(v/rng)*(H-10)-5}));
  ctx.beginPath(); pts.forEach((p,i)=>i===0?ctx.moveTo(p.x,p.y):ctx.lineTo(p.x,p.y));
  ctx.lineTo(W,H); ctx.lineTo(0,H); ctx.closePath();
  const g=ctx.createLinearGradient(0,0,0,H); g.addColorStop(0,color+'44'); g.addColorStop(1,color+'00');
  ctx.fillStyle=g; ctx.fill();
  ctx.beginPath(); pts.forEach((p,i)=>i===0?ctx.moveTo(p.x,p.y):ctx.lineTo(p.x,p.y));
  ctx.strokeStyle=color; ctx.lineWidth=2; ctx.stroke();
}

function renderProcs(snap) {
  const procs = snap.processes || snap.container_metrics?.processes || [];
  const el = document.getElementById('pmp-pr');
  if(!procs.length) {
    const phase = snap.pod_info?.phase || 'Unknown';
    const container = snap.target_container || '—';
    const cmErr = snap.container_metrics?.error || snap.processes_error || '';
    el.innerHTML=`<div style="color:var(--tx3);padding:30px;text-align:center">
      <div style="margin-bottom:8px">无进程数据</div>
      <div style="font-size:11px;opacity:0.7">
        Pod 状态: ${esc(phase)} | 容器: ${esc(container)}
        ${cmErr ? '<br>原因: '+esc(cmErr) : ''}
        ${phase !== 'Running' ? '<br>需要 Pod 处于 Running 状态' : ''}
      </div>
    </div>`;
    console.warn('[renderProcs] 无进程数据:', { phase, container, cmErr, hasCm: !!snap.container_metrics });
    return;
  }
  const normProc = p => ({
    pid: p.pid || '?',
    user: p.user || '—',
    cpu: p.cpu ?? p.cpu_percent ?? 0,
    mem: p.mem ?? p.mem_percent ?? 0,
    stat: p.stat || p.status || '—',
    cmd: p.cmd || p.name || '—',
    name: p.name || '',
    threads: p.threads || '',
    cpu_ticks: p.cpu_ticks || 0,
  });
  // 调试：打印进程数据结构
  console.log('[renderProcs] processes data:', procs.slice(0, 2));
  el.innerHTML = `<div style="background:var(--bg2);border:1px solid var(--ln);border-radius:7px;overflow:hidden;margin-bottom:8px">
    <table class="ptbl"><thead><tr><th>PID</th><th>进程名</th><th>状态</th><th>线程</th><th>CPU ticks</th><th>命令</th></tr></thead>
    <tbody>${procs.map(raw=>{ const p = normProc(raw); return `<tr><td class="ppid">${esc(p.pid)}</td><td style="color:var(--a)">${esc(p.name)}</td><td class="ps-${(p.stat||'S')[0]}">${esc(p.stat)}</td><td>${esc(p.threads)}</td><td>${esc(p.cpu_ticks)}</td><td style="max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(p.cmd)}">${esc(p.cmd)}</td></tr>`; }).join('')}</tbody>
    </table></div>
  <div style="font-size:10px;color:var(--tx3)">状态: <code>R</code>=运行中 <code>S</code>=睡眠 <code>D</code>=不可中断 <code>Z</code>=僵尸 <code>T</code>=停止</div>`;
}

function renderNetwork(snap) {
  const net = snap.container_metrics?.network||[], info = snap.pod_info;
  const el = document.getElementById('pmp-nw');
  let html = `<div class="two-col">
    <div class="ic"><div class="ic-hd"><span>🌐</span><span class="ic-tt">Pod 网络</span></div>
    <div class="ic-bd">${mkv('Pod IP',info.pod_ip||'—')}${mkv('Host IP',info.host_ip||'—')}${mkv('节点',info.node_name||'—')}</div></div>
    <div class="ic"><div class="ic-hd"><span>🔌</span><span class="ic-tt">暴露端口</span></div>
    <div class="ic-bd">${(info.containers||[]).flatMap(c=>c.ports.map(p=>mkv(c.name+':'+p.containerPort,p.protocol||'TCP'))).join('')||mkv('无','—')}</div></div>
  </div>`;
  if(net.length) {
    html += `<div style="background:var(--bg2);border:1px solid var(--ln);border-radius:7px;overflow:hidden">
    <table class="ptbl"><thead><tr><th>接口</th><th>RX 字节</th><th>RX 包</th><th>RX 错误</th><th>TX 字节</th><th>TX 包</th><th>TX 错误</th></tr></thead>
    <tbody>${net.map(n=>`<tr><td style="color:var(--a)">${esc(n.iface)}</td><td style="color:var(--a3)">${fmtSz(n.rx_bytes)}</td><td style="color:var(--a3)">${n.rx_packets.toLocaleString()}</td><td class="${n.rx_errors?'pc':''}">${n.rx_errors}</td><td style="color:var(--a4)">${fmtSz(n.tx_bytes)}</td><td style="color:var(--a4)">${n.tx_packets.toLocaleString()}</td><td class="${n.tx_errors?'pc':''}">${n.tx_errors}</td></tr>`).join('')}</tbody>
    </table></div>
    <div style="font-size:10px;color:var(--tx3);margin-top:6px">注：数据为 Pod 启动至今累计值，非实时速率</div>`;
  }
  el.innerHTML = html;
}

function renderDisk(snap) {
  const cm = snap.container_metrics || {};
  const mounts = cm.disk_mounts || [];
  const el = document.getElementById('pmp-dk');
  if (!mounts.length) {
    const phase = snap.pod_info?.phase || 'Unknown';
    el.innerHTML = `<div style="color:var(--tx3);padding:30px;text-align:center">
      <div style="margin-bottom:8px">无磁盘数据</div>
      <div style="font-size:11px;opacity:0.7">Pod 状态: ${esc(phase)} | 需要 Pod Running 且 df 可用</div>
    </div>`;
    return;
  }

  // 网络挂载关键字
  const netFs = ['nfs','nfs4','cifs','smb','fuse.sshfs','glusterfs','ceph','9p'];
  const isNet = m => netFs.some(nf => (m.fs_type||'').toLowerCase().includes(nf) || m.filesystem.toLowerCase().includes(nf)) || m.filesystem.includes(':');

  let html = `<div style="font-size:10px;color:var(--tx2);text-transform:uppercase;letter-spacing:1px;margin-bottom:7px">磁盘挂载点 (${mounts.length})</div>`;
  html += `<div style="background:var(--bg2);border:1px solid var(--ln);border-radius:7px;overflow:hidden;margin-bottom:8px">
    <table class="ptbl" style="font-size:11px"><thead><tr><th>Filesystem</th><th>Type</th><th>Size</th><th>Used</th><th>Avail</th><th>Use%</th><th>Mounted on</th></tr></thead>
    <tbody>${mounts.map(m => {
      const pct = m.use_pct_val || 0;
      const barColor = pct > 85 ? 'var(--a5)' : pct > 70 ? 'var(--a4)' : 'var(--a3)';
      const net = isNet(m);
      const netTag = net ? '<span style="font-size:9px;color:var(--a);background:var(--bg3);border-radius:3px;padding:1px 5px;margin-left:4px">网络</span>' : '';
      const fsType = m.fs_type || '';
      return `<tr style="${net?'background:rgba(0,212,255,0.04)':''}">
        <td style="color:var(--tx2);max-width:240px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(m.filesystem)}">${esc(m.filesystem)}${netTag}</td>
        <td style="color:var(--tx3)">${esc(fsType)}</td>
        <td>${esc(m.size)}</td>
        <td style="color:var(--a4)">${esc(m.used)}</td>
        <td style="color:var(--a3)">${esc(m.avail)}</td>
        <td><div style="display:flex;align-items:center;gap:4px"><div style="background:var(--bg3);border-radius:2px;width:50px;height:6px;overflow:hidden;flex-shrink:0"><div style="background:${barColor};height:100%;width:${Math.min(pct,100)}%;border-radius:2px"></div></div><span style="color:${barColor};font-weight:600;min-width:32px">${esc(m.use_pct)}</span></div></td>
        <td style="color:var(--a);font-weight:600">${esc(m.mount)}</td>
      </tr>`;
    }).join('')}</tbody></table></div>`;

  // 网络挂载详情
  const netMounts = mounts.filter(isNet);
  if (netMounts.length) {
    html += `<div style="font-size:10px;color:var(--tx2);text-transform:uppercase;letter-spacing:1px;margin:10px 0 7px">网络挂载详情 (${netMounts.length})</div>`;
    html += netMounts.map(m => {
      const pct = m.use_pct_val || 0;
      const barColor = pct > 85 ? 'var(--a5)' : pct > 70 ? 'var(--a4)' : 'var(--a3)';
      return `<div style="background:var(--bg2);border:1px solid var(--ln);border-radius:7px;padding:12px;margin-bottom:8px;border-left:3px solid var(--a)">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
          <span style="font-size:13px;color:var(--a);font-weight:700">${esc(m.mount)}</span>
          <span style="font-size:11px;color:var(--tx3);background:var(--bg3);border-radius:3px;padding:1px 6px">${esc(m.fs_type||'—')}</span>
          <span style="margin-left:auto;font-size:14px;font-weight:700;color:${barColor}">${esc(m.use_pct)}</span>
        </div>
        <div style="background:var(--bg3);border-radius:3px;height:8px;overflow:hidden;margin-bottom:10px">
          <div style="background:${barColor};height:100%;width:${Math.min(pct,100)}%;border-radius:3px;transition:width .3s"></div>
        </div>
        <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:6px;font-size:11px;margin-bottom:8px">
          <div style="background:var(--bg3);border-radius:4px;padding:6px 8px"><div style="font-size:9px;color:var(--tx3);margin-bottom:2px">总量</div><div style="color:var(--a)">${esc(m.size)}</div></div>
          <div style="background:var(--bg3);border-radius:4px;padding:6px 8px"><div style="font-size:9px;color:var(--tx3);margin-bottom:2px">已用</div><div style="color:var(--a4)">${esc(m.used)}</div></div>
          <div style="background:var(--bg3);border-radius:4px;padding:6px 8px"><div style="font-size:9px;color:var(--tx3);margin-bottom:2px">可用</div><div style="color:var(--a3)">${esc(m.avail)}</div></div>
          <div style="background:var(--bg3);border-radius:4px;padding:6px 8px"><div style="font-size:9px;color:var(--tx3);margin-bottom:2px">使用率</div><div style="color:${barColor}">${esc(m.use_pct)}</div></div>
        </div>
        <div style="font-size:11px;border-top:1px solid var(--ln);padding-top:8px;display:grid;grid-template-columns:auto 1fr;gap:4px 12px">
          <span style="color:var(--tx3)">挂载源</span><span style="color:var(--a);word-break:break-all">${esc(m.mount_source||m.filesystem)}</span>
          <span style="color:var(--tx3)">文件系统</span><span style="color:var(--tx2)">${esc(m.fs_type||'—')}</span>
          <span style="color:var(--tx3)">挂载选项</span><span style="color:var(--tx2);word-break:break-all;font-size:10px">${esc(m.mount_options||'—')}</span>
        </div>
      </div>`;
    }).join('');
  }

  el.innerHTML = html;
}

function renderEvents(snap) {
  const events = snap.events||[], el = document.getElementById('pmp-ev');
  const warns = events.filter(e=>e.type==='Warning').length;
  const bdg = document.getElementById('evBdg');
  if(bdg) bdg.innerHTML = warns>0 ? `<span style="margin-left:4px;background:var(--a4);color:#0b0f18;border-radius:10px;padding:1px 6px;font-size:9px">${warns}</span>` : '';
  if(!events.length) { el.innerHTML='<div style="color:var(--tx3);padding:30px;text-align:center">无事件记录</div>'; return; }
  const icons = {Warning:'⚠️',Normal:'✅',Error:'❌'};
  el.innerHTML = `<div class="ev-list">${events.map(e=>`<div class="ev-item ${e.type||'Normal'}">
    <div class="ev-icon">${icons[e.type]||'ℹ️'}</div>
    <div class="ev-body">
      <div class="ev-reason">${esc(e.reason)}${e.count>1?`<span class="ev-cnt">×${e.count}</span>`:''}</div>
      <div class="ev-msg">${esc(e.message)}</div>
      <div class="ev-meta">${esc(e.source||'')}  ${fmtTs(e.last_time)}</div>
    </div>
  </div>`).join('')}</div>`;
}

function renderConfig(snap) {
  const info = snap.pod_info, el = document.getElementById('pmp-cf');
  const ann = info.annotations||{}, vols = info.volumes||{}, ctrs = info.containers||[];
  el.innerHTML = `<div class="two-col">
    <div class="ic"><div class="ic-hd"><span>📌</span><span class="ic-tt">Annotations</span></div>
    <div class="ic-bd" style="max-height:180px;overflow-y:auto">
      ${Object.keys(ann).length ? Object.entries(ann).map(([k,v])=>mkv(k,v.length>80?v.slice(0,80)+'…':v)).join('') : '<span style="color:var(--tx3)">无</span>'}
    </div></div>
    <div class="ic"><div class="ic-hd"><span>💾</span><span class="ic-tt">Volumes (${(vols||[]).length})</span></div>
    <div class="ic-bd">${(vols||[]).map(v=>mkv(v.name,`<code>${v.type}</code>`,true)).join('')||'<span style="color:var(--tx3)">无</span>'}</div></div>
  </div>
  ${ctrs.map(c=>`<div class="ic" style="margin-bottom:10px">
    <div class="ic-hd"><span>📦</span><span class="ic-tt">容器: ${esc(c.name)}</span></div>
    <div class="ic-bd">
      <div class="two-col" style="margin:0">
        <div>${mkv('Image',c.image)}${mkv('Pull Policy',c.image_pull_policy)}${mkv('State',c.state)}${mkv('Ready',c.ready?'✓ true':'✗ false')}${mkv('Restart Count',c.restart_count)}</div>
        <div>${mkv('CPU Requests',c.requests_cpu||'—')}${mkv('CPU Limits',c.limits_cpu||'—')}${mkv('Mem Requests',c.requests_mem||'—')}${mkv('Mem Limits',c.limits_mem||'—')}</div>
      </div>
      ${c.env.length?`<div style="margin-top:9px"><div style="font-size:10px;color:var(--tx2);text-transform:uppercase;letter-spacing:1px;margin-bottom:5px">环境变量 (前20)</div><div style="max-height:160px;overflow-y:auto">${c.env.map(e=>mkv(e.name,typeof e.value==='string'?e.value:'[valueFrom]')).join('')}</div></div>`:''}
      ${c.volume_mounts.length?`<div style="margin-top:9px"><div style="font-size:10px;color:var(--tx2);text-transform:uppercase;letter-spacing:1px;margin-bottom:5px">Volume Mounts</div>${c.volume_mounts.map(vm=>mkv(vm.name,`${vm.mountPath}${vm.readOnly?' (ro)':''}`)).join('')}</div>`:''}
    </div>
  </div>`).join('')}
  ${info.tolerations?.length?`<div class="ic"><div class="ic-hd"><span>🔑</span><span class="ic-tt">Tolerations</span></div><div class="ic-bd">${info.tolerations.map(t=>mkv(t.key||'(全部)',`${t.operator||'Exists'}${t.effect?' : '+t.effect:''}`)).join('')}</div></div>`:''}`;
}

// ── Logs ──────────────────────────────────────────────────────────────────────
async function loadLogs() {
  const t = getT();
  if(!t.cluster_name || !t.pod_name) { toast('请先配置目标 Pod','warn'); return; }
  const container = document.getElementById('logCtr').value;
  const tail = parseInt(document.getElementById('logTail').value);
  const since = document.getElementById('logSince').value;
  const filter = document.getElementById('logFilt').value.trim();
  const box = document.getElementById('logBox');
  box.innerHTML = '<div class="o-dim">加载中...</div>';
  try {
    const r = await fetch(`${API}/monitor/logs`, {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({...t, container, tail, since})});
    // 先检查 Content-Type，防止 server 返回 HTML 错误页被误当 JSON 解析
    const ct = r.headers.get('content-type') || '';
    if(!ct.includes('application/json')) {
      const text = await r.text();
      throw new Error(`服务器返回非 JSON 响应 (${r.status})。\n请确认 server.py 正在运行（python server.py）\n响应前100字符: ${text.slice(0,100)}`);
    }
    if(!r.ok) {
      const e = await r.json();
      throw new Error(e.error || `请求失败 (${r.status})`);
    }
    const d = await r.json(); _logRaw = d.logs||'';
    renderLogs(_logRaw, filter);
    document.getElementById('logStat').textContent = `${_logRaw.split('\n').length} 行`;
    document.getElementById('btnDlLog').disabled = !_logRaw;
  } catch(e) {
    box.innerHTML = `<div class="o-err" style="white-space:pre-wrap;font-size:11px">加载失败: ${esc(e.message)}</div>`;
  }
}

function renderLogs(raw, filter) {
  const box = document.getElementById('logBox');
  const lines = raw.split('\n');
  const html = lines.map(line => {
    let cls = 'll-i';
    const ll = line.toLowerCase();
    if(ll.includes('error')||ll.includes('exception')||ll.includes('fatal')) cls='ll-e';
    else if(ll.includes('warn')) cls='ll-w';
    else if(ll.includes('debug')||ll.includes('trace')) cls='ll-d';
    let content = esc(line), hiCls = '';
    if(filter && line.toLowerCase().includes(filter.toLowerCase())) {
      hiCls = ' ll-hi';
      const re = new RegExp(filter.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'), 'gi');
      content = content.replace(re, m => `<mark style="background:rgba(251,191,36,.25);color:var(--a6)">${esc(m)}</mark>`);
    }
    return `<div class="${cls}${hiCls}">${content}</div>`;
  }).join('');
  box.innerHTML = html; box.scrollTop = box.scrollHeight;
}

function toggleWrap() {
  _logWrap = !_logWrap;
  document.getElementById('logBox').style.whiteSpace = _logWrap ? 'pre-wrap' : 'pre';
}

function downloadLogsFile() {
  if(!_logRaw) { toast('请先加载日志','warn'); return; }
  const t = getT();
  const ctr = document.getElementById('logCtr').value || 'default';
  const fname = `logs-${t.pod_name}-${ctr||'default'}-${fmtNowTs()}.log`;
  const blob = new Blob([_logRaw], {type:'text/plain;charset=utf-8'});
  const url = URL.createObjectURL(blob); const a = document.createElement('a');
  a.href=url; a.download=fname; a.click(); URL.revokeObjectURL(url);
  toast(`已下载: ${fname}`, 'success');
}

// ── Pod File Browser ──────────────────────────────────────────────────────────
async function fbList() {
  const t = getT();
  if(!t.cluster_name || !t.pod_name) { toast('请先配置集群和 Pod','warn'); return; }
  const path = document.getElementById('fbPath').value || '/tmp';
  _fbCurPath = path; _fbSelected = null;
  document.getElementById('fbDlBtn').disabled = true;
  document.getElementById('fbPreviewBtn').disabled = true;
  document.getElementById('fbSelInfo').textContent = '';
  document.getElementById('fbStatus').textContent = '加载中...';
  document.getElementById('fbCurPath').textContent = path;
  document.getElementById('fbPreviewBox').classList.remove('show');

  try {
    const r = await fetch(`${API}/pod/files`, {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({...t, path})});
    const d = await r.json();
    if(d.error) { document.getElementById('fbStatus').textContent = ''; document.getElementById('fbList').innerHTML = `<div style="color:var(--a5);padding:20px;font-size:12px">✗ ${esc(d.error)}</div>`; return; }
    const files = d.files||[];
    document.getElementById('fbStatus').textContent = '';
    document.getElementById('fbCount').textContent = `  ${files.length} 项`;

    let html = '';
    // Parent dir shortcut
    if(path !== '/') {
      html += `<div class="fb-item fb-dir" onclick="fbNav('..')">
        <span class="fb-icon">📁</span>
        <span class="fb-name">..</span>
        <span class="fb-meta" style="color:var(--tx3)">上级目录</span>
      </div>`;
    }
    if(!files.length) { html += `<div style="color:var(--tx3);padding:20px;text-align:center;font-size:12px">目录为空</div>`; }
    for(const f of files) {
      const icon = f.is_dir ? '📁' : getFileIcon(f.name);
      html += `<div class="fb-item ${f.is_dir?'fb-dir':''}"
        data-path="${esc(f.path)}" data-name="${esc(f.name)}" data-isdir="${f.is_dir}"
        onclick="fbSelectEl(this)" ondblclick="fbDblClickEl(this)">
        <span class="fb-icon">${icon}</span>
        <span class="fb-name" title="${esc(f.path)}">${esc(f.name)}${f.is_link?' ↗':''}</span>
        <span class="fb-size">${f.is_dir?'':esc(f.size)}</span>
        <span class="fb-meta">${esc(f.modified)}</span>
      </div>`;
    }
    document.getElementById('fbList').innerHTML = html;
  } catch(e) { document.getElementById('fbStatus').textContent = ''; document.getElementById('fbList').innerHTML = `<div style="color:var(--a5);padding:20px;font-size:12px">✗ ${esc(e.message)}</div>`; }
}

function getFileIcon(name) {
  const n = name.toLowerCase();
  if(n.endsWith('.log')||n.endsWith('.txt')) return '📄';
  if(n.endsWith('.java')||n.endsWith('.class')) return '☕';
  if(n.endsWith('.json')||n.endsWith('.yaml')||n.endsWith('.yml')) return '📋';
  if(n.endsWith('.sh')||n.endsWith('.bash')) return '⚡';
  if(n.endsWith('.html')||n.endsWith('.htm')) return '🔥';
  if(n.endsWith('.jfr')||n.endsWith('.hprof')) return '📊';
  if(n.endsWith('.zip')||n.endsWith('.tar')||n.endsWith('.gz')) return '📦';
  if(n.endsWith('.xml')||n.endsWith('.properties')||n.endsWith('.conf')) return '⚙️';
  return '📄';
}

function fbSelectEl(el) {
  document.querySelectorAll('.fb-item').forEach(e => e.classList.remove('selected'));
  el.classList.add('selected');
  const path  = el.dataset.path;
  const name  = el.dataset.name;
  const isDir = el.dataset.isdir === 'true';
  if(!isDir) {
    _fbSelected = path;
    document.getElementById('fbDlBtn').disabled = false;
    document.getElementById('fbPreviewBtn').disabled = false;
    document.getElementById('fbSelInfo').textContent = `已选: ${name}`;
    document.getElementById('fbPreviewBox').classList.remove('show');
  } else {
    _fbSelected = null;
    document.getElementById('fbDlBtn').disabled = true;
    document.getElementById('fbPreviewBtn').disabled = true;
    document.getElementById('fbSelInfo').textContent = `目录: ${name}`;
  }
}

function fbDblClickEl(el) {
  const path  = el.dataset.path;
  const isDir = el.dataset.isdir === 'true';
  if(isDir) { document.getElementById('fbPath').value = path; fbList(); }
}

function fbNav(relative) {
  const cur = document.getElementById('fbPath').value || '/';
  let newPath;
  if(relative === '..') {
    const parts = cur.split('/').filter(Boolean);
    parts.pop();
    newPath = '/' + parts.join('/') || '/';
  } else {
    newPath = (cur.endsWith('/') ? cur : cur+'/') + relative;
  }
  document.getElementById('fbPath').value = newPath;
  fbList();
}

function fbUp() {
  fbNav('..');
}

async function fbDownload() {
  if(!_fbSelected) { toast('请先选择文件','warn'); return; }
  const t = getT();
  if(!t.cluster_name || !t.pod_name) { toast('请先配置集群和 Pod','warn'); return; }
  document.getElementById('fbDlBtn').disabled = true;
  document.getElementById('fbStatus').textContent = '下载中...';
  try {
    // Use form POST to trigger browser download
    const form = document.createElement('form'); form.method='POST'; form.action=`${API}/pod/files/download`;
    form.style.display='none'; form.target='_blank';
    // Can't directly POST JSON to get file download, so use fetch+blob
    console.log('fbDownload:', {t, path: _fbSelected});
    const r = await fetch(`${API}/pod/files/download`, {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({...t, path: _fbSelected})
    });
    if(!r.ok) {
      const e = await r.json();
      const detail = [e.error, e.debug ? JSON.stringify(e.debug) : null].filter(Boolean).join('\n');
      throw new Error(detail || '下载失败');
    }
    const blob = await r.blob();
    const fname = _fbSelected.split('/').pop();
    const url = URL.createObjectURL(blob); const a = document.createElement('a');
    a.href=url; a.download=fname; a.click(); URL.revokeObjectURL(url);
    toast(`已下载: ${fname}`, 'success');
    document.getElementById('fbStatus').textContent = `✓ 已下载 ${fname}`;
  } catch(e) {
    const msg = e.message || String(e);
    toast(msg.split('\n')[0], 'error');
    document.getElementById('fbStatus').textContent = '✗ ' + msg.split('\n')[0];
  }
  document.getElementById('fbDlBtn').disabled = false;
}

async function fbPreview() {
  if(!_fbSelected) return;
  const t = getT();
  const box = document.getElementById('fbPreviewBox');
  box.textContent = '加载中...'; box.classList.add('show');
  try {
    const d = await safePost(`${API}/pod/files/tail`, {...t, path: _fbSelected, lines: 200});
    if(d.error) { box.textContent = '✗ ' + d.error; return; }
    box.textContent = d.content || '(空文件)';
  } catch(e) { box.textContent = '✗ ' + e.message; }
}

// ── Monitor File Browser ──────────────────────────────────────────────────────
let _fbMonSelected = null;
async function fbListMon() {
  // Use ConnectionStore to get current connection
  var conn = null;
  if (window.ConnectionStore && typeof ConnectionStore.getCurrentConnection === 'function') {
    conn = ConnectionStore.getCurrentConnection();
  }
  if (!conn) { toast('请先连接 Pod', 'warn'); return; }
  var t = {
    cluster_name: conn.cluster || conn.cluster_name || '',
    namespace: conn.namespace || 'default',
    pod_name: conn.pod || conn.pod_name || '',
    container: conn.container || '',
  };
  if (!t.pod_name) { toast('请先连接 Pod', 'warn'); return; }
  const path = document.getElementById('fbPathMon')?.value || '/tmp';
  const listEl = document.getElementById('fbListMon');
  if (!listEl) return;
  listEl.innerHTML = '<div style="color:var(--tx3);padding:20px;text-align:center">加载中...</div>';
  try {
    const d = await safePost(`${API}/pod/files`, {...t, path});
    if (d.error) { listEl.innerHTML = `<div style="color:var(--red);padding:20px;text-align:center">✗ ${d.error}</div>`; return; }
    const files = d.files || [];
    if (!files.length) { listEl.innerHTML = '<div style="color:var(--tx3);padding:20px;text-align:center">空目录</div>'; return; }
    // 添加上级目录链接
    let html = '';
    if (path !== '/') {
      html = `<div class="fb-item fb-dir" onclick="fbUpMon()">
        <span>📁</span>
        <span>..</span>
        <span style="margin-left:auto;color:var(--tx3);font-size:10px">上级目录</span>
      </div>`;
    }
    html += files.map(f => {
      const isDir = f.is_dir || f.type === 'dir';
      const icon = isDir ? '📁' : '📄';
      const type = isDir ? 'dir' : 'file';
      return `
        <div class="fb-item ${_fbMonSelected===f.path?'on':''} ${isDir?'fb-dir':''}" data-path="${esc(f.path)}" data-type="${type}" onclick="fbSelectMon(this,'${esc(f.path)}','${type}')">
          <span>${icon}</span>
          <span>${esc(f.name)}</span>
          <span style="margin-left:auto;color:var(--tx3);font-size:10px">${isDir?'':(f.size||'')}</span>
        </div>
      `;
    }).join('');
    listEl.innerHTML = html;
    document.getElementById('fbCurPathMon').textContent = path;
    document.getElementById('fbCountMon').textContent = ` (${files.length} 项)`;
  } catch(e) { listEl.innerHTML = `<div style="color:var(--red);padding:20px;text-align:center">✗ ${e.message}</div>`; }
}
function fbSelectMon(el, path, type) {
  _fbMonSelected = path;
  document.querySelectorAll('#fbListMon .fb-item').forEach(i => i.classList.remove('on'));
  el.classList.add('on');
  // 启用下载和预览按钮
  const dlBtn = document.getElementById('fbDlBtnMon');
  const pvBtn = document.getElementById('fbPreviewBtnMon');
  const selInfo = document.getElementById('fbSelInfoMon');
  if (type === 'dir') {
    // 目录：点击进入，不启用下载/预览
    if (dlBtn) dlBtn.disabled = true;
    if (pvBtn) pvBtn.disabled = true;
    if (selInfo) selInfo.textContent = '';
    document.getElementById('fbPathMon').value = path;
    fbListMon();
  } else {
    // 文件：启用下载/预览
    if (dlBtn) dlBtn.disabled = false;
    if (pvBtn) pvBtn.disabled = false;
    if (selInfo) selInfo.textContent = path.split('/').pop();
  }
}
function fbUpMon() {
  const path = document.getElementById('fbPathMon')?.value || '/tmp';
  const parts = path.split('/').filter(Boolean);
  parts.pop();
  document.getElementById('fbPathMon').value = '/' + parts.join('/');
  fbListMon();
}
async function fbDownloadMon() {
  if (!_fbMonSelected) return;
  var conn = null;
  if (window.ConnectionStore && typeof ConnectionStore.getCurrentConnection === 'function') {
    conn = ConnectionStore.getCurrentConnection();
  }
  if (!conn) { toast('请先连接 Pod', 'warn'); return; }
  var t = {
    cluster_name: conn.cluster || conn.cluster_name || '',
    namespace: conn.namespace || 'default',
    pod_name: conn.pod || conn.pod_name || '',
    container: conn.container || '',
  };
  try {
    const r = await fetch(`${API}/pod/files/download`, {
      method: 'POST', headers: {'Content-Type':'application/json'}, credentials: 'include',
      body: JSON.stringify({...t, path: _fbMonSelected})
    });
    if (!r.ok) throw new Error('下载失败');
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = _fbMonSelected.split('/').pop(); a.click();
    URL.revokeObjectURL(url);
  } catch(e) { toast('下载失败: ' + e.message, 'err'); }
}
async function fbPreviewMon() {
  if (!_fbMonSelected) return;
  var conn = null;
  if (window.ConnectionStore && typeof ConnectionStore.getCurrentConnection === 'function') {
    conn = ConnectionStore.getCurrentConnection();
  }
  if (!conn) { toast('请先连接 Pod', 'warn'); return; }
  var t = {
    cluster_name: conn.cluster || conn.cluster_name || '',
    namespace: conn.namespace || 'default',
    pod_name: conn.pod || conn.pod_name || '',
    container: conn.container || '',
  };
  const pane = document.getElementById('fbPreviewPaneMon');
  const content = document.getElementById('fbPreviewContentMon');
  if (!pane || !content) return;
  pane.style.display = 'flex';
  content.textContent = '加载中...';
  try {
    const d = await safePost(`${API}/pod/files/tail`, {...t, path: _fbMonSelected, lines: 200});
    if (d.error) { content.textContent = '✗ ' + d.error; return; }
    content.textContent = d.content || '(空文件)';
  } catch(e) { content.textContent = '✗ ' + e.message; }
}

// ── Cluster management ─────────────────────────────────────────────────────────
async function loadClusters() {
  try {
    const r = await fetch(`${API}/clusters`, { credentials: 'include' });
    if (r.status === 401) { window.location.replace('/login.html'); return; }
    const d = await r.json();
    _clusters = d.clusters || d || [];
  } catch { _clusters = []; }
  // 恢复上次选中的集群（或自动选中第一个）
  if (!_ac && _clusters.length) {
    const saved = (() => { try { return localStorage.getItem('arthas_ac'); } catch { return null; } })();
    const found = saved && _clusters.find(c => c.name === saved);
    // 优先恢复上次选中，没有则自动选第一个
    const target = found ? found.name : _clusters[0].name;
    _ac = target;
    try { localStorage.setItem('arthas_ac', target); } catch {}
  }
  renderSidebar();
}

function renderSidebar() {
  const el = document.getElementById('sbCls');
  if(!_clusters.length) { el.innerHTML='<div class="sb-empty">暂无集群<br>请到系统管理 → 集群管理创建</div>'; return; }
  el.innerHTML = _clusters.map((c, idx) => {
    const safeName = esc(c.name);
    // 使用 data 属性存储集群名称，避免 HTML 属性中的字符串转义问题
    return `
    <div class="sb-itm ${_ac===c.name?'on':''}" data-cluster-name="${safeName}" data-cluster-idx="${idx}">
      <div class="sb-dt" id="sbd_${btoa(encodeURIComponent(c.name)).replace(/[^a-zA-Z0-9]/g,'_')}"></div>
      <span class="sb-nm" title="${safeName}">${safeName}</span>
      <button class="sb-edit" data-action="edit" title="编辑">✎</button>
      <button class="sb-del" data-action="del" title="删除">✕</button>
    </div>`;
  }).join('');
  
  // 绑定事件委托，避免内联 onclick 的字符串转义问题
  el.querySelectorAll('.sb-itm').forEach(item => {
    const name = item.dataset.clusterName;
    item.addEventListener('click', (e) => {
      if (e.target.tagName === 'BUTTON') return; // 按钮有单独处理
      selCluster(name);
    });
    item.querySelector('[data-action="edit"]').addEventListener('click', (e) => {
      e.stopPropagation();
      openEditCluster(name);
    });
    item.querySelector('[data-action="del"]').addEventListener('click', (e) => {
      e.stopPropagation();
      delCluster(name);
    });
  });
}

function selCluster(name) {
  _ac = name;
  try { localStorage.setItem('arthas_ac', name); } catch {}
  renderSidebar(); pingCluster(name);
  resetConnectionFlowForTargetChange();
  // Auto-load namespaces for this cluster
  const cached = window._clusterNs && window._clusterNs[name];
  if(cached) { populateNsList(cached); }
  else { autoLoadNs(name); }
}

async function pingCluster(name, showToast = false) {
  const did = 'sbd_' + btoa(encodeURIComponent(name)).replace(/[^a-zA-Z0-9]/g,'_');
  const dot = document.getElementById(did); if(dot) dot.className='sb-dt pinging';
  try {
    const r = await fetch(`${API}/clusters/${encodeURIComponent(name)}/test`, {method:'POST'});
    const d = await r.json();
    if(dot) dot.className = 'sb-dt ' + (d.ok?'ok':'err');
    if (showToast) toast(`集群连接测试${d.ok ? '成功' : '失败'}${d.ok ? '' : '：' + (d.error || d.message || '请检查 kubeconfig')}`, d.ok ? 'success' : 'error');
    return d;
  } catch(e) {
    if(dot) dot.className='sb-dt err';
    if (showToast) toast('集群连接测试失败：' + e.message, 'error');
    return { ok: false, error: e.message };
  }
}

async function delCluster(name) {
  if(!confirm(`删除集群 "${name}"？`)) return;
  await fetch(`${API}/clusters/${encodeURIComponent(name)}`, {method:'DELETE'});
  if(_ac===name) _ac=null; loadClusters();
}

let _editingCluster = null;

function openAddCluster() {
  _editingCluster = null;
  document.getElementById('mName').value = '';
  document.getElementById('mKc').value   = '';
  document.getElementById('mCtx').value  = '';
  document.getElementById('mCtxWrap').style.display = 'none';
  document.getElementById('mErr').style.display = 'none';
  document.getElementById('m-tt').textContent = '添加 K8s 集群';
  document.getElementById('clModal').classList.add('open');
}

function openEditCluster(name) {
  const c = _clusters.find(x => x.name===name);
  if(!c) return;
  _editingCluster = name;
  document.getElementById('mName').value = c.name;
  document.getElementById('mKc').value   = c.kubeconfig;
  document.getElementById('mCtx').value  = c.context||'';
  document.getElementById('mCtxWrap').style.display = 'none';
  document.getElementById('mErr').style.display = 'none';
  document.getElementById('m-tt').textContent = `编辑集群: ${name}`;
  document.getElementById('clModal').classList.add('open');
}

async function autoLoadNs(clusterName) {
  // Auto-populate namespace selector after cluster add/select
  try {
    const r = await fetch(`${API}/clusters/${encodeURIComponent(clusterName)}/namespaces`);
    const d = await r.json();
    const ns = d.namespaces||[];
    if(!ns.length) return;
    // store in global for reuse
    window._clusterNs = window._clusterNs||{};
    window._clusterNs[clusterName] = ns;
    // If this is the active cluster, populate pt-sel
    if(clusterName === _ac) populateNsList(ns);
  } catch {}
}

function normalizeActiveNamespace(nsList) {
  const ptNs = document.getElementById('ptNs');
  if (!ptNs) return;
  const allowed = nsList || [];
  // 重建选项前记住当前连接的真实 namespace
  const prevValue = ptNs.value;
  const connNs = (window._currentConnId || '').split('/')[1] || '';
  ptNs.dataset.allowedNamespaces = JSON.stringify(allowed);
  if (!allowed.length) {
    ptNs.innerHTML = '<option value="">无可用 namespace</option>';
    ptNs.value = '';
    return;
  }
  ptNs.innerHTML = allowed.map(n => `<option value="${esc(n)}">${esc(n)}</option>`).join('');
  // 优先恢复连接的 namespace，其次保留之前选中的值，最后 fallback
  if (connNs && allowed.includes(connNs)) {
    ptNs.value = connNs;
  } else if (prevValue && allowed.includes(prevValue)) {
    ptNs.value = prevValue;
  } else {
    ptNs.value = allowed.includes('default') ? 'default' : allowed[0];
  }
}

function validateSelectedNamespace() {
  const ptNs = document.getElementById('ptNs');
  if (!ptNs) return true;
  let allowed = [];
  try { allowed = JSON.parse(ptNs.dataset.allowedNamespaces || '[]'); } catch {}
  if (allowed.length && !allowed.includes(ptNs.value)) {
    toast('请选择已授权的 namespace', 'warn');
    return false;
  }
  return true;
}

function populateNsList(nsList) {
  normalizeActiveNamespace(nsList);
}
function closeClusterModal() { document.getElementById('clModal').classList.remove('open'); }
function closeModal() { closeClusterModal(); }

async function fetchCtxs() {
  const kc = document.getElementById('mKc').value.trim();
  if(!kc) { toast('请先填写 kubeconfig 路径','warn'); return; }
  try {
    // 使用专用接口直接获取 contexts，不创建/删除临时集群，避免服务器崩溃
    const r2 = await fetch(`${API}/contexts`, {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({kubeconfig: kc}),
    });
    if(!r2.ok) { const e=await r2.json(); toast(e.error || '获取失败', 'error'); return; }
    const d = await r2.json();
    const sel = document.getElementById('mCtxSel');
    sel.innerHTML = '<option value="">—</option>' + (d.contexts||[]).map(c=>`<option value="${c}">${c}</option>`).join('');
    if(d.current) {
      sel.value = d.current;
      document.getElementById('mCtx').value = d.current;  // 同步到文本框，保存时能读取
    }
    document.getElementById('mCtxWrap').style.display = 'block';
    toast(`找到 ${(d.contexts||[]).length} 个 context`);
  } catch(e) { toast('获取失败: '+e.message, 'error'); }
}

async function saveCluster() {
  const name = document.getElementById('mName').value.trim();
  const kc   = document.getElementById('mKc').value.trim();
  const ctx  = document.getElementById('mCtx').value.trim();
  const err  = document.getElementById('mErr');
  const saveBtn = document.getElementById('mSaveBtn');
  const oldSaveText = saveBtn ? saveBtn.textContent : '';
  if(!name || !kc) { err.textContent='名称和路径必填'; err.style.display='block'; return; }
  err.style.display='none';
  if (saveBtn) { saveBtn.disabled = true; saveBtn.textContent = '保存中...'; }
  try {
    // 编辑已有集群用 POST（避免某些代理/防火墙拦截 PUT），新增也用 POST
    // 编辑时 URL 带旧名称，后端通过 URL 参数识别是更新操作
    const url    = _editingCluster
      ? `${API}/clusters/${encodeURIComponent(_editingCluster)}`
      : `${API}/clusters`;
    console.log('[saveCluster] _editingCluster=', _editingCluster, 'url=', url);
    const r = await fetch(url, {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({name, kubeconfig:kc, context:ctx}),
    });
    const d = await r.json();
    if(!r.ok) { err.textContent = d.error; err.style.display='block'; return; }
    _editingCluster = null;
    closeModal();
    toast('集群已保存，正在后台测试连接...', 'success');
    await loadClusters();
    // 选中集群但不立即 ping（ping 是异步的，不阻塞保存响应）
    _ac = name;
    try { localStorage.setItem('arthas_ac', name); } catch {}
    renderSidebar();
    if (window.ConnectionPool && typeof window.ConnectionPool.loadClusters === 'function') {
      window.ConnectionPool.loadClusters();
    }
    // 延迟 ping，避免 kubectl 阻塞导致前端报错
    setTimeout(() => pingCluster(name, true), 800);
    // Auto-load namespaces for sidebar display
    autoLoadNs(name);
  } catch(e) { err.textContent=e.message; err.style.display='block'; }
  finally {
    if (saveBtn) { saveBtn.disabled = false; saveBtn.textContent = oldSaveText || '保存并连接测试'; }
  }
}

// ── Tasks & Files ──────────────────────────────────────────────────────────────
async function loadHistory() {
  // Update filter label visibility
  updateHistoryFilterLabel();
  // Check if filter checkbox is active
  var checkbox = getHistoryViewElement('filter-checkbox');
  var filterConnId = (checkbox && checkbox.checked && _currentConnId) ? _currentConnId : null;
  await loadPfHistory(filterConnId);
  await loadLocalFiles();
  updateHistoryCounts();
}

function refreshHistoryIfFiltered() {
  var root = getHistoryViewRoot();
  if (!isHistoryViewVisible(root)) return;
  var checkbox = getHistoryViewElement('filter-checkbox');
  if (checkbox && checkbox.checked) {
    toggleHistoryConnFilter();
  }
}

async function loadPfHistory(connectionId) {
  try {
    // Use the new SamplingHistory component for the global profiler tab
    const container = getHistoryViewElement('panel-profiler');
    if (!container) return;

    if (typeof SamplingHistory !== 'undefined') {
      var opts = { mode: 'global' };
      if (connectionId) opts.connectionId = connectionId;
      SamplingHistory.mount(container, opts);
      // Count is updated internally by the component
      window._pfTasksCount = 0; // Will be updated by component
    } else {
      // Fallback to legacy rendering if component not loaded
      const r = await fetch(`${API}/profile/tasks`); const tasks = await r.json();
      let filteredTasks = tasks;
      if (connectionId) {
        const currentConn = _connections.find(c => c.id === connectionId);
        if (currentConn) {
          filteredTasks = tasks.filter(t =>
            t.config.cluster === currentConn.cluster_name &&
            t.config.namespace === currentConn.namespace &&
            t.config.pod === currentConn.pod_name
          );
        }
      }
      window._pfTasksCount = filteredTasks.length;
      const countEl = getHistoryViewElement('count-profiler');
      if (countEl) countEl.textContent = filteredTasks.length;
      updateHistoryCounts();
      // Legacy rendering omitted — component should be available
    }
  } catch (e) {
    console.error('loadPfHistory error:', e);
  }
}

async function loadLocalFiles() {
  try {
    const r = await fetch(`${API}/files`); const files = await r.json();
    window._dlFilesCount = files.length;
    const countEl = getHistoryViewElement('count-files');
    if (countEl) countEl.textContent = files.length;
    const el = getHistoryViewElement('panel-files');
    if(!el) return;
    if(!files.length) {
      el.innerHTML = `<div class="hist-empty">
        <svg class="hist-empty-icon" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" stroke-linecap="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
        <div class="hist-empty-title">暂无下载记录</div>
        <div class="hist-empty-sub">采样完成后可在此下载结果文件</div>
      </div>`;
      updateHistoryCounts();
      return;
    }

    // SVG icon by file type
    const fileIcon = (name) => {
      if (name.endsWith('.html')) return `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z"/></svg>`;
      if (name.endsWith('.jfr')) return `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>`;
      if (name.endsWith('.log')) return `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>`;
      return `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>`;
    };

    const fileTypeClass = (name) => {
      if (name.endsWith('.html')) return 'html';
      if (name.endsWith('.jfr')) return 'jfr';
      if (name.endsWith('.log')) return 'log';
      return 'other';
    };

    const showUser = typeof isAdmin === 'function' && isAdmin();
    
    let headerHtml = '';
    if (showUser) {
      headerHtml = `<div class="hist-files-header">
        <span>包含：采样报告 + 文件浏览器下载的文件</span>
        <span style="color:var(--a);background:rgba(0,122,255,.1);padding:2px 6px;border-radius:3px;font-size:10px">按用户隔离</span>
      </div>`;
    } else {
      headerHtml = `<div class="hist-files-header">
        <span>包含：采样报告 + 文件浏览器下载的文件（保存在 <code>data/profiler/</code>）</span>
      </div>`;
    }
    
    el.innerHTML = headerHtml + `<div class="hist-files-list">` + files.map(f => {
      const metaParts = [fmtSz(f.size), fmtTs(f.modified)];
      if (showUser && f.username) {
        metaParts.push(`<span class="user">@${esc(f.username)}</span>`);
      }
      return `<div class="hist-file-row">
        <div class="hist-file-icon ${fileTypeClass(f.name)}">${fileIcon(f.name)}</div>
        <div class="hist-file-info">
          <div class="hist-file-name">${esc(f.name)}</div>
          <div class="hist-file-meta">${metaParts.join('<span>·</span>')}</div>
        </div>
        <button class="hist-file-dl" onclick="downloadOutputFile('${esc(f.name)}')" title="下载">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
        </button>
      </div>`;
    }).join('') + `</div>`;
    updateHistoryCounts();
  } catch {}
}

// ── Init ───────────────────────────────────────────────────────────────────────
// 等待 DOM 加载完成后初始化
document.addEventListener('DOMContentLoaded', async function() {
  initUserDisplay();
  const deepLinkIntent = readWorkspaceDeepLinkIntent();

  // ✅ 恢复持久化的 Profiler 任务（切换页签后不丢失）
  if (typeof _loadPersistedPfTasks === 'function') _loadPersistedPfTasks();
  
  // ✅ P0修复: 先从数据库 API 加载最新连接,再恢复活跃连接
  try {
    const r = await fetch(`${API}/arthas/connections`, { credentials: 'include' });
    const d = await r.json();
    if (r.ok && d.ok && d.connections) {
      console.log('[初始化] 从数据库加载连接:', d.connections.length, '个');
      _connections = d.connections.map(_normalizeConnectionRecord);
      
      // ✅ 同步到 ConnectionStore (确保连接中心能正确渲染)
      if (typeof ConnectionStore !== 'undefined') {
        ConnectionStore.setConnections(_connections);
        ConnectionStore._persist();
        console.log('[初始化] 已同步到 ConnectionStore');
      }
      
      const user = getCurrentUser();
      const key = user ? `arthas_connections_${user.username}` : 'arthas_connections';
      localStorage.setItem(key, JSON.stringify(_connections));
      _syncState();
      renderConnList();
      
      // ✅ 恢复活跃连接 (与 loadConnections 相同的逻辑)
      const activeKey = user ? `arthas_active_conn_${user.username}` : 'arthas_active_conn';
      const levelKey = user ? `arthas_active_level_${user.username}` : 'arthas_active_level';
      const savedConnId = localStorage.getItem(activeKey);
      const savedLevel = localStorage.getItem(levelKey);
      
      const preferredConnId = deepLinkIntent.connId && _connections.find(c => c.id === deepLinkIntent.connId)
        ? deepLinkIntent.connId
        : '';
      const restoreConnId = preferredConnId || savedConnId;
      if (restoreConnId && _connections.find(c => c.id === restoreConnId)) {
        const conn = _connections.find(c => c.id === restoreConnId);
        if (conn) {
          const restoreLevel = preferredConnId ? _inferLevel(conn) : savedLevel;
          console.log('[初始化] 恢复活跃连接:', restoreConnId, '层级:', restoreLevel);
          // ✅ 修复: 去掉 800ms 延迟，立即开始恢复，减少 UI 闪烁
          _restoreActiveConnection(conn, restoreLevel).catch(e => {
            console.warn('[初始化] 自动恢复连接失败:', e);
            _currentConnId = null;
            _syncState();
            renderConnList();
            localStorage.removeItem(activeKey);
            localStorage.removeItem(levelKey);
            // ✅ 修复: 清除恢复标志 + 用户可见提示
            if (typeof ConnectionStore !== 'undefined') {
              ConnectionStore.setState({ isRestoring: false, connState: 'disconnected' });
            }
            toast(`连接恢复失败: ${e.message}`, 'warning');
          });
        }
      }
    } else {
      console.warn('[初始化] 数据库加载失败, 从 localStorage 加载');
      loadConnections();
    }
  } catch (e) {
    console.error('[初始化] 数据库加载异常:', e);
    loadConnections();
  }
  
  // 初始化工作台：显示 Tab 栏并切换到连接 Tab
  showWorkspace();
  applyWorkspaceDeepLink();

  renderCmdPal();
  hardenCommandSearchAutofill();
  setTimeout(hardenCommandSearchAutofill, 300);
  checkHealth();
  setInterval(checkHealth, 8000);
  // 连接健康检查：加载后 3 秒首次检查，之后每 60 秒检查一次
  setTimeout(checkConnectionsHealth, 3000);
  setInterval(checkConnectionsHealth, 60000);
  loadClusters();
  loadLocalFiles();
  
  // 初始化两步连接流程组件
  if (typeof initTwoStepConnection === 'function') {
    initTwoStepConnection();
  }
  
  // Pre-load history counts after a short delay
  setTimeout(loadHistory, 1500);
});

// Fix pm-lg panel: it should be hidden initially, shown by switchPm()
const _pmLg = document.querySelector('#pmp-lg');
if (_pmLg) _pmLg.style.display = 'none';

// ── 全局函数暴露 ─────────────────────────────────────────────────────────
// 将所有需要在 HTML onclick 中调用的函数暴露到 window 对象
// 注意：所有函数必须在暴露之前定义完成

// 集群相关
window.openAddCluster = openAddCluster;
window.openEditCluster = openEditCluster;
window.closeClusterModal = closeClusterModal;
window.closeModal = closeModal;
window.saveCluster = saveCluster;
window.delCluster = delCluster;
window.selCluster = selCluster;
window.pingCluster = pingCluster;
window.fetchCtxs = fetchCtxs;
window.autoLoadNs = autoLoadNs;
window.loadPods = loadPods;
window.loadClusters = loadClusters;

// 连接相关
window.renderConnList = renderConnList;
window.switchConnection = switchConnection;
window.deleteConnection = deleteConnectionPersistent;
window.checkPod = checkPod;
window.arthasConnect = arthasConnect;

// 两步连接流程函数在 two-step-connection.js 中暴露

// 标签页切换
window.setMainShellMode = setMainShellMode;
window.navigateTo = navigateTo;
window.navigateToTaskCenter = navigateToTaskCenter;
window.navigateToDiagnosis = navigateToDiagnosis;
window.switchTab = switchTab;
window.openSamplingHistory = openSamplingHistory;
window.rememberWorkspaceHistoryReturn = rememberWorkspaceHistoryReturn;
window.switchPm = switchPm;
window.switchHistTab = switchHistTab;

// 命令执行
window.runCmd = runCmd;
window.interruptCmd = interruptCmd;
window.clearConOut = clearConOut;

// Profiler
window.pfStart = pfStart;
window.pfSetMode = pfSetMode;
window.pfSetDur = pfSetDur;
window.pfClearLog = pfClearLog;
window.historyGoBack = historyGoBack;
window.toggleHistoryConnFilter = toggleHistoryConnFilter;

// 监控
window.loadSnap = loadSnap;
window.toggleAutoRefresh = toggleAutoRefresh;
window.loadLogs = loadLogs;
window.downloadLogsFile = downloadLogsFile;
window.toggleWrap = toggleWrap;

// 文件浏览器
window.fbList = fbList;
window.fbUp = fbUp;
window.fbNav = fbNav;
window.fbDownload = fbDownload;
window.fbPreview = fbPreview;
window.fbSelectEl = fbSelectEl;
window.fbDblClickEl = fbDblClickEl;

// 终端
window.termInit = termInit;
window.termClear = termClear;

// 命令面板
window.toggleCmdCat = toggleCmdCat;
window.selCmd = selCmd;
window.buildAndRun = buildAndRun;

// 其他
window.openConnectionCenter = openConnectionCenter;
window.toggleSideNavGroup = toggleSideNavGroup;
window.openTaskCenter = openTaskCenter;
window.openToolchainCenter = openToolchainCenter;
window.loadToolchainCenter = loadToolchainCenter;
window.createToolPackageFromForm = createToolPackageFromForm;
window.uploadToolPackageFromForm = uploadToolPackageFromForm;
window.distributeToolPackage = distributeToolPackage;
window.verifyToolPackage = verifyToolPackage;
window.toggleToolPackageStatus = toggleToolPackageStatus;
window.deleteToolPackage = deleteToolPackage;
window.fillToolchainPodTargetFromCurrent = fillToolchainPodTargetFromCurrent;
window.openTaskCenterFromToolchain = openTaskCenterFromToolchain;
window.uploadArthasSourceFromForm = uploadArthasSourceFromForm;
window.renderToolQuickPlans = renderToolQuickPlans;
window.renderArthasUserCaseCapabilities = renderArthasUserCaseCapabilities;
window.createTaskFromTemplateQuick = createTaskFromTemplateQuick;
window.openModelConfig = openModelConfig;
window.openMcpCenter = openMcpCenter;
window.loadTaskCenter = loadTaskCenter;
window.createTaskDefinitionFromForm = createTaskDefinitionFromForm;
window.runTaskDefinition = runTaskDefinition;
window.toggleTaskRunLog = toggleTaskRunLog;
window.syncTaskTemplateRuntime = syncTaskTemplateRuntime;
window.toggleTaskTargetFields = toggleTaskTargetFields;
window.fillTaskPodTargetFromCurrent = fillTaskPodTargetFromCurrent;
window.openCreateScheduleModal = openCreateScheduleModal;
window.closeCreateScheduleModal = closeCreateScheduleModal;
window.submitCreateSchedule = submitCreateSchedule;
window.toggleTaskScheduleStatus = toggleTaskScheduleStatus;
window.deleteTaskSchedule = deleteTaskSchedule;
window.openApiHelp = openApiHelp;

window.openChangePasswordModal = openChangePasswordModal;
window.closeChangePasswordModal = closeChangePasswordModal;
window.submitChangePassword = submitChangePassword;
window.doLogout = doLogout;
window.loadHistory = loadHistory;
window.hardenCommandSearchAutofill = hardenCommandSearchAutofill;
window.gcDownloadPath = gcDownloadPath;
window.gcPreviewPath = gcPreviewPath;
window.toggleCtr = toggleCtr;


// 来自 utils.js 的工具函数
window.mkv = mkv;
window.gRow = gRow;
window.toast = toast;

// ── 组件模块函数暴露 ─────────────────────────────────────────────────────
// 来自 components/connections.js
window.addConnection = addConnection;
window.removeConnection = removeConnection;
window.reconnectConnectionById = reconnectConnectionById;
window.upgradeConnectionById = upgradeConnectionById;
window.reconnectCurrentConnection = reconnectCurrentConnection;



// 来自 components/profiler.js
window.pfSetTask = pfSetTask;
window.pfGetTask = pfGetTask;
window.getPfState = getPfState;
window.renderProfilerStatus = renderProfilerStatus;

// 来自 components/monitor.js
window.getMetrics = getMetrics;
window.setMetrics = setMetrics;
window.startMetricsPolling = startMetricsPolling;
window.stopMetricsPolling = stopMetricsPolling;
window.renderOverview = renderOverview;
window.renderProcs = renderProcs;


// ── Connection Detail Functions ─────────────────────────────────────
function openConnectionDetail(connectionId) {
  if (!connectionId) return;
  fetch(`${API}/pod/connections`, { credentials: 'include' })
    .then(r => r.json())
    .then(data => {
      const conn = (data.connections || []).find(c => c.connection_id === connectionId);
      if (!conn) { toast('连接不存在', 'e'); return; }
      renderConnectionDetail(conn);
    })
    .catch(e => toast('加载连接详情失败: ' + e.message, 'e'));
}

function renderConnectionDetail(conn) {
  document.getElementById('cdCluster').textContent = conn.cluster_name || '—';
  document.getElementById('cdNamespace').textContent = conn.namespace || '—';
  document.getElementById('cdPod').textContent = conn.pod_name || '—';
  document.getElementById('cdContainer').textContent = conn.container || '—';
  document.getElementById('cdLevel').textContent = conn.level || '—';
  document.getElementById('cdAlive').textContent = conn.alive ? '✅ 存活' : '❌ 离线';
  document.getElementById('cdRuntime').textContent = conn.runtime ? `${conn.runtime} ${conn.runtime_version || ''}`.trim() : '—';
  document.getElementById('cdJavaPid').textContent = conn.java_pid || '—';
  document.getElementById('cdArthasVersion').textContent = conn.arthas_version || '—';
  document.getElementById('cdLocalPort').textContent = conn.local_port || '—';

  // 操作按钮显隐
  const isArthas = conn.level === 'arthas';
  document.getElementById('cdBtnUpgrade').style.display = isArthas ? 'none' : 'inline-block';
  document.getElementById('cdBtnDisconnect').style.display = 'inline-block';

  document.getElementById('connectionDetailTitle').textContent = `${conn.cluster_name}/${conn.namespace}/${conn.pod_name}`;
  document.getElementById('connectionDetailSub').textContent = `层级: ${conn.level || 'pod'}  |  状态: ${conn.alive ? '在线' : '离线'}`;

  // 切换面板
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('on'));
  document.getElementById('panel-connection-detail').classList.add('on');
}

function closeConnectionDetail() {
  document.getElementById('panel-connection-detail').classList.remove('on');
  // 回到连接中心
  document.getElementById('panel-connections').classList.add('on');
}

// ── Dashboard 控制面板 ─────────────────────────────────────────
function openDashboard() {
  // 获取当前连接
  fetch(`${API}/pod/connections`, { credentials: 'include' })
    .then(r => r.json())
    .then(data => {
      const conns = data.connections || [];
      const arthasConn = conns.find(c => c.level === 'arthas' && c.alive);
      if (!arthasConn) {
        toast('请先建立 Arthas 连接', 'e');
        return;
      }
      window.__currentDashboardConnId = arthasConn.connection_id;
      // 打开面板
      document.querySelectorAll('.panel').forEach(p => p.classList.remove('on'));
      document.getElementById('panel-dashboard').classList.add('on');
      refreshDashboard();
    })
    .catch(e => toast('加载连接失败: ' + e.message, 'e'));
}

function refreshDashboard() {
  const connId = window.__currentDashboardConnId;
  if (!connId) { toast('没有活跃的 Arthas 连接', 'e'); return; }
  document.getElementById('dbThreadsContent').textContent = '加载中...';
  document.getElementById('dbMemoryContent').textContent = '加载中...';
  document.getElementById('dbGCContent').textContent = '加载中...';
  document.getElementById('dbRuntimeContent').textContent = '加载中...';

  fetch(`${API}/diagnose/tool`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ connection_id: connId, tool: 'dashboard' })
  })
    .then(r => r.json())
    .then(resp => {
      if (!resp.ok) { toast(resp.error || 'dashboard 执行失败', 'e'); return; }
      renderDashboard(resp.data);
    })
    .catch(e => toast('dashboard 请求失败: ' + e.message, 'e'));
}

function renderDashboard(data) {
  if (!data) return;
  // data 是 Arthas dashboard 的返回，结构：{ results: [{ threads, memoryInfo, gcInfos, runtimeInfo }] }
  const results = data.results || data.body?.results || [];
  const d = results[0] || {};
  // 线程
  const threads = d.threads || [];
  const threadHtml = threads.length
    ? `<div class="dc-list">${threads.slice(0, 10).map(t => {
        const cpu = parseFloat(t.cpu || 0);
        const cls = cpu > 50 ? 'dc-high' : cpu > 20 ? 'dc-mid' : 'dc-low';
        return `<div class="${cls}">${t.threadName || t.id} — CPU ${t.cpu}%</div>`;
      }).join('')}</div>`
    : '<div class="dc-empty">无数据</div>';
  document.getElementById('dbThreadsContent').innerHTML = threadHtml;
  // 内存
  const mem = d.memoryInfo || {};
  const memHtml = Object.entries(mem).map(([k, v]) => {
    const used = parseFloat(v.used || 0);
    const total = parseFloat(v.total || v.max || 0);
    const pct = total ? Math.round(used / total * 100) : 0;
    const cls = pct > 85 ? 'dc-high' : pct > 60 ? 'dc-mid' : 'dc-low';
    return `<div class="${cls}">${k}: ${pct}%</div>`;
  }).join('');
  document.getElementById('dbMemoryContent').innerHTML = memHtml || '—';
  // GC
  const gc = d.gcInfos || [];
  const gcHtml = gc.map(g => {
    const name = g.name || '';
    const count = g.collectionCount || 0;
    const time = g.collectionTime || 0;
    const cls = name.includes('Full') ? 'dc-high' : 'dc-low';
    return `<div class="${cls}">${name}: ${count} 次 / ${time}ms</div>`;
  }).join('');
  document.getElementById('dbGCContent').innerHTML = gcHtml || '—';
  // 运行时
  const rt = d.runtimeInfo || {};
  const rtHtml = `
    <div>OS: ${rt.os || '—'}</div>
    <div>JVM: ${rt.vmName || '—'} ${rt.vmVersion || ''}</div>
    <div>PID: ${rt.pid || '—'}</div>
  `;
  document.getElementById('dbRuntimeContent').innerHTML = rtHtml;
}

function closeDashboard() {
  document.getElementById('panel-dashboard').classList.remove('on');
}



// ── 线程诊断 ──────────────────────────────────
function renderThreads(data) {
  if (!data) return;
  window.__lastThreadData = data;
  const results = data.results || data.body?.results || [];
  const d = results[0] || {};
  const threads = d.threads || d.busyThreads || [];
  const filter = document.getElementById("threadStateFilter")?.value || "";
  const filtered = filter ? threads.filter(t => (t.state || "") === filter) : threads;
  if (!filtered.length) {
    document.getElementById("threadListContent").innerHTML = '<div class="dc-empty">无数据</div>';
    return;
  }
  const html = '<table class="thread-table"><thead><tr>' +
    '<th>线程名</th><th>ID</th><th>状态</th><th>CPU</th><th>操作</th></tr></thead><tbody>' +
    filtered.map(t => {
      const cpu = parseFloat(t.cpu || 0);
      const cls = cpu > 50 ? "dc-high" : cpu > 20 ? "dc-mid" : "dc-low";
      const tstr = JSON.stringify(t).replace(/"/g, '&');
      return '<tr class="' + cls + '" onclick="showThreadStack(' + tstr + ')">' +
        '<td>' + (t.threadName || '-') + '</td>' +
        '<td>' + (t.id || '-') + '</td>' +
        '<td>' + (t.state || '-') + '</td>' +
        '<td>' + (t.cpu || 0) + '%</td>' +
        '<td><button class="btn btn-sm" onclick="event.stopPropagation();showThreadStack(' + tstr + ')">查看堆栈</button></td>' +
        '</tr>'; }).join('') +
    '</tbody></table>';
  document.getElementById("threadListContent").innerHTML = html;
}

function loadThreads() {
  const connId = window.__currentDashboardConnId || "";
  if (!connId) { toast("没有活跃的 Arthas 连接", "e"); return; }
  const topN = parseInt(document.getElementById("threadTopN")?.value || 15);
  document.getElementById("threadListContent").textContent = "加载中...";
  fetch(`${API}/diagnose/tool`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ connection_id: connId, tool: "threads", args: { top_n: topN } })
  })
    .then(r => r.json())
    .then(resp => {
      if (!resp.ok) { toast(resp.error || "线程获取失败", "e"); return; }
      renderThreads(resp.data);
    })
    .catch(e => toast("线程请求失败: " + e.message, "e"));
}

function filterThreads() {
  if (window.__lastThreadData) renderThreads(window.__lastThreadData);
}

function showThreadStack(t) {
  const stack = t.stack || t.stackTrace || "无堆栈信息";
  document.getElementById("tsThreadName").textContent = t.threadName || "-";
  document.getElementById("tsStackText").textContent = typeof stack === "string" ? stack : JSON.stringify(stack, null, 2);
  document.getElementById("threadStackContent").style.display = "block";
}

function checkDeadlock() {
  const connId = window.__currentDashboardConnId || "";
  if (!connId) { toast("没有活跃的 Arthas 连接", "e"); return; }
  fetch(`${API}/diagnose/tool`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ connection_id: connId, tool: "threads", args: { check_deadlock: true } })
  })
    .then(r => r.json())
    .then(resp => {
      if (resp.deadlock && resp.deadlock.blockingThread) {
        toast("⚠️ 检测到死锁！", "e");
        showThreadStack(resp.deadlock.blockingThread);
      } else {
        toast("未检测到死锁", "i");
      }
    })
    .catch(e => toast("死锁检测失败: " + e.message, "e"));
}

function closeThreadDiag() {
  document.getElementById("panel-thread-diagnosis").classList.remove("on");
}

function closeThreadStack() {
  document.getElementById("threadStackContent").style.display = "none";
}

function cdPodConnect() {
  // 跳转到连接中心，让用户选择集群/命名空间/Pod 建立连接
  switchTab('connections');
  toast('请在连接中心选择 Pod 并建立连接', 'i');
}
async function cdUpgradeToArthas() {
  const detailTitle = document.getElementById('connectionDetailTitle')?.textContent || '';
  const connId = _currentConnId || (_connections.find(c =>
    detailTitle.includes(c.pod_name || c.pod)
  )?.id);

  if (!connId) {
    switchTab('connections');
    toast('请先在连接中心选择 Pod 并建立连接', 'warn');
    return;
  }

  if (typeof upgradeConnectionById === 'function') {
    try {
      await upgradeConnectionById(connId, { source: 'connection-detail' });
      return;
    } catch (_) {
      return;
    }
  }

  switchTab('connections');
  toast('请在连接中心升级到 Arthas 连接', 'i');
}
function cdHealthCheck() { checkConnectionsHealth(); }
function cdDisconnect() {
  // 获取当前连接详情面板中的连接 ID
  const detailTitle = document.getElementById('connectionDetailTitle')?.textContent || '';
  const connId = _currentConnId || (_connections.find(c =>
    detailTitle.includes(c.pod_name || c.pod)
  )?.id);
  if (!connId) { toast('没有可断开的连接', 'e'); return; }
  if (!confirm('确定断开此连接吗？')) return;
  deleteConnectionPersistent(connId);
  closeConnectionDetail();
}
function cdOpenPanel(panelId) {
  // 使用 switchTab 统一导航，保持侧边栏状态同步
  switchTab(panelId);
}

// 暴露给全局
window.openConnectionDetail = openConnectionDetail;
window.renderConnectionDetail = renderConnectionDetail;
window.closeConnectionDetail = closeConnectionDetail;
window.cdPodConnect = cdPodConnect;
window.cdUpgradeToArthas = cdUpgradeToArthas;
window.cdHealthCheck = cdHealthCheck;
window.cdDisconnect = cdDisconnect;
window.refreshConnectionList = refreshConnectionList;
window.cdOpenPanel = cdOpenPanel;
window.openDashboard = openDashboard;
window.refreshDashboard = refreshDashboard;
window.renderDashboard = renderDashboard;
window.closeDashboard = closeDashboard;
window.renderThreads = renderThreads;
window.loadThreads = loadThreads;
window.filterThreads = filterThreads;
window.showThreadStack = showThreadStack;
window.checkDeadlock = checkDeadlock;
window.closeThreadDiag = closeThreadDiag;
window.closeThreadStack = closeThreadStack;

// 来自 components/filebrowser.js
window.fbGetCurPath = fbGetCurPath;
window.fbSetCurPath = fbSetCurPath;
window.fbGetFiles = fbGetFiles;
window.renderFileBrowser = renderFileBrowser;

// ══ Hot Swap Workbench 热替换工作台 ══════════════════════════════════════════
// 四步工作流：jad 反编译 → 编辑 → mc 编译 → retransform 热加载

let _hs = { classname: '', sourceCode: '', classFile: '', cloaderHash: '' };

function hotswapReset() {
  _hs = { classname: '', sourceCode: '', classFile: '', cloaderHash: '' };
  document.getElementById('hs-classname').value = '';
  document.getElementById('hs-source').value = '';
  document.getElementById('hs-rt-classfile').value = '';
  document.getElementById('hs-mc-result').style.display = 'none';
  document.getElementById('hs-rt-result').style.display = 'none';
  document.getElementById('hs-mc-btn').disabled = true;
  document.getElementById('hs-rt-btn').disabled = true;
  document.getElementById('hs-editor-status').textContent = '等待反编译...';
  document.getElementById('hs-editor-filename').textContent = '—';
  document.querySelectorAll('.hotswap-step').forEach(el => { el.classList.remove('active','done'); });
  document.getElementById('hs-step1').classList.add('active');
  document.getElementById('hs-log-wrap').style.display = 'none';
  document.getElementById('hs-log').innerHTML = '';
}

function _hsLog(msg, type) {
  const wrap = document.getElementById('hs-log-wrap');
  const log = document.getElementById('hs-log');
  wrap.style.display = 'block';
  const cls = type === 'ok' ? 'hs-ok' : type === 'err' ? 'hs-err' : type === 'cmd' ? 'hs-cmd' : 'hs-dim';
  log.innerHTML += `<span class="${cls}">${msg}</span>\n`;
  log.scrollTop = log.scrollHeight;
}

async function hotswapJad() {
  if(!_connected) { toast('请先连接 Arthas','warn'); return; }
  const cls = document.getElementById('hs-classname').value.trim();
  if(!cls) { toast('请输入类全限定名','warn'); return; }
  _hs.classname = cls;
  const sourceOnly = document.getElementById('hs-source-only').checked;
  const cmd = sourceOnly ? `jad --source-only ${cls}` : `jad ${cls}`;
  _hsLog(`$ ${cmd}`, 'cmd');
  document.getElementById('hs-jad-btn').disabled = true;
  document.getElementById('hs-editor-status').textContent = '反编译中...';
  document.getElementById('hs-step1').classList.add('active');
  try {
    const r = await fetch(`${API}/arthas/exec`, {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({..._ap, command: cmd, connection_id: _currentConnId, timeout_ms: 60000})});
    const d = await r.json();
    if(d.state === 'SUCCEEDED' && d.body?.results) {
      let source = '', hash = '';
      for(const res of d.body.results) {
        if(res.type === 'jad') {
          source = res.sourceCode || res.body?.sourceCode || '';
          // 提取 classloader hash
          if(res.classloaderHash || res.body?.classloaderHash) {
            hash = res.classloaderHash || res.body?.classloaderHash;
          }
        }
        // 也从纯文本结果中提取
        if(res.type === 'text' || res.type === 'normal') {
          const txt = res.body || res.message || '';
          if(!source && txt.includes('package ')) {
            source = txt;
          }
          const hashMatch = txt.match(/hash:\s*([a-f0-9]+)/i);
          if(hashMatch && !hash) hash = hashMatch[1];
        }
      }
      if(source) {
        _hs.sourceCode = source;
        _hs.cloaderHash = hash;
        document.getElementById('hs-source').value = source;
        document.getElementById('hs-editor-status').textContent = hash ? `已反编译 · classloader: ${hash}` : '已反编译';
        document.getElementById('hs-editor-filename').textContent = cls.replace(/\./g, '/') + '.java';
        document.getElementById('hs-mc-btn').disabled = false;
        document.getElementById('hs-step1').classList.remove('active');
        document.getElementById('hs-step1').classList.add('done');
        document.getElementById('hs-step2').classList.add('active');
        _hsLog('✓ 反编译成功', 'ok');
      } else {
        // 尝试从原始输出中提取
        const rawOutput = JSON.stringify(d.body?.results || d);
        document.getElementById('hs-source').value = rawOutput;
        document.getElementById('hs-editor-status').textContent = '原始输出（可能需要手动提取源码）';
        document.getElementById('hs-mc-btn').disabled = false;
        _hsLog('⚠ 未解析到标准格式，已输出原始结果', 'err');
      }
    } else {
      const errMsg = d.message || d.error || JSON.stringify(d);
      document.getElementById('hs-editor-status').textContent = '反编译失败';
      _hsLog('✗ 反编译失败: ' + errMsg, 'err');
    }
  } catch(e) {
    document.getElementById('hs-editor-status').textContent = '请求失败';
    _hsLog('✗ 请求异常: ' + e.message, 'err');
  }
  document.getElementById('hs-jad-btn').disabled = false;
}

async function hotswapMc() {
  if(!_connected) { toast('请先连接 Arthas','warn'); return; }
  const source = document.getElementById('hs-source').value.trim();
  if(!source) { toast('源码为空，请先反编译或手动输入','warn'); return; }

  // 将源码写入 Pod 临时文件
  const tmpJava = `/tmp/arthas-hotswap/${_hs.classname.replace(/\./g, '/')}.java`;
  const tmpDir = `/tmp/arthas-hotswap`;
  const outputDir = document.getElementById('hs-mc-output').value.trim() || '/tmp';

  _hsLog(`$ 写入源码到 ${tmpJava}`, 'cmd');
  document.getElementById('hs-mc-btn').disabled = true;

  try {
    // 1. 在 Pod 中创建临时目录
    await fetch(`${API}/pod/exec`, {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({..._ap, command: `mkdir -p ${tmpDir}`, connection_id: _currentConnId})});

    // 2. 写入源码文件（通过 cat heredoc）
    const escapedSource = source.replace(/'/g, "'\\''");
    await fetch(`${API}/pod/exec`, {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({..._ap, command: `mkdir -p $(dirname ${tmpJava}) && cat > ${tmpJava} << 'ARTHAS_HOTSWAP_EOF'\n${source}\nARTHAS_HOTSWAP_EOF`, connection_id: _currentConnId})});

    // 3. 执行 mc 编译
    const mcCmd = `mc ${tmpJava} -d ${outputDir}`;
    _hsLog(`$ ${mcCmd}`, 'cmd');
    const r = await fetch(`${API}/arthas/exec`, {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({..._ap, command: mcCmd, connection_id: _currentConnId, timeout_ms: 60000})});
    const d = await r.json();

    const mcResult = document.getElementById('hs-mc-result');
    mcResult.style.display = 'block';

    if(d.state === 'SUCCEEDED') {
      // 从结果中提取 .class 文件路径
      let classFile = '';
      if(d.body?.results) {
        for(const res of d.body.results) {
          const txt = res.body || res.message || JSON.stringify(res);
          const pathMatch = txt.match(/(\/[^\s"']+\.class)/);
          if(pathMatch) classFile = pathMatch[1];
        }
      }
      if(!classFile) {
        // 根据类名推算 .class 路径
        classFile = `${outputDir}/${_hs.classname.replace(/\./g, '/')}.class`;
      }
      _hs.classFile = classFile;
      document.getElementById('hs-rt-classfile').value = classFile;
      document.getElementById('hs-rt-btn').disabled = false;
      mcResult.innerHTML = `<div style="padding:8px 10px;background:rgba(52,199,89,.06);border:1px solid rgba(52,199,89,.18);border-radius:6px;color:var(--a3);font-size:11px">✓ 编译成功 → ${classFile}</div>`;
      document.getElementById('hs-step2').classList.remove('active');
      document.getElementById('hs-step2').classList.add('done');
      document.getElementById('hs-step3').classList.remove('active');
      document.getElementById('hs-step3').classList.add('done');
      document.getElementById('hs-step4').classList.add('active');
      _hsLog('✓ 编译成功: ' + classFile, 'ok');
    } else {
      mcResult.innerHTML = `<div style="padding:8px 10px;background:rgba(255,59,48,.06);border:1px solid rgba(255,59,48,.18);border-radius:6px;color:var(--a5);font-size:11px">✗ 编译失败: ${esc(d.message || JSON.stringify(d))}</div>`;
      _hsLog('✗ 编译失败', 'err');
    }
  } catch(e) {
    _hsLog('✗ 编译异常: ' + e.message, 'err');
  }
  document.getElementById('hs-mc-btn').disabled = false;
}

async function hotswapRetransform() {
  if(!_connected) { toast('请先连接 Arthas','warn'); return; }
  const classFile = document.getElementById('hs-rt-classfile').value.trim() || _hs.classFile;
  if(!classFile) { toast('请先编译获取 .class 文件','warn'); return; }

  const rtCmd = `retransform ${classFile}`;
  _hsLog(`$ ${rtCmd}`, 'cmd');
  document.getElementById('hs-rt-btn').disabled = true;

  try {
    const r = await fetch(`${API}/arthas/exec`, {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({..._ap, command: rtCmd, connection_id: _currentConnId, timeout_ms: 60000})});
    const d = await r.json();

    const rtResult = document.getElementById('hs-rt-result');
    rtResult.style.display = 'block';

    if(d.state === 'SUCCEEDED') {
      rtResult.innerHTML = `<div style="padding:10px 12px;background:rgba(52,199,89,.08);border:1px solid rgba(52,199,89,.25);border-radius:6px;color:var(--a3);font-size:12px;font-weight:600">🔥 热加载成功！类 ${_hs.classname} 已更新，无需重启 JVM</div>`;
      document.getElementById('hs-step4').classList.remove('active');
      document.getElementById('hs-step4').classList.add('done');
      _hsLog('✓ 热加载成功！', 'ok');
      _hsLog('提示：retransform 不允许增删方法/字段，如需更大改动请使用 redefine', 'dim');
    } else {
      rtResult.innerHTML = `<div style="padding:8px 10px;background:rgba(255,59,48,.06);border:1px solid rgba(255,59,48,.18);border-radius:6px;color:var(--a5);font-size:11px">✗ 热加载失败: ${esc(d.message || JSON.stringify(d))}</div>`;
      _hsLog('✗ 热加载失败', 'err');
    }
  } catch(e) {
    _hsLog('✗ 热加载异常: ' + e.message, 'err');
  }
  document.getElementById('hs-rt-btn').disabled = false;
}

window.hotswapReset = hotswapReset;
window.hotswapJad = hotswapJad;
window.hotswapMc = hotswapMc;
window.hotswapRetransform = hotswapRetransform;

// ✅ 工具包分发历史
window.loadDistributionHistory = loadDistributionHistory;
window.renderDistributionHistory = renderDistributionHistory;

// ✅ 初始化 ConnectionStore (DOM Ready 后)
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', _initConnectionStore);
} else {
  _initConnectionStore();
}
