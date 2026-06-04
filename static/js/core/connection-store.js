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
    isRestoring: false,  // 页面刷新后正在恢复连接的标志
  },

  // 监听器列表
  _listeners: [],

  // Phase 5: 多标签页同步 BroadcastChannel
  _broadcastChannel: null,
  _isSyncingFromBroadcast: false,
  
  /**
   * 获取完整状态
   */
  getState() {
    return { ...this._state };
  },
  
  /**
   * 更新状态 (触发所有监听器 + 广播到其他标签页)
   */
  setState(updates) {
    const oldState = { ...this._state };
    this._state = { ...this._state, ...updates };

    // ✅ 关键修复: 所有状态更新都同步到 window 全局变量。
    // conn-status-bar / connection-guard 等旧组件仍从 window.* 读取状态，
    // 只同步 currentConnId 会导致连接层级显示滞后（例如已 Arthas 就绪仍显示 Pod连接）。
    this.syncToGlobal();

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

    // Phase 5: 广播状态变化到其他标签页 (非来自广播的更新才广播)
    if (!this._isSyncingFromBroadcast) {
      this._broadcastStateChanges(updates, oldState);
    }
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
        connHealth: this._state.connHealth,
        isRestoring: this._state.isRestoring,
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
        // ✅ 修复: 恢复缓存的 connState 和 runtimeInfo，避免 UI 闪烁"未连接"
        // 实际连接状态会在 _restoreActiveConnection 完成后更新
        if (data.currentConnId && data.connState && data.connState !== ConnectionState.DISCONNECTED) {
          this._state.connState = data.connState;
          this._state.runtimeInfo = data.runtimeInfo || null;
          this._state.isRestoring = true;  // 标记正在恢复，状态栏显示"恢复中..."
          console.log('[ConnectionStore] Restoring cached state:', data.connState);
        } else {
          this._state.connState = ConnectionState.DISCONNECTED;
          this._state.runtimeInfo = null;
        }
        this._state.podPhase = data.podPhase || '';
        this._state.podConnId = data.podConnId || null;
        this._state.connHealth = data.connHealth || {};

        console.log('[ConnectionStore] Loaded (currentConnId=', this._state.currentConnId, ', cachedState=', this._state.connState, ')');
      } else {
        console.log('[ConnectionStore] No stored data found');
      }
    } catch (e) {
      console.error('[ConnectionStore] Init error:', e);
      this._state.connections = [];
    }

    // Phase 5: 初始化 BroadcastChannel 多标签页同步
    this._initBroadcastChannel();
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
    window._isRestoring = this._state.isRestoring;
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
    if (window._isRestoring !== undefined) this._state.isRestoring = window._isRestoring;
  },

  // ── Phase 5: 多标签页 BroadcastChannel 同步 ────────────────────────────

  /**
   * 初始化 BroadcastChannel 用于跨标签页连接状态同步
   */
  _initBroadcastChannel() {
    if (this._broadcastChannel) return; // 已初始化

    try {
      this._broadcastChannel = new BroadcastChannel('arthas-connection-sync');
      this._broadcastChannel.onmessage = (event) => {
        this._handleBroadcastMessage(event.data);
      };
      console.log('[ConnectionStore] BroadcastChannel initialized for multi-tab sync');
    } catch (e) {
      console.warn('[ConnectionStore] BroadcastChannel not supported:', e);
      this._broadcastChannel = null;
    }
  },

  /**
   * 广播状态变化到其他标签页
   * @param {object} updates - 本次 setState 的更新字段
   * @param {object} oldState - 更新前的完整状态
   */
  _broadcastStateChanges(updates, oldState) {
    if (!this._broadcastChannel) return;

    // 确定事件类型
    let eventType = null;
    let payload = {};

    if ('currentConnId' in updates && updates.currentConnId !== oldState.currentConnId) {
      eventType = 'connection-switch';
      payload = {
        currentConnId: updates.currentConnId,
        previousConnId: oldState.currentConnId,
      };
    } else if ('connections' in updates) {
      const oldIds = (oldState.connections || []).map(c => c.id).sort().join(',');
      const newIds = (updates.connections || []).map(c => c.id).sort().join(',');
      if (oldIds !== newIds) {
        const added = (updates.connections || []).filter(c => !oldIds.includes(c.id));
        const removed = (oldState.connections || []).filter(c => !newIds.includes(c.id));
        if (added.length > 0) {
          eventType = 'connection-added';
          payload = { connections: updates.connections, added };
        } else if (removed.length > 0) {
          eventType = 'connection-removed';
          payload = { connections: updates.connections, removed };
        }
      }
    } else if ('connHealth' in updates) {
      eventType = 'health-updated';
      payload = { connHealth: updates.connHealth };
    }

    if (!eventType) return;

    try {
      this._broadcastChannel.postMessage({
        type: eventType,
        payload,
        timestamp: Date.now(),
      });
    } catch (e) {
      console.warn('[ConnectionStore] Broadcast failed:', e);
    }
  },

  /**
   * 处理从其他标签页收到的广播消息
   * @param {object} message - { type, payload, timestamp }
   */
  _handleBroadcastMessage(message) {
    if (!message || !message.type) return;

    // 标记为正在同步，避免无限广播循环
    this._isSyncingFromBroadcast = true;

    try {
      switch (message.type) {
        case 'connection-switch':
          if (message.payload && message.payload.currentConnId) {
            this._state.currentConnId = message.payload.currentConnId;
            this.syncToGlobal();
            this._persist();
            this._notify();
            console.log('[ConnectionStore] Synced connection switch from another tab:', message.payload.currentConnId);
          }
          break;

        case 'connection-added':
        case 'connection-removed':
          if (message.payload && message.payload.connections) {
            this._state.connections = message.payload.connections;
            this.syncToGlobal();
            this._persist();
            this._notify();
            console.log('[ConnectionStore] Synced connection list from another tab (' + message.type + ')');
          }
          break;

        case 'health-updated':
          if (message.payload && message.payload.connHealth) {
            this._state.connHealth = message.payload.connHealth;
            this.syncToGlobal();
            this._persist();
            this._notify();
            console.log('[ConnectionStore] Synced health data from another tab');
          }
          break;

        default:
          console.warn('[ConnectionStore] Unknown broadcast type:', message.type);
      }
    } catch (e) {
      console.error('[ConnectionStore] Error handling broadcast:', e);
    } finally {
      this._isSyncingFromBroadcast = false;
    }
  },

  /**
   * 通知所有监听器 (内部方法，用于广播同步时触发本地监听器)
   */
  _notify() {
    this._listeners.forEach(fn => {
      try {
        fn(this._state, { ...this._state });
      } catch (e) {
        console.error('[ConnectionStore] Listener error:', e);
      }
    });
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
      ConnectionStore._state.currentConnId = data.currentConnId || null;
      // ✅ 修复: 恢复缓存的 connState，避免 UI 闪烁"未连接"
      if (data.currentConnId && data.connState && data.connState !== ConnectionState.DISCONNECTED) {
        ConnectionStore._state.connState = data.connState;
        ConnectionStore._state.runtimeInfo = data.runtimeInfo || null;
        ConnectionStore._state.isRestoring = true;
      } else {
        ConnectionStore._state.connState = ConnectionState.DISCONNECTED;
        ConnectionStore._state.runtimeInfo = null;
      }
      ConnectionStore._state.podPhase = data.podPhase || '';
      ConnectionStore._state.podConnId = data.podConnId || null;
      ConnectionStore._state.connHealth = data.connHealth || {};
      console.log('[ConnectionStore] Initialized (cachedState=', ConnectionStore._state.connState, ', isRestoring=', ConnectionStore._state.isRestoring, ')');
    } else {
      console.log('[ConnectionStore] Ready (no cached state)');
    }
  } catch (e) {
    console.error('[ConnectionStore] Init error:', e);
  }
  ConnectionStore.syncToGlobal();
});
