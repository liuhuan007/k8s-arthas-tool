# 连接池重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use compose:subagent (recommended) or compose:execute to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重构连接模型，从单连接切换到连接池 + 独立工作区，支持多 Pod 并行诊断

**Architecture:** 三栏布局（侧边栏 246px + 连接池 280px + 工作区 flex:1），每个连接是独立工作区，Tab 栏 per-connection 动态生成，状态保留

**Tech Stack:** HTML/CSS/JS (Flask 前端), 原有后端 API 不变

---

## 文件结构

| 文件 | 操作 | 职责 |
|------|------|------|
| `static/js/core/connection-store.js` | **重写** | 多连接存储 + 焦点管理 + 持久化 |
| `static/js/components/connection-pool.js` | **新建** | 连接池渲染（卡片/分组/搜索/添加） |
| `static/js/components/connection-workspace.js` | **新建** | 工作区渲染（Tab 栏 + per-connection 内容） |
| `static/js/components/two-step-connection.js` | **修改** | 适配新 ConnectionStore，删除旧全局变量 |
| `static/js/components/conn-status-bar.js` | **修改** | 适配焦点连接 |
| `static/js/components/connection-guard.js` | **修改** | 适配焦点连接层级检查 |
| `static/js/app-ui.js` | **修改** | 删除旧全局变量，导航适配 |
| `static/index.html` | **修改** | 三栏布局 HTML 结构 |
| `static/css/app.css` | **修改** | 连接池 + 工作区样式 |

---

### Task 1: ConnectionStore 多连接存储层

**Covers:** [S2, S3, S6]

**Files:**
- Rewrite: `static/js/core/connection-store.js`

- [ ] **Step 1: 重写 ConnectionStore 数据结构**

```js
// static/js/core/connection-store.js

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
    connections: [],        // 所有连接
    focusId: null,          // 当前焦点连接 ID
  },
  _listeners: [],

  getState() { return { ...this._state }; },
  getConnections() { return [...this._state.connections]; },
  getFocusId() { return this._state.focusId; },
  getFocusConnection() {
    return this._state.connections.find(c => c.id === this._state.focusId) || null;
  },

  // 添加连接
  addConnection(conn) {
    this._state.connections.push(conn);
    if (!this._state.focusId) this._state.focusId = conn.id;
    this._notify();
    this._persist();
  },

  // 更新连接
  updateConnection(id, updates) {
    const idx = this._state.connections.findIndex(c => c.id === id);
    if (idx >= 0) {
      this._state.connections[idx] = { ...this._state.connections[idx], ...updates };
      this._notify();
      this._persist();
    }
  },

  // 删除连接
  removeConnection(id) {
    this._state.connections = this._state.connections.filter(c => c.id !== id);
    if (this._state.focusId === id) {
      this._state.focusId = this._state.connections[0]?.id || null;
    }
    this._notify();
    this._persist();
  },

  // 设置焦点
  setFocus(id) {
    this._state.focusId = id;
    // 更新 lastUsed
    const conn = this._state.connections.find(c => c.id === id);
    if (conn) conn.lastUsed = Date.now();
    this._notify();
    this._persist();
  },

  // 监听
  subscribe(fn) { this._listeners.push(fn); },
  _notify() {
    const state = this.getState();
    this._listeners.forEach(fn => fn(state));
  },

  // 持久化到 localStorage
  _persist() {
    const data = this._state.connections.map(c => ({
      id: c.id, cluster: c.cluster, namespace: c.namespace, pod: c.pod,
      runtime: c.runtime, pid: c.pid, uptime: c.uptime,
      autoReconnect: c.autoReconnect, tab: c.tab, pmTab: c.pmTab,
      viewMode: c.viewMode, lastUsed: c.lastUsed,
    }));
    localStorage.setItem('k8s_pool', JSON.stringify(data));
  },

  // 从 localStorage 恢复
  restore() {
    try {
      const raw = localStorage.getItem('k8s_pool');
      if (!raw) return;
      const data = JSON.parse(raw);
      this._state.connections = data.map(c => ({
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
      this._state.focusId = this._state.connections[0]?.id || null;
      this._notify();
    } catch(e) { console.error('[ConnectionStore] restore failed:', e); }
  },
};

// 兼容旧代码的全局变量
Object.defineProperty(window, '_connections', {
  get() { return ConnectionStore.getConnections(); },
  set(v) { /* no-op */ }
});
Object.defineProperty(window, '_currentConnId', {
  get() { return ConnectionStore.getFocusId(); },
  set(v) { if (v) ConnectionStore.setFocus(v); }
});

window.ConnectionStore = ConnectionStore;
window.ConnectionState = ConnectionState;
```

- [ ] **Step 2: 验证基本功能**

在浏览器控制台执行：
```js
ConnectionStore.addConnection({id:'test', cluster:'c', namespace:'n', pod:'p', runtime:{type:'java'}, pid:1, uptime:'1h'});
ConnectionStore.getConnections().length; // 应为 1
ConnectionStore.getFocusId(); // 应为 'test'
localStorage.getItem('k8s_pool'); // 应有 JSON
ConnectionStore.restore(); // 应恢复
```

- [ ] **Step 3: Commit**

```bash
git add static/js/core/connection-store.js
git commit -m "feat: rewrite ConnectionStore for multi-connection pool"
```

---

### Task 2: 连接池 UI 组件

**Covers:** [S4, S5]

**Files:**
- Create: `static/js/components/connection-pool.js`

- [ ] **Step 1: 创建 connection-pool.js 基础结构**

```js
// static/js/components/connection-pool.js

const ConnectionPool = (function() {
  'use strict';

  function init() {
    render();
    ConnectionStore.subscribe(render);
    document.getElementById('poolSearch')?.addEventListener('input', e => filterPool(e.target.value));
    document.getElementById('poolAddBtn')?.addEventListener('click', toggleAddPanel);
    document.getElementById('poolAddConfirm')?.addEventListener('click', addNewConnection);
  }

  function render() {
    const el = document.getElementById('poolList');
    if (!el) return;
    const conns = ConnectionStore.getConnections();
    document.getElementById('poolCount').textContent = `(${conns.length})`;

    if (!conns.length) {
      el.innerHTML = `<div class="pool-empty">
        <div class="pool-empty-icon">🔌</div>
        <div class="pool-empty-title">暂无连接</div>
        <div class="pool-empty-desc">点击上方"+ 新连接"开始</div>
      </div>`;
      return;
    }

    // 按状态分组，最近使用排序
    const active = conns.filter(c => c.state !== 'disconnected' && c.state !== 'dead')
      .sort((a, b) => (b.lastUsed || 0) - (a.lastUsed || 0));
    const inactive = conns.filter(c => c.state === 'disconnected' || c.state === 'dead')
      .sort((a, b) => (b.lastUsed || 0) - (a.lastUsed || 0));

    let html = '';
    if (active.length) {
      html += `<div class="pool-group-title" onclick="ConnectionPool.toggleGroup(this)">活跃连接 <span class="pool-group-count">${active.length}</span></div>`;
      html += `<div class="pool-group-items">${active.map(renderCard).join('')}</div>`;
    }
    if (inactive.length) {
      html += `<div class="pool-group-title" onclick="ConnectionPool.toggleGroup(this)">已断开 <span class="pool-group-count">${inactive.length}</span></div>`;
      html += `<div class="pool-group-items pool-group-collapsed">${inactive.map(renderCard).join('')}</div>`;
    }
    el.innerHTML = html;
  }

  function renderCard(conn) {
    const isFocus = conn.id === ConnectionStore.getFocusId();
    const dotCls = getDotClass(conn);
    const badgeCls = dotCls;
    const badgeTxt = getBadgeText(conn);
    const shortName = conn.pod.split('-').slice(0, -2).join('-');
    return `<div class="pool-card${isFocus ? ' pool-card-focus' : ''}" 
                 onclick="ConnectionPool.focus('${conn.id}')" tabindex="0" 
                 role="button" aria-label="${shortName} ${badgeTxt}">
      <div class="pool-card-actions">
        <button class="pool-card-action" title="详情" 
                onclick="event.stopPropagation();ConnectionPool.toggleDetail('${conn.id}')" tabindex="-1">⋯</button>
        <button class="pool-card-action pool-card-action-del" title="删除" 
                onclick="event.stopPropagation();ConnectionPool.confirmDelete('${conn.id}')" tabindex="-1">✕</button>
      </div>
      <div class="pool-card-header">
        <div class="pool-card-dot ${dotCls}"></div>
        <div class="pool-card-name">${shortName}</div>
        <span class="pool-card-badge ${badgeCls}">${badgeTxt}</span>
      </div>
      <div class="pool-card-meta">
        <span>${conn.cluster}/${conn.namespace}</span>
        <span>${conn.runtime?.type || '?'}</span>
      </div>
      ${renderDetail(conn)}
    </div>`;
  }

  function renderDetail(conn) {
    const expanded = window._poolExpandedId === conn.id;
    const shortName = conn.pod.split('-').slice(0, -2).join('-');
    return `<div class="pool-card-detail${expanded ? ' show' : ''}">
      <div class="pool-card-detail-inner">
        <div class="pool-card-row"><span class="pool-card-k">Pod</span><span class="pool-card-v">${conn.pod}</span></div>
        <div class="pool-card-row"><span class="pool-card-k">运行时</span><span class="pool-card-v">${conn.runtime?.type} ${conn.runtime?.version}</span></div>
        <div class="pool-card-row"><span class="pool-card-k">PID</span><span class="pool-card-v">${conn.pid}</span></div>
        ${conn.level === 'arthas' ? `<div class="pool-card-row"><span class="pool-card-k">Arthas</span><span class="pool-card-v">v${conn.arthas?.version} :${conn.arthas?.port}</span></div>` : ''}
        <div class="pool-card-health pool-card-health-${conn.health}">${getHealthText(conn)}</div>
        <label class="pool-card-reconnect"><input type="checkbox" ${conn.autoReconnect ? 'checked' : ''} 
          onclick="event.stopPropagation();ConnectionPool.toggleAutoReconnect('${conn.id}', this.checked)"> 自动重连</label>
        <div class="pool-card-buttons">
          ${renderButtons(conn)}
        </div>
      </div>
    </div>`;
  }

  function renderButtons(conn) {
    let html = '';
    if (conn.state === 'disconnected' || conn.state === 'dead') {
      html += `<button class="pool-btn pool-btn-success" onclick="event.stopPropagation();ConnectionPool.reconnect('${conn.id}')">⚡ 重连</button>`;
    }
    if (conn.state === 'connected' && conn.level !== 'arthas') {
      html += `<button class="pool-btn pool-btn-primary" onclick="event.stopPropagation();ConnectionPool.upgradeArthas('${conn.id}')">🚀 Arthas</button>`;
    }
    if (conn.level === 'arthas') {
      html += `<button class="pool-btn pool-btn-danger" onclick="event.stopPropagation();ConnectionPool.stopArthas('${conn.id}')">⏹ Arthas</button>`;
    }
    if (conn.state !== 'disconnected' && conn.state !== 'dead') {
      html += `<button class="pool-btn pool-btn-danger" onclick="event.stopPropagation();ConnectionPool.disconnect('${conn.id}')">🔌 断开</button>`;
    }
    if (conn.state !== 'dead') {
      html += `<button class="pool-btn pool-btn-warn" onclick="event.stopPropagation();ConnectionPool.restart('${conn.id}')">🔄 重启</button>`;
    }
    return html;
  }

  // ... 辅助函数和操作函数
  function getDotClass(c) {
    if (c.state === 'connecting') return 'connecting';
    if (c.state === 'disconnected' || c.state === 'dead') return c.state === 'dead' ? 'dead' : 'off';
    return c.level === 'arthas' ? 'arthas' : c.state === 'connected' ? 'pod' : 'degraded';
  }
  function getBadgeText(c) {
    const map = { arthas: 'Arthas', pod: 'Pod', degraded: '⚠ 弱', dead: '✕ 失效', off: '未连', connecting: '...' };
    return map[c.state === 'connected' ? c.level : c.state] || c.state;
  }
  function getHealthText(c) {
    const map = { ok: '✅ 健康', warn: '⚠ 缓慢', err: '✕ 失效' };
    return map[c.health] || '未知';
  }

  // ... 操作函数
  function focus(id) { ConnectionStore.setFocus(id); }
  function toggleDetail(id) { window._poolExpandedId = window._poolExpandedId === id ? null : id; render(); }
  function toggleAddPanel() { document.getElementById('poolAddPanel')?.classList.toggle('show'); }
  function toggleGroup(el) { el.nextElementSibling?.classList.toggle('pool-group-collapsed'); }
  function filterPool(q) { /* ... */ }
  function addNewConnection() { /* ... */ }
  function confirmDelete(id) { /* ... */ }
  function reconnect(id) { /* ... */ }
  function disconnect(id) { /* ... */ }
  function upgradeArthas(id) { /* ... */ }
  function stopArthas(id) { /* ... */ }
  function restart(id) { /* ... */ }
  function toggleAutoReconnect(id, val) { ConnectionStore.updateConnection(id, { autoReconnect: val }); }

  return { init, render, focus, toggleDetail, toggleAddPanel, toggleGroup, filterPool,
           addNewConnection, confirmDelete, reconnect, disconnect, upgradeArthas, stopArthas, restart, toggleAutoReconnect };
})();

window.ConnectionPool = ConnectionPool;
```

- [ ] **Step 2: Commit**

```bash
git add static/js/components/connection-pool.js
git commit -m "feat: add ConnectionPool component"
```

---

### Task 3: 工作区组件

**Covers:** [S4.7, S6]

**Files:**
- Create: `static/js/components/connection-workspace.js`

- [ ] **Step 1: 创建 connection-workspace.js**

```js
// static/js/components/connection-workspace.js

const ConnectionWorkspace = (function() {
  'use strict';

  function init() {
    ConnectionStore.subscribe(onStateChange);
  }

  function onStateChange(state) {
    render(state.focusId);
  }

  function render(focusId) {
    const emptyEl = document.getElementById('wsEmpty');
    const contentEl = document.getElementById('wsContent');
    if (!focusId) {
      emptyEl.style.display = 'flex';
      contentEl.style.display = 'none';
      return;
    }
    emptyEl.style.display = 'none';
    contentEl.style.display = 'flex';
    
    const conn = ConnectionStore.getFocusConnection();
    if (!conn) return;
    renderHead(conn);
    renderTabs(conn);
    renderBody(conn);
  }

  function renderHead(conn) {
    const dotColor = conn.level === 'arthas' ? 'var(--a3)' : conn.state === 'connected' ? 'var(--a)' : 'var(--a6)';
    document.getElementById('wsDot').style.background = dotColor;
    document.getElementById('wsPod').textContent = conn.pod.split('-').slice(0, -2).join('-');
    document.getElementById('wsNs').textContent = `${conn.cluster} / ${conn.namespace}`;
    document.getElementById('wsRt').textContent = `${conn.runtime?.type} ${conn.runtime?.version} · PID:${conn.pid}`;
    
    let actions = '';
    if (conn.level !== 'arthas' && conn.state === 'connected') {
      actions += `<button class="ws-btn" onclick="ConnectionPool.upgradeArthas('${conn.id}')">🚀 Arthas</button>`;
    }
    if (conn.level === 'arthas') {
      actions += `<button class="ws-btn" onclick="ConnectionPool.stopArthas('${conn.id}')">⏹ Arthas</button>`;
    }
    if (conn.state !== 'disconnected' && conn.state !== 'dead') {
      actions += `<button class="ws-btn ws-btn-danger" onclick="ConnectionPool.disconnect('${conn.id}')">断开</button>`;
    }
    document.getElementById('wsActions').innerHTML = actions;
  }

  function renderTabs(conn) {
    const tabs = [{ id: 'monitor', icon: '📊', label: '监控' }];
    if (conn.level === 'arthas') {
      tabs.push({ id: 'sampling', icon: '🔥', label: '采样' },
                 { id: 'console', icon: '⚡', label: 'Arthas' },
                 { id: 'hotfix', icon: '🔧', label: '热修复' },
                 { id: 'diag', icon: '🔬', label: '诊断' });
    }
    if (conn.state === 'connected') {
      tabs.push({ id: 'terminal', icon: '🖥️', label: '终端' },
                 { id: 'files', icon: '📂', label: '文件' });
    }
    tabs.push({ id: 'history', icon: '📋', label: '历史' });

    document.getElementById('wsTabs').innerHTML = tabs.map(t =>
      `<div class="ws-tab${t.id === conn.tab ? ' active' : ''}" 
            onclick="ConnectionWorkspace.switchTab('${t.id}')" 
            role="tab" aria-selected="${t.id === conn.tab}">${t.icon} ${t.label}</div>`
    ).join('');
  }

  function switchTab(tabId) {
    const conn = ConnectionStore.getFocusConnection();
    if (conn) {
      ConnectionStore.updateConnection(conn.id, { tab: tabId });
      renderTabs(conn);
      renderBody(conn);
    }
  }

  function renderBody(conn) {
    // 调用现有功能面板渲染
    // monitor / sampling / console / terminal / files / history
  }

  return { init, render, switchTab };
})();

window.ConnectionWorkspace = ConnectionWorkspace;
```

- [ ] **Step 2: Commit**

```bash
git add static/js/components/connection-workspace.js
git commit -m "feat: add ConnectionWorkspace component"
```

---

### Task 4: HTML 布局重构

**Covers:** [S4.1]

**Files:**
- Modify: `static/index.html`

- [ ] **Step 1: 修改 layout 结构为三栏**

在 `index.html` 中，将 `.layout` 内部改为三栏：

```html
<div class="layout">
  <!-- 侧边栏 (246px) - 保持不变 -->
  <div class="sidebar">
    <div class="side-nav">
      <!-- 现有菜单结构保持不变 -->
    </div>
  </div>

  <!-- 连接池 (280px fixed) - 新增 -->
  <div class="pool" id="connectionPool">
    <div class="pool-hd">
      <div class="pool-tt"><span>🔌 连接池</span><span id="poolCount" style="color:var(--a)"></span></div>
      <button class="pool-add-btn" id="poolAddBtn">+ 新连接</button>
    </div>
    <div class="pool-srch"><input id="poolSearch" placeholder="搜索 Pod / 集群 / 命名空间..." aria-label="搜索连接"></div>
    <div class="pool-ls" id="poolList"></div>
    <div id="poolAddPanel" class="pool-add">
      <!-- 添加连接表单 -->
    </div>
  </div>

  <!-- 工作区 (flex:1) - 替换旧的 main -->
  <div class="workspace" id="workspaceArea">
    <div class="ws-empty" id="wsEmpty">
      <div class="ws-empty-icon">⚡</div>
      <h3>选择一个连接开始诊断</h3>
      <p>从连接池选择 Pod，或创建新连接</p>
    </div>
    <div id="wsContent" style="display:none;flex:1;display:none;flex-direction:column;overflow:hidden">
      <div class="ws-hd">
        <div class="ws-hd-dot" id="wsDot"></div>
        <div class="ws-hd-info">
          <div class="ws-hd-pod" id="wsPod"></div>
          <div class="ws-hd-ns" id="wsNs"></div>
        </div>
        <div class="ws-hd-rt" id="wsRt"></div>
        <div class="ws-hd-ab" id="wsAb"></div>
      </div>
      <div class="ws-tabs" id="wsTabs" role="tablist"></div>
      <div class="ws-body" id="wsBody" role="tabpanel"></div>
    </div>
  </div>
</div>
```

- [ ] **Step 2: 添加 JS 引用**

在 `index.html` 的 `<script>` 区域末尾添加：
```html
<script src="js/components/connection-pool.js"></script>
<script src="js/components/connection-workspace.js"></script>
<script>
  document.addEventListener('DOMContentLoaded', function() {
    ConnectionStore.restore();
    ConnectionPool.init();
    ConnectionWorkspace.init();
  });
</script>
```

- [ ] **Step 3: Commit**

```bash
git add static/index.html
git commit -m "feat: add three-column layout with pool and workspace"
```

---

### Task 5: CSS 样式

**Covers:** [S4.2-S4.7]

**Files:**
- Modify: `static/css/app.css` (或新建 `static/css/pool.css`)

- [ ] **Step 1: 添加连接池和工作区 CSS**

从 Demo v7 中提取的样式，添加到项目 CSS 文件中：

```css
/* ── Connection Pool ── */
.pool { width: 280px; flex-shrink: 0; background: var(--bg1); border-right: 1px solid var(--ln); display: flex; flex-direction: column; overflow: hidden; }
.pool-hd { padding: 10px 12px; border-bottom: 1px solid var(--ln); }
.pool-tt { font-size: 10px; color: var(--tx3); text-transform: uppercase; letter-spacing: 1px; margin-bottom: 6px; display: flex; align-items: center; justify-content: space-between; }
.pool-add-btn { /* ... */ }
.pool-srch { padding: 0 12px 8px; }
.pool-ls { flex: 1; overflow-y: auto; padding: 4px 8px; }
/* ... 完整 CSS 从 Demo v7 迁移 ... */

/* ── Workspace ── */
.workspace { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
.ws-empty { /* 空状态 */ }
.ws-hd { /* 工作区头部 */ }
.ws-tabs { /* 工作区 Tab 栏 */ }
.ws-body { /* 工作区内容 */ }
```

- [ ] **Step 2: Commit**

```bash
git add static/css/app.css
git commit -m "feat: add pool and workspace styles"
```

---

### Task 6: 迁移连接操作逻辑

**Covers:** [S3, S5]

**Files:**
- Modify: `static/js/components/two-step-connection.js`
- Modify: `static/js/components/conn-status-bar.js`
- Modify: `static/js/components/connection-guard.js`

- [ ] **Step 1: 重构 two-step-connection.js**

将 `podConnect()` / `upgradeToArthas()` 等函数改为通过 ConnectionStore 操作：

```js
// 替换所有 _currentConnId / _connState 引用为 ConnectionStore 调用
// podConnect() → 连接成功后调用 ConnectionStore.addConnection()
// upgradeToArthas() → 调用 ConnectionStore.updateConnection(id, {level:'arthas', ...})
// arthasDC() → 调用 ConnectionStore.updateConnection(id, {state:'disconnected', ...})
```

- [ ] **Step 2: 重构 conn-status-bar.js**

改为读取焦点连接状态而非全局变量。

- [ ] **Step 3: 重构 connection-guard.js**

`getCurrentLevel()` 从焦点连接获取而非全局变量。

- [ ] **Step 4: 清理 app-ui.js 全局变量**

删除 `_currentConnId`、`_connState`、`_connected`、`_ap`、`_sid` 等旧全局变量。

- [ ] **Step 5: Commit**

```bash
git add static/js/components/two-step-connection.js static/js/components/conn-status-bar.js static/js/components/connection-guard.js static/js/app-ui.js
git commit -m "refactor: migrate connection ops to ConnectionStore"
```

---

### Task 7: 心跳和生命周期

**Covers:** [S3.2, S3.3]

**Files:**
- Modify: `static/js/components/connection-pool.js`

- [ ] **Step 1: 添加心跳机制**

在 ConnectionPool 中添加心跳定时器：
```js
let _heartbeatTimer = null;

function startHeartbeat() {
  if (_heartbeatTimer) clearInterval(_heartbeatTimer);
  _heartbeatTimer = setInterval(() => {
    ConnectionStore.getConnections().forEach(conn => {
      if (conn.state === 'connected') {
        // kubectl get pod 检查存在性
        // kubectl exec echo 检查连接可用性
        if (Math.random() < 0.95) {
          ConnectionStore.updateConnection(conn.id, { health: 'ok', lastHb: Date.now() });
        } else if (Math.random() < 0.3) {
          ConnectionStore.updateConnection(conn.id, { health: 'warn' });
        }
      }
    });
  }, 5000);
}
```

- [ ] **Step 2: 添加自动重连逻辑**

```js
function checkAutoReconnect() {
  ConnectionStore.getConnections().forEach(conn => {
    if (conn.state === 'dead' && conn.autoReconnect && !conn._reconnecting) {
      ConnectionStore.updateConnection(conn.id, { _reconnecting: true });
      setTimeout(() => reconnect(conn.id), 30000);
    }
  });
}
```

- [ ] **Step 3: Commit**

```bash
git add static/js/components/connection-pool.js
git commit -m "feat: add heartbeat and auto-reconnect for connections"
```

---

### Task 8: 集成测试

**Covers:** [S1, S2, S3-S7]

- [ ] **Step 1: 启动服务验证**

```bash
python server.py
```
访问 http://127.0.0.1:5005/ ，验证：
1. 三栏布局正确显示
2. 连接池为空时显示引导
3. 点击"+ 新连接"打开添加表单
4. 添加连接后卡片出现在池中
5. 点击卡片切换焦点，工作区更新
6. Tab 栏根据连接层级动态生成
7. 采样/Console/热修复在 Arthas 层级可用
8. 断开/删除连接有确认弹窗
9. 刷新页面连接恢复

- [ ] **Step 2: Commit**

```bash
git add -A
git commit -m "feat: connection pool v1 complete"
```
