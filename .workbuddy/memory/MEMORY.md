# k8s-arthas-tool 项目记忆

## 项目概述
Flask + 前端单页应用，用于通过 Web UI 管理 K8s 集群并使用 Arthas 诊断 Java 应用。
服务器部署在 Linux (10.101.64.10:5001)，本地开发在 Windows。

## 开发约定
- 静态文件修改后需强制刷新浏览器（Ctrl+Shift+R），否则会加载缓存
- clusters.json 路径在 Linux 服务器上需使用 Linux 格式（/root/.kube/config）
- server.py 用 Flask + flask-cors，支持 CORS
- **使用场景**：多用户并发访问
- **Python 版本约定**：服务器已安装并确认 Python 3.10 可用（2026-04-28 用户反馈）。后续代码检查和开发按 Python 3.10+ 处理，不再为了 Python 3.6 降级语法；可使用 Python 3.10 支持的现代写法。

## 数据存储（SQLite）
- SQLite 数据库文件：`arthas.db`
- 核心表：`connections`、`arthas_command_logs`（原 arthas_commands）、`profiler_tasks`、`profiler_logs`、`audit_logs`、`users`、`user_clusters`
- 诊断中心表：`diagnosis_capabilities`、`arthas_command_templates`、`diagnosis_scenario_steps`、`ai_diagnosis_handlers`
- 任务中心表：`task_definitions`、`task_logs`（原 task_runs，已重命名）、`task_artifacts`、`task_schedules`
- 工具表：`tool_packages`、`script_templates`
- 表结构文档：`docs/superpowers/specs/2026-05-06-architecture-design.md`（综合设计文档）

## 连接中心关键架构
- **两层连接**：PodConnection（kubectl，无需 Arthas）→ ArthasConnection（Arthas Agent + port-forward）
- **连接状态管理**：`backend/core/connection_state.py` 的 ConnectionStateManager，支持 TTL 清理
- **TTL**：`connections.ttl_hours` 字段（0=不过期），每 30 分钟清理；`last_active_at` 在每次执行命令时更新
- **运行时连接池**：`server._connections` 字典（内存），DB 中的 connections 表是元数据
- **前端恢复**：localStorage 保存 `arthas_active_conn` + `arthas_active_level`，刷新页面时调 `_restoreActiveConnection()` 先 Pod 后 Arthas

## 诊断中心关键架构
- **统一执行器**：`backend/core/arthas_executor.py` 的 ArthasCommandExecutor，需要 `connection.http_client.exec_once()`
- **诊断能力执行路径**：`api/task_center.py` → `_get_active_arthas_connection()` → 从 `server._connections` 获取 ArthasConnection
- **诊断历史 API**：`GET /api/tasks/diagnosis/history`（查询 task_logs + 关联 diagnosis_capabilities）
- **诊断取消 API**：`POST /api/tasks/runs/<id>/cancel`（更新 task_logs.status = 'cancelled'）

## UI 标签和布局
- 左侧边栏：集群列表、连接列表（最近切换优先）
- 顶部导航：官方文档、HTTP API、命令手册、历史记录
- 主标签页：Arthas 命令、采样工具、Pod 监控、GC 日志、文件浏览、历史记录、诊断中心(diagnosis-cap)

