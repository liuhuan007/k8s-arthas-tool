# 任务中心重新设计 — Scheduler 模块

**版本**: v1.0 | **日期**: 2026-06-07 | **状态**: 已确认

## 1. 概述

### 1.1 核心定位

任务中心重新定位为**定时任务 + 系统任务 + 自定义脚本执行平台**，支持在 Pod 或 Node 上运行监控脚本/运维工具（如 k8s_scan），支持 Cron/间隔调度。

与现有诊断中心完全解耦：诊断中心负责 JVM 深度诊断（Arthas 命令、场景方案、AI 诊断），任务中心负责脚本执行和定时调度。

### 1.2 设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 架构方案 | B. 独立重建 | 干净模块边界，零历史包袱 |
| 工具分发 | 与执行分离 | 工具箱管分发，任务中心管调度执行 |
| 调度能力 | Cron + 间隔 | 覆盖运维常见场景 |
| 与诊断关系 | 完全分离 | 各自独立 API、独立数据表 |
| 脚本管理 | 在线编写 + 上传 | 灵活度最高 |
| 旧数据迁移 | 不迁移 | 全新起步 |

## 2. 模块架构

### 2.1 项目结构

```
├── api/
│   ├── task_center.py          # 保留，仅供诊断中心使用
│   └── scheduler.py            # 新增，任务中心专属
├── services/
│   └── scheduler_service.py    # 新增，调度引擎核心逻辑
└── static/js/components/
    └── scheduler.js            # 新增，前端组件
```

### 2.2 API 设计

前缀：`/api/scheduler/`，与 `/api/tasks/`（诊断）零耦合。

**任务管理**

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/scheduler/tasks` | 任务列表（支持筛选/分页） |
| POST | `/api/scheduler/tasks` | 创建任务（在线脚本 or 上传文件） |
| GET | `/api/scheduler/tasks/<id>` | 任务详情 |
| PUT | `/api/scheduler/tasks/<id>` | 编辑任务 |
| DELETE | `/api/scheduler/tasks/<id>` | 删除任务 |

**执行管理**

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/scheduler/tasks/<id>/run` | 手动触发执行（单目标） |
| POST | `/api/scheduler/tasks/<id>/run-batch` | 批量执行（按 NS / Pod 列表） |
| POST | `/api/scheduler/logs/<id>/cancel` | 取消执行 |
| GET | `/api/scheduler/logs` | 执行日志列表 |
| GET | `/api/scheduler/logs/<id>` | 执行日志详情（含 stdout/stderr） |
| GET | `/api/scheduler/logs/export` | 导出执行日志（JSON/CSV/TXT） |

**调度管理**

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/scheduler/schedules` | 调度列表 |
| POST | `/api/scheduler/schedules` | 创建调度（cron/interval） |
| PUT | `/api/scheduler/schedules/<id>` | 修改/暂停/恢复 |
| DELETE | `/api/scheduler/schedules/<id>` | 删除调度 |

**文件上传**

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/scheduler/upload` | 上传脚本/二进制文件 |

### 2.3 模块边界

- **诊断中心** → 继续用 `/api/tasks/`，不动
- **工具箱** → 继续用 `/api/tasks/tool-packages/`，不动
- **任务中心（新）** → 全部走 `/api/scheduler/`
- **告警中心** → 任务失败时通过现有告警模块发通知

## 3. 数据模型

3 张核心表，存于同一 SQLite 数据库。

### 3.1 scheduler_tasks（任务定义）

```sql
CREATE TABLE scheduler_tasks (
    id TEXT PRIMARY KEY,              -- UUID
    name TEXT NOT NULL,               -- 任务名称
    description TEXT,                 -- 说明

    -- 脚本来源
    script_source TEXT NOT NULL,      -- 'inline' | 'upload' | 'path'
    script_body TEXT,                 -- 内联脚本内容（inline 时用）
    script_path TEXT,                 -- 上传文件路径（upload）或 Pod 内绝对路径（path）
    runtime TEXT NOT NULL,            -- 'shell' | 'python' | 'binary'

    -- 执行目标
    target_type TEXT NOT NULL,        -- 'node' | 'pod' | 'pods' | 'namespace'
    target_config TEXT,               -- JSON: {"cluster":"","namespace":"","pod":"","pods":[],"container":""}

    -- 参数
    timeout_seconds INTEGER DEFAULT 300,
    env_vars TEXT,                    -- JSON: {"KEY":"VAL"}
    params_schema TEXT,               -- JSON: 参数定义（模板化时用）

    -- 告警
    alert_on_failure INTEGER DEFAULT 0,  -- 失败时是否告警

    -- 元数据
    status TEXT DEFAULT 'active',     -- 'active' | 'disabled'
    created_by TEXT,
    created_at TEXT,
    updated_at TEXT
);
```

### 3.2 scheduler_logs（执行日志）

```sql
CREATE TABLE scheduler_logs (
    id TEXT PRIMARY KEY,              -- UUID
    task_id TEXT NOT NULL,            -- FK → scheduler_tasks
    schedule_id TEXT,                 -- FK → scheduler_schedules（手动执行时为 NULL）

    -- 目标快照（执行时锁定）
    target_snapshot TEXT,             -- JSON: 实际执行时的集群/NS/Pod/容器
    connection_id TEXT,               -- 关联连接 ID（Pod 模式时用）

    -- 执行结果
    status TEXT DEFAULT 'pending',    -- 'pending' | 'running' | 'success' | 'failed' | 'cancelled'
    exit_code INTEGER,
    stdout TEXT,
    stderr TEXT,
    duration_ms INTEGER,

    -- 触发信息
    trigger_type TEXT,                -- 'manual' | 'scheduled' | 'retry'

    -- 时间
    started_at TEXT,
    finished_at TEXT,
    created_at TEXT
);
```

### 3.3 scheduler_schedules（调度配置）

```sql
CREATE TABLE scheduler_schedules (
    id TEXT PRIMARY KEY,              -- UUID
    task_id TEXT NOT NULL,            -- FK → scheduler_tasks
    name TEXT,                        -- 调度名称

    -- 调度类型
    schedule_type TEXT NOT NULL,      -- 'cron' | 'interval'
    cron_expr TEXT,                   -- Cron 表达式（如 "0 */2 * * *"）
    interval_seconds INTEGER,        -- 间隔秒数（如 300）

    -- 状态
    status TEXT DEFAULT 'active',     -- 'active' | 'paused'
    last_run_at TEXT,
    next_run_at TEXT,

    -- 元数据
    created_by TEXT,
    created_at TEXT,
    updated_at TEXT
);
```

**设计要点**：

1. **批量执行 = 多条 log 记录**：一次"按 Namespace 批量"执行，每个 Pod 产生独立 log，可单独查看/取消
2. **target_config 是灵活 JSON**：不同 target_type 填不同字段，避免多列稀疏
3. **script_source 三种模式**：inline（在线编写）、upload（上传文件）、path（引用已分发工具路径）
4. **env_vars 支持环境变量注入**：脚本执行时传入

## 4. 调度引擎

### 4.1 架构

```
┌─────────────────────────────────────────────────────┐
│              scheduler_service.py                     │
├─────────────────────────────────────────────────────┤
│                                                       │
│  ┌──────────────┐     ┌──────────────────────────┐   │
│  │ SchedulerLoop│     │     TaskExecutor          │   │
│  │ (后台线程)    │     │     (执行引擎)            │   │
│  │              │     │                          │   │
│  │ 每 30s 检查  │────▶│ Node 模式:               │   │
│  │ next_run_at  │     │   subprocess.Popen()     │   │
│  │ 到期的调度   │     │   本机执行脚本/二进制     │   │
│  │              │     │                          │   │
│  │ Cron 解析:   │     │ Pod 模式:                │   │
│  │ croniter库   │     │   kubectl exec 执行      │   │
│  │ 计算下次时间 │     │   单Pod / 批量 / NS全量  │   │
│  └──────────────┘     │                          │   │
│                       │ 批量执行:                 │   │
│  ┌──────────────┐     │   列出目标 Pod 列表      │   │
│  │ CronParser   │     │   每 Pod 创建一条 run    │   │
│  │ croniter     │     │   并行执行(ThreadPool)   │   │
│  └──────────────┘     └──────────────────────────┘   │
│                                                       │
│  ┌──────────────────────────────────────────────┐    │
│  │ AlertBridge (告警桥接)                        │    │
│  │ 执行失败 → 调用现有告警中心 API 发送通知      │    │
│  └──────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────┘
```

### 4.2 关键技术选型

| 决策 | 选择 | 理由 |
|------|------|------|
| Cron 解析库 | `croniter` | Python 生态最成熟，支持标准 5 段 Cron |
| 调度循环间隔 | 30 秒 | 平衡精度与负载，Cron 最细粒度通常为分钟级 |
| Node 执行方式 | `subprocess.Popen` | 非阻塞，支持超时 kill，捕获 stdout/stderr |
| Pod 执行方式 | `kubectl exec` | 复用现有 KubectlExecutor 基础能力 |
| 批量并发度 | `ThreadPoolExecutor(max_workers=5)` | 避免大量并发 kubectl 导致 API Server 压力 |
| 超时处理 | `subprocess + timeout` | Node: Popen timeout; Pod: 后台线程跟踪 |
| 失败告警 | 桥接现有告警模块 | 不自建通知通道，复用 `/api/alerts/` |

### 4.3 调度循环伪代码

```python
def scheduler_loop():
    while True:
        now = datetime.utcnow()
        due = db.query("SELECT * FROM scheduler_schedules WHERE status='active' AND next_run_at <= ?", now)
        for schedule in due:
            task = db.get_task(schedule.task_id)
            if task.status != 'active':
                continue
            if schedule.schedule_type == 'cron':
                next_time = croniter(schedule.cron_expr, now).get_next()
            else:
                next_time = now + timedelta(seconds=schedule.interval_seconds)
            schedule.next_run_at = next_time
            schedule.last_run_at = now
            db.update_schedule(schedule)
            execute_task(task, trigger='scheduled', schedule_id=schedule.id)
        sleep(30)
```

### 4.4 执行流程

**Node 模式**：
1. 创建 scheduler_log 记录（status=pending）
2. `subprocess.Popen(script, env=env_vars, stdout=PIPE, stderr=PIPE)`
3. 更新 status=running, started_at
4. 等待完成或超时 kill
5. 记录 exit_code, stdout, stderr, duration_ms
6. status=success/failed
7. 如果 failed 且 task.alert_on_failure → 调用告警 API

**Pod 模式（单 Pod）**：
1. 创建 scheduler_log 记录
2. `kubectl exec {pod} -- {script}` （通过 KubectlExecutor）
3. 同 Node 模式步骤 3-7

**批量模式（按 NS / Pod 列表）**：
1. 列出目标 Pod 列表
2. 为每个 Pod 创建独立的 scheduler_log 记录
3. `ThreadPoolExecutor(max_workers=5)` 并行执行
4. 每条 log 独立记录结果

## 5. 前端设计

### 5.1 导航

侧边栏"任务"分组下，仅一个入口"📦 任务中心"。

### 5.2 四个子面板

| 面板 | 图标 | 核心内容 |
|------|------|---------|
| 任务列表 | 📋 | 卡片式任务列表，名称+类型标签+调度状态+上次执行结果 |
| 调度管理 | ⏱ | 调度列表，Cron/间隔配置，暂停/恢复 |
| 执行日志 | 📊 | 表格式日志，展开行显示 stdout/stderr |
| 脚本库 | 📁 | 可复用脚本模板，在线编写/上传文件 |

### 5.3 任务卡片设计

每张任务卡片包含：
- **标题行**：任务名 + 运行时标签(SHELL/PYTHON/BINARY) + 执行目标标签(NODE/POD/批量) + 调度标签(Cron/间隔)
- **状态**：上次执行结果（成功/失败/无记录）
- **描述**：一行任务说明
- **操作按钮**：立即执行 / 编辑 / 查看记录

### 5.4 任务创建流程（3 步向导）

**Step 1 — 基本信息 + 执行目标**：
- 任务名称（必填）
- 说明
- 运行时：Shell / Python / Binary
- 执行目标：Node 本机 / 指定 Pod / 批量 Pod / 按 Namespace
- 超时时间（1~3600 秒）

**Step 2 — 脚本配置**：
- 脚本来源：在线编写 / 上传文件 / 工具路径
- 在线编写 → 代码编辑器
- 上传文件 → 文件选择器（.sh/.py/二进制）
- 工具路径 → 输入框（引用工具箱已分发的路径）
- 环境变量：键值对列表，可动态添加

**Step 3 — 调度设置**：
- 执行方式：Cron 定时 / 固定间隔 / 仅手动
- Cron 模式 → 表达式输入 + 快捷按钮（每小时/每天/每周/每月）+ 下次执行预览
- 间隔模式 → 秒数输入
- 失败告警：开关

### 5.5 执行日志表

| 列 | 说明 |
|------|------|
| 任务名 | 关联 scheduler_tasks.name |
| 目标 | Node / pod-name / 批量(N个Pod) |
| 触发 | 手动 / Cron调度 / 重试 |
| 状态 | pending → running → success/failed/cancelled |
| 耗时 | duration_ms 格式化为 "12s" / "2m30s" |
| 时间 | started_at |

展开行：stdout / stderr / 退出码 / 连接快照

筛选：按任务名 / 按状态 / 按时间范围

导出：JSON / CSV / TXT（单条或批量勾选）

## 6. 告警联动

任务创建时可开启"失败告警"开关（`alert_on_failure` 字段）。

执行失败时：
1. 后端检测 `task.alert_on_failure == 1`
2. 调用现有 `/api/alerts/` 接口创建告警记录
3. 告警内容包含：任务名、目标、错误摘要、时间、快速跳转链接
4. 侧边栏"🔔 告警中心"中展示

## 7. 依赖

- `croniter` — Cron 表达式解析（需加入 requirements.txt）
- 现有 `KubectlExecutor` — Pod 内命令执行
- 现有告警模块 — 失败通知
