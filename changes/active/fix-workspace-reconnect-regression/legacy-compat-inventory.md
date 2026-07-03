# Legacy 兼容层清单

## 目标
- 新工作区（`static/index.html` + `static/js/components/connection-workspace.js`）作为唯一真实状态源。
- 旧页面、旧路由、旧 `panel-*` DOM 本阶段仅保留兼容，不再决定真实连接层级、重连语义或采样可用性。

## 新工作区仍挂载的旧面板

| 兼容面板 | 当前消费者 | 当前用途 | 移除前置条件 |
| --- | --- | --- | --- |
| `panel-monitor` | `ConnectionWorkspace.renderMonitor()` | 承载 Pod 监控面板与监控快照入口 | 监控区改为工作区原生渲染，不再通过 DOM 挪面板 |
| `panel-profiler` | `ConnectionWorkspace.renderBody('sampling')` | 承载采样工具、运行态日志、进度条 | 采样 UI 与历史入口迁入工作区原生组件 |
| `panel-console` | `ConnectionWorkspace.renderBody('console')` | 承载 Arthas 命令台 | 控制台抽成独立工作区组件，不再依赖旧 tab/panel |
| `panel-terminal` | `ConnectionWorkspace.renderBody('terminal')` | 承载 Pod 终端 | 终端容器支持直接挂载到工作区 |
| `panel-filebrowser` | `ConnectionWorkspace.renderBody('files')` | 承载文件浏览/下载 | 文件浏览器支持工作区原生 mount |
| `panel-history` | `ConnectionWorkspace.renderBody('history')` | 承载采样/命令历史 | 历史记录拆出共享组件并支持连接上下文切换 |
| `panel-hotfix` | `ConnectionWorkspace.renderBody('hotfix')` | 承载 jad/mc/redefine 热修复 | 热修复改为工作区原生工具页 |
| `panel-diag` | `ConnectionWorkspace.renderBody('diag')` | 承载诊断中心兼容入口 | 诊断中心完成新工作区嵌入或深链跳转 |

## 仍对外暴露的独立旧页面 / 旧路由

| 路由 | 页面 | 当前消费者 | 移除前置条件 |
| --- | --- | --- | --- |
| `/connections` | `static/connections.html` | 直接书签、旧导航入口 | 提供 `index.html` 新工作区深链并完成重定向 |
| `/workspace` | `static/workspace.html` | 直接书签、旧导航入口 | 新工作区支持同等深链能力并承接旧 hash |
| `/monitor` | `static/monitor.html` | 旧监控直达入口 | 新工作区监控可单独直达，旧链接完成迁移 |
| `/profiler` | `static/profiler.html` | 旧采样直达入口 | 新工作区采样可单独直达，且具备连接守卫 |
| `/history` | `static/history.html` | 历史记录旧入口 | 新历史页或工作区历史支持直达 |
| `/terminal` | `static/terminal.html` | 终端旧入口 | 新工作区终端可深链直达 |
| `/files` | `static/filebrowser.html` | 文件浏览旧入口 | 文件浏览迁入工作区并完成路由替换 |
| `/diagnose` | `static/diagnose.html` | 旧诊断页入口 | 新诊断中心承接旧能力并提供迁移跳转 |
| `/console` | `static/arthas-console.html` | 旧 Arthas 控制台入口 | 新工作区控制台可深链直达 |

## 兼容层依赖结论

1. 新工作区当前最大 legacy 依赖是 `ConnectionWorkspace.renderLegacyFeature()` 对 `panel-*` 的挪挂。
2. 旧页面和旧路由仍然可直接访问，因此还不能删除对应 HTML 文件与服务端 `send_from_directory(...)` 路由。
3. 本次修复后，真实连接层级、重连编排、采样目标与 tab 解析都应回到新工作区与共享连接状态上；旧面板只保留展示容器职责。
