/**
 * ConnectionPoolUI - 前端连接池管理
 * 
 * 核心模型：多连接并存 + 独立工作区 + 焦点切换（零延迟）
 * 
 * 关键特性：
 * - 多个连接同时存在，每个连接独立维护
 * - 切换焦点 = 切换视图（无网络开销）
 * - per-connection 工作区状态完整保留
 * - 后台心跳守护，自动检测连接健康
 */

// ═══════════════════════════════════════════════════════════════════════════════
// 连接状态枚举
// ═══════════════════════════════════════════════════════════════════════════════

const PoolConnectionState = {
  DISCONNECTED: 'disconnected',
  CONNECTING: 'connecting',
  POD_CONNECTED: 'pod_connected',
  ARTHAS_UPGRADING: 'arthas_upgrading',
  ARTHAS_READY: 'arthas_ready',
  DEGRADED: 'degraded',
  DEAD: 'dead',
};

// ═══════════════════════════════════════════════════════════════════════════════
// 工作区 Tab 枚举
// ═══════════════════════════════════════════════════════════════════════════════

const WorkspaceTab = {
  MONITOR: 'monitor',
  SAMPLING: 'sampling',
  ARTHAS: 'arthas',
  TERMINAL: 'terminal',
  FILES: 'files',
  HISTORY: 'history',
  HOTFIX: 'hotfix',
  DIAGNOSIS: 'diagnosis',
};

// ═══════════════════════════════════════════════════════════════════════════════
// 连接池 UI 类
// ═══════════════════════════════════════════════════════════════════════════════

class ConnectionPoolUI {
  constructor() {
    // 连接池数据
    this.connections = new Map();  // connId -> PoolConnection
    this.focusId = null;          // 当前焦点连接 ID
    this.workspaces = new Map();  // connId -> WorkspaceState
    
    // 订阅者列表
    this._subscribers = [];
    
    // 初始化
    this._init();
  }
  
  // ── 初始化 ────────────────────────────────────────────────────────────────
  
  async _init() {
    // 从后端加载连接池
    await this.loadFromBackend();
    
    // 恢复焦点（从 localStorage）
    this._restoreFocus();
    
    // 启动心跳轮询
    this._startHeartbeatPolling();
    
    console.log('[ConnectionPoolUI] Initialized');
  }
  
  async loadFromBackend() {
    try {
      const resp = await fetch('/api/pool', { credentials: 'include' });
      if (!resp.ok) return;
      
      const data = await resp.json();
      if (!data.ok) return;
      
      // 更新连接池
      this.connections.clear();
      this.workspaces.clear();
      
      for (const conn of data.connections) {
        this.connections.set(conn.conn_id, {
          ...conn,
          status: conn.state,
        });
        
        // 创建工作区
        this.workspaces.set(conn.conn_id, {
          activeTab: WorkspaceTab.MONITOR,
          subTab: '',
          scrollPositions: {},
          data: {},
          commandHistory: [],
        });
      }
      
      // 恢复焦点
      if (data.focus_id && this.connections.has(data.focus_id)) {
        this.focusId = data.focus_id;
      } else if (this.connections.size > 0) {
        this.focusId = this.connections.keys().next().value;
      }
      
      this._notify();
      
    } catch (e) {
      console.error('[ConnectionPoolUI] Load failed:', e);
    }
  }
  
  _restoreFocus() {
    const savedFocus = localStorage.getItem('pool_focus_id');
    if (savedFocus && this.connections.has(savedFocus)) {
      this.focusId = savedFocus;
    }
  }
  
  _saveFocus() {
    if (this.focusId) {
      localStorage.setItem('pool_focus_id', this.focusId);
    } else {
      localStorage.removeItem('pool_focus_id');
    }
  }
  
  // ── 连接管理 ──────────────────────────────────────────────────────────────
  
  async addConnection(cluster, namespace, pod, options = {}) {
    const connId = `${cluster}/${namespace}/${pod}`;
    
    // 检查是否已在池中
    if (this.connections.has(connId)) {
      this.setFocus(connId);
      return { ok: true, existing: true };
    }
    
    try {
      const resp = await fetch('/api/pool/connect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          cluster_name: cluster,
          namespace: namespace,
          pod_name: pod,
          container: options.container || '',
          java_pid: options.javaPid || null,
          ttl_hours: options.ttlHours || 0,
        }),
      });
      
      const data = await resp.json();
      if (!data.ok) {
        return { ok: false, error: data.error || data.message };
      }
      
      // 添加到本地池
      this.connections.set(connId, {
        conn_id: connId,
        state: PoolConnectionState.ARTHAS_READY,
        local_port: data.local_port,
        java_pid: data.java_pid,
        arthas_version: data.arthas_version,
        arthas_address: data.arthas_address,
        mcp_available: data.mcp_available,
        cluster_name: cluster,
        namespace: namespace,
        pod_name: pod,
        is_alive: true,
      });
      
      // 创建工作区
      this.workspaces.set(connId, {
        activeTab: WorkspaceTab.MONITOR,
        subTab: '',
        scrollPositions: {},
        data: {},
        commandHistory: [],
      });
      
      // 设置为焦点
      this.setFocus(connId);
      
      return { ok: true, conn_id: connId };
      
    } catch (e) {
      console.error('[ConnectionPoolUI] Add failed:', e);
      return { ok: false, error: e.message };
    }
  }
  
  async removeConnection(connId) {
    try {
      const resp = await fetch(`/api/pool/${encodeURIComponent(connId)}`, {
        method: 'DELETE',
        credentials: 'include',
      });
      
      if (!resp.ok) {
        console.error('[ConnectionPoolUI] Remove failed');
        return false;
      }
      
      // 从本地池移除
      this.connections.delete(connId);
      this.workspaces.delete(connId);
      
      // 如果是焦点连接，切换到下一个
      if (this.focusId === connId) {
        const nextId = this.connections.keys().next().value || null;
        this.setFocus(nextId);
      }
      
      this._notify();
      return true;
      
    } catch (e) {
      console.error('[ConnectionPoolUI] Remove failed:', e);
      return false;
    }
  }
  
  // ── 焦点管理 ──────────────────────────────────────────────────────────────
  
  async setFocus(connId) {
    if (connId && !this.connections.has(connId)) {
      console.warn('[ConnectionPoolUI] Cannot focus:', connId);
      return false;
    }
    
    const oldFocus = this.focusId;
    this.focusId = connId;
    
    // 保存焦点
    this._saveFocus();
    
    // 通知后端（异步，不阻塞 UI）
    if (connId) {
      fetch(`/api/pool/${encodeURIComponent(connId)}/focus`, {
        method: 'POST',
        credentials: 'include',
      }).catch(() => {});
    }
    
    // 通知订阅者
    this._notify();
    
    console.log('[ConnectionPoolUI] Focus changed:', oldFocus, '->', connId);
    return true;
  }
  
  getFocusId() {
    return this.focusId;
  }
  
  getFocused() {
    if (!this.focusId) return null;
    return this.connections.get(this.focusId) || null;
  }
  
  // ── 工作区管理 ──────────────────────────────────────────────────────────────
  
  getWorkspace(connId) {
    return this.workspaces.get(connId) || null;
  }
  
  getFocusedWorkspace() {
    return this.getWorkspace(this.focusId);
  }
  
  setWorkspaceTab(connId, tab, subTab = '') {
    const workspace = this.workspaces.get(connId);
    if (!workspace) return false;
    
    workspace.activeTab = tab;
    workspace.subTab = subTab;
    
    // 通知后端（异步）
    fetch(`/api/pool/${encodeURIComponent(connId)}/workspace`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ active_tab: tab, sub_tab: subTab }),
    }).catch(() => {});
    
    return true;
  }
  
  // ── 订阅机制 ──────────────────────────────────────────────────────────────
  
  subscribe(callback) {
    this._subscribers.push(callback);
    return () => {
      this._subscribers = this._subscribers.filter(cb => cb !== callback);
    };
  }
  
  _notify() {
    const state = this.getState();
    for (const cb of this._subscribers) {
      try {
        cb(state);
      } catch (e) {
        console.error('[ConnectionPoolUI] Subscriber error:', e);
      }
    }
  }
  
  getState() {
    return {
      connections: Array.from(this.connections.values()),
      focusId: this.focusId,
      focused: this.getFocused(),
      total: this.connections.size,
    };
  }
  
  // ── 心跳轮询 ──────────────────────────────────────────────────────────────
  
  _startHeartbeatPolling() {
    setInterval(() => {
      this._checkConnectionsHealth();
    }, 10000);  // 每 10 秒检查一次
  }
  
  async _checkConnectionsHealth() {
    for (const [connId, conn] of this.connections) {
      if (conn.state === PoolConnectionState.DISCONNECTED ||
          conn.state === PoolConnectionState.DEAD) {
        continue;
      }
      
      try {
        const resp = await fetch(`/api/pool/${encodeURIComponent(connId)}/status`, {
          credentials: 'include',
        });
        
        if (resp.ok) {
          const data = await resp.json();
          if (data.ok) {
            // 更新状态
            const oldState = conn.state;
            conn.state = data.state;
            conn.is_alive = data.is_alive;
            
            if (oldState !== data.state) {
              this._notify();
            }
          }
        }
      } catch (e) {
        // 忽略网络错误
      }
    }
  }
  
  // ── UI 渲染 ──────────────────────────────────────────────────────────────
  
  renderConnectionPool(container) {
    if (!container) return;
    
    const connections = Array.from(this.connections.values());
    const active = connections.filter(c => 
      c.state === PoolConnectionState.ARTHAS_READY ||
      c.state === PoolConnectionState.POD_CONNECTED
    );
    const degraded = connections.filter(c => 
      c.state === PoolConnectionState.DEGRADED
    );
    const dead = connections.filter(c => 
      c.state === PoolConnectionState.DEAD ||
      c.state === PoolConnectionState.DISCONNECTED
    );
    
    let html = `
      <div class="connection-pool">
        <div class="pool-header">
          <span class="pool-title">连接池 (${connections.length})</span>
          <button class="btn-add-conn" onclick="connectionPoolUI.showAddDialog()">
            + 新连接
          </button>
        </div>
        <input type="text" class="pool-search" placeholder="搜索 Pod..." 
               name="pool_search_${Date.now()}"
               autocomplete="new-password"
               oninput="connectionPoolUI._filterConnections(this.value)">
        <div class="pool-list">
    `;
    
    // 活跃连接
    if (active.length > 0) {
      html += `<div class="pool-group"><div class="pool-group-title">活跃 (${active.length})</div>`;
      for (const conn of active) {
        html += this._renderConnectionCard(conn);
      }
      html += '</div>';
    }
    
    // 降级连接
    if (degraded.length > 0) {
      html += `<div class="pool-group"><div class="pool-group-title">降级 (${degraded.length})</div>`;
      for (const conn of degraded) {
        html += this._renderConnectionCard(conn);
      }
      html += '</div>';
    }
    
    // 断开连接
    if (dead.length > 0) {
      html += `<div class="pool-group collapsed"><div class="pool-group-title">已断开 (${dead.length})</div>`;
      for (const conn of dead) {
        html += this._renderConnectionCard(conn);
      }
      html += '</div>';
    }
    
    // 空状态
    if (connections.length === 0) {
      html += `
        <div class="pool-empty">
          <div class="pool-empty-icon">🔌</div>
          <div class="pool-empty-text">暂无连接</div>
          <button class="btn-add-conn" onclick="connectionPoolUI.showAddDialog()">
            + 添加第一个连接
          </button>
        </div>
      `;
    }
    
    html += '</div></div>';
    
    container.innerHTML = html;
  }
  
  _renderConnectionCard(conn) {
    const isFocused = conn.conn_id === this.focusId;
    const stateClass = this._getStateClass(conn.state);
    const stateIcon = this._getStateIcon(conn.state);
    
    return `
      <div class="pool-card ${stateClass} ${isFocused ? 'focused' : ''}" 
           onclick="connectionPoolUI.setFocus('${conn.conn_id}')">
        <div class="card-header">
          <span class="card-icon">${stateIcon}</span>
          <span class="card-name">${conn.pod_name || conn.conn_id.split('/').pop()}</span>
          <span class="card-level">${conn.state === PoolConnectionState.ARTHAS_READY ? 'Arthas' : 'Pod'}</span>
        </div>
        <div class="card-info">
          <span class="card-namespace">${conn.namespace || ''}</span>
          <span class="card-cluster">${conn.cluster_name || ''}</span>
        </div>
        <div class="card-actions">
          <button class="btn-icon" onclick="event.stopPropagation(); connectionPoolUI.removeConnection('${conn.conn_id}')" title="断开">
            ✕
          </button>
        </div>
      </div>
    `;
  }
  
  _getStateClass(state) {
    switch (state) {
      case PoolConnectionState.ARTHAS_READY: return 'state-ready';
      case PoolConnectionState.POD_CONNECTED: return 'state-pod';
      case PoolConnectionState.CONNECTING: return 'state-connecting';
      case PoolConnectionState.DEGRADED: return 'state-degraded';
      case PoolConnectionState.DEAD: return 'state-dead';
      default: return 'state-disconnected';
    }
  }
  
  _getStateIcon(state) {
    switch (state) {
      case PoolConnectionState.ARTHAS_READY: return '🟢';
      case PoolConnectionState.POD_CONNECTED: return '🔵';
      case PoolConnectionState.CONNECTING: return '🟡';
      case PoolConnectionState.DEGRADED: return '🟡';
      case PoolConnectionState.DEAD: return '🔴';
      default: return '⚫';
    }
  }
  
  _filterConnections(query) {
    const cards = document.querySelectorAll('.pool-card');
    const lowerQuery = query.toLowerCase();
    
    cards.forEach(card => {
      const text = card.textContent.toLowerCase();
      card.style.display = text.includes(lowerQuery) ? '' : 'none';
    });
  }
  
  showAddDialog() {
    // 触发添加连接对话框
    if (typeof showAddConnectionDialog === 'function') {
      showAddConnectionDialog();
    }
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// 全局实例
// ═══════════════════════════════════════════════════════════════════════════════

const connectionPoolUI = new ConnectionPoolUI();

// 导出到 window
window.ConnectionPoolUI = ConnectionPoolUI;
window.connectionPoolUI = connectionPoolUI;
window.PoolConnectionState = PoolConnectionState;
window.WorkspaceTab = WorkspaceTab;
