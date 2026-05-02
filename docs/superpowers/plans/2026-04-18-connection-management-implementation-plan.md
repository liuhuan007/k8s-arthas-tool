# Connection Management Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the sidebar-centric connection workflow with a dedicated connection management flow (list → detail → work page), keep connection state reusable across pages, preserve the lightweight current-connection strip, and move AI to a global entry.

**Architecture:** Keep the existing Flask + static HTML + vanilla JS stack. Reuse `static/js/components/connections.js` as the canonical connection store, refactor `static/js/components/two-step-connection.js` so it can drive both the new detail page and existing shared actions, and move page-to-page navigation through query-string connection context (`?conn=<id>`). To reduce migration risk, keep the existing panel implementations alive while introducing new pages first; only remove the old sidebar/tab assumptions after the new routes and pages work.

**Tech Stack:** Flask, static HTML, vanilla JavaScript, existing `static/js/components/*`, `static/css/app.css`, pytest for route/markup smoke tests, manual browser smoke checks via `python server.py`.

---

## File Structure

### Create
- `tests/test_connection_page_routes.py` — smoke-test route registration for the new pages.
- `tests/test_connection_page_markup.py` — smoke-test the static HTML/JS shell shape during migration.
- `static/connection-detail.html` — single-connection management page.
- `static/terminal.html` — terminal work page.
- `static/monitor.html` — Pod monitor work page.
- `static/filebrowser.html` — file download work page.
- `static/diagnose.html` — performance diagnosis work page.
- `static/arthas-console.html` — Arthas command work page.
- `static/profiler.html` — sampling/profiler work page.
- `static/history.html` — global history page moved out of the old top tab bar.
- `static/js/components/page-shell.js` — shared top navigation + page header + global AI launcher/drawer mount.
- `static/js/components/connection-page-context.js` — parse `?conn=`, load current connection, and navigate between detail/work pages.
- `static/js/page-connection-list.js` — connection list table rendering, filters, table actions.
- `static/js/page-connection-detail.js` — detail page rendering + lifecycle action wiring.
- `static/js/page-history.js` — history page bootstrap.
- `static/js/page-workspace.js` — shared bootstrap for terminal/monitor/filebrowser/diagnose/arthas-console/profiler pages.

### Modify
- `server.py` — register routes for the new pages.
- `static/index.html` — repurpose from old workspace shell into the connection management list page.
- `static/css/app.css` — add page-shell, table, detail card, work-entry, drawer, and lightweight context strip styles.
- `static/js/app.js` — expose the new page-context helpers on `window.App`.
- `static/js/app-ui.js` — remove duplicated connection helper logic and stop assuming one tabbed mega-page is the primary UX.
- `static/js/components/connections.js` — keep canonical connection store helpers and dispatch page-safe connection-change events.
- `static/js/components/two-step-connection.js` — make DOM targets configurable so the same lifecycle logic can drive the detail page.
- `static/js/components/conn-status-bar.js` — downgrade to a lightweight current-context strip with a “查看详情” action instead of connect/upgrade actions.
- `static/js/ai-chat.js` — mount into a global drawer instead of the old top-level `tab-ai` panel while preserving connection awareness.

## Migration Rules

1. **Repurpose `index.html` instead of inventing a new home route.** `index.html` becomes the connection management page so `/` keeps working.
2. **Introduce new pages before deleting old behavior.** Route tests, page shells, and detail/work pages land first.
3. **Move shared state before moving UI.** Canonical helpers live in `connections.js` + `connection-page-context.js`; page code reads from them.
4. **Keep the current connection strip, but shrink its responsibility.** No connect/upgrade/delete actions there; detail page owns those actions.
5. **Treat AI as global UI.** It opens from any page, can work with no connection, and deepens when a Pod/Arthas context exists.

---

### Task 1: Register the new page routes first

**Files:**
- Create: `tests/test_connection_page_routes.py`
- Modify: `server.py:196-231`
- Test: `tests/test_connection_page_routes.py`

- [ ] **Step 1: Write the failing route smoke test**

```python
from server import app


def test_connection_management_routes_are_registered():
    rules = {rule.rule for rule in app.url_map.iter_rules()}

    assert '/connections.html' in rules
    assert '/connection-detail.html' in rules
    assert '/terminal.html' in rules
    assert '/monitor.html' in rules
    assert '/filebrowser.html' in rules
    assert '/diagnose.html' in rules
    assert '/arthas-console.html' in rules
    assert '/profiler.html' in rules
    assert '/history.html' in rules
```

- [ ] **Step 2: Run the test to confirm the routes are missing**

Run:
```bash
python -m pytest tests/test_connection_page_routes.py -q
```

Expected: FAIL with missing route assertions such as `'/connection-detail.html' not in rules`.

- [ ] **Step 3: Add explicit Flask routes for the new pages**

```python
@app.route('/')
@app.route('/index.html')
@app.route('/index')
@app.route('/connections.html')
def index():
    if not current_user.is_authenticated:
        return redirect('/login.html')
    return app.send_static_file('index.html')


@app.route('/connection-detail.html')
@login_required
def connection_detail_page():
    return app.send_static_file('connection-detail.html')


@app.route('/terminal.html')
@login_required
def terminal_page():
    return app.send_static_file('terminal.html')


@app.route('/monitor.html')
@login_required
def monitor_page():
    return app.send_static_file('monitor.html')


@app.route('/filebrowser.html')
@login_required
def filebrowser_page():
    return app.send_static_file('filebrowser.html')


@app.route('/diagnose.html')
@login_required
def diagnose_page():
    return app.send_static_file('diagnose.html')


@app.route('/arthas-console.html')
@login_required
def arthas_console_page():
    return app.send_static_file('arthas-console.html')


@app.route('/profiler.html')
@login_required
def profiler_page():
    return app.send_static_file('profiler.html')


@app.route('/history.html')
@login_required
def history_page():
    return app.send_static_file('history.html')
```

- [ ] **Step 4: Run the route test again**

Run:
```bash
python -m pytest tests/test_connection_page_routes.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit the routing baseline**

```bash
git add tests/test_connection_page_routes.py server.py
git commit -m "feat: register connection management page routes"
```

---

### Task 2: Repurpose `index.html` into the connection management list page

**Files:**
- Create: `tests/test_connection_page_markup.py`
- Create: `static/js/page-connection-list.js`
- Modify: `static/index.html:104-220`
- Modify: `static/css/app.css`
- Test: `tests/test_connection_page_markup.py`

- [ ] **Step 1: Write the failing list-page markup test**

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'static'


def read_page(name: str) -> str:
    return (ROOT / name).read_text(encoding='utf-8')


def test_index_page_is_connection_management_shell():
    html = read_page('index.html')

    assert '连接管理' in html
    assert 'id="connectionsFilters"' in html
    assert 'id="connectionsTable"' in html
    assert 'id="tab-profiler"' not in html
    assert 'id="connList"' not in html
```

- [ ] **Step 2: Run the markup test and confirm the old shell still exists**

Run:
```bash
python -m pytest tests/test_connection_page_markup.py -q
```

Expected: FAIL because `index.html` still contains `connList` and the old tab bar.

- [ ] **Step 3: Replace the old sidebar + top tabs with a list-page shell**

`static/index.html` should become a full-width page with global nav, page header, filter bar, and table container:

```html
<body data-page="connections">
  <div id="pageShell"></div>

  <main class="page page-connections">
    <section class="page-header">
      <div>
        <h1>连接管理</h1>
        <p>管理 Pod / Arthas 连接，查看状态并进入详情。</p>
      </div>
      <div class="page-actions">
        <button class="ab ab-g" onclick="checkConnectionsHealth()">健康检查</button>
        <button class="ab ab-g" onclick="cleanupStaleConnections()">清理失效连接</button>
        <button class="ab ab-p" onclick="openConnectionCreator()">新建连接</button>
      </div>
    </section>

    <section class="filter-card" id="connectionsFilters">
      <select id="filterCluster"></select>
      <select id="filterNamespace"></select>
      <select id="filterLevel">
        <option value="">全部层级</option>
        <option value="pod">Pod</option>
        <option value="arthas">Arthas</option>
      </select>
      <select id="filterStatus">
        <option value="">全部状态</option>
        <option value="healthy">正常</option>
        <option value="warning">异常</option>
        <option value="stale">失效</option>
      </select>
      <input id="filterPodKeyword" placeholder="搜索 Pod 名称">
    </section>

    <section class="table-card">
      <table class="tbl" id="connectionsTable">
        <thead>
          <tr>
            <th>Pod</th>
            <th>Namespace</th>
            <th>集群</th>
            <th>连接层级</th>
            <th>状态</th>
            <th>运行时</th>
            <th>最近检查</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody id="connectionsTableBody"></tbody>
      </table>
    </section>
  </main>

  <script src="js/components/page-shell.js"></script>
  <script src="js/page-connection-list.js"></script>
</body>
```

`static/js/page-connection-list.js` should own table rendering instead of the old sidebar renderer:

```javascript
(function () {
  function renderConnectionTable() {
    const body = document.getElementById('connectionsTableBody');
    const rows = (getConnections() || []).map(conn => {
      const level = inferConnLevel(conn);
      const runtime = getConnRuntime(conn);
      return `
        <tr onclick="openConnectionDetail('${esc(conn.id)}')">
          <td>${esc(conn.pod_name)}</td>
          <td>${esc(conn.namespace || '')}</td>
          <td>${esc(conn.cluster_name || '')}</td>
          <td>${level === 'arthas' ? 'Arthas' : 'Pod'}</td>
          <td>${renderConnectionStatus(conn)}</td>
          <td>${runtime ? esc(runtime.type + (runtime.version ? ' ' + runtime.version : '')) : '—'}</td>
          <td>${esc(conn.last_checked_at || '—')}</td>
          <td><button class="ab ab-g ab-sm" onclick="event.stopPropagation();openConnectionDetail('${esc(conn.id)}')">查看详情</button></td>
        </tr>
      `;
    });
    body.innerHTML = rows.join('') || '<tr><td colspan="8" class="empty-msg">暂无连接</td></tr>';
  }

  window.openConnectionDetail = function (connId) {
    location.href = `/connection-detail.html?conn=${encodeURIComponent(connId)}`;
  };

  document.addEventListener('DOMContentLoaded', function () {
    PageShell.init({ activeNav: 'connections', title: '连接管理' });
    renderConnectionTable();
    document.addEventListener('connection-changed', renderConnectionTable);
  });
})();
```

Add the shared table/filter/page-card styles to `static/css/app.css` instead of scattering new inline CSS.

- [ ] **Step 4: Run the markup test again**

Run:
```bash
python -m pytest tests/test_connection_page_markup.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit the connection list page**

```bash
git add tests/test_connection_page_markup.py static/index.html static/css/app.css static/js/page-connection-list.js
git commit -m "feat: turn index into connection management list page"
```

---

### Task 3: Add shared page shell and canonical connection page context helpers

**Files:**
- Modify: `tests/test_connection_page_markup.py`
- Create: `static/js/components/page-shell.js`
- Create: `static/js/components/connection-page-context.js`
- Modify: `static/js/app.js`
- Modify: `static/js/components/connections.js`
- Modify: `static/js/app-ui.js:141-158,1106-1209`
- Test: `tests/test_connection_page_markup.py`

- [ ] **Step 1: Extend the markup smoke test for shared shell assets**

```python
def test_connection_pages_reference_shared_shell_assets():
    html = read_page('index.html')

    assert 'js/components/page-shell.js' in html
    assert 'js/components/connection-page-context.js' in html
```

- [ ] **Step 2: Run the markup test and confirm the shared helpers are not wired yet**

Run:
```bash
python -m pytest tests/test_connection_page_markup.py -q
```

Expected: FAIL because `index.html` does not yet load both shared helper scripts.

- [ ] **Step 3: Introduce reusable shell/context helpers and remove duplicated connection helpers from `app-ui.js`**

Create `static/js/components/page-shell.js`:

```javascript
window.PageShell = (function () {
  const NAV_ITEMS = [
    { key: 'connections', label: '连接管理', href: '/index.html' },
    { key: 'model-config', label: '模型配置', href: '/mcp-config.html' },
    { key: 'history', label: '历史记录', href: '/history.html' },
    { key: 'user-management', label: '用户管理', href: '/user-management.html' },
    { key: 'audit-logs', label: '审计日志', href: '/audit-logs.html' },
  ];

  function init({ activeNav, title }) {
    const mount = document.getElementById('pageShell');
    mount.innerHTML = `
      <header class="topbar-shell">
        <div class="tb-logo"><div class="tb-hex"></div><span class="tb-title">Arthas <em>K8s</em></span></div>
        <nav class="tb-links">${NAV_ITEMS.map(item => `<a class="tb-lnk ${item.key === activeNav ? 'on' : ''}" href="${item.href}">${item.label}</a>`).join('')}</nav>
        <button id="globalAiLauncher" class="tb-ai-btn" type="button">AI 助手</button>
      </header>
      <div id="globalAiDrawer" class="ai-drawer"></div>
    `;
    document.title = `${title} - K8s Arthas Tool`;
  }

  return { init };
})();
```

Create `static/js/components/connection-page-context.js`:

```javascript
window.ConnectionPageContext = (function () {
  function getRequestedConnId() {
    const params = new URLSearchParams(window.location.search);
    return params.get('conn') || getCurrentConnId();
  }

  function requireConnection({ redirectTo = '/index.html' } = {}) {
    const connId = getRequestedConnId();
    const connection = (getConnections() || []).find(c => c.id === connId) || null;
    if (!connection) {
      window.location.href = redirectTo;
      return null;
    }
    setCurrentConnId(connId);
    return { connId, connection, level: inferConnLevel(connection), runtime: getConnRuntime(connection) };
  }

  function go(path, connId = getCurrentConnId()) {
    window.location.href = `${path}?conn=${encodeURIComponent(connId)}`;
  }

  return { getRequestedConnId, requireConnection, go };
})();
```

Update `static/js/app.js` to expose the shared helpers:

```javascript
window.App = {
  // ...existing exports...
  inferConnLevel,
  getConnRuntime,
  canUpgradeConnection,
  setCurrentConnId,
  ConnectionPageContext,
  PageShell,
};
```

Then stop duplicating `_inferLevel`, `_getRt`, and `_canUpgrade` inside `static/js/app-ui.js`; replace their call sites with the canonical `inferConnLevel`, `getConnRuntime`, and `canUpgradeConnection` functions from `connections.js`.

- [ ] **Step 4: Re-run the markup test and do a manual navigation smoke check**

Run:
```bash
python -m pytest tests/test_connection_page_markup.py -q
```

Expected: PASS.

Then run:
```bash
python server.py
```

Manual check:
- `/index.html` shows the new top nav.
- Clicking a connection row opens `/connection-detail.html?conn=<id>`.
- Refreshing the detail page keeps the current connection context.

- [ ] **Step 5: Commit the shared shell/context helpers**

```bash
git add tests/test_connection_page_markup.py static/js/components/page-shell.js static/js/components/connection-page-context.js static/js/app.js static/js/components/connections.js static/js/app-ui.js static/index.html
git commit -m "refactor: share connection page shell and context helpers"
```

---

### Task 4: Build the connection detail page and refactor the two-step connection UI to target it

**Files:**
- Modify: `tests/test_connection_page_markup.py`
- Create: `static/connection-detail.html`
- Create: `static/js/page-connection-detail.js`
- Modify: `static/js/components/two-step-connection.js`
- Modify: `static/js/components/connections.js`
- Test: `tests/test_connection_page_markup.py`

- [ ] **Step 1: Write the failing detail-page markup test**

```python
def test_connection_detail_page_contains_management_sections():
    html = read_page('connection-detail.html')

    assert 'id="detailBasicInfo"' in html
    assert 'id="detailCurrentState"' in html
    assert 'id="detailRuntimeCapabilities"' in html
    assert 'id="detailActions"' in html
    assert 'id="detailWorkEntrances"' in html
```

- [ ] **Step 2: Run the markup test to confirm the page does not exist yet**

Run:
```bash
python -m pytest tests/test_connection_page_markup.py -q
```

Expected: FAIL with `FileNotFoundError` or missing IDs.

- [ ] **Step 3: Create the detail page and make `two-step-connection.js` DOM-targetable**

`static/connection-detail.html` should contain the management-only layout from the approved spec:

```html
<body data-page="connection-detail">
  <div id="pageShell"></div>

  <main class="page page-detail">
    <section class="page-header">
      <div>
        <h1 id="detailTitle">连接详情</h1>
        <p id="detailSubtitle">查看单连接信息、状态与能力，并进入工作页。</p>
      </div>
      <div class="page-actions">
        <button class="ab ab-g" onclick="ConnectionPageContext.go('/index.html')">返回连接列表</button>
      </div>
    </section>

    <section class="detail-grid">
      <article class="detail-card" id="detailBasicInfo"></article>
      <article class="detail-card" id="detailCurrentState"></article>
      <article class="detail-card" id="detailRuntimeCapabilities"></article>
      <article class="detail-card" id="detailActions"></article>
    </section>

    <section class="detail-card" id="detailWorkEntrances"></section>
  </main>
</body>
```

Refactor `static/js/components/two-step-connection.js` so it no longer hardcodes `ptConnBtn`, `runtimeInfo`, and `connStatus`:

```javascript
const defaultConnectionDom = {
  connectButtonId: 'ptConnBtn',
  runtimeInfoId: 'runtimeInfo',
  statusId: 'connStatus',
};

let _connectionDom = { ...defaultConnectionDom };

function bindConnectionDom(overrides = {}) {
  _connectionDom = { ...defaultConnectionDom, ...overrides };
}

function getConnectButton() {
  return document.getElementById(_connectionDom.connectButtonId);
}

function getRuntimeInfoEl() {
  return document.getElementById(_connectionDom.runtimeInfoId);
}

function getStatusEl() {
  return document.getElementById(_connectionDom.statusId);
}
```

Then implement `static/js/page-connection-detail.js` around the new sections:

```javascript
(function () {
  function renderWorkEntrances(conn) {
    const level = inferConnLevel(conn);
    const links = [
      { href: '/terminal.html', label: '🖥️ 终端', enabled: level === 'pod' || level === 'arthas' },
      { href: '/monitor.html', label: '📊 Pod 监控', enabled: level === 'pod' || level === 'arthas' },
      { href: '/filebrowser.html', label: '📂 文件下载', enabled: level === 'pod' || level === 'arthas' },
      { href: '/diagnose.html', label: '🔬 性能诊断', enabled: level === 'pod' || level === 'arthas' },
      { href: '/arthas-console.html', label: '⚡ Arthas命令', enabled: level === 'arthas' },
      { href: '/profiler.html', label: '🔥 采样工具', enabled: level === 'arthas' },
    ];

    document.getElementById('detailWorkEntrances').innerHTML = links.map(link => `
      <button class="work-entry ${link.enabled ? '' : 'disabled'}" ${link.enabled ? `onclick="ConnectionPageContext.go('${link.href}', '${conn.id}')"` : 'disabled'}>
        ${link.label}
      </button>
    `).join('');
  }

  document.addEventListener('DOMContentLoaded', function () {
    PageShell.init({ activeNav: 'connections', title: '连接详情' });
    const ctx = ConnectionPageContext.requireConnection();
    if (!ctx) return;

    bindConnectionDom({
      connectButtonId: 'detailPrimaryAction',
      runtimeInfoId: 'detailRuntimeInfo',
      statusId: 'detailActionStatus',
    });

    renderConnectionDetail(ctx.connection);
    renderWorkEntrances(ctx.connection);
  });
})();
```

- [ ] **Step 4: Run the markup test and manually verify the detail lifecycle**

Run:
```bash
python -m pytest tests/test_connection_page_markup.py -q
```

Expected: PASS.

Then run:
```bash
python server.py
```

Manual check:
- Open a connection detail page from the list.
- For a disconnected target, the primary action is “建立 Pod 连接”.
- For a Java Pod connection, the primary action changes to “升级到 Arthas”.
- Work entry buttons unlock according to Pod vs Arthas level.

- [ ] **Step 5: Commit the detail page and two-step refactor**

```bash
git add tests/test_connection_page_markup.py static/connection-detail.html static/js/page-connection-detail.js static/js/components/two-step-connection.js static/js/components/connections.js
git commit -m "feat: add connection detail page and shared lifecycle actions"
```

---

### Task 5: Split the connection-scoped tools into independent work pages

**Files:**
- Modify: `tests/test_connection_page_markup.py`
- Create: `static/terminal.html`
- Create: `static/monitor.html`
- Create: `static/filebrowser.html`
- Create: `static/diagnose.html`
- Create: `static/arthas-console.html`
- Create: `static/profiler.html`
- Create: `static/history.html`
- Create: `static/js/page-workspace.js`
- Create: `static/js/page-history.js`
- Modify: `static/js/app-ui.js:1106-1209`
- Modify: `static/css/app.css`
- Test: `tests/test_connection_page_markup.py`

- [ ] **Step 1: Write the failing workspace-page smoke test**

```python
def test_workspace_pages_exist_with_page_markers():
    for page_name, marker in [
        ('terminal.html', 'data-workspace-page="terminal"'),
        ('monitor.html', 'data-workspace-page="monitor"'),
        ('filebrowser.html', 'data-workspace-page="filebrowser"'),
        ('diagnose.html', 'data-workspace-page="diag"'),
        ('arthas-console.html', 'data-workspace-page="console"'),
        ('profiler.html', 'data-workspace-page="profiler"'),
        ('history.html', 'data-page="history"'),
    ]:
        assert marker in read_page(page_name)
```

- [ ] **Step 2: Run the markup test and confirm the new pages are missing**

Run:
```bash
python -m pytest tests/test_connection_page_markup.py -q
```

Expected: FAIL because the workspace pages do not exist yet.

- [ ] **Step 3: Create a shared workspace bootstrap and move each tool behind its own route**

Use one shared JS bootstrap instead of six divergent page scripts:

```javascript
const WORKSPACE_CONFIG = {
  terminal: { title: '终端', requiredLevel: 'pod', panelId: 'panel-terminal' },
  monitor: { title: 'Pod 监控', requiredLevel: 'pod', panelId: 'panel-monitor' },
  filebrowser: { title: '文件下载', requiredLevel: 'pod', panelId: 'panel-filebrowser' },
  diag: { title: '性能诊断', requiredLevel: 'pod', panelId: 'panel-diag' },
  console: { title: 'Arthas命令', requiredLevel: 'arthas', panelId: 'panel-console' },
  profiler: { title: '采样工具', requiredLevel: 'arthas', panelId: 'panel-profiler' },
};

document.addEventListener('DOMContentLoaded', function () {
  const pageKey = document.body.dataset.workspacePage;
  const config = WORKSPACE_CONFIG[pageKey];
  const ctx = ConnectionPageContext.requireConnection();
  if (!ctx) return;

  PageShell.init({ activeNav: 'connections', title: config.title });
  renderWorkspaceHeader(ctx.connection, config.title);
  mountWorkspacePanel(config.panelId, ctx);
});
```

Each page stays thin and declarative, for example `static/monitor.html`:

```html
<body data-page="workspace" data-workspace-page="monitor">
  <div id="pageShell"></div>
  <main class="page workspace-page">
    <section id="workspaceHeader"></section>
    <section id="workspacePanel"></section>
  </main>
  <script src="js/components/page-shell.js"></script>
  <script src="js/components/connection-page-context.js"></script>
  <script src="js/page-workspace.js"></script>
</body>
```

`static/history.html` becomes a normal top-level page and no longer depends on a connection context:

```javascript
document.addEventListener('DOMContentLoaded', function () {
  PageShell.init({ activeNav: 'history', title: '历史记录' });
  loadHistory();
});
```

Finally, trim `static/js/app-ui.js:1106-1209` so `switchTab()` is no longer the primary navigation model. Keep only the panel-specific rendering helpers that the new pages still call.

- [ ] **Step 4: Run the markup test and manually verify page-by-page navigation**

Run:
```bash
python -m pytest tests/test_connection_page_markup.py -q
```

Expected: PASS.

Then run:
```bash
python server.py
```

Manual check:
- Detail page opens terminal/monitor/filebrowser/diagnose pages for Pod-level connections.
- Arthas-only pages remain disabled until the connection reaches Arthas level.
- History opens from the top navigation without requiring a connection.
- Each work page shows current connection info and a link back to the detail page.

- [ ] **Step 5: Commit the page split**

```bash
git add tests/test_connection_page_markup.py static/terminal.html static/monitor.html static/filebrowser.html static/diagnose.html static/arthas-console.html static/profiler.html static/history.html static/js/page-workspace.js static/js/page-history.js static/js/app-ui.js static/css/app.css
git commit -m "feat: split connection tools into dedicated pages"
```

---

### Task 6: Move AI to a global drawer and downgrade the status bar to lightweight context only

**Files:**
- Modify: `tests/test_connection_page_markup.py`
- Modify: `static/js/components/page-shell.js`
- Modify: `static/js/ai-chat.js`
- Modify: `static/js/components/conn-status-bar.js`
- Modify: `static/index.html`
- Modify: `static/connection-detail.html`
- Modify: `static/terminal.html`
- Modify: `static/monitor.html`
- Modify: `static/filebrowser.html`
- Modify: `static/diagnose.html`
- Modify: `static/arthas-console.html`
- Modify: `static/profiler.html`
- Modify: `static/history.html`
- Modify: `static/css/app.css`
- Test: `tests/test_connection_page_markup.py`

- [ ] **Step 1: Extend the smoke test for the AI launcher and status-strip downgrade**

```python
def test_index_page_no_longer_contains_legacy_ai_tab():
    html = read_page('index.html')
    assert 'id="tab-ai"' not in html


def test_page_shell_mounts_global_ai_entry():
    js = (ROOT / 'js' / 'components' / 'page-shell.js').read_text(encoding='utf-8')
    assert 'globalAiLauncher' in js
    assert 'globalAiDrawer' in js


def test_status_bar_js_uses_detail_navigation_copy():
    js = (ROOT / 'js' / 'components' / 'conn-status-bar.js').read_text(encoding='utf-8')
    assert '查看详情' in js
    assert '启动 Arthas' not in js
```

- [ ] **Step 2: Run the smoke test and confirm the old AI tab / status actions still leak through**

Run:
```bash
python -m pytest tests/test_connection_page_markup.py -q
```

Expected: FAIL because the old `tab-ai` and action-heavy status bar behavior still exist.

- [ ] **Step 3: Replace the AI tab with a global drawer and simplify the current-connection strip**

Update `static/js/components/page-shell.js` so every page gets the same AI launcher + drawer container:

```javascript
function init({ activeNav, title }) {
  const mount = document.getElementById('pageShell');
  mount.innerHTML = `
    <header class="topbar-shell">...</header>
    <aside id="globalAiDrawer" class="ai-drawer" aria-hidden="true">
      <div class="ai-drawer-hd">
        <span>AI 助手</span>
        <button type="button" onclick="AIChatDrawer.close()">关闭</button>
      </div>
      <div id="aiDrawerMount"></div>
    </aside>
  `;
  document.getElementById('globalAiLauncher').addEventListener('click', AIChatDrawer.open);
}
```

Refactor `static/js/ai-chat.js` so it mounts into `#aiDrawerMount` instead of assuming `tab-ai`/`panel-ai` exist:

```javascript
window.AIChatDrawer = (function () {
  function open() {
    document.getElementById('globalAiDrawer').classList.add('open');
    initAIChat({
      mountId: 'aiDrawerMount',
      connectionProvider: () => getCurrentConnection(),
    });
  }

  function close() {
    document.getElementById('globalAiDrawer').classList.remove('open');
  }

  return { open, close };
})();
```

Then simplify `static/js/components/conn-status-bar.js` so it only reflects context and links to detail:

```javascript
function refresh() {
  const conn = _getCurrentConn();
  if (!conn) {
    _action.style.display = 'none';
    _target.textContent = '— 尚未选择连接';
    return;
  }

  _action.textContent = '查看详情';
  _action.className = 'csb-action csb-action-detail';
  _action.style.display = '';
}

function handleAction() {
  const conn = _getCurrentConn();
  if (conn) {
    window.location.href = `/connection-detail.html?conn=${encodeURIComponent(conn.id)}`;
  }
}
```

- [ ] **Step 4: Run the smoke test and complete a full browser regression pass**

Run:
```bash
python -m pytest tests/test_connection_page_markup.py -q
```

Expected: PASS.

Then run:
```bash
python server.py
```

Manual check:
- AI 助手 can be opened from the list page, detail page, and each work page.
- AI 助手 still works with no current connection selected.
- When a current connection exists, AI uses it automatically.
- The current-connection strip shows connection summary + “查看详情”, but no connect/upgrade/delete controls.
- The old sidebar connection list and old top tab navigation are fully gone.

- [ ] **Step 5: Commit the global AI entry and status-bar cleanup**

```bash
git add tests/test_connection_page_markup.py static/js/components/page-shell.js static/js/ai-chat.js static/js/components/conn-status-bar.js static/index.html static/connection-detail.html static/terminal.html static/monitor.html static/filebrowser.html static/diagnose.html static/arthas-console.html static/profiler.html static/history.html static/css/app.css
git commit -m "feat: add global ai entry and simplify connection status strip"
```

---

## Final Verification Checklist

- [ ] `python -m pytest tests/test_connection_page_routes.py tests/test_connection_page_markup.py -q`
- [ ] `python server.py`
- [ ] Browser smoke test: no connection → connection list → connection detail → Pod-level pages → Arthas upgrade → Arthas-only pages → history → AI drawer from multiple pages.
- [ ] Browser smoke test: refresh on `connection-detail.html?conn=<id>` and `monitor.html?conn=<id>` preserves context.
- [ ] Browser smoke test: deleting a connection from the detail page redirects back to `/index.html` and removes stale context.

## Spec Coverage Check

- **Information architecture adjustment:** Covered by Tasks 1-2 and Task 5.
- **Page split (list/detail/work pages):** Covered by Tasks 2, 4, and 5.
- **Existing connection logic migration:** Covered by Task 3.
- **Two-step connection logic migration:** Covered by Task 4.
- **AI context logic migration to global entry:** Covered by Task 6.
- **Status bar retained with reduced responsibilities:** Covered by Task 6.
- **Low-risk migration order:** Reflected in task order and migration rules.

## Placeholder Scan

- No `TODO`, `TBD`, or “similar to above” placeholders remain.
- Every new file path is explicit.
- Every validation step includes exact commands or manual checks.

Plan complete and saved to `docs/superpowers/plans/2026-04-18-connection-management-implementation-plan.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
