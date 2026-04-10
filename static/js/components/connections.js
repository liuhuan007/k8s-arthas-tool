/**
 * 连接管理组件
 * 处理连接列表、连接切换、连接删除
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
      window._connections = window._connections.map(c => ({
        ...c,
        id: c.id || `${c.cluster}/${c.namespace}/${c.pod}`
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
    listEl.innerHTML = '<div class="empty-state">暂无连接</div>';
    return;
  }
  
  listEl.innerHTML = (window._connections || []).map(conn => {
    const isActive = conn.id === (window._currentConnId || null);
    const statusIcon = conn.status === 'connected' ? '●' : (conn.status === 'error' ? '⊘' : '○');
    const statusStyle = conn.status === 'connected' ? 'color:var(--a3)' : (conn.status === 'error' ? 'color:var(--a5)' : 'color:var(--tx3)');
    return `
      <div class="conn-itm ${isActive ? 'on' : ''}" data-id="${esc(conn.id)}" onclick="switchConnection('${esc(conn.id)}')">
        <div class="conn-info">
          <div class="conn-cluster"><span style="font-size:9px;${statusStyle};margin-right:3px">${statusIcon}</span> ${esc(conn.cluster || conn.cluster_name || '')}</div>
          <div class="conn-pod"><span class="conn-ns">${esc(conn.namespace || '')}</span><span class="conn-slash">/</span><span class="conn-name">${esc(conn.pod || conn.pod_name || '')}</span></div>
        </div>
        <button class="del-conn" onclick="event.stopPropagation();deleteConnection('${esc(conn.id)}')" title="删除">×</button>
      </div>`;
  }).join('');
}

// ── 操作 ─────────────────────────────────────────────────────────────────

function addConnection(conn) {
  const exists = (window._connections || []).find(c => c.id === conn.id);
  if (!exists) {
    // 添加默认状态
    conn.status = conn.status || 'connected';
    conn.mcp_available = conn.mcp_available || false;
    window._connections.push(conn);
    saveConnections();
  } else {
    // 更新现有连接的状态信息
    exists.status = conn.status || 'connected';
    exists.mcp_available = conn.mcp_available !== undefined ? conn.mcp_available : exists.mcp_available;
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

function switchConnection(connId) {
  const conn = (window._connections || []).find(c => c.id === connId);
  if (!conn) return;
  
  // 切换前断开当前连接
  if (window._currentConnId && window._currentConnId !== connId) {
    stopPoll();
  }
  
  // 更新新连接的状态
  conn.status = 'connected';
  
  window._currentConnId = connId;
  saveConnections();  // 保存状态到 localStorage
  renderConnList();
  
  // 触发连接事件
  document.dispatchEvent(new CustomEvent('connection-changed', {
    detail: { connId, conn }
  }));
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
    saveConnections,
    loadConnections,
    renderConnList,
    addConnection,
    removeConnection,
    switchConnection,
    deleteConnection
  };
}
