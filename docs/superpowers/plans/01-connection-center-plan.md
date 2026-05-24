# 连接中心实施计划

| 项目 | 内容 |
|---|---|
| 文档状态 | 基于 2026-04-18 连接管理重构实施计划整理 |
| 创建日期 | 2026-05-22 |
| 版本 | v1.0 |
| 状态 | 实施计划 |

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

**文件：**
- 创建：`tests/test_connection_page_routes.py`
- 修改：`server.py:196-231`
- 测试：`tests/test_connection_page_routes.py`

**步骤：**
1. 编写失败的路由冒烟测试
2. 运行测试确认路由缺失
3. 为新页面添加显式 Flask 路由
4. 再次运行路由测试
5. 提交路由基线

### 任务 2：将 `index.html` 重新用作连接管理列表页面

**文件：**
- 创建：`tests/test_connection_page_markup.py`
- 创建：`static/js/page-connection-list.js`
- 修改：`static/index.html:104-220`
- 修改：`static/css/app.css`
- 测试：`tests/test_connection_page_markup.py`

**步骤：**
1. 编写失败的列表页面标记测试
2. 运行标记测试确认旧外壳仍然存在
3. 用列表页面外壳替换旧侧栏 + 顶部标签
4. 再次运行标记测试
5. 提交连接列表页面

### 任务 3：添加共享页面外壳和规范连接页面上下文辅助函数

**文件：**
- 修改：`tests/test_connection_page_markup.py`
- 创建：`static/js/components/page-shell.js`
- 创建：`static/js/components/connection-page-context.js`
- 修改：`static/js/app.js`
- 修改：`static/js/components/connections.js`
- 修改：`static/js/app-ui.js:141-158,1106-1209`
- 测试：`tests/test_connection_page_markup.py`

**步骤：**
1. 扩展共享外壳资产的标记冒烟测试
2. 运行标记测试确认共享辅助函数尚未连接
3. 引入可重用的外壳/上下文辅助函数，并从 `app-ui.js` 中移除重复的连接辅助函数
4. 重新运行标记测试并进行手动导航冒烟检查
5. 提交共享外壳/上下文辅助函数

### 任务 4：构建连接详情页并重构两步连接 UI 以定位它

**文件：**
- 修改：`tests/test_connection_page_markup.py`
- 创建：`static/connection-detail.html`
- 创建：`static/js/page-connection-detail.js`
- 修改：`static/js/components/two-step-connection.js`
- 修改：`static/js/components/connections.js`
- 测试：`tests/test_connection_page_markup.py`

**步骤：**
1. 编写失败的详情页面标记测试
2. 运行标记测试确认页面尚不存在
3. 创建详情页面并使 `two-step-connection.js` DOM 可定位
4. 运行标记测试并手动验证详情生命周期
5. 提交详情页面和两步重构

### 任务 5：将连接范围的工具拆分为独立的工作页面

**文件：**
- 修改：`tests/test_connection_page_markup.py`
- 创建：`static/terminal.html`, `static/monitor.html`, `static/filebrowser.html`, `static/diagnose.html`, `static/arthas-console.html`, `static/profiler.html`, `static/history.html`
- 创建：`static/js/page-workspace.js`, `static/js/page-history.js`
- 修改：`static/js/app-ui.js:1106-1209`, `static/css/app.css`
- 测试：`tests/test_connection_page_markup.py`

**步骤：**
1. 编写失败的工作区页面冒烟测试
2. 运行标记测试确认新页面缺失
3. 创建共享工作区引导并将每个工具移到自己的路由后面
4. 运行标记测试并手动验证逐页导航
5. 提交页面拆分

### 任务 6：将 AI 移至全局抽屉并将状态栏降级为仅轻量上下文

**文件：**
- 修改：`tests/test_connection_page_markup.py`
- 修改：`static/js/components/page-shell.js`, `static/js/ai-chat.js`, `static/js/components/conn-status-bar.js`
- 修改：`static/index.html`, `static/connection-detail.html`, `static/terminal.html`, `static/monitor.html`, `static/filebrowser.html`, `static/diagnose.html`, `static/arthas-console.html`, `static/profiler.html`, `static/history.html`, `static/css/app.css`
- 测试：`tests/test_connection_page_markup.py`

**步骤：**
1. 扩展 AI 启动器和状态栏降级的冒烟测试
2. 运行冒烟测试确认旧 AI 标签/状态操作仍然存在
3. 用全局抽屉替换 AI 标签并简化当前连接条
4. 运行冒烟测试并完成完整浏览器回归
5. 提交全局 AI 入口和状态栏清理

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