/**
 * 两步连接流程组件
 * 
 * 实现：
 * 1. Pod 连接（轻量级，2-3秒）
 * 2. 可选升级到 Arthas（仅 Java 应用）
 * 
 * 替代原有的 arthasConnect() 函数
 */

// ── 连接状态管理 ──────────────────────────────────────────────────────────────

/**
 * 连接状态枚举
 */
const ConnectionState = {
  DISCONNECTED: 'disconnected',      // 未连接
  POD_CONNECTING: 'pod_connecting',  // Pod 连接中
  POD_CONNECTED: 'pod_connected',    // Pod 已连接
  ARTHAS_UPGRADING: 'arthas_upgrading', // Arthas 升级中
  ARTHAS_READY: 'arthas_ready'       // Arthas 就绪
};

/**
 * 当前连接状态
 */
let _connState = ConnectionState.DISCONNECTED;
let _podConnId = null;       // Pod 连接 ID
let _runtimeInfo = null;     // 运行时信息
let _podPhase = null;        // Pod 阶段

/**
 * 获取连接状态
 */
function getConnectionState() {
  return _connState;
}

/**
 * 检查是否可以升级到 Arthas
 */
function canUpgradeToArthas() {
  return _connState === ConnectionState.POD_CONNECTED && 
         _runtimeInfo && 
         _runtimeInfo.runtime_type === 'java';
}

// ── UI 更新函数 ──────────────────────────────────────────────────────────────

/**
 * 更新连接按钮状态
 */
function updateConnectionButton() {
  const btn = document.getElementById('ptConnBtn');
  if (!btn) return;

  switch (_connState) {
    case ConnectionState.DISCONNECTED:
      btn.textContent = '🔌 Pod 连接';
      btn.className = 'pt-btn';
      btn.disabled = false;
      btn.onclick = podConnect;
      break;

    case ConnectionState.POD_CONNECTING:
      btn.textContent = '连接中...';
      btn.className = 'pt-btn';
      btn.disabled = true;
      break;

    case ConnectionState.POD_CONNECTED:
      if (canUpgradeToArthas()) {
        btn.textContent = '⚡ 启动 Arthas';
        btn.className = 'pt-btn';
        btn.disabled = false;
        btn.onclick = upgradeToArthas;
      } else {
        btn.textContent = '✓ Pod 已连接';
        btn.className = 'pt-btn success';
        btn.disabled = true;
      }
      break;

    case ConnectionState.ARTHAS_UPGRADING:
      btn.textContent = '启动中...';
      btn.className = 'pt-btn';
      btn.disabled = true;
      break;

    case ConnectionState.ARTHAS_READY:
      btn.textContent = '⚡ Arthas 就绪';
      btn.className = 'pt-btn success';
      btn.disabled = true;
      break;
  }
}

/**
 * 更新连接状态显示
 */
function updateConnectionStatus(message, type = 'info') {
  const statusEl = document.getElementById('connStatus');
  if (!statusEl) return;

  statusEl.style.display = 'block';
  
  const colors = {
    info: 'var(--a3)',
    success: 'var(--green)',
    warning: '#f59e0b',
    error: 'var(--red)'
  };

  statusEl.innerHTML = `
    <div style="padding: 8px 12px; background: rgba(0,0,0,0.3); border-left: 3px solid ${colors[type]}; border-radius: 4px; font-size: 12px; color: ${colors[type]}">
      ${message}
    </div>
  `;
}

/**
 * 更新运行时信息展示
 * 功能点6: 增强展示——区分连接层级，显示 Pod/Arthas 状态
 */
function updateRuntimeDisplay() {
  const runtimeEl = document.getElementById('runtimeInfo');
  if (!runtimeEl) return;

  if (!_runtimeInfo) {
    runtimeEl.style.display = 'none';
    return;
  }

  runtimeEl.style.display = 'block';

  const runtimeIcons = {
    java: '☕',
    node: '🟢',
    python: '🐍',
    go: '🔵',
    unknown: '❓'
  };

  const icon = runtimeIcons[_runtimeInfo.runtime_type] || '❓';
  const version = _runtimeInfo.version ? ` ${_runtimeInfo.version}` : '';
  const isArthas = _connState === ConnectionState.ARTHAS_READY;
  const isPod = _connState === ConnectionState.POD_CONNECTED;

  let html = `
    <div style="padding: 8px 12px; background: rgba(0,0,0,0.2); border-radius: 4px; font-size: 12px;">
      <div style="color: var(--a5); margin-bottom: 4px;">运行时环境</div>
      <div style="color: var(--fg); font-size: 14px;">
        ${icon} <strong>${_runtimeInfo.runtime_type}</strong>${version}
      </div>
  `;

  // 显示连接层级状态
  if (isArthas) {
    html += `
      <div style="margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--border); color: var(--a3);">
        <div style="margin-bottom: 4px;">⚡ Arthas 模式 — 全部功能已解锁</div>
        <div style="display: flex; gap: 8px; flex-wrap: wrap;">
          <span class="feature-tag">📊 监控</span>
          <span class="feature-tag">📁 文件</span>
          <span class="feature-tag">🖥️ 终端</span>
          <span class="feature-tag">🔬 诊断</span>
          <span class="feature-tag">⚡ Arthas</span>
          <span class="feature-tag">🔥 采样</span>
        </div>
      </div>
    `;
  } else if (isPod) {
    if (_runtimeInfo.runtime_type === 'java') {
      html += `
        <div style="margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--border); color: var(--a4);">
          <div style="margin-bottom: 4px;">💡 Pod 已连接 — 可启动 Arthas 解锁深度诊断</div>
          <div style="display: flex; gap: 8px; flex-wrap: wrap;">
            <span class="feature-tag">📊 监控</span>
            <span class="feature-tag">📁 文件</span>
            <span class="feature-tag">🖥️ 终端</span>
            <span class="feature-tag">🔬 诊断</span>
            <span class="feature-tag" style="opacity:.4;text-decoration:line-through">⚡ Arthas</span>
            <span class="feature-tag" style="opacity:.4;text-decoration:line-through">🔥 采样</span>
          </div>
        </div>
      `;
    } else {
      html += `
        <div style="margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--border); color: var(--a3);">
          <div style="margin-bottom: 4px;">✓ Pod 已连接（${_runtimeInfo.runtime_type} 运行时）</div>
          <div style="display: flex; gap: 8px; flex-wrap: wrap;">
            <span class="feature-tag">📊 监控</span>
            <span class="feature-tag">📁 文件</span>
            <span class="feature-tag">🖥️ 终端</span>
            <span class="feature-tag">🔬 诊断</span>
            <span class="feature-tag" style="opacity:.4;text-decoration:line-through">⚡ Arthas</span>
            <span class="feature-tag" style="opacity:.4;text-decoration:line-through">🔥 采样</span>
          </div>
        </div>
      `;
    }
  }

  html += `</div>`;
  runtimeEl.innerHTML = html;
}

/**
 * 更新功能标签的可用状态
 * 通过 ConnectionGuard 统一管理层级需求
 */
function updateFeatureTabs() {
  // 所有 Tab 及其所需层级
  const tabConfig = {
    'monitor':     'pod',       // 📊 Pod 监控
    'filebrowser': 'pod',       // 📂 文件下载
    'terminal':    'pod',       // 🖥️ 终端
    'diag':        'pod',       // 🔬 性能诊断（混合：Pod 可用部分，Arthas 解锁全部）
    'console':     'arthas',    // ⚡ Arthas 命令
    'profiler':    'arthas',    // 🔥 采样工具
    'ai':          'none',      // 🤖 AI 助手
    'history':     'none',      // 📋 历史记录
  };

  const currentLevel = window.ConnectionGuard ? ConnectionGuard.getCurrentLevel() :
    (_connState === ConnectionState.ARTHAS_READY ? 'arthas' :
     _connState === ConnectionState.POD_CONNECTED ? 'pod' : 'none');
  const levelRank = { none: 0, pod: 1, arthas: 2 };

  Object.entries(tabConfig).forEach(([tabId, required]) => {
    const tab = document.getElementById(`tab-${tabId}`);
    if (!tab) return;

    const ok = levelRank[currentLevel] >= levelRank[required];
    const isDiag = tabId === 'diag'; // 混合 Tab 特殊处理

    // 清除所有状态 class
    tab.classList.remove('disabled', 'locked', 'partial');

    if (ok) {
      if (isDiag && currentLevel === 'pod') {
        // 诊断 Tab：Pod 层级可用部分功能
        tab.classList.add('partial');
        tab.title = '部分功能可用（完整诊断需启动 Arthas）';
      } else {
        tab.title = '';
      }
    } else if (required === 'arthas' && currentLevel === 'pod') {
      // Pod 已连接但需 Arthas → locked 态（可见不可用）
      tab.classList.add('locked');
      tab.title = '需要启动 Arthas 诊断环境';
    } else if (required !== 'none') {
      // 未连接 → disabled 态
      tab.classList.add('disabled');
      tab.title = required === 'arthas' ? '需要启动 Arthas 诊断环境' : '需要先建立 Pod 连接';
    }
  });

  // 连接升级/降级时，清除所有面板的锁定态（切 Tab 时会重新判断）
  document.querySelectorAll('.panel-locked').forEach(el => el.classList.remove('panel-locked'));
  // 隐藏所有引导面板
  if (window.ConnectionGuard) ConnectionGuard.hideGuide();
  // 刷新连接信息提示条
  if (typeof csbRefresh === 'function') csbRefresh();
}

// ── 核心连接函数 ──────────────────────────────────────────────────────────────

/**
 * 第一步：建立 Pod 连接
 */
async function podConnect() {
  const t = getT();
  if (!t.cluster_name || !t.pod_name) {
    toast('请先配置集群和 Pod', 'warn');
    return;
  }

  // 更新状态
  _connState = ConnectionState.POD_CONNECTING;
  updateConnectionButton();
  updateConnectionStatus('正在建立 Pod 连接...', 'info');

  try {
    const r = await fetch(`${API}/pod/connect`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({
        cluster_name: t.cluster_name,
        namespace: t.namespace,
        pod_name: t.pod_name,
        container: t.container
      })
    });

    const d = await r.json();

    if (!d.ok) {
      throw new Error(d.error || 'Pod 连接失败');
    }

    // 连接成功
    _connState = ConnectionState.POD_CONNECTED;
    _podConnId = d.connection_id;
    _runtimeInfo = d.runtime;
    _podPhase = d.pod_phase;

    // 同步到旧版全局状态：Pod 连接也必须成为当前连接，供监控/文件/终端等 Pod 级功能使用
    if (typeof _currentConnId !== 'undefined') _currentConnId = d.connection_id;
    if (typeof _connected !== 'undefined') _connected = false; // _connected 仅表示 Arthas 可用
    if (typeof _ap !== 'undefined') _ap = getT();
    if (typeof _connHealth !== 'undefined') {
      _connHealth[d.connection_id] = { alive: true, pod_exists: true, pod_phase: d.pod_phase || 'Running' };
    }

    // 将 Pod 连接加入全局连接列表（带 level 字段）
    if (typeof addConnection === 'function') {
      addConnection({
        id: d.connection_id,
        cluster_name: t.cluster_name,
        namespace: t.namespace,
        pod_name: t.pod_name,
        container: t.container,
        level: 'pod',
        runtime: d.runtime,
        pod_phase: d.pod_phase,
        pod_conn_id: d.connection_id,
        status: 'connected',
        created_at: new Date().toISOString()
      });
    }
    if (typeof renderConnList === 'function') renderConnList();

    // 更新 UI
    updateConnectionButton();
    updateRuntimeDisplay();
    updateFeatureTabs();

    const versionInfo = _runtimeInfo && _runtimeInfo.version ? ` ${_runtimeInfo.version}` : '';
    updateConnectionStatus(
      `✓ Pod 连接成功 (${_runtimeInfo.runtime_type}${versionInfo}) - ${d.message}`,
      'success'
    );

    // 显示提示
    if (_runtimeInfo.runtime_type === 'java') {
      toast('Pod 连接成功，可启动 Arthas 进行深度诊断', 'success');
    } else {
      toast(`Pod 连接成功 (${_runtimeInfo.runtime_type})，基础运维功能已可用`, 'success');
    }

    // 同步到全局状态
    _syncState && _syncState();

    // 刷新连接信息提示条
    if (typeof csbRefresh === 'function') csbRefresh();

  } catch (e) {
    console.error('Pod 连接失败:', e);
    _connState = ConnectionState.DISCONNECTED;
    updateConnectionButton();
    updateConnectionStatus(`✗ Pod 连接失败: ${e.message}`, 'error');
    
    // 使用精准错误提示
    if (typeof showPodError === 'function') {
      showPodError(e.message);
    } else {
      toast(`连接失败: ${e.message}`, 'error');
    }
  }
}

/**
 * 第二步：升级到 Arthas 连接
 */
async function upgradeToArthas() {
  if (!canUpgradeToArthas()) {
    toast('当前不是 Java 应用，无法启动 Arthas', 'warn');
    return;
  }

  // 前置检查：验证后端连接缓存是否有效
  if (!_podConnId) {
    toast('连接 ID 无效，请重新建立 Pod 连接', 'error');
    _connState = ConnectionState.DISCONNECTED;
    updateConnectionButton();
    return;
  }

  try {
    const checkR = await fetch(`${API}/pod/connections`);
    const checkD = await checkR.json();
    if (checkD.ok && Array.isArray(checkD.connections)) {
      const exists = checkD.connections.some(c => c.id === _podConnId || c.connection_id === _podConnId);
      if (!exists) {
        // 后端连接缓存失效，需要重建
        toast('Pod 连接已失效，请重新连接', 'warn');
        _connState = ConnectionState.DISCONNECTED;
        _podConnId = null;
        if (typeof renderConnList === 'function') renderConnList();
        if (typeof updateConnectionButton === 'function') updateConnectionButton();
        return;
      }
    }
  } catch (_) {
    // 检查失败不阻塞，继续尝试
  }

  // 更新状态
  _connState = ConnectionState.ARTHAS_UPGRADING;
  updateConnectionButton();
  updateConnectionStatus('正在启动 Arthas 诊断环境...', 'info');

  try {
    const r = await fetch(`${API}/pod/upgrade-to-arthas`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({
        connection_id: _podConnId,
        java_pid: window._selectedJavaPid || null
      })
    });

    const d = await r.json();

    if (!d.ok) {
      throw new Error(d.error || 'Arthas 启动失败');
    }

    // 升级成功
    _connState = ConnectionState.ARTHAS_READY;

    // 更新全局连接状态（兼容旧代码）
    _connected = true;
    _currentConnId = _podConnId;
    _ap = getT();

    // 更新连接信息（升级 level 为 arthas）
    const conn = _connections.find(c => c.id === _podConnId);
    if (conn) {
      conn.level = 'arthas';
      conn.local_port = d.local_port;
      conn.java_pid = d.java_pid;
      conn.arthas_version = d.arthas_version;
      conn.arthas_address = d.arthas_address;
      conn.http_url = d.http_url;
      conn.mcp_available = d.mcp_available;
      conn.status = 'connected';
    }

    // 更新 UI
    updateConnectionButton();
    updateFeatureTabs();

    const verSuffix = d.arthas_version ? ` Arthas ${d.arthas_version}` : '';
    updateConnectionStatus(
      `✓ Arthas 诊断环境就绪${verSuffix} - ${d.message}`,
      'success'
    );

    // 更新连接状态提示（复用原有逻辑）
    setCpSt('ok', `✓ ${d.message} (port:${d.local_port})`);
    document.getElementById('runBtn').disabled = false;

    // 更新 conTitle tooltip
    updateConTitle(d);

    toast('Arthas 诊断环境已就绪', 'success');

    // 同步到全局状态
    _syncState && _syncState();
    renderConnList && renderConnList();

    // 刷新连接信息提示条
    if (typeof csbRefresh === 'function') csbRefresh();

  } catch (e) {
    console.error('Arthas 启动失败:', e);
    _connState = ConnectionState.POD_CONNECTED; // 回退到 Pod 连接状态
    updateConnectionButton();
    updateConnectionStatus(`✗ Arthas 启动失败: ${e.message}`, 'error');
    
    // 使用精准错误提示
    if (typeof showArthasError === 'function') {
      showArthasError(e.message);
    } else {
      toast(`启动失败: ${e.message}`, 'error');
    }
  }
}

/**
 * 断开连接
 */
async function podDisconnect() {
  if (!_podConnId) {
    toast('没有活动连接', 'warn');
    return;
  }

  try {
    const r = await fetch(`${API}/pod/disconnect`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({
        connection_id: _podConnId
      })
    });

    const d = await r.json();

    if (d.ok) {
      // 从全局连接列表中移除（在重置之前，需要用到 _podConnId）
      if (_podConnId && typeof removeConnection === 'function') {
        removeConnection(_podConnId);
      }

      // 重置状态
      _connState = ConnectionState.DISCONNECTED;
      _podConnId = null;
      _runtimeInfo = null;
      _podPhase = null;
      _connected = false;
      _currentConnId = null;

      // 更新 UI
      updateConnectionButton();
      updateRuntimeDisplay();
      updateFeatureTabs();
      updateConnectionStatus('', 'info');

      // 隐藏状态显示
      const statusEl = document.getElementById('connStatus');
      if (statusEl) statusEl.style.display = 'none';

      toast('连接已断开', 'info');

      // 同步到全局状态
      _syncState && _syncState();
      renderConnList && renderConnList();
    }

  } catch (e) {
    console.error('断开连接失败:', e);
    toast(`断开失败: ${e.message}`, 'error');
  }
}

/**
 * 更新 conTitle tooltip（复用原有逻辑）
 */
function updateConTitle(data) {
  const conTitleEl = document.getElementById('conTitle');
  if (!conTitleEl) return;

  const t = getT();
  const mcpClass = data.mcp_available ? 'live' : 'dead';
  const mcpText = data.mcp_available ? '✓ 可用' : '✗ 不可用';
  const addrInfo = data.arthas_address || data.http_url || `http://127.0.0.1:${data.local_port}`;

  const tipRows = [
    `<div class="ct-tip-row"><span class="ct-tip-k">集群</span><span class="ct-tip-v">${esc(t.cluster_name)}</span></div>`,
    `<div class="ct-tip-row"><span class="ct-tip-k">命名空间</span><span class="ct-tip-v">${esc(t.namespace)}</span></div>`,
    `<div class="ct-tip-row"><span class="ct-tip-k">Pod</span><span class="ct-tip-v">${esc(t.pod_name)}</span></div>`,
    data.java_pid ? `<div class="ct-tip-row"><span class="ct-tip-k">Java PID</span><span class="ct-tip-v">${esc(String(data.java_pid))}</span></div>` : '',
    `<div class="ct-tip-row"><span class="ct-tip-k">本地端口</span><span class="ct-tip-v">${esc(String(data.local_port))}</span></div>`,
    `<div class="ct-tip-row"><span class="ct-tip-k">地址</span><span class="ct-tip-v">${esc(addrInfo)}</span></div>`,
    data.arthas_version ? `<div class="ct-tip-row"><span class="ct-tip-k">Arthas</span><span class="ct-tip-v">${esc(data.arthas_version)}</span></div>` : '',
    `<div class="ct-tip-row"><span class="ct-tip-k">MCP</span><span class="ct-tip-v ${mcpClass}">${mcpText}</span></div>`,
  ].filter(Boolean).join('');

  conTitleEl.innerHTML = `${esc(t.cluster_name)}/${esc(t.namespace)}/${esc(t.pod_name)}<span class="ct-tip"><div class="ct-tip-hd"><div class="ct-tip-icon">⚡</div><div><div class="ct-tip-pod">${esc(t.pod_name)}</div><div class="ct-tip-ns">${esc(t.cluster_name)} / ${esc(t.namespace)}</div></div></div><div class="ct-tip-body">${tipRows}</div></span>`;

  // 更新 Arthas 版本徽章
  const verBadge = document.getElementById('arthasVerBadge');
  if (verBadge) {
    if (data.arthas_version) {
      verBadge.textContent = `Arthas v${data.arthas_version}`;
      verBadge.style.display = '';
    } else {
      verBadge.style.display = 'none';
    }
  }
}

// ── 初始化 ────────────────────────────────────────────────────────────────────

/**
 * 初始化两步连接流程
 */
function initTwoStepConnection() {
  console.log('两步连接流程已初始化');
  
  // 重置状态
  _connState = ConnectionState.DISCONNECTED;
  
  // 更新按钮
  updateConnectionButton();
  
  // 隐藏运行时信息
  const runtimeEl = document.getElementById('runtimeInfo');
  if (runtimeEl) runtimeEl.style.display = 'none';
  
  // 隐藏连接状态
  const statusEl = document.getElementById('connStatus');
  if (statusEl) statusEl.style.display = 'none';
}

// ── 全局函数暴露 ──────────────────────────────────────────────────────────────
// 将函数暴露到 window 对象，供 HTML onclick 调用
window.podConnect = podConnect;
window.podDisconnect = podDisconnect;
window.upgradeToArthas = upgradeToArthas;
window.getConnectionState = getConnectionState;
window.canUpgradeToArthas = canUpgradeToArthas;
window.initTwoStepConnection = initTwoStepConnection;
// P0-1: 状态变更时自动同步到 window，让 diagnose.js 等模块可读取
// 用 getter/setter 拦截，确保外部赋值也能更新内部状态
(function() {
  Object.defineProperty(window, '_connState', {
    get() { return _connState; },
    set(v) {
      // 外部赋值时同步到内部状态
      if (typeof ConnectionState !== 'undefined') {
        if (v === 'pod_connected' || v === ConnectionState.POD_CONNECTED) {
          _connState = ConnectionState.POD_CONNECTED;
        } else if (v === 'arthas_ready' || v === ConnectionState.ARTHAS_READY) {
          _connState = ConnectionState.ARTHAS_READY;
        } else if (v === 'disconnected' || v === ConnectionState.DISCONNECTED) {
          _connState = ConnectionState.DISCONNECTED;
        } else {
          _connState = v;
        }
      } else {
        _connState = v;
      }
    },
    configurable: true
  });
  Object.defineProperty(window, '_runtimeInfo', {
    get() { return _runtimeInfo; },
    set(v) { _runtimeInfo = v; },
    configurable: true
  });
})();
