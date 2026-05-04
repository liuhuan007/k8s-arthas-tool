/**
 * 连接管理组件
 * 处理连接列表、连接切换、连接删除
 * 
 * 连接层级 (level):
 *   'pod'    — 仅 Pod 连接（kubectl exec 通道）
 *   'arthas' — Pod + Arthas 连接（深度诊断）
 */

// ── State ─────────────────────────────────────────────────────────────────
// ✅ 使用 ConnectionStore 统一管理连接状态

// ── 获取/设置 ────────────────────────────────────────────────────────────

function getConnections() {
  // ✅ 优先从 ConnectionStore 获取
  if (typeof ConnectionStore !== 'undefined') {
    return ConnectionStore.getConnections();
  }
  return window._connections || [];
}

function setConnections(conns) {
  // ✅ 优先使用 ConnectionStore
  if (typeof ConnectionStore !== 'undefined') {
    ConnectionStore.setState({ connections: conns || [] });
  } else {
    window._connections = conns || [];
  }
  saveConnections();
}

function getCurrentConnId() {
  // ✅ 优先从 ConnectionStore 获取
  if (typeof ConnectionStore !== 'undefined') {
    return ConnectionStore.getCurrentConnId();
  }
  return window._currentConnId || null;
}

function setCurrentConnId(id) {
  // ✅ 优先使用 ConnectionStore
  if (typeof ConnectionStore !== 'undefined') {
    ConnectionStore.setCurrentConnection(id);
  } else {
    window._currentConnId = id;
  }
}

function getCurrentConnection() {
  // ✅ 优先从 ConnectionStore 获取
  if (typeof ConnectionStore !== 'undefined') {
    return ConnectionStore.getCurrentConnection();
  }
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

/**
 * ✅ renderConnList() 已在 app-ui.js 中重新定义
 * 此处的版本已被覆盖,保留仅为向后兼容
 * 实际渲染使用 app-ui.js 中的版本,从 ConnectionStore 获取数据
 */

// 原 renderConnList 实现已移至 app-ui.js
// 如需查看实现,请搜索 app-ui.js 中的 renderConnList() 函数

// ── 操作 ─────────────────────────────────────────────────────────────────

function addConnection(conn) {
  const exists = (window._connections || []).find(c => c.id === conn.id);
  if (!exists) {
    // 确保 level 字段
    conn.level = inferConnLevel(conn);
    conn.status = conn.status || 'connected';
    window._connections.push(conn);
    saveConnections();
  } else {
    // 更新现有连接的状态信息
    exists.status = conn.status || 'connected';
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
    // ✅ renderConnList 已移至 app-ui.js
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
