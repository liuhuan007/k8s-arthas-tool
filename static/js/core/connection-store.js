/**
 * ConnectionStore - 多连接池统一状态管理
 *
 * 核心模型: 连接池 + 焦点连接 + 独立工作区
 * 每个连接独立维护，切换焦点不触发网络操作
 */

const ConnectionState = {
  DISCONNECTED: 'disconnected',
  CONNECTING: 'connecting',
  POD_CONNECTED: 'pod_connected',
  ARTHAS_UPGRADING: 'arthas_upgrading',
  ARTHAS_READY: 'arthas_ready',
  DEGRADED: 'degraded',
  DEAD: 'dead',
};

const ConnectionStore = {
  _state: {
    connections: [],
    focusId: null,
  },
  _listeners: [],
  _broadcastChannel: null,
  _isSyncingFromBroadcast: false,
  _heartbeatTimer: null,
  _lastNotifiedState: null,

  getState() {
    return {
      ...this._state,
      currentConnId: this._state.focusId,
    };
  },
  getConnections() { return [...this._state.connections]; },
  getFocusId() { return this._state.focusId; },

  getFocusConnection() {
    return this._state.connections.find(c => c.id === this._state.focusId) || null;
  },

  getConnection(id) {
    return this._state.connections.find(c => c.id === id) || null;
  },

  // ── 连接操作 ──────────────────────────────────────────────────

  addConnection(conn) {
    // 默认值
    conn = {
      state: ConnectionState.CONNECTING,
      level: 'disconnected',
      arthas: null,
      health: 'off',
      autoReconnect: false,
      tab: 'monitor',
      pmTab: 'ov',
      sampSt: null,
      viewMode: 'compact',
      lastUsed: Date.now(),
      lastHb: 0,
      ...conn,
    };
    this._state.connections.push(conn);
    if (!this._state.focusId) this._state.focusId = conn.id;
    this._notify();
    this._persist();
  },

  updateConnection(id, updates) {
    const idx = this._state.connections.findIndex(c => c.id === id);
    if (idx >= 0) {
      this._state.connections[idx] = { ...this._state.connections[idx], ...updates };
      this._notify();
      this._persist();
    }
  },

  removeConnection(id) {
    this._state.connections = this._state.connections.filter(c => c.id !== id);
    if (this._state.focusId === id) {
      this._state.focusId = this._state.connections[0]?.id || null;
    }
    this._notify();
    this._persist();
  },

  // ── 旧代码兼容方法 ──────────────────────────────────────────

  setConnections(connections) {
    this._state.connections = connections || [];
    this._notify();
    this._persist();
  },

  setState(updates) {
    if (updates.currentConnId) this._state.focusId = updates.currentConnId;
    Object.assign(this._state, updates);
    this._notify();
    this._persist();
  },

  getCurrentConnId() { return this._state.focusId; },
  setCurrentConnection(id) { this.setFocus(id); },
  getCurrentConnection() { return this.getFocusConnection(); },
  getConnectionState() { return this._state.connState || 'disconnected'; },
  isArthasReady() { return this._state.connState === 'arthas_ready'; },
  isPodConnected() { return this._state.connState === 'pod_connected'; },

  // ── 焦点管理 ──────────────────────────────────────────────────

  setFocus(id) {
    this._state.focusId = id;
    const conn = this._state.connections.find(c => c.id === id);
    if (conn) {
      conn.lastUsed = Date.now();
      // 按最近使用重排
      this._state.connections.sort((a, b) => (b.lastUsed || 0) - (a.lastUsed || 0));
    }
    this._notify();
    this._persist();
  },

  // ── 监听 ──────────────────────────────────────────────────────

  subscribe(fn) {
    this._listeners.push(fn);
    return () => { this._listeners = this._listeners.filter(l => l !== fn); };
  },

  _notify() {
    const state = this.getState();
    const oldState = this._lastNotifiedState || state;
    this._listeners.forEach(fn => {
      try { fn(state, oldState); } catch (e) { console.error('[ConnectionStore] Listener error:', e); }
    });
    this._lastNotifiedState = {
      ...state,
      connections: [...(state.connections || [])],
    };
    this._broadcast('state-changed', state);
  },

  // ── 持久化 (仅配置，运行时状态每次重建) ─────────────────────

  _persist() {
    try {
      const data = this._state.connections.map(c => ({
        id: c.id, cluster: c.cluster, namespace: c.namespace, pod: c.pod,
        runtime: c.runtime, pid: c.pid, uptime: c.uptime,
        autoReconnect: c.autoReconnect, tab: c.tab, pmTab: c.pmTab,
        viewMode: c.viewMode, lastUsed: c.lastUsed,
      }));
      localStorage.setItem('k8s_pool', JSON.stringify({
        connections: data,
        focusId: this._state.focusId,
      }));
    } catch (e) { console.error('[ConnectionStore] persist error:', e); }
  },

  restore() {
    try {
      const raw = localStorage.getItem('k8s_pool');
      if (!raw) return;
      const data = JSON.parse(raw);
      this._state.connections = (data.connections || []).map(c => ({
        ...c,
        state: ConnectionState.DISCONNECTED,
        level: 'disconnected',
        arthas: null,
        health: 'off',
        autoReconnect: c.autoReconnect ?? false,
        tab: c.tab || 'monitor',
        pmTab: c.pmTab || 'ov',
        sampSt: null,
        viewMode: c.viewMode || 'compact',
        lastUsed: c.lastUsed || Date.now(),
        lastHb: 0,
      }));
      this._state.focusId = data.focusId || this._state.connections[0]?.id || null;
      this._notify();
    } catch (e) { console.error('[ConnectionStore] restore error:', e); }
  },

  // ── 心跳 ──────────────────────────────────────────────────────

  startHeartbeat(checkFn) {
    this.stopHeartbeat();
    this._heartbeatTimer = setInterval(() => {
      this._state.connections.forEach(conn => {
        if (conn.state === ConnectionState.CONNECTING || conn.state === ConnectionState.DISCONNECTED) return;
        if (typeof checkFn === 'function') {
          checkFn(conn).then(ok => {
            if (ok) {
              this.updateConnection(conn.id, { health: 'ok', lastHb: Date.now() });
            } else {
              const fails = (conn._heartbeatFails || 0) + 1;
              this.updateConnection(conn.id, {
                _heartbeatFails: fails,
                health: fails >= 10 ? 'err' : fails >= 3 ? 'warn' : 'ok',
                state: fails >= 10 ? ConnectionState.DEAD : fails >= 3 ? ConnectionState.DEGRADED : conn.state,
              });
            }
          }).catch(() => {
            const fails = (conn._heartbeatFails || 0) + 1;
            this.updateConnection(conn.id, {
              _heartbeatFails: fails,
              health: fails >= 10 ? 'err' : fails >= 3 ? 'warn' : conn.health,
              state: fails >= 10 ? ConnectionState.DEAD : fails >= 3 ? ConnectionState.DEGRADED : conn.state,
            });
          });
        }
      });
    }, 5000);
  },

  stopHeartbeat() {
    if (this._heartbeatTimer) { clearInterval(this._heartbeatTimer); this._heartbeatTimer = null; }
  },

  // ── BroadcastChannel (多标签页同步) ──────────────────────────

  _broadcast(type, payload) {
    if (!this._broadcastChannel || this._isSyncingFromBroadcast) return;
    try { this._broadcastChannel.postMessage({ type, payload, ts: Date.now() }); } catch (e) {}
  },

  _initBroadcast() {
    try {
      this._broadcastChannel = new BroadcastChannel('k8s-pool-sync');
      this._broadcastChannel.onmessage = (e) => {
        if (!e.data?.type) return;
        this._isSyncingFromBroadcast = true;
        if (e.data.type === 'state-changed' && e.data.payload) {
          this._state.connections = e.data.payload.connections || [];
          this._state.focusId = e.data.payload.focusId;
          this._notify();
        }
        this._isSyncingFromBroadcast = false;
      };
    } catch (e) {}
  },
};

// ── 兼容旧全局变量 ──────────────────────────────────────────────
Object.defineProperty(window, '_connections', {
  get() { return ConnectionStore.getConnections(); },
  set() {},
});
Object.defineProperty(window, '_currentConnId', {
  get() { return ConnectionStore.getFocusId(); },
  set(v) { if (v) ConnectionStore.setFocus(v); },
});

window.ConnectionState = ConnectionState;
window.ConnectionStore = ConnectionStore;

document.addEventListener('DOMContentLoaded', () => {
  // 清理 localStorage 中的旧连接数据
  localStorage.removeItem('k8s_pool');
  ConnectionStore.restore();
  ConnectionStore._initBroadcast();
});
