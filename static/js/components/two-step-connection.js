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
 * ✅ 使用 connection-store.js 中定义的 ConnectionState
 * 不再重复定义,避免冲突
 */

/**
 * ✅ 使用 ConnectionStore 统一管理状态
 * 不声明本地变量,直接使用 app-ui.js 中的全局变量,避免重复声明
 */
// _connState, _runtimeInfo, _podConnId, _podPhase 由 app-ui.js 声明

/**
 * ✅ 初始化 ConnectionStore 同步
 */
function _initTwoStepConnectionStore() {
  if (typeof ConnectionStore === 'undefined') {
    console.warn('[two-step-connection] ConnectionStore not loaded, using legacy state');
    return;
  }
  
  // 从 ConnectionStore 同步到本地变量
  const state = ConnectionStore.getState();
  _connState = state.connState;
  _runtimeInfo = state.runtimeInfo;
  _podPhase = state.podPhase;
  _podConnId = state.podConnId;
  
  // 订阅状态变化
  ConnectionStore.subscribe((newState, oldState) => {
    // ✅ 修复: 只更新 UI,不覆盖局部变量
    // 局部变量由 podConnect/upgradeToArthas 等函数直接管理
    if (typeof updateConnectionButton === 'function') updateConnectionButton();
    if (typeof updateRuntimeDisplay === 'function') updateRuntimeDisplay();
    if (typeof updateFeatureTabs === 'function') updateFeatureTabs();
  });
  
  console.log('[two-step-connection] ConnectionStore synced');
}

function resetTwoStepConnectionState() {
  // ✅ 优先使用 ConnectionStore
  if (typeof ConnectionStore !== 'undefined') {
    ConnectionStore.setState({
      connState: ConnectionState.DISCONNECTED,
      runtimeInfo: null,
      podPhase: null,
      podConnId: null,
    });
  }
  
  // 更新本地变量
  _connState = ConnectionState.DISCONNECTED;
  _podConnId = null;
  _runtimeInfo = null;
  _podPhase = null;
  
  if (typeof updateConnectionButton === 'function') updateConnectionButton();
  if (typeof updateRuntimeDisplay === 'function') updateRuntimeDisplay();
  const statusEl = document.getElementById('connStatus');
  if (statusEl) statusEl.style.display = 'none';
}

/**
 * 获取连接状态
 */
function getConnectionState() {
  // ✅ 优先从 ConnectionStore 获取
  if (typeof ConnectionStore !== 'undefined') {
    return ConnectionStore.getConnectionState();
  }
  return _connState;
}

function getFocusedPodConnectionForUpgrade() {
  let conn = null;
  if (typeof ConnectionStore !== 'undefined' && typeof ConnectionStore.getFocusConnection === 'function') {
    conn = ConnectionStore.getFocusConnection();
  }

  const connId = _podConnId || _currentConnId || window._currentConnId || conn?.id;
  if (!conn && connId && typeof getConnectionRecordById === 'function') {
    conn = getConnectionRecordById(connId);
  }
  if (!conn && connId && Array.isArray(_connections)) {
    const idText = String(connId);
    conn = _connections.find(item => {
      if (!item) return false;
      return [item.id, item.pod_conn_id, item.connection_id].some(value => {
        if (!value) return false;
        const valueText = String(value);
        return valueText === idText || valueText.split('@u')[0] === idText || idText.split('@u')[0] === valueText;
      });
    }) || null;
  }
  return conn || null;
}

function normalizeRuntimeForUpgrade(conn) {
  if (!conn) return _runtimeInfo || null;
  if (conn.runtime && typeof conn.runtime === 'object') {
    const runtimeType = conn.runtime.runtime_type || conn.runtime.type || conn.runtime_type || 'unknown';
    return {
      ...conn.runtime,
      runtime_type: runtimeType,
      type: conn.runtime.type || conn.runtime.runtime_type || runtimeType,
      version: conn.runtime.version || conn.runtime.runtime_version || conn.runtime_version || '',
      runtime_version: conn.runtime.runtime_version || conn.runtime.version || conn.runtime_version || '',
      pid: conn.runtime.pid || conn.runtime.java_pid || conn.pid || conn.java_pid || null,
    };
  }
  const runtimeType = conn.runtime_type || (typeof conn.runtime === 'string' ? conn.runtime : '');
  if (!runtimeType && !_runtimeInfo) return null;
  return {
    runtime_type: runtimeType || _runtimeInfo?.runtime_type || _runtimeInfo?.type || 'unknown',
    type: runtimeType || _runtimeInfo?.type || _runtimeInfo?.runtime_type || 'unknown',
    version: conn.runtime_version || _runtimeInfo?.version || _runtimeInfo?.runtime_version || '',
    runtime_version: conn.runtime_version || _runtimeInfo?.runtime_version || _runtimeInfo?.version || '',
    pid: conn.pid || conn.java_pid || _runtimeInfo?.pid || _runtimeInfo?.java_pid || null,
  };
}

function isFocusedPodUsableForUpgrade(conn) {
  if (!conn) return false;
  const state = String(conn.state || conn.status || '').toLowerCase();
  const level = String(conn.level || conn.connection_level || '').toLowerCase();
  const runtime = normalizeRuntimeForUpgrade(conn);
  const hasConnectionId = !!(conn.pod_conn_id || conn.connection_id || conn.id);
  const connectedLike = !state || ['connected', 'pod_connected', 'connecting', 'ready', 'ok', 'healthy'].includes(state);
  const podLike = level === 'pod' || level === 'connected' || !!runtime;
  return hasConnectionId && connectedLike && podLike && !!runtime;
}

function hydrateFocusedPodStateForUpgrade() {
  if (_connState === ConnectionState.POD_CONNECTED && _runtimeInfo && _podConnId) return true;
  const conn = getFocusedPodConnectionForUpgrade();
  if (!isFocusedPodUsableForUpgrade(conn)) return false;

  if (typeof hydratePodConnectionForUpgrade === 'function') {
    hydratePodConnectionForUpgrade(conn);
  } else {
    const runtime = normalizeRuntimeForUpgrade(conn);
    const podConnId = conn.pod_conn_id || conn.connection_id || conn.id;
    _connState = ConnectionState.POD_CONNECTED;
    _runtimeInfo = runtime;
    _podConnId = podConnId;
    _podPhase = conn.pod_phase || _podPhase || 'Running';
    window._connState = ConnectionState.POD_CONNECTED;
    window._runtimeInfo = runtime;
    window._currentConnId = conn.id || podConnId;
    if (typeof ConnectionStore !== 'undefined' && typeof ConnectionStore.setState === 'function') {
      ConnectionStore.setState({
        currentConnId: conn.id || podConnId,
        connState: ConnectionState.POD_CONNECTED,
        runtimeInfo: runtime,
        podConnId,
      });
    }
  }
  return Boolean(_connState === ConnectionState.POD_CONNECTED && _runtimeInfo && _podConnId);
}

/**
 * 检查是否可以升级到 Arthas
 */
function canUpgradeToArthas() {
  // 这里校验的是“是否已有可升级的 Pod 连接态”，真正的 Java 校验交给后端升级接口。
  if (_connState === ConnectionState.POD_CONNECTED && _runtimeInfo && _podConnId) return true;
  return hydrateFocusedPodStateForUpgrade();
}

// ── UI 更新函数 ──────────────────────────────────────────────────────────────

/**
 * 更新连接按钮状态
 * ✅ 修复: 步骤3和步骤4的按钮独立控制
 */
function updateConnectionButton() {
  const btn = document.getElementById('ptConnBtn');
  const upgradeBtn = document.getElementById('ptUpgradeBtn');
  
  console.log('[updateConnectionButton] 被调用, _connState:', _connState);
  
  if (!btn) {
    console.warn('[updateConnectionButton] ptConnBtn 不存在!');
    return;
  }

  switch (_connState) {
    case ConnectionState.DISCONNECTED:
      // 步骤3: Pod 连接按钮可用
      btn.textContent = '🔌 Pod 连接';
      btn.className = 'pt-btn';
      btn.disabled = false;
      btn.onclick = podConnect;
      
      // 步骤4: Arthas 升级按钮禁用
      if (upgradeBtn) {
        upgradeBtn.disabled = true;
        upgradeBtn.style.opacity = '0.5';
        upgradeBtn.style.display = 'none';  // ✅ 隐藏按钮
      }
      break;

    case ConnectionState.POD_CONNECTING:
      // 步骤3: Pod 连接中
      btn.textContent = '连接中...';
      btn.className = 'pt-btn';
      btn.disabled = true;
      
      // 步骤4: Arthas 升级按钮禁用
      if (upgradeBtn) {
        upgradeBtn.disabled = true;
        upgradeBtn.style.opacity = '0.5';
        upgradeBtn.style.display = 'none';  // ✅ 隐藏按钮
      }
      break;

    case ConnectionState.POD_CONNECTED:
      console.log('[updateConnectionButton] 进入 POD_CONNECTED case');
      console.log('[updateConnectionButton] canUpgradeToArthas():', canUpgradeToArthas());
      // 步骤3: Pod 已连接
      if (canUpgradeToArthas()) {
        console.log('[updateConnectionButton] canUpgradeToArthas() = true, 启用 Arthas 按钮');
        btn.textContent = '✓ Pod 已连接';
        btn.className = 'pt-btn success';
        btn.disabled = true;
        
        // 步骤4: Arthas 升级按钮可用
        if (upgradeBtn) {
          upgradeBtn.disabled = false;
          upgradeBtn.style.opacity = '1';
          upgradeBtn.style.display = '';  // ✅ 显示按钮
          upgradeBtn.textContent = '⚡ 启动 Arthas';
          upgradeBtn.className = 'pt-btn success';
          console.log('[updateConnectionButton] Arthas 按钮已启用');
        }
      } else {
        console.log('[updateConnectionButton] canUpgradeToArthas() = false, 禁用 Arthas 按钮');
        console.log('[updateConnectionButton] _runtimeInfo:', _runtimeInfo);
        btn.textContent = '✓ Pod 已连接';
        btn.className = 'pt-btn success';
        btn.disabled = true;
        
        // 步骤4: 非 Java 应用, Arthas 升级按钮禁用
        if (upgradeBtn) {
          upgradeBtn.disabled = true;
          upgradeBtn.style.opacity = '0.5';
          upgradeBtn.style.display = '';  // ✅ 显示按钮
          upgradeBtn.textContent = '⚠️ 非 Java 应用,无法升级';
          upgradeBtn.className = 'pt-btn';
        }
      }
      break;

    case ConnectionState.ARTHAS_UPGRADING:
      // 步骤3: Pod 已连接
      btn.textContent = '✓ Pod 已连接';
      btn.className = 'pt-btn success';
      btn.disabled = true;
      
      // 步骤4: Arthas 升级中
      if (upgradeBtn) {
        upgradeBtn.textContent = '启动中...';
        upgradeBtn.className = 'pt-btn';
        upgradeBtn.disabled = true;
        upgradeBtn.style.display = '';  // ✅ 显示按钮
      }
      break;

    case ConnectionState.ARTHAS_READY:
      // 步骤3: Pod 已连接 - ✅ 禁用并隐藏
      btn.textContent = '✓ Pod 已连接';
      btn.className = 'pt-btn success';
      btn.disabled = true;
      btn.style.display = 'none';  // ✅ Arthas 已连接时隐藏 Pod 连接按钮
      
      // 步骤4: Arthas 已就绪
      if (upgradeBtn) {
        upgradeBtn.textContent = '✓ Arthas 已就绪';
        upgradeBtn.className = 'pt-btn success';
        upgradeBtn.disabled = true;
        upgradeBtn.style.display = '';  // ✅ 显示按钮
      }
      break;
  }
}

/**
 * 更新连接状态显示
 * ✅ 修复: 根据状态显示在不同的区域
 */
function updateConnectionStatus(message, type = 'info') {
  // ✅ 步骤3: Pod 连接状态
  const podStatusEl = document.getElementById('podConnStatus');
  // ✅ 步骤4: Arthas 升级状态
  const arthasStatusEl = document.getElementById('arthasUpgradeStatus');
  // 旧版兼容: 通用状态
  const statusEl = document.getElementById('connStatus');

  const colors = {
    info: 'var(--a3)',
    success: 'var(--green)',
    warning: '#f59e0b',
    error: 'var(--red)'
  };

  const html = `
    <div style="padding: 8px 12px; background: rgba(0,0,0,0.3); border-left: 3px solid ${colors[type]}; border-radius: 4px; font-size: 12px; color: ${colors[type]}">
      ${message}
    </div>
  `;

  // ✅ 根据状态显示在不同的区域
  switch (_connState) {
    case ConnectionState.POD_CONNECTING:
    case ConnectionState.POD_CONNECTED:
      // 步骤3: 显示在 Pod 连接下方
      if (podStatusEl) {
        podStatusEl.style.display = 'block';
        podStatusEl.innerHTML = html;
      }
      // 隐藏 Arthas 升级状态
      if (arthasStatusEl) {
        arthasStatusEl.style.display = 'none';
      }
      break;

    case ConnectionState.ARTHAS_UPGRADING:
    case ConnectionState.ARTHAS_READY:
      // 步骤4: 显示在 Arthas 升级下方
      if (arthasStatusEl) {
        arthasStatusEl.style.display = 'block';
        arthasStatusEl.innerHTML = html;
      }
      // 隐藏 Pod 连接状态
      if (podStatusEl) {
        podStatusEl.style.display = 'none';
      }
      break;

    default:
      // 兼容旧版: 显示在通用区域
      if (statusEl) {
        statusEl.style.display = 'block';
        statusEl.innerHTML = html;
      }
  }
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

  // ✅ 空值保护
  const runtimeType = _runtimeInfo ? _runtimeInfo.runtime_type || 'unknown' : 'unknown';
  const icon = runtimeIcons[runtimeType] || '❓';
  const version = _runtimeInfo && _runtimeInfo.version ? ` ${_runtimeInfo.version}` : '';
  const isArthas = _connState === ConnectionState.ARTHAS_READY;
  const isPod = _connState === ConnectionState.POD_CONNECTED;

  let html = `
    <div style="padding: 8px 12px; background: rgba(0,0,0,0.2); border-radius: 4px; font-size: 12px;">
      <div style="color: var(--a5); margin-bottom: 4px;">运行时环境</div>
      <div style="color: var(--fg); font-size: 14px;">
        ${icon} <strong>${runtimeType === 'unknown' ? '未知' : runtimeType}</strong>${version}
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
    // ✅ 移除 Java 检查,简化提示
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
async function podConnect(options = {}) {
  const silentError = !!options.silentError;
  const t = getT();
  window._lastPodConnectError = '';
  if (!t.cluster_name || !t.pod_name) {
    if (!silentError) toast('请先配置集群和 Pod', 'warn');
    window._lastPodConnectError = '请先配置集群和 Pod';
    return false;
  }
  if (typeof validateSelectedNamespace === 'function' && !validateSelectedNamespace()) {
    window._lastPodConnectError = 'namespace 校验失败';
    return false;
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

    // ✅ 调试: 打印后端返回的数据
    console.log('[Pod Connect] ========== 收到后端响应 ==========');
    console.log('[Pod Connect] Backend response:', d);
    console.log('[Pod Connect] runtime:', d.runtime);
    console.log('[Pod Connect] d.ok:', d.ok);

    if (!d.ok) {
      throw new Error(d.error || 'Pod 连接失败');
    }

    // 连接成功
    console.log('[Pod Connect] ========== 开始更新状态 ==========');
    window._manualTargetDirty = false;
    _connState = ConnectionState.POD_CONNECTED;
    console.log('[Pod Connect] _connState 设置为:', _connState, '(ConnectionState.POD_CONNECTED =', ConnectionState.POD_CONNECTED, ')');
    _podConnId = d.connection_id;
    _runtimeInfo = d.runtime || null;  // ✅ 空值保护
    _podPhase = d.pod_phase || null;
    
    console.log('[Pod Connect] _runtimeInfo set to:', _runtimeInfo);
    console.log('[Pod Connect] canUpgradeToArthas():', canUpgradeToArthas());
    
    // ✅ 关键修复: 立即保存状态,防止后续操作覆盖
    const savedConnState = ConnectionState.POD_CONNECTED;
    const savedRuntimeInfo = _runtimeInfo;
    const savedPodConnId = _podConnId;
    const savedPodPhase = _podPhase;
    console.log('[Pod Connect] 保存正确状态: connState=', savedConnState, ', runtimeInfo=', savedRuntimeInfo);
    
    // ✅ 立即更新 UI
    console.log('[Pod Connect] ========== 立即更新 UI ==========');
    updateConnectionButton();
    updateRuntimeDisplay();
    updateFeatureTabs();
    
    console.log('[Pod Connect] ========== 开始同步全局状态 ==========');

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

    // 同步到新连接池
    if (typeof ConnectionStore !== 'undefined' && typeof ConnectionPool !== 'undefined') {
      const existingConn = ConnectionStore.getConnection(d.connection_id);
      if (existingConn) {
        ConnectionStore.updateConnection(d.connection_id, {
          state: ConnectionState.POD_CONNECTED, level: 'pod',
          health: 'ok', lastHb: Date.now(), runtime: d.runtime, pid: d.runtime?.pid,
        });
      } else {
        ConnectionStore.addConnection({
          id: d.connection_id, cluster: t.cluster_name, namespace: t.namespace,
          pod: t.pod_name, runtime: d.runtime, pid: d.runtime?.pid, uptime: '0h',
        });
        ConnectionStore.updateConnection(d.connection_id, {
          state: ConnectionState.POD_CONNECTED, level: 'pod',
          health: 'ok', lastHb: Date.now(),
        });
      }
      ConnectionStore.setFocus(d.connection_id);
      ConnectionPool.render();
      ConnectionWorkspace.render();
    }

    if (typeof renderConnList === 'function') renderConnList();

    // ✅ UI 已经在前面更新过了,这里不再重复调用
    // updateConnectionButton();
    // updateRuntimeDisplay();
    // updateFeatureTabs();

    const versionInfo = _runtimeInfo && _runtimeInfo.version ? ` ${_runtimeInfo.version}` : '';
    const runtimeType = _runtimeInfo ? _runtimeInfo.runtime_type || '未知' : '未知';
    updateConnectionStatus(
      `✓ Pod 连接成功 (${runtimeType}${versionInfo}) - ${d.message}`,
      'success'
    );

    // ✅ 移除 Java 检查,统一提示
    toast('Pod 连接成功，可启动 Arthas 进行深度诊断', 'success');

    // ✅ 关键修复: 设置 window._currentConnId,让状态栏能找到当前连接
    if (typeof _currentConnId !== 'undefined') _currentConnId = d.connection_id;
    window._currentConnId = d.connection_id;
    window._connState = ConnectionState.POD_CONNECTED;
    _connState = savedConnState;
    _runtimeInfo = savedRuntimeInfo;
    _podConnId = savedPodConnId;
    _podPhase = savedPodPhase;

    // 同步到全局状态。跳过从 ConnectionStore 回读，避免旧快照覆盖刚建立的 Pod 状态。
    _syncState && _syncState({ skipMerge: true });
    
    console.log('[Pod Connect] 同步后: _connState=', _connState, ', _runtimeInfo=', _runtimeInfo);
    
    // 再次更新 UI
    updateConnectionButton();
    updateRuntimeDisplay();
    updateFeatureTabs();

    // 刷新连接信息提示条
    if (typeof csbRefresh === 'function') csbRefresh();
    
    // ✅ 关键修复: 清除"正在建立"提示,更新为成功状态
    if (typeof updateConnectionStatus === 'function') {
      const versionInfo = _runtimeInfo && _runtimeInfo.version ? ` ${_runtimeInfo.version}` : '';
      const runtimeType = _runtimeInfo ? _runtimeInfo.runtime_type || '未知' : '未知';
      updateConnectionStatus(
        `✓ Pod 连接成功 (${runtimeType}${versionInfo}) - ${d.message}`,
        'success'
      );
    }

    // Pod 连接成功后收起目标选择区，避免连接操作表单继续占据工作区。
    const podTarget = document.getElementById('podTarget');
    const ptArrow = document.getElementById('ptCollapseArrow');
    if (podTarget && !podTarget.classList.contains('collapsed')) {
      podTarget.classList.add('collapsed');
      if (ptArrow) ptArrow.classList.add('up');
    }

    return true;

  } catch (e) {
    console.error('Pod 连接失败:', e);
    window._lastPodConnectError = e.message || 'Pod 连接失败';
    _connState = ConnectionState.DISCONNECTED;
    updateConnectionButton();
    updateConnectionStatus(`✗ Pod 连接失败: ${e.message}`, 'error');
    
    // 使用精准错误提示
    if (!silentError) {
      if (typeof showPodError === 'function') {
        showPodError(e.message);
      } else {
        toast(`连接失败: ${e.message}`, 'error');
      }
    }
    return false;
  }
}

/**
 * 第二步：升级到 Arthas 连接
 */
async function upgradeToArthas(options = {}) {
  const silentError = !!options.silentError;
  window._lastArthasUpgradeError = '';
  if (!canUpgradeToArthas()) {
    window._lastArthasUpgradeError = '当前不是 Java 应用，无法启动 Arthas';
    if (!silentError) toast('当前不是 Java 应用，无法启动 Arthas', 'warn');
    return false;
  }

  // 前置检查：验证后端连接缓存是否有效
  if (!_podConnId) {
    window._lastArthasUpgradeError = '连接 ID 无效，请重新建立 Pod 连接';
    if (!silentError) toast('连接 ID 无效，请重新建立 Pod 连接', 'error');
    _connState = ConnectionState.DISCONNECTED;
    updateConnectionButton();
    return false;
  }

  try {
    const checkR = await fetch(`${API}/pod/connections`);
    const checkD = await checkR.json();
    if (checkD.ok && Array.isArray(checkD.connections)) {
      const exists = checkD.connections.some(c => c.id === _podConnId || c.connection_id === _podConnId);
      if (!exists) {
        // 后端连接缓存失效，需要重建
        window._lastArthasUpgradeError = 'Pod 连接已失效，请重新连接';
        if (!silentError) toast('Pod 连接已失效，请重新连接', 'warn');
        _connState = ConnectionState.DISCONNECTED;
        _podConnId = null;
        if (typeof renderConnList === 'function') renderConnList();
        if (typeof updateConnectionButton === 'function') updateConnectionButton();
        return false;
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
    window._currentConnId = _podConnId;
    window._connState = ConnectionState.ARTHAS_READY;
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
      conn.status = 'connected';
    }

    const currentConnId = _podConnId || _currentConnId || window._currentConnId;
    if (currentConnId && typeof ConnectionStore !== 'undefined') {
      const connHealth = {
        ...(typeof _connHealth !== 'undefined' ? _connHealth : {}),
        [currentConnId]: { alive: true, pod_exists: true, pod_phase: _podPhase || 'Running' }
      };
      ConnectionStore.setState({
        currentConnId,
        connState: ConnectionState.ARTHAS_READY,
        runtimeInfo: _runtimeInfo || null,
        podConnId: currentConnId,
        connHealth,
      });
      ConnectionStore.updateConnection(currentConnId, {
        level: 'arthas',
        status: 'connected',
        local_port: d.local_port,
        java_pid: d.java_pid,
        arthas_version: d.arthas_version,
        arthas_address: d.arthas_address,
        http_url: d.http_url,
        runtime: _runtimeInfo || null,
        runtime_version: _runtimeInfo?.version || _runtimeInfo?.runtime_version || null,
        alive: true
      });
      console.log('[Arthas Upgrade] ConnectionStore 状态已同步为 arthas_ready:', currentConnId);
    }

    // 更新 UI
    updateConnectionButton();
    updateFeatureTabs();

    // 刷新新连接池和工作区
    if (typeof ConnectionPool !== 'undefined') ConnectionPool.render();
    if (typeof ConnectionWorkspace !== 'undefined') ConnectionWorkspace.render();

    const reused = Boolean(d.reused);
    const verSuffix = d.arthas_version ? ` Arthas ${d.arthas_version}` : '';
    
    // ✅ 只在 Arthas 升级状态区域显示,避免重复
    updateConnectionStatus(
      `✓ Arthas 诊断环境就绪${verSuffix}${reused ? '（复用已有进程）' : ''}`,
      'success'
    );

    // 启用诊断按钮
    document.getElementById('runBtn').disabled = false;

    // 更新 conTitle tooltip
    updateConTitle(d);

    toast('Arthas 诊断环境已就绪', 'success');

    // 同步到全局状态
    _syncState && _syncState();
    if (typeof saveConnections === 'function') saveConnections();
    renderConnList && renderConnList();

    // 刷新连接信息提示条
    if (typeof csbRefresh === 'function') csbRefresh();

    return true;
  } catch (e) {
    console.error('Arthas 启动失败:', e);
    window._lastArthasUpgradeError = e.message || 'Arthas 启动失败';
    _connState = ConnectionState.POD_CONNECTED; // 回退到 Pod 连接状态
    updateConnectionButton();
    updateConnectionStatus(`✗ Arthas 启动失败: ${e.message}`, 'error');
    
    // 使用精准错误提示
    if (!silentError) {
      if (typeof showArthasError === 'function') {
        showArthasError(e.message);
      } else {
        toast(`启动失败: ${e.message}`, 'error');
      }
    }
    return false;
  }
}

/**
 * 断开连接
 */
async function podDisconnect() {
  // ✅ 优先使用 Arthas 连接 ID,如果不存在则使用 Pod 连接 ID
  const activeConnId = _currentConnId || _podConnId;
  
  if (!activeConnId) {
    toast('没有活动连接', 'warn');
    return;
  }

  try {
    // ✅ 优先尝试调用 /api/pod/disconnect (新接口)
    const r = await fetch(`${API}/pod/disconnect`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({
        connection_id: activeConnId
      })
    });

    const d = await r.json();

    if (d.ok) {
      // 从全局连接列表中移除
      if (activeConnId && typeof removeConnection === 'function') {
        removeConnection(activeConnId);
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
      const podStatusEl = document.getElementById('podConnStatus');
      const arthasStatusEl = document.getElementById('arthasUpgradeStatus');
      const statusEl = document.getElementById('connStatus');
      if (podStatusEl) podStatusEl.style.display = 'none';
      if (arthasStatusEl) arthasStatusEl.style.display = 'none';
      if (statusEl) statusEl.style.display = 'none';

      // ✅ 重新显示 Pod 连接按钮
      const btn = document.getElementById('ptConnBtn');
      if (btn) {
        btn.style.display = '';
      }

      toast('连接已断开', 'info');

      // 同步到全局状态
      _syncState && _syncState();
      renderConnList && renderConnList();
    } else {
      // ✅ 如果新接口失败,尝试旧接口
      console.warn('[断开] /api/pod/disconnect 失败,尝试旧接口:', d.error);
      
      const r2 = await fetch(`${API}/arthas/disconnect`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          conn_id: activeConnId
        })
      });
      
      const d2 = await r2.json();
      
      if (d2.ok || r2.status === 200) {
        // 成功断开
        if (activeConnId && typeof removeConnection === 'function') {
          removeConnection(activeConnId);
        }
        
        _connState = ConnectionState.DISCONNECTED;
        _podConnId = null;
        _runtimeInfo = null;
        _podPhase = null;
        _connected = false;
        _currentConnId = null;
        
        updateConnectionButton();
        updateRuntimeDisplay();
        updateFeatureTabs();
        updateConnectionStatus('', 'info');
        
        const podStatusEl = document.getElementById('podConnStatus');
        const arthasStatusEl = document.getElementById('arthasUpgradeStatus');
        const statusEl = document.getElementById('connStatus');
        if (podStatusEl) podStatusEl.style.display = 'none';
        if (arthasStatusEl) arthasStatusEl.style.display = 'none';
        if (statusEl) statusEl.style.display = 'none';
        
        const btn = document.getElementById('ptConnBtn');
        if (btn) {
          btn.style.display = '';
        }
        
        toast('连接已断开', 'info');
        _syncState && _syncState();
        renderConnList && renderConnList();
      } else {
        throw new Error(d2.error || d.error || '断开连接失败');
      }
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
  const addrInfo = data.arthas_address || data.http_url || `http://127.0.0.1:${data.local_port}`;

  const tipRows = [
    `<div class="ct-tip-row"><span class="ct-tip-k">集群</span><span class="ct-tip-v">${esc(t.cluster_name)}</span></div>`,
    `<div class="ct-tip-row"><span class="ct-tip-k">命名空间</span><span class="ct-tip-v">${esc(t.namespace)}</span></div>`,
    `<div class="ct-tip-row"><span class="ct-tip-k">Pod</span><span class="ct-tip-v">${esc(t.pod_name)}</span></div>`,
    data.java_pid ? `<div class="ct-tip-row"><span class="ct-tip-k">Java PID</span><span class="ct-tip-v">${esc(String(data.java_pid))}</span></div>` : '',
    `<div class="ct-tip-row"><span class="ct-tip-k">本地端口</span><span class="ct-tip-v">${esc(String(data.local_port))}</span></div>`,
    `<div class="ct-tip-row"><span class="ct-tip-k">地址</span><span class="ct-tip-v">${esc(addrInfo)}</span></div>`,
    data.arthas_version ? `<div class="ct-tip-row"><span class="ct-tip-k">Arthas</span><span class="ct-tip-v">${esc(data.arthas_version)}</span></div>` : '',
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
  resetTwoStepConnectionState();
  
  // 隐藏运行时信息
  const runtimeEl = document.getElementById('runtimeInfo');
  if (runtimeEl) runtimeEl.style.display = 'none';
  
  // 隐藏连接状态
  const statusEl = document.getElementById('connStatus');
  if (statusEl) statusEl.style.display = 'none';
}

// ── 全局函数暴露 ──────────────────────────────────────────────────────────────
// _connState, _runtimeInfo, _podConnId, _podPhase 已在 app-ui.js 中声明为全局变量
// 无需 defineProperty 拦截，直接使用即可

// ✅ 初始化 ConnectionStore (DOM Ready 后)
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', _initTwoStepConnectionStore);
} else {
  _initTwoStepConnectionStore();
}

// ✅ 暴露全局函数 (延迟到 DOMContentLoaded 后,确保所有依赖已加载)
function _exposeGlobalFunctions() {
  console.log('[two-step-connection] ========== 开始暴露全局函数 ==========');
  console.log('[two-step-connection] podConnect function exists:', typeof podConnect);
  console.log('[two-step-connection] upgradeToArthas function exists:', typeof upgradeToArthas);
  console.log('[two-step-connection] getT function exists:', typeof getT);

  // 暴露所有全局函数
  window.podConnect = podConnect;
  window.podDisconnect = podDisconnect;
  window.upgradeToArthas = upgradeToArthas;
  window.getConnectionState = getConnectionState;
  window.canUpgradeToArthas = canUpgradeToArthas;
  window.initTwoStepConnection = initTwoStepConnection;
  window.resetTwoStepConnectionState = resetTwoStepConnectionState;

  console.log('[two-step-connection] window.podConnect:', typeof window.podConnect);
  console.log('[two-step-connection] window.upgradeToArthas:', typeof window.upgradeToArthas);
  console.log('[two-step-connection] window.podDisconnect:', typeof window.podDisconnect);
  console.log('[two-step-connection] ========== 全局函数暴露完成 ==========');

  // 立即测试
  if (typeof window.podConnect === 'function') {
    console.log('✅ SUCCESS: podConnect 已成功暴露到全局!');
  } else {
    console.error('❌ ERROR: podConnect 暴露失败!');
  }
}

// DOM Ready 后暴露全局函数
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', _exposeGlobalFunctions);
} else {
  _exposeGlobalFunctions();
}
