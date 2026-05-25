# 连接中心实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将侧栏中心化连接工作流替换为专用连接管理流程（列表 → 详情 → 工作页），保持跨页面可复用的连接状态，保留轻量级当前连接条，并将 AI 移至全局入口。

**Architecture:** 保持现有的 Flask + 静态 HTML + 原生 JS 技术栈。复用 `static/js/components/connections.js` 作为规范连接存储，重构 `static/js/components/two-step-connection.js` 使其能驱动新详情页和现有共享操作，并通过查询字符串连接上下文（`?conn=<id>`）进行页面间导航。

**Tech Stack:** Flask, 静态 HTML, 原生 JavaScript, 现有 `static/js/components/*`, `static/css/app.css`, pytest 用于路由/标记冒烟测试。

---

## 1. 目标

将侧栏中心化连接工作流替换为专用连接管理流程（列表 → 详情 → 工作页），保持跨页面可复用的连接状态，保留轻量级当前连接条，并将 AI 移至全局入口。

## 2. 架构

保持现有的 Flask + 静态 HTML + 原生 JS 技术栈。复用 `static/js/components/connections.js` 作为规范连接存储，重构 `static/js/components/two-step-connection.js` 使其能驱动新详情页和现有共享操作，并通过查询字符串连接上下文（`?conn=<id>`）进行页面间导航。

## 3. 技术栈

Flask, 静态 HTML, 原生 JavaScript, 现有 `static/js/components/*`, `static/css/app.css`, pytest 用于路由/标记冒烟测试。

## 4. 迁移规则

1. **重用 `index.html` 而不是创建新的主页路由。** `index.html` 成为连接管理页面，使 `/` 继续工作。
2. **在删除旧行为前引入新页面。** 路由测试、页面外壳和详情/工作页面首先落地。
3. **在移动 UI 前移动共享状态。** 规范辅助函数位于 `connections.js` + `connection-page-context.js`；页面代码从中读取。
4. **保留当前连接条，但缩小其职责。** 不在其中执行连接/升级/删除操作；详情页拥有这些操作。
5. **将 AI 视为全局 UI。** 从任何页面打开，可以在没有连接的情况下工作，并在存在 Pod/Arthas 上下文时深化。

## 5. 文件结构

### 5.1 创建新文件

- `tests/test_connection_page_routes.py` - 新页面的路由冒烟测试
- `tests/test_connection_page_markup.py` - 迁移期间静态 HTML/JS 外壳形状的冒烟测试
- `static/connection-detail.html` - 单连接管理页面
- `static/terminal.html` - 终端工作页面
- `static/monitor.html` - Pod 监控工作页面
- `static/filebrowser.html` - 文件下载工作页面
- `static/diagnose.html` - 性能诊断工作页面
- `static/arthas-console.html` - Arthas 命令工作页面
- `static/profiler.html` - 采样/分析器工作页面
- `static/history.html` - 全局历史页面（从旧顶部标签栏移出）
- `static/js/components/page-shell.js` - 共享顶部导航 + 页面标题 + 全局 AI 启动器/抽屉挂载
- `static/js/components/connection-page-context.js` - 解析 `?conn=`，加载当前连接，并在详情/工作页面间导航
- `static/js/page-connection-list.js` - 连接列表表格渲染、过滤器、表格操作
- `static/js/page-connection-detail.js` - 详情页渲染 + 生命周期操作连接
- `static/js/page-history.js` - 历史页面引导
- `static/js/page-workspace.js` - 终端/监控/文件浏览器/诊断/Arthas 控制台/分析器页面的共享引导

### 5.2 修改现有文件

- `server.py` - 注册新页面路由
- `static/index.html` - 从旧工作区外壳重新用作连接管理列表页面
- `static/css/app.css` - 添加页面外壳、表格、详情卡片、工作入口、抽屉和轻量上下文条样式
- `static/js/app.js` - 在 `window.App` 上公开新的页面上下文辅助函数
- `static/js/app-ui.js` - 移除重复的连接辅助逻辑，停止假设一个标签页式大型页面是主要 UX
- `static/js/components/connections.js` - 保留规范连接存储辅助函数并分发页面安全的连接更改事件
- `static/js/components/two-step-connection.js` - 使 DOM 目标可配置，以便相同的生命周期逻辑可以驱动详情页
- `static/js/components/conn-status-bar.js` - 降级为轻量级当前上下文条，带有"查看详情"操作而非连接/升级操作
- `static/js/ai-chat.js` - 挂载到全局抽屉而非旧的顶级 `tab-ai` 面板，同时保持连接感知

## 6. 任务分解

### 任务 1：注册新页面路由

**Files:**
- Create: `tests/test_connection_page_routes.py`
- Modify: `server.py:196-231`
- Test: `tests/test_connection_page_routes.py`

**Step 1: Write the failing test**

```python
# tests/test_connection_page_routes.py

import pytest
from server import app

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_connection_detail_route_exists(client):
    """Test that /connection-detail route exists"""
    response = client.get('/connection-detail')
    assert response.status_code == 200

def test_terminal_route_exists(client):
    """Test that /terminal route exists"""
    response = client.get('/terminal')
    assert response.status_code == 200

def test_monitor_route_exists(client):
    """Test that /monitor route exists"""
    response = client.get('/monitor')
    assert response.status_code == 200
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_connection_page_routes.py -v`
Expected: FAIL with "404 NOT FOUND"

**Step 3: Write minimal implementation**

```python
# server.py:196-231

@app.route('/connection-detail')
@login_required
def connection_detail_page():
    return send_from_directory('static', 'connection-detail.html')

@app.route('/terminal')
@login_required
def terminal_page():
    return send_from_directory('static', 'terminal.html')

@app.route('/monitor')
@login_required
def monitor_page():
    return send_from_directory('static', 'monitor.html')
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_connection_page_routes.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_connection_page_routes.py server.py
git commit -m "feat: add new page routes for connection management"
```

### 任务 2：将 `index.html` 重新用作连接管理列表页面

**Files:**
- Create: `tests/test_connection_page_markup.py`
- Create: `static/js/page-connection-list.js`
- Modify: `static/index.html:104-220`
- Modify: `static/css/app.css`
- Test: `tests/test_connection_page_markup.py`

**Step 1: Write the failing test**

```python
# tests/test_connection_page_markup.py

import pytest
from server import app

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_index_page_has_connection_list_structure(client):
    """Test that index.html has connection list structure"""
    response = client.get('/')
    assert response.status_code == 200
    html = response.data.decode()
    assert 'connection-list-container' in html
    assert 'connection-table' in html
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_connection_page_markup.py -v`
Expected: FAIL with "connection-list-container not found"

**Step 3: Write minimal implementation**

```html
<!-- static/index.html:104-220 -->
<div id="connection-list-container">
    <div class="connection-list-header">
        <h2>连接管理</h2>
        <button id="add-connection-btn" class="btn btn-primary">添加连接</button>
    </div>
    <table id="connection-table" class="table">
        <thead>
            <tr>
                <th>集群</th>
                <th>命名空间</th>
                <th>Pod</th>
                <th>状态</th>
                <th>操作</th>
            </tr>
        </thead>
        <tbody id="connection-table-body">
            <!-- 动态填充 -->
        </tbody>
    </table>
</div>
```

```javascript
// static/js/page-connection-list.js

class ConnectionListPage {
    constructor() {
        this.init();
    }
    
    init() {
        this.loadConnections();
        this.bindEvents();
    }
    
    loadConnections() {
        // 加载连接列表
    }
    
    bindEvents() {
        // 绑定事件
    }
}
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_connection_page_markup.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_connection_page_markup.py static/index.html static/js/page-connection-list.js
git commit -m "feat: convert index.html to connection list page"
```

### 任务 3：添加共享页面外壳和规范连接页面上下文辅助函数

**Files:**
- Modify: `tests/test_connection_page_markup.py`
- Create: `static/js/components/page-shell.js`
- Create: `static/js/components/connection-page-context.js`
- Modify: `static/js/app.js`
- Modify: `static/js/components/connections.js`
- Modify: `static/js/app-ui.js:141-158,1106-1209`
- Test: `tests/test_connection_page_markup.py`

**Step 1: Write the failing test**

```python
# tests/test_connection_page_markup.py (extend)

def test_page_shell_component_exists(client):
    """Test that page-shell.js is loaded"""
    response = client.get('/')
    html = response.data.decode()
    assert 'page-shell.js' in html

def test_connection_page_context_component_exists(client):
    """Test that connection-page-context.js is loaded"""
    response = client.get('/connection-detail')
    html = response.data.decode()
    assert 'connection-page-context.js' in html
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_connection_page_markup.py -v`
Expected: FAIL with "page-shell.js not found"

**Step 3: Write minimal implementation**

```javascript
// static/js/components/page-shell.js

class PageShell {
    constructor() {
        this.init();
    }
    
    init() {
        this.renderHeader();
        this.renderAIButton();
    }
    
    renderHeader() {
        const header = document.createElement('header');
        header.className = 'page-header';
        header.innerHTML = `
            <div class="header-left">
                <h1 class="page-title">K8s Arthas Tool</h1>
            </div>
            <div class="header-right">
                <button id="ai-drawer-btn" class="btn btn-icon">AI</button>
            </div>
        `;
        document.body.prepend(header);
    }
    
    renderAIButton() {
        // AI 按钮逻辑
    }
}
```

```javascript
// static/js/components/connection-page-context.js

class ConnectionPageContext {
    constructor() {
        this.connectionId = null;
        this.init();
    }
    
    init() {
        this.parseQueryString();
        this.loadConnection();
    }
    
    parseQueryString() {
        const params = new URLSearchParams(window.location.search);
        this.connectionId = params.get('conn');
    }
    
    loadConnection() {
        if (this.connectionId) {
            // 加载连接信息
        }
    }
}
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_connection_page_markup.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add static/js/components/page-shell.js static/js/components/connection-page-context.js
git commit -m "feat: add shared page shell and connection context components"
```

### 任务 4：构建连接详情页并重构两步连接 UI 以定位它

**Files:**
- Modify: `tests/test_connection_page_markup.py`
- Create: `static/connection-detail.html`
- Create: `static/js/page-connection-detail.js`
- Modify: `static/js/components/two-step-connection.js`
- Modify: `static/js/components/connections.js`
- Test: `tests/test_connection_page_markup.py`

**Step 1: Write the failing test**

```python
# tests/test_connection_page_markup.py (extend)

def test_connection_detail_page_exists(client):
    """Test that connection-detail.html exists"""
    response = client.get('/connection-detail')
    assert response.status_code == 200
    html = response.data.decode()
    assert 'connection-detail-container' in html

def test_two_step_connection_dom_target(client):
    """Test that two-step-connection.js has configurable DOM target"""
    response = client.get('/connection-detail')
    html = response.data.decode()
    assert 'two-step-connection.js' in html
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_connection_page_markup.py -v`
Expected: FAIL with "connection-detail-container not found"

**Step 3: Write minimal implementation**

```html
<!-- static/connection-detail.html -->

<!DOCTYPE html>
<html>
<head>
    <title>连接详情</title>
    <link rel="stylesheet" href="/static/css/app.css">
</head>
<body>
    <div id="connection-detail-container">
        <div class="connection-detail-header">
            <h2>连接详情</h2>
            <button id="back-btn" class="btn btn-secondary">返回</button>
        </div>
        <div id="connection-info" class="connection-info">
            <!-- 连接信息 -->
        </div>
        <div id="two-step-connection-container">
            <!-- 两步连接 UI -->
        </div>
    </div>
    <script src="/static/js/components/page-shell.js"></script>
    <script src="/static/js/components/connection-page-context.js"></script>
    <script src="/static/js/components/two-step-connection.js"></script>
    <script src="/static/js/page-connection-detail.js"></script>
</body>
</html>
```

```javascript
// static/js/page-connection-detail.js

class ConnectionDetailPage {
    constructor() {
        this.connectionId = null;
        this.init();
    }
    
    init() {
        this.parseQueryString();
        this.loadConnection();
        this.initTwoStepConnection();
    }
    
    parseQueryString() {
        const params = new URLSearchParams(window.location.search);
        this.connectionId = params.get('conn');
    }
    
    loadConnection() {
        if (this.connectionId) {
            // 加载连接信息
        }
    }
    
    initTwoStepConnection() {
        // 初始化两步连接 UI
        const container = document.getElementById('two-step-connection-container');
        if (container) {
            // 配置 DOM 目标
        }
    }
}
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_connection_page_markup.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add static/connection-detail.html static/js/page-connection-detail.js
git commit -m "feat: add connection detail page with two-step connection UI"
```

### 任务 5：将连接范围的工具拆分为独立的工作页面

**Files:**
- Modify: `tests/test_connection_page_markup.py`
- Create: `static/terminal.html`, `static/monitor.html`, `static/filebrowser.html`, `static/diagnose.html`, `static/arthas-console.html`, `static/profiler.html`, `static/history.html`
- Create: `static/js/page-workspace.js`, `static/js/page-history.js`
- Modify: `static/js/app-ui.js:1106-1209`, `static/css/app.css`
- Test: `tests/test_connection_page_markup.py`

**Step 1: Write the failing test**

```python
# tests/test_connection_page_markup.py (extend)

def test_workspace_pages_exist(client):
    """Test that all workspace pages exist"""
    pages = ['/terminal', '/monitor', '/filebrowser', '/diagnose', '/arthas-console', '/profiler', '/history']
    for page in pages:
        response = client.get(page)
        assert response.status_code == 200
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_connection_page_markup.py -v`
Expected: FAIL with "404 NOT FOUND"

**Step 3: Write minimal implementation**

```html
<!-- static/terminal.html -->
<!DOCTYPE html>
<html>
<head>
    <title>终端</title>
    <link rel="stylesheet" href="/static/css/app.css">
</head>
<body>
    <div id="terminal-container">
        <div class="terminal-header">
            <h2>终端</h2>
            <button id="back-btn" class="btn btn-secondary">返回</button>
        </div>
        <div id="terminal-content">
            <!-- 终端内容 -->
        </div>
    </div>
    <script src="/static/js/components/page-shell.js"></script>
    <script src="/static/js/components/connection-page-context.js"></script>
    <script src="/static/js/page-workspace.js"></script>
</body>
</html>
```

```javascript
// static/js/page-workspace.js

class WorkspacePage {
    constructor() {
        this.connectionId = null;
        this.init();
    }
    
    init() {
        this.parseQueryString();
        this.loadConnection();
        this.initWorkspace();
    }
    
    parseQueryString() {
        const params = new URLSearchParams(window.location.search);
        this.connectionId = params.get('conn');
    }
    
    loadConnection() {
        if (this.connectionId) {
            // 加载连接信息
        }
    }
    
    initWorkspace() {
        // 初始化工作区
    }
}
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_connection_page_markup.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add static/terminal.html static/monitor.html static/filebrowser.html static/diagnose.html static/arthas-console.html static/profiler.html static/history.html static/js/page-workspace.js static/js/page-history.js
git commit -m "feat: split workspace into separate pages"
```

### 任务 6：将 AI 移至全局抽屉并将状态栏降级为仅轻量上下文

**Files:**
- Modify: `tests/test_connection_page_markup.py`
- Modify: `static/js/components/page-shell.js`, `static/js/ai-chat.js`, `static/js/components/conn-status-bar.js`
- Modify: `static/index.html`, `static/connection-detail.html`, `static/terminal.html`, `static/monitor.html`, `static/filebrowser.html`, `static/diagnose.html`, `static/arthas-console.html`, `static/profiler.html`, `static/history.html`, `static/css/app.css`
- Test: `tests/test_connection_page_markup.py`

**Step 1: Write the failing test**

```python
# tests/test_connection_page_markup.py (extend)

def test_ai_drawer_exists(client):
    """Test that AI drawer exists in all pages"""
    pages = ['/', '/connection-detail', '/terminal', '/monitor', '/filebrowser', '/diagnose', '/arthas-console', '/profiler', '/history']
    for page in pages:
        response = client.get(page)
        html = response.data.decode()
        assert 'ai-drawer' in html
        assert 'ai-drawer-btn' in html

def test_status_bar_is_lightweight(client):
    """Test that status bar is lightweight"""
    response = client.get('/')
    html = response.data.decode()
    assert 'conn-status-bar' in html
    assert '查看详情' in html
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_connection_page_markup.py -v`
Expected: FAIL with "ai-drawer not found"

**Step 3: Write minimal implementation**

```javascript
// static/js/components/page-shell.js (update)

class PageShell {
    constructor() {
        this.init();
    }
    
    init() {
        this.renderHeader();
        this.renderAIDrawer();
        this.renderStatusBar();
    }
    
    renderHeader() {
        const header = document.createElement('header');
        header.className = 'page-header';
        header.innerHTML = `
            <div class="header-left">
                <h1 class="page-title">K8s Arthas Tool</h1>
            </div>
            <div class="header-right">
                <button id="ai-drawer-btn" class="btn btn-icon">AI</button>
            </div>
        `;
        document.body.prepend(header);
    }
    
    renderAIDrawer() {
        const drawer = document.createElement('div');
        drawer.id = 'ai-drawer';
        drawer.className = 'ai-drawer hidden';
        drawer.innerHTML = `
            <div class="ai-drawer-header">
                <h3>AI 助手</h3>
                <button id="close-ai-drawer" class="btn btn-icon">×</button>
            </div>
            <div class="ai-drawer-content">
                <!-- AI 内容 -->
            </div>
        `;
        document.body.appendChild(drawer);
    }
    
    renderStatusBar() {
        const statusBar = document.createElement('div');
        statusBar.id = 'conn-status-bar';
        statusBar.className = 'conn-status-bar';
        statusBar.innerHTML = `
            <div class="status-bar-content">
                <span class="connection-info">未连接</span>
                <button id="view-detail-btn" class="btn btn-link">查看详情</button>
            </div>
        `;
        document.body.appendChild(statusBar);
    }
}
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_connection_page_markup.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add static/js/components/page-shell.js static/js/ai-chat.js static/js/components/conn-status-bar.js
git commit -m "feat: move AI to global drawer and simplify status bar"
```

## 7. 最终验证清单

- [ ] `python -m pytest tests/test_connection_page_routes.py tests/test_connection_page_markup.py -q`
- [ ] `python server.py`
- [ ] 浏览器冒烟测试：无连接 → 连接列表 → 连接详情 → Pod 级别页面 → Arthas 升级 → Arthas 专属页面 → 历史 → 多个页面的 AI 抽屉
- [ ] 浏览器冒烟测试：刷新 `connection-detail.html?conn=<id>` 和 `monitor.html?conn=<id>` 保留上下文
- [ ] 浏览器冒烟测试：从详情页删除连接会重定向回 `/index.html` 并移除过时上下文

## 8. 规范覆盖检查

- **信息架构调整：** 由任务 1-2 和任务 5 覆盖
- **页面拆分（列表/详情/工作页面）：** 由任务 2、4 和 5 覆盖
- **现有连接逻辑迁移：** 由任务 3 覆盖
- **两步连接逻辑迁移：** 由任务 4 覆盖
- **AI 上下文逻辑迁移到全局入口：** 由任务 6 覆盖
- **状态栏保留但职责减少：** 由任务 6 覆盖
- **低风险迁移顺序：** 反映在任务顺序和迁移规则中

## 9. 执行选项

**1. 子代理驱动（推荐）** - 每个任务分派一个新的子代理，任务之间进行审查，快速迭代

**2. 内联执行** - 使用 executing-plans 在此会话中执行任务，批量执行并设置检查点