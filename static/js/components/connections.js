/**
 * 连接管理组件
 * 处理连接列表、连接切换、连接删除
 * 
 * 连接层级 (level):
 *   'pod'    — 仅 Pod 连接（kubectl exec 通道）
 *   'arthas' — Pod + Arthas 连接（深度诊断）
 */

// ── State ─────────────────────────────────────────────────────────────────
// _connections, _currentConnId 在 app-ui.js 中声明，使用 window 访问

// ── 获取/设置 ────────────────────────────────────────────────────────────

function getConnections() {
  return window._connections || [];
}

function setConnections(conns) {
  window._connections = conns || [];
  saveConnections();
}

function getCurrentConnId() {
  return window._currentConnId || null;
}

function setCurrentConnId(id) {
  window._currentConnId = id;
}

function getCurrentConnection() {
  return (window._connections || []).find(c => c.id === (window._currentConnId || null)) || null;
}

// ── level 辅助函数 ──────────────────────────────────────────────────────

/**
 * 推断连接层级
 * 优先使用显式 level 字段，否则根据元数据推断
 */
function inferConnLevel(conn) {
  if (conn.level) return conn.level;
  // 有 Arthas 元数据 → arthas
  if (conn.local_port || conn.arthas_version || conn.java_pid) return 'arthas';
  // 有 runtime 信息但无 Arthas → pod
  if (conn.runtime_type || conn.runtime) return 'pod';
  // 兼容旧数据：有 status=connected 的一般是旧 Arthas 连接
  if (conn.status === 'connected') return 'arthas';
  return 'pod';
}

/**
 * 获取连接的运行时信息
 */
function getConnRuntime(conn) {
  if (conn.runtime && typeof conn.runtime === 'object') {
    // 后端 RuntimeInfo.__dict__ 字段为 runtime_type/version，前端统一为 type/version
    const rt = conn.runtime;
    return { type: rt.type || rt.runtime_type, version: rt.version || rt.runtime_version || '' };
  }
  // 兼容旧字段
  if (conn.runtime_type) return { type: conn.runtime_type, version: conn.runtime_version || '' };
  return null;
}

/**
 * 获取运行时图标
 */
function getRuntimeIcon(type) {
  const icons = { java: '☕', node: '🟢', python: '🐍', go: '🔵', dotnet: '🟣', unknown: '❓' };
  return icons[type] || '❓';
}

/**
 * 判断连接是否可升级到 Arthas
 * 条件：level=pod 且运行时为 Java
 */
function canUpgradeConnection(conn) {
  if (!conn) return false;
  const level = inferConnLevel(conn);
  if (level === 'arthas') return false;
  const rt = getConnRuntime(conn);
  return rt && rt.type === 'java';
}

// ── 本地存储 ─────────────────────────────────────────────────────────────

function saveConnections() {
  localStorage.setItem('arthas_connections', JSON.stringify(window._connections || []));
  // 保存当前选中的连接 ID
  if (window._currentConnId) {
    localStorage.setItem('arthas_current_conn_id', window._currentConnId);
  } else {
    localStorage.removeItem('arthas_current_conn_id');
  }
}

function loadConnections() {
  try {
    const stored = localStorage.getItem('arthas_connections');
    if (stored) {
      window._connections = JSON.parse(stored);
      // 确保 id 和 level 字段
      window._connections = window._connections.map(c => ({
        ...c,
        id: c.id || `${c.cluster || c.cluster_name}/${c.namespace}/${c.pod || c.pod_name}`,
        level: inferConnLevel(c),
      }));
    } else {
      window._connections = [];
    }
    
    // 加载当前选中的连接 ID
    const currentStored = localStorage.getItem('arthas_current_conn_id');
    if (currentStored) {
      window._currentConnId = currentStored;
    }
  } catch (e) {
    console.error('加载连接失败:', e);
    window._connections = [];
  }
}

// ── 渲染 ─────────────────────────────────────────────────────────────────

function renderConnList() {
  const listEl = document.getElementById('connList');
  if (!listEl) return;
  
  if ((window._connections || []).length === 0) {
    listEl.innerHTML = '<div class="sb-empty">暂无连接<br>使用下方添加</div>';
    return;
  }
  
  listEl.innerHTML = (window._connections || []).map(conn => {
    const isActive = conn.id === (window._currentConnId || null);
    const level = inferConnLevel(conn);
    const rt = getConnRuntime(conn);
    
    // 层级标识
    const levelIcon = level === 'arthas' ? '⚡' : '🔵';
    const levelBadge = `<span class="conn-level ${level}">${level === 'arthas' ? 'Arthas连接' : 'Pod连接'}</span>`;
    
    // 运行时信息行（补充：从当前连接状态获取，以防旧缓存中缺失）
    let runtimeLine = '';
    if (rt) {
      const icon = getRuntimeIcon(rt.type);
      runtimeLine = `<div class="conn-runtime">${icon} ${rt.type}${rt.version ? ' ' + rt.version : ''}${conn.java_pid ? ' · PID ' + conn.java_pid : ''}</div>`;
    } else if (isActive && window._runtimeInfo) {
      const ri = window._runtimeInfo;
      if (ri.runtime_type || ri.type) {
        const rt2type = ri.type || ri.runtime_type;
        const rt2ver = ri.version || ri.runtime_version || '';
        const rt2pid = ri.java_pid || '';
        runtimeLine = `<div class="conn-runtime">${getRuntimeIcon(rt2type)} ${rt2type}${rt2ver ? ' ' + rt2ver : ''}${rt2pid ? ' · PID ' + rt2pid : ''}</div>`;
      }
    }
    
    // 升级按钮（Pod + Java → 可升级）
    let upgradeBtn = '';
    if (canUpgradeConnection(conn)) {
      upgradeBtn = `<div class="conn-upgrade-btn" onclick="event.stopPropagation();upgradeConnectionFromList('${esc(conn.id)}')">⚡ 启动 Arthas</div>`;
    }
    
    // 状态图标
    const h = (window._connHealth || {})[conn.id];
    let statusIcon = '', statusStyle = '', statusHint = '';
    if (h) {
      if (h.pod_exists === false) {
        statusIcon = '⚠'; statusStyle = 'color:var(--a5)'; statusHint = 'Pod 不存在';
      } else if (h.alive === false && level === 'arthas') {
        statusIcon = '◉'; statusStyle = 'color:#f59e0b'; statusHint = 'Arthas 已断开';
      } else if (h.alive === false) {
        statusIcon = '◈'; statusStyle = 'color:#f59e0b'; statusHint = '连接已断开';
      } else if (h.pod_exists === true) {
        statusIcon = '●'; statusStyle = 'color:var(--a3)'; statusHint = '连接正常';
      }
    }
    
    return `
      <div class="conn-itm ${isActive ? 'on' : ''}" data-id="${esc(conn.id)}" onclick="switchConnection('${esc(conn.id)}')" title="${esc(conn.cluster_name || conn.cluster || '')} / ${esc(conn.namespace)} / ${esc(conn.pod_name || conn.pod || '')}${statusHint ? '\n' + statusHint : ''}">
        <div class="conn-info">
          <div class="conn-cluster">
            ${statusIcon ? `<span style="font-size:9px;${statusStyle};margin-right:3px" title="${statusHint}">${statusIcon}</span>` : `<span style="font-size:11px">${levelIcon}</span>`}
            ${esc(conn.cluster_name || conn.cluster || '')}
            ${levelBadge}
          </div>
          <div class="conn-pod"><span class="conn-ns">${esc(conn.namespace)}</span><span class="conn-slash">/</span><span class="conn-name">${esc(conn.pod_name || conn.pod || '')}</span></div>
          ${runtimeLine}
          ${upgradeBtn}
        </div>
        <button class="del-conn" onclick="event.stopPropagation();deleteConnection('${esc(conn.id)}')" title="删除连接">✕</button>
      </div>`;
  }).join('');
}

// ── 操作 ─────────────────────────────────────────────────────────────────

function addConnection(conn) {
  const exists = (window._connections || []).find(c => c.id === conn.id);
  if (!exists) {
    // 确保 level 字段
    conn.level = inferConnLevel(conn);
    conn.status = conn.status || 'connected';
    conn.mcp_available = conn.mcp_available || false;
    window._connections.push(conn);
    saveConnections();
  } else {
    // 更新现有连接的状态信息
    exists.status = conn.status || 'connected';
    exists.mcp_available = conn.mcp_available !== undefined ? conn.mcp_available : exists.mcp_available;
    // 更新 level
    if (conn.level) exists.level = conn.level;
    // 更新运行时信息
    if (conn.runtime) exists.runtime = conn.runtime;
    if (conn.runtime_type) exists.runtime_type = conn.runtime_type;
    // 更新 Arthas 信息
    if (conn.local_port) exists.local_port = conn.local_port;
    if (conn.java_pid) exists.java_pid = conn.java_pid;
    if (conn.arthas_version) exists.arthas_version = conn.arthas_version;
    if (conn.arthas_address) exists.arthas_address = conn.arthas_address;
    saveConnections();
  }
}

function removeConnection(connId) {
  window._connections = (window._connections || []).filter(c => c.id !== connId);
  if (window._currentConnId === connId) {
    window._currentConnId = null;
  }
  saveConnections();
}

/**
 * 从连接列表中触发升级到 Arthas
 */
function upgradeConnectionFromList(connId) {
  const conn = (window._connections || []).find(c => c.id === connId);
  if (!conn) return;
  
  // 先切换到这个连接
  switchConnection(connId);
  
  // 然后触发 Arthas 升级
  setTimeout(() => {
    if (typeof upgradeToArthas === 'function') {
      upgradeToArthas();
    }
  }, 300);
}

async function deleteConnection(connId) {
  if (!confirm('确定删除此连接？')) return;
  
  // 如果删除的是当前连接，先断开
  if (window._currentConnId === connId) {
    await stopPoll();
    window._currentConnId = null;
  }
  
  removeConnection(connId);
  renderConnList();
}

// 导出
if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    getConnections,
    setConnections,
    getCurrentConnId,
    setCurrentConnId,
    getCurrentConnection,
    inferConnLevel,
    getConnRuntime,
    canUpgradeConnection,
    saveConnections,
    loadConnections,
    renderConnList,
    addConnection,
    removeConnection,
    switchConnection,
    deleteConnection,
    upgradeConnectionFromList
  };
}

// 全局暴露（供 HTML onclick 调用）
window.upgradeConnectionFromList = upgradeConnectionFromList;
window.inferConnLevel = inferConnLevel;
window.getConnRuntime = getConnRuntime;
window.canUpgradeConnection = canUpgradeConnection;
