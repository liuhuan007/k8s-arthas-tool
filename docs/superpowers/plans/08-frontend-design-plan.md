# 前端设计实施计划

| 项目 | 内容 |
|---|---|
| 文档状态 | 基于 08-frontend-design.md 和 08-frontend-design-detail.md 设计文档整理 |
| 创建日期 | 2026-05-24 |
| 版本 | v1.0 |
| 状态 | 实施计划 |

## 1. 目标

实现前端设计，包括页面结构、组件、交互逻辑、状态管理、响应式设计等。

## 2. 架构

前端采用原生 JavaScript + CSS + HTML 技术栈，不依赖外部框架。采用组件化设计，支持模块化开发和按需加载。

## 3. 页面结构

### 3.1 主要页面

| 页面 | 路径 | 说明 |
|------|------|------|
| 连接列表 | `/` | 连接管理主页 |
| 连接详情 | `/connection-detail.html` | 单连接管理页面 |
| 诊断中心 | `/diagnosis.html` | 诊断能力目录和执行 |
| 任务中心 | `/tasks.html` | 任务日志和调度 |
| 工具箱 | `/toolbox.html` | 工具包管理 |
| AI 助手 | `/ai-assistant.html` | AI 对话界面 |
| 系统管理 | `/admin.html` | 用户、审计、配置 |
| 终端 | `/terminal.html` | Pod 终端交互 |
| 监控 | `/monitor.html` | Pod 监控 |
| 文件浏览器 | `/filebrowser.html` | Pod 文件下载 |
| 性能诊断 | `/diagnose.html` | 性能采样分析 |
| Arthas 控制台 | `/arthas-console.html` | Arthas 命令交互 |
| 采样分析器 | `/profiler.html` | 采样任务管理 |
| 历史记录 | `/history.html` | 全局历史查询 |

### 3.2 页面导航

```
┌─────────────────────────────────────────────────────────────────┐
│                        顶部导航栏                                │
│                                                                 │
│  🏠 首页  │  🔗 连接中心  │  🧠 诊断中心  │  📦 任务中心  │  🛠️ 工具箱  │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                      当前连接上下文                       │   │
│  │  cluster: dev  │  namespace: default  │  pod: my-app-xxx  │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## 4. 组件设计

### 4.1 核心组件

| 组件 | 文件 | 说明 |
|------|------|------|
| 页面外壳 | `static/js/components/page-shell.js` | 共享顶部导航 + 页面标题 |
| 连接上下文 | `static/js/components/connection-page-context.js` | 解析 `?conn=`，加载当前连接 |
| 能力卡片 | `static/js/components/diagnosis.js` | 能力目录展示和执行 |
| 参数表单 | `static/js/components/diagnosis-execution.js` | 动态参数表单生成 |
| 执行进度 | `static/js/components/diagnosis-execution.js` | HTTP 轮询执行进度 |
| 诊断报告 | `static/js/components/diagnosis-history.js` | 报告展示 |
| 执行历史 | `static/js/components/diagnosis-history.js` | 历史记录查询 |
| Agent 对话 | `static/js/components/ai-assistant.js` | 对话界面 |
| 连接状态条 | `static/js/components/conn-status-bar.js` | 轻量级当前上下文条 |

### 4.2 状态管理

| 状态 | 文件 | 说明 |
|------|------|------|
| 连接存储 | `static/js/core/connection-store.js` | 规范连接存储辅助函数 |
| 诊断上下文 | `static/js/core/diagnosis-context.js` | 当前连接上下文、运行中任务索引 |
| 全局状态 | `static/js/app-ui.js` | 全局状态管理 |

## 5. 交互逻辑

### 5.1 连接管理流程

```
用户选择连接 → 连接详情页 → 执行诊断 → 查看结果
      │              │              │              │
      ▼              ▼              ▼              ▼
  连接列表页      连接详情页      诊断执行页      诊断报告页
```

### 5.2 诊断执行流程

```
选择能力 → 填写参数 → 确认执行 → 轮询状态 → 查看结果
    │          │          │          │          │
    ▼          ▼          ▼          ▼          ▼
 能力卡片   参数表单   确认弹窗   进度条     诊断报告
```

### 5.3 实时通信策略

**P0 策略：HTTP 轮询**

| 场景 | 轮询方式 | 间隔 |
|------|---------|------|
| 诊断执行状态 | `GET /api/diagnosis/runs/{run_id}/status` | 2秒 |
| 任务执行状态 | `GET /api/tasks/{task_id}/status` | 3秒 |
| 连接健康检查 | `GET /api/arthas/connections/{id}/health` | 30秒 |

## 6. 响应式设计

### 6.1 断点定义

| 断点 | 宽度 | 设备 |
|------|------|------|
| xs | <576px | 手机 |
| sm | ≥576px | 平板 |
| md | ≥768px | 小桌面 |
| lg | ≥992px | 桌面 |
| xl | ≥1200px | 大桌面 |

### 6.2 布局适配

- **手机**：单列布局，侧边栏折叠
- **平板**：双列布局，侧边栏可收起
- **桌面**：三列布局，侧边栏固定

## 7. 任务分解

### 任务 1：创建页面外壳和导航

**文件：**
- 创建：`static/js/components/page-shell.js`
- 修改：`static/index.html`
- 修改：`static/css/app.css`

**步骤：**
1. 设计页面外壳结构
2. 实现顶部导航栏
3. 实现连接上下文条
4. 实现响应式布局
5. 编写样式

### 任务 2：实现连接列表页

**文件：**
- 修改：`static/index.html`
- 创建：`static/js/page-connection-list.js`
- 修改：`static/css/app.css`

**步骤：**
1. 设计连接列表表格
2. 实现过滤器和搜索
3. 实现表格操作
4. 编写样式

### 任务 3：实现连接详情页

**文件：**
- 创建：`static/connection-detail.html`
- 创建：`static/js/page-connection-detail.js`
- 修改：`static/css/app.css`

**步骤：**
1. 设计连接详情卡片
2. 实现连接生命周期操作
3. 实现工作入口
4. 编写样式

### 任务 4：实现诊断中心页

**文件：**
- 创建：`static/diagnosis.html`
- 创建：`static/js/components/diagnosis.js`
- 创建：`static/js/components/diagnosis-execution.js`
- 修改：`static/css/app.css`

**步骤：**
1. 设计能力卡片布局
2. 实现参数表单组件
3. 实现执行进度组件
4. 实现诊断报告组件
5. 编写样式

### 任务 5：实现任务中心页

**文件：**
- 创建：`static/tasks.html`
- 创建：`static/js/components/task-center.js`
- 修改：`static/css/app.css`

**步骤：**
1. 设计任务列表
2. 实现任务详情
3. 实现任务调度
4. 编写样式

### 任务 6：实现工具箱页

**文件：**
- 创建：`static/toolbox.html`
- 创建：`static/js/components/toolbox.js`
- 修改：`static/css/app.css`

**步骤：**
1. 设计工具包列表
2. 实现工具包详情
3. 实现工具包操作
4. 编写样式

### 任务 7：实现工作页面

**文件：**
- 创建：`static/terminal.html`
- 创建：`static/monitor.html`
- 创建：`static/filebrowser.html`
- 创建：`static/diagnose.html`
- 创建：`static/arthas-console.html`
- 创建：`static/profiler.html`
- 创建：`static/js/page-workspace.js`
- 修改：`static/css/app.css`

**步骤：**
1. 设计工作页面布局
2. 实现共享引导逻辑
3. 实现各工作页面功能
4. 编写样式

### 任务 8：实现全局组件

**文件：**
- 创建：`static/js/components/conn-status-bar.js`
- 创建：`static/js/components/ai-assistant.js`
- 创建：`static/js/core/connection-store.js`
- 创建：`static/js/core/diagnosis-context.js`
- 修改：`static/css/app.css`

**步骤：**
1. 实现连接状态条
2. 实现 AI 助手对话
3. 实现连接存储
4. 实现诊断上下文
5. 编写样式

### 任务 9：实现响应式设计

**文件：**
- 修改：`static/css/app.css`
- 修改：`static/js/components/page-shell.js`

**步骤：**
1. 定义断点
2. 实现响应式布局
3. 实现移动端适配
4. 编写样式

### 任务 10：实现前端测试

**文件：**
- 创建：`tests/test_frontend_components.py`
- 创建：`tests/test_frontend_pages.py`

**步骤：**
1. 编写组件测试
2. 编写页面测试
3. 编写集成测试
4. 验证测试覆盖率

## 8. 验收标准

- [ ] 页面外壳和导航实现完成
- [ ] 连接列表页实现完成
- [ ] 连接详情页实现完成
- [ ] 诊断中心页实现完成
- [ ] 任务中心页实现完成
- [ ] 工具箱页实现完成
- [ ] 工作页面实现完成
- [ ] 全局组件实现完成
- [ ] 响应式设计实现完成
- [ ] 前端测试覆盖率 > 80%

## 9. 风险与缓解措施

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 浏览器兼容性 | 中 | 测试主流浏览器 |
| 性能问题 | 中 | 优化代码，按需加载 |
| 用户体验差 | 中 | 用户反馈，持续优化 |
| 组件复用性低 | 中 | 组件化设计，文档完善 |

## 10. 后续演进

### P1 阶段

- 实现 WebSocket 实时推送
- 实现 PWA 支持
- 实现主题切换

### P2 阶段

- 实现组件库
- 实现微前端架构
- 实现国际化
