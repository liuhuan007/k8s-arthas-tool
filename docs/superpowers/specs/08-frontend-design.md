# K8s Arthas 智能诊断平台 — 前端交互设计


**文档版本**: v1.0
**创建日期**: 2026-05-23
**状态**: 设计完成

---

## 目录

1. [侧边栏菜单结构](#1-侧边栏菜单结构)
2. [诊断中心内部布局](#2-诊断中心内部布局)
3. [连接选择器](#3-连接选择器)
4. [前端状态管理](#4-前端状态管理)
5. [交互式诊断对话](#5-交互式诊断对话)
6. [前端架构设计](#6-前端架构设计)
7. [响应式设计](#7-响应式设计)
8. [性能优化](#8-性能优化)

---

## 1. 侧边栏菜单结构

```html
<div class="side-nav-group">
  <div class="side-nav-group-title">🔗 连接管理</div>
  <button class="side-nav-item" data-tab="connections">连接中心</button>
</div>

<div class="side-nav-group">
  <div class="side-nav-group-title">🧠 诊断</div>
  <button class="side-nav-item" data-tab="diagnosis-center">诊断中心</button>
</div>

<div class="side-nav-group">
  <div class="side-nav-group-title">📦 任务</div>
  <button class="side-nav-item" data-tab="task-center">任务中心</button>
</div>

<div class="side-nav-group">
  <div class="side-nav-group-title">🛠️ 工具箱（仅系统级）</div>
  <button class="side-nav-item" data-tab="toolchain-center">工具包管理</button>
  <button class="side-nav-item" data-tab="tunnel-server">Tunnel Server</button>
</div>

<div class="side-nav-group">
  <div class="side-nav-group-title">🤖 AI</div>
  <button class="side-nav-item" data-tab="ai">AI 助手</button>
</div>

<div class="side-nav-group admin-only">
  <div class="side-nav-group-title">⚙️ 系统</div>
  <button class="side-nav-item" data-tab="user-management">用户管理</button>
  <button class="side-nav-item" data-tab="audit-logs">审计日志</button>
  <button class="side-nav-item" data-tab="model-config">模型配置</button>
  <button class="side-nav-item" data-tab="mcp-center">MCP 接入</button>
</div>

<!-- 注意：连接相关能力（终端、Pod监控、文件下载、采样工具、Arthas命令、在线修复）不在一级菜单中，
     而是作为连接详情页或连接工作页的入口 -->
```

---

## 2. 诊断中心内部布局

```
┌────────────────────────────────────────────────────────────┐
│  🧠 诊断中心                                                │
├────────────────────────────────────────────────────────────┤
│  左侧导航（子菜单）          │  右侧内容区                   │
│  ┌──────────────────┐       │                              │
│  │ ⚡ 快捷工具       │       │  [选中快捷工具时]             │
│  │ 🔍 诊断模板       │  ←─── │  ┌──────────────────────┐   │
│  │ 📋 场景方案       │       │  │ JVM Dashboard        │   │
│  │ 🤖 AI 诊断       │       │  │ [执行] [查看帮助]     │   │
│  │ 🔔 异常告警       │       │  └──────────────────────┘   │
│  │ 📊 执行历史       │       │                              │
│  │ ⚙️ 能力管理       │       │  [选中场景方案时]             │
│  └──────────────────┘       │  ┌──────────────────────┐   │
│                              │  │ 接口响应慢诊断        │   │
│                              │  │ Step1: trace          │   │
│                              │  │ Step2: watch          │   │
│                              │  │ Step3: profiler       │   │
│                              │  │ [执行] [查看帮助]     │   │
│                              │  └──────────────────────┘   │
└────────────────────────────────────────────────────────────┘
```

---

## 3. 连接选择器

诊断中心支持多连接，但一次诊断执行绑定一个明确目标。

| 能力类型 | 连接要求 | 选择器行为 |
|---------|---------|-----------|
| Pod 只读诊断 | `level=pod` 或 `level=arthas` | 展示所有可访问连接 |
| Arthas 命令诊断 | `level=arthas` 且 HTTP Ready | 只展示 Ready 连接；Pod-only 展示"升级" |
| profiler/JFR/dump | Arthas Ready、PID 已确认 | 展示风险和预计耗时 |
| 在线修复/redefine | Arthas Ready + 二次确认 | 强制确认连接摘要 |

**交互规则**：

- 只有一个连接时自动选中，但展示连接信息
- 多个连接时弹出选择器，支持过滤
- 无连接时展示快捷入口
- 执行开始后生成 `run_id` 并固化 `connection_snapshot_json`
- 页面顶部增加"运行中诊断"区域

---

## 4. 前端状态管理

**架构评审改进**：引入 `DiagnosisContext` 管理共享状态。

```javascript
const DiagnosisContext = {
  currentConnection: null,
  activeExecutions: new Map(),  // executionId → {status, capabilityId, startTime}
  listeners: new Set(),

  onConnectionChange(newConn) {
    // 连接切换，取消所有正在执行的诊断
    // 通知所有监听器
  },

  registerExecution(executionId, capabilityId) { ... },
  updateExecution(executionId, status) { ... },
  cancelExecution(executionId) { ... },
};
```

---

## 5. 交互式诊断对话

AI 诊断助手以对话形式引导用户：

```
🤖 AI: 检测到 CPU 使用率异常升高到 95%，是否开始诊断？
👤 用户: 是的
🤖 AI: 正在执行诊断...
     ✅ Step 1: 采集 Dashboard
     ✅ Step 2: 分析线程状态
     ✅ Step 3: Trace 慢方法
     🔍 根因: OrderService.createOrder() 方法慢，置信度 87%
     [查看完整报告] [深入分析] [执行修复]
```

---

## 6. 前端架构设计

### 6.1 技术栈选择

| 技术 | 选择 | 理由 |
|------|------|------|
| 框架 | 原生JavaScript | 保持现有代码库一致性，避免引入新依赖 |
| UI库 | 自定义CSS变量系统 | 与现有暗色主题保持一致 |
| 状态管理 | 自定义EventBus | 轻量级，适合当前规模 |
| 路由 | Hash路由 | 简单可靠，无需后端支持 |
| 实时通信 | HTTP轮询（P0） | P0阶段统一使用轮询，WebSocket作为P2目标态 |

### 6.2 前端目录结构

```
static/
├── js/
│   ├── app.js                    # 主入口
│   ├── router.js                 # 路由管理
│   ├── store.js                  # 状态管理
│   ├── api.js                    # API封装
│   ├── websocket.js              # WebSocket管理
│   ├── components/               # 通用组件
│   │   ├── DiagnosisCard.js      # 诊断卡片
│   │   ├── CommandConsole.js     # 命令控制台
│   │   ├── AnalysisPanel.js      # 分析面板
│   │   ├── ProgressBar.js        # 进度条
│   │   └── Modal.js              # 模态框
│   ├── pages/                    # 页面组件
│   │   ├── Home.js               # 首页
│   │   ├── DiagnosisCenter.js    # 诊断中心
│   │   ├── TaskCenter.js         # 任务中心
│   │   ├── ReportCenter.js       # 报告中心
│   │   ├── KnowledgeBase.js      # 知识库
│   │   └── Settings.js           # 设置
│   └── utils/                    # 工具函数
│       ├── format.js             # 格式化工具
│       ├── validate.js           # 验证工具
│       └── storage.js            # 本地存储
├── css/
│   ├── variables.css             # CSS变量定义
│   ├── base.css                  # 基础样式
│   ├── components.css            # 组件样式
│   └── pages.css                 # 页面样式
└── index.html                    # 主入口页面
```

### 6.3 路由设计

```javascript
// router.js - Hash路由实现
const routes = {
  '/': 'home',
  '/diagnosis': 'diagnosis-center',
  '/diagnosis/:skillId': 'diagnosis-wizard',
  '/diagnosis/:skillId/execute': 'diagnosis-execute',
  '/diagnosis/:skillId/report/:taskId': 'diagnosis-report',
  '/tasks': 'task-center',
  '/tasks/:taskId': 'task-detail',
  '/reports': 'report-center',
  '/reports/:reportId': 'report-detail',
  '/knowledge': 'knowledge-base',
  '/settings': 'settings'
};
```

### 6.4 状态管理

```javascript
// store.js - 简单状态管理
class Store {
  constructor() {
    this.state = {
      user: null,
      connections: [],
      currentConnection: null,
      skills: [],
      tasks: [],
      currentTask: null,
      reports: [],
      loading: false,
      error: null
    };
    
    this.listeners = new Map();
  }
  
  getState() {
    return this.state;
  }
  
  setState(newState) {
    this.state = { ...this.state, ...newState };
    this.notifyListeners();
  }
  
  subscribe(key, callback) {
    if (!this.listeners.has(key)) {
      this.listeners.set(key, []);
    }
    this.listeners.get(key).push(callback);
    
    return () => {
      const callbacks = this.listeners.get(key);
      const index = callbacks.indexOf(callback);
      if (index > -1) {
        callbacks.splice(index, 1);
      }
    };
  }
  
  notifyListeners() {
    for (const [key, callbacks] of this.listeners) {
      if (this.state.hasOwnProperty(key)) {
        callbacks.forEach(callback => callback(this.state[key]));
      }
    }
  }
}
```

### 6.5 WebSocket管理

```javascript
// websocket.js - WebSocket连接管理
class WebSocketManager {
  constructor() {
    this.connections = new Map();
    this.reconnectAttempts = new Map();
    this.maxReconnectAttempts = 5;
  }
  
  connect(taskId, callbacks = {}) {
    const wsUrl = `ws://${window.location.host}/api/diagnosis/stream/${taskId}`;
    
    const ws = new WebSocket(wsUrl);
    
    ws.onopen = () => {
      console.log(`WebSocket connected for task ${taskId}`);
      this.reconnectAttempts.set(taskId, 0);
      callbacks.onOpen?.();
    };
    
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      this.handleMessage(taskId, data, callbacks);
    };
    
    ws.onclose = (event) => {
      console.log(`WebSocket closed for task ${taskId}`);
      this.connections.delete(taskId);
      
      if (!event.wasClean) {
        this.reconnect(taskId, callbacks);
      }
    };
    
    ws.onerror = (error) => {
      console.error(`WebSocket error for task ${taskId}:`, error);
      callbacks.onError?.(error);
    };
    
    this.connections.set(taskId, ws);
    return ws;
  }
  
  handleMessage(taskId, data, callbacks) {
    switch (data.type) {
      case 'command_start':
        callbacks.onCommandStart?.(data);
        break;
      case 'command_output':
        callbacks.onCommandOutput?.(data);
        break;
      case 'command_complete':
        callbacks.onCommandComplete?.(data);
        break;
      case 'llm_analysis':
        callbacks.onLLMAnalysis?.(data);
        break;
      case 'diagnosis_complete':
        callbacks.onDiagnosisComplete?.(data);
        break;
      case 'error':
        callbacks.onError?.(data);
        break;
    }
  }
  
  reconnect(taskId, callbacks) {
    const attempts = this.reconnectAttempts.get(taskId) || 0;
    if (attempts >= this.maxReconnectAttempts) {
      console.log(`Max reconnect attempts reached for task ${taskId}`);
      return;
    }
    
    const delay = Math.pow(2, attempts) * 1000;
    
    setTimeout(() => {
      console.log(`Reconnecting to task ${taskId} (attempt ${attempts + 1})`);
      this.reconnectAttempts.set(taskId, attempts + 1);
      this.connect(taskId, callbacks);
    }, delay);
  }
  
  disconnect(taskId) {
    const ws = this.connections.get(taskId);
    if (ws) {
      ws.close(1000, 'Client disconnect');
      this.connections.delete(taskId);
    }
  }
}
```

### 6.6 API封装

```javascript
// api.js - API请求封装
class API {
  constructor() {
    this.baseUrl = '/api';
    this.credentials = 'include';
  }
  
  async request(endpoint, options = {}) {
    const url = `${this.baseUrl}${endpoint}`;
    
    const config = {
      credentials: this.credentials,
      headers: {
        'Content-Type': 'application/json',
        ...options.headers
      },
      ...options
    };
    
    if (config.body && typeof config.body === 'object') {
      config.body = JSON.stringify(config.body);
    }
    
    try {
      const response = await fetch(url, config);
      
      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.message || `HTTP ${response.status}`);
      }
      
      return await response.json();
    } catch (error) {
      console.error(`API request failed: ${endpoint}`, error);
      throw error;
    }
  }
  
  async getSkills() {
    return this.request('/diagnosis/skills');
  }
  
  async getSkill(skillId) {
    return this.request(`/diagnosis/skills/${skillId}`);
  }
  
  async runDiagnosis(skillId, parameters, connectionId) {
    return this.request('/diagnosis/run', {
      method: 'POST',
      body: { skill_id: skillId, parameters, connection_id: connectionId }
    });
  }
  
  async getTasks(params = {}) {
    const queryString = new URLSearchParams(params).toString();
    return this.request(`/tasks?${queryString}`);
  }
  
  async getTask(taskId) {
    return this.request(`/tasks/${taskId}`);
  }
  
  async cancelTask(taskId) {
    return this.request(`/tasks/${taskId}`, { method: 'DELETE' });
  }
  
  async getReports(params = {}) {
    const queryString = new URLSearchParams(params).toString();
    return this.request(`/reports?${queryString}`);
  }
  
  async getReport(reportId) {
    return this.request(`/reports/${reportId}`);
  }
}
```

---

## 7. 响应式设计

### 7.1 布局系统

```css
/* variables.css - CSS变量定义 */
:root {
  /* 颜色系统 */
  --color-primary: #007AFF;
  --color-success: #34C759;
  --color-warning: #FF9500;
  --color-danger: #FF3B30;
  --color-info: #5AC8FA;
  
  /* 背景色 */
  --bg-primary: #0d1117;
  --bg-secondary: #161b22;
  --bg-tertiary: #21262d;
  
  /* 文本色 */
  --text-primary: #c9d1d9;
  --text-secondary: #8b949e;
  --text-muted: #484f58;
  
  /* 间距 */
  --spacing-xs: 4px;
  --spacing-sm: 8px;
  --spacing-md: 16px;
  --spacing-lg: 24px;
  --spacing-xl: 32px;
  
  /* 圆角 */
  --radius-sm: 4px;
  --radius-md: 8px;
  --radius-lg: 12px;
  
  /* 阴影 */
  --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.3);
  --shadow-md: 0 4px 8px rgba(0, 0, 0, 0.4);
  --shadow-lg: 0 8px 16px rgba(0, 0, 0, 0.5);
  
  /* 断点 */
  --breakpoint-sm: 576px;
  --breakpoint-md: 768px;
  --breakpoint-lg: 992px;
  --breakpoint-xl: 1200px;
}

/* 响应式布局 */
.layout {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}

.layout-content {
  display: flex;
  flex: 1;
}

.layout-sidebar {
  width: 260px;
  background: var(--bg-secondary);
  border-right: 1px solid var(--border-color);
}

.layout-main {
  flex: 1;
  overflow: auto;
  padding: var(--spacing-lg);
}

/* 响应式断点 */
@media (max-width: 768px) {
  .layout-sidebar {
    position: fixed;
    left: -260px;
    top: 0;
    bottom: 0;
    z-index: 1000;
    transition: left 0.3s ease;
  }
  
  .layout-sidebar.open {
    left: 0;
  }
  
  .layout-main {
    padding: var(--spacing-md);
  }
  
  .card-grid {
    grid-template-columns: 1fr;
  }
}

@media (min-width: 769px) and (max-width: 992px) {
  .card-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (min-width: 993px) {
  .card-grid {
    grid-template-columns: repeat(3, 1fr);
  }
}
```

### 7.2 组件样式

```css
/* components.css - 组件样式 */

/* 诊断卡片 */
.diagnosis-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  padding: var(--spacing-lg);
  cursor: pointer;
  transition: all 0.2s ease;
}

.diagnosis-card:hover {
  border-color: var(--color-primary);
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
}

.diagnosis-card.selected {
  border-color: var(--color-primary);
  background: rgba(0, 122, 255, 0.1);
}

/* 命令控制台 */
.command-console {
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.command-console-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-color);
}

.command-console-output {
  padding: var(--spacing-md);
  font-family: var(--font-mono);
  font-size: 13px;
  line-height: 1.5;
  max-height: 400px;
  overflow-y: auto;
}

/* 分析面板 */
.analysis-panel {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  padding: var(--spacing-lg);
}

.analysis-panel-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin-bottom: var(--spacing-md);
  font-weight: 600;
}

.analysis-panel-content {
  margin-bottom: var(--spacing-md);
}

.analysis-panel-suggestions {
  border-top: 1px solid var(--border-color);
  padding-top: var(--spacing-md);
}

/* 进度条 */
.progress-bar {
  height: 8px;
  background: var(--bg-tertiary);
  border-radius: 4px;
  overflow: hidden;
}

.progress-bar-fill {
  height: 100%;
  background: var(--color-primary);
  transition: width 0.3s ease;
}

.progress-bar-fill.success {
  background: var(--color-success);
}

.progress-bar-fill.warning {
  background: var(--color-warning);
}

.progress-bar-fill.danger {
  background: var(--color-danger);
}
```

---

## 8. 性能优化

### 8.1 虚拟滚动

```javascript
// 虚拟滚动实现
class VirtualScroller {
  constructor(container, itemHeight, renderItem) {
    this.container = container;
    this.itemHeight = itemHeight;
    this.renderItem = renderItem;
    this.items = [];
    this.visibleItems = [];
    this.scrollTop = 0;
    
    this.init();
  }
  
  init() {
    this.container.style.overflow = 'auto';
    this.container.addEventListener('scroll', () => this.onScroll());
    
    this.virtualContainer = document.createElement('div');
    this.virtualContainer.className = 'virtual-container';
    this.container.appendChild(this.virtualContainer);
    
    this.contentContainer = document.createElement('div');
    this.contentContainer.className = 'virtual-content';
    this.virtualContainer.appendChild(this.contentContainer);
  }
  
  setItems(items) {
    this.items = items;
    this.virtualContainer.style.height = `${items.length * this.itemHeight}px`;
    this.render();
  }
  
  onScroll() {
    this.scrollTop = this.container.scrollTop;
    this.render();
  }
  
  render() {
    const startIndex = Math.floor(this.scrollTop / this.itemHeight);
    const endIndex = Math.min(
      startIndex + Math.ceil(this.container.clientHeight / this.itemHeight) + 1,
      this.items.length
    );
    
    this.visibleItems = this.items.slice(startIndex, endIndex);
    
    this.contentContainer.style.transform = `translateY(${startIndex * this.itemHeight}px)`;
    this.contentContainer.innerHTML = this.visibleItems
      .map(item => this.renderItem(item))
      .join('');
  }
}
```

### 8.2 防抖和节流

```javascript
// 防抖函数
function debounce(func, wait) {
  let timeout;
  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout);
      func(...args);
    };
    clearTimeout(timeout);
    timeout = setTimeout(later, wait);
  };
}

// 节流函数
function throttle(func, limit) {
  let inThrottle;
  return function executedFunction(...args) {
    if (!inThrottle) {
      func(...args);
      inThrottle = true;
      setTimeout(() => inThrottle = false, limit);
    }
  };
}
```

---

**文档结束**