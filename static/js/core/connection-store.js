/**
 * ConnectionStore - 统一前端连接状态管理
 * 
 * 解决问题:
 * - app-ui.js 维护 _currentConnId, _connected, _connState
 * - two-step-connection.js 维护 _connState
 * - connections.js 维护 window._connections
 * 
 * 统一后: 所有模块通过 ConnectionStore 访问和更新状态
 */

const ConnectionState = {
  DISCONNECTED: 'disconnected',
  POD_CONNECTING: 'pod_connecting',
  POD_CONNECTED: 'pod_connected',
  ARTHAS_UPGRADING: 'arthas_upgrading',
  ARTHAS_READY: 'arthas_ready',
};

const ConnectionStore = {
  // 私有状态
  _state: {
    currentConnId: null,
    connections: [],
    connState: ConnectionState.DISCONNECTED,
    runtimeInfo: null,
    podPhase: null,
    podConnId: null,
    connHealth: {},
  },
  
  // 监听器列表
  _listeners: [],
  
  /**
   * 获取完整状态
   */
  getState() {
    return { ...this._state };
  },
  
  /**
   * 更新状态 (触发所有监听器)
   */
  setState(updates) {
    const oldState = { ...this._state };
    this._state = { ...this._state, ...updates };
    
    // ✅ 关键修复: 同步到 window 全局变量
    if (updates.currentConnId !== undefined) {
      window._currentConnId = updates.currentConnId;
    }
    
    // 触发所有监听器
    this._listeners.forEach(fn => {
      try {
        fn(this._state, oldState);
      } catch (e) {
        console.error('[ConnectionStore] Listener error:', e);
      }
    });
    
    // 持久化到 localStorage
    this._persist();
  },
  
  /**
   * 订阅状态变化
   * @param {Function} fn - (newState, oldState) => void
   * @returns {Function} 取消订阅函数
   */
  subscribe(fn) {
    this._listeners.push(fn);
    return () => {
      this._listeners = this._listeners.filter(l => l !== fn);
    };
  },
  
  // ── 便捷访问方法 ───────────────────────────────────────────────────
  
  getCurrentConnId() {
    return this._state.currentConnId;
  },
  
  getCurrentConnection() {
    return this._state.connections.find(c => c.id === this._state.currentConnId) || null;
  },
  
  getConnections() {
    return this._state.connections;
  },
  
  /**
   * 设置连接列表 (用于刷新列表)
   */
  setConnections(connections) {
    this._state.connections = connections || [];
    
    // ✅ 修复: 如果有连接但没有选中任何连接,自动选中第一条(最近使用的)
    if (this._state.connections.length > 0 && !this._state.currentConnId) {
      this._state.currentConnId = this._state.connections[0].id;
      console.log('[ConnectionStore] Auto-selected first connection:', this._state.currentConnId);
    }
    
    // ✅ 关键修复: 同步到 window,让状态栏能找到
    this.syncToGlobal();
    
    this._notify();
    this._persist();
  },
  
  getConnectionState() {
    return this._state.connState;
  },
  
  isArthasReady() {
    return this._state.connState === ConnectionState.ARTHAS_READY;
  },
  
  isPodConnected() {
    return this._state.connState === ConnectionState.POD_CONNECTED;
  },
  
  // ── 状态转换方法 ───────────────────────────────────────────────────
  
  setConnectionState(newState) {
    if (!Object.values(ConnectionState).includes(newState)) {
      console.error('[ConnectionStore] Invalid state:', newState);
      return;
    }
    this.setState({ connState: newState });
  },
  
  setCurrentConnection(connId) {
    this.setState({ currentConnId: connId });
  },
  
  updateConnection(connId, updates) {
    const connections = this._state.connections.map(c => 
      c.id === connId ? { ...c, ...updates } : c
    );
    this.setState({ connections });
  },
  
  addConnection(conn) {
    const connections = [...this._state.connections, conn];
    this.setState({ connections });
  },
  
  removeConnection(connId) {
    const connections = this._state.connections.filter(c => c.id !== connId);
    const updates = { connections };
    
    // 如果删除的是当前连接,清空 currentConnId
    if (this._state.currentConnId === connId) {
      updates.currentConnId = null;
    }
    
    this.setState(updates);
  },
  
  setRuntimeInfo(info) {
    this.setState({ runtimeInfo: info });
  },
  
  setPodPhase(phase) {
    this.setState({ podPhase: phase });
  },
  
  updateConnectionHealth(connId, health) {
    const connHealth = { ...this._state.connHealth, [connId]: health };
    this.setState({ connHealth });
  },
  
  // ── 持久化 ─────────────────────────────────────────────────────────
  
  _persist() {
    try {
      // 存储所有关键状态
      const persistData = {
        connections: this._state.connections,
        currentConnId: this._state.currentConnId,
        connState: this._state.connState,
        runtimeInfo: this._state.runtimeInfo,
        podPhase: this._state.podPhase,
        podConnId: this._state.podConnId,
        connHealth: this._state.connHealth
      };
      
      localStorage.setItem('arthas_connection_store', JSON.stringify(persistData));
    } catch (e) {
      console.error('[ConnectionStore] Persist error:', e);
    }
  },
  
  // ── 初始化 ─────────────────────────────────────────────────────────
  
  init() {
    try {
      // 加载 v2 统一存储格式
      const stored = localStorage.getItem('arthas_connection_store');
      if (stored) {
        const data = JSON.parse(stored);
        // 不加载 connections (由数据库 API 提供)
        this._state.currentConnId = data.currentConnId || null;
        // ✅ 修复: 不加载旧的 connState 和 runtimeInfo,避免覆盖当前状态
        this._state.connState = ConnectionState.DISCONNECTED;  // 强制重置,等待连接后更新
        this._state.runtimeInfo = null;  // 强制清空,等待后端返回
        this._state.podPhase = data.podPhase || '';
        this._state.podConnId = data.podConnId || null;
        this._state.connHealth = data.connHealth || {};
        
        console.log('[ConnectionStore] Loaded (connState & runtimeInfo cleared, currentConnId=', this._state.currentConnId, ')');
      } else {
        console.log('[ConnectionStore] No stored data found');
      }
    } catch (e) {
      console.error('[ConnectionStore] Init error:', e);
      this._state.connections = [];
    }
  },
  
  // ── 兼容性方法 (逐步替换旧代码) ───────────────────────────────────
  
  /**
   * 兼容旧的 window._connections
   */
  syncToGlobal() {
    window._connections = this._state.connections;
    window._currentConnId = this._state.currentConnId;
    window._connState = this._state.connState;
    window._runtimeInfo = this._state.runtimeInfo;
    window._podPhase = this._state.podPhase;
    window._podConnId = this._state.podConnId;
    window._connHealth = this._state.connHealth;
  },
  
  /**
   * 从旧的 window.* 变量同步状态
   */
  syncFromGlobal() {
    if (window._connections) this._state.connections = window._connections;
    if (window._currentConnId) this._state.currentConnId = window._currentConnId;
    if (window._connState) this._state.connState = window._connState;
    if (window._runtimeInfo) this._state.runtimeInfo = window._runtimeInfo;
    if (window._podPhase) this._state.podPhase = window._podPhase;
    if (window._podConnId) this._state.podConnId = window._podConnId;
    if (window._connHealth) this._state.connHealth = window._connHealth;
  },
  
};

// 导出
window.ConnectionState = ConnectionState;
window.ConnectionStore = ConnectionStore;

// DOM Ready 时初始化 (延迟到数据库加载后)
document.addEventListener('DOMContentLoaded', () => {
  // ✅ 仅初始化,不从 localStorage 加载 connections (由数据库 API 提供)
  // 保留其他状态 (connState 等) 的本地缓存
  try {
    const stored = localStorage.getItem('arthas_connection_store');
    if (stored) {
      const data = JSON.parse(stored);
      // 不加载 connections,保持为空数组,等待数据库 API 填充
      // ✅ 修复: 不加载旧的 connState 和 runtimeInfo,避免覆盖当前状态
      ConnectionStore._state.currentConnId = data.currentConnId || null;
      ConnectionStore._state.connState = ConnectionState.DISCONNECTED;  // 强制重置,等待连接后更新
      ConnectionStore._state.runtimeInfo = null;  // 强制清空,等待后端返回
      ConnectionStore._state.podPhase = data.podPhase || '';
      ConnectionStore._state.podConnId = data.podConnId || null;
      ConnectionStore._state.connHealth = data.connHealth || {};
      console.log('[ConnectionStore] Initialized (connState & runtimeInfo cleared)');
    } else {
      console.log('[ConnectionStore] Ready (no cached state)');
    }
  } catch (e) {
    console.error('[ConnectionStore] Init error:', e);
  }
  ConnectionStore.syncToGlobal();
});
