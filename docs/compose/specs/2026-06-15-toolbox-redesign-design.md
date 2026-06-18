# 工具箱（Toolbox）功能重设计

> **日期**: 2026-06-15
> **状态**: 设计完成，待实现
> **范围**: 侧边栏菜单重构 + 工具箱功能重设计 + 批量分发工作流

---

## [S1] 问题定义

### 现状问题

1. **"工具中心"菜单定位模糊** — 包含在线修复、采样工具、终端、Pod 监控、文件下载、工具箱，这些工具的能力层级和使用场景完全不同，混在一起让用户困惑
2. **"工具箱"嵌套在"工具中心"里** — 语义重叠（工具管理 vs 工具执行），用户不清楚区别
3. **工具分发只支持单个 Pod** — 批量分发 Arthas JAR 到多个 Pod 需要重复操作
4. **工具分类不清晰** — 二进制工具、脚本工具、快捷操作混在一起，没有统一的管理视图

### 设计目标

- 重新定义"工具箱"在整个站点中的定位：**诊断辅助工具集**
- 工具按**形态**分类：二进制工具、脚本工具、快捷操作
- 工具分发支持**单个 + 批量**，双入口（工具箱 + 连接中心）
- 分发流程**感知 Pod 能力**（Java/Go/Python），避免无效操作

---

## [S2] 侧边栏菜单重构

### 重新规划的完整菜单结构

```
连接管理
├── 🔌 连接中心                    [panel-connections]
│   · 集群管理 / Pod 选择 / Arthas 升级 / 连接记录
└── 📋 连接详情                    [panel-connection-detail]
    · 单个连接的状态、操作、能力入口

诊断
├── ⚡ 快捷诊断                    [panel-diagnosis-quick]
│   · 一键诊断：选择场景 → 自动执行
├── 📋 场景方案                    [panel-diagnosis-scenario]
│   · 预设诊断场景（CPU/内存/线程/GC）
├── 🤖 AI 诊断                    [panel-diagnosis-ai]
│   · AI 辅助诊断，对话式交互
├── 📊 诊断历史                    [panel-diagnosis-history]
│   · 历次诊断记录、结果回溯
└── 📈 控制面板                    [panel-dashboard]
    · JVM 实时仪表盘（线程/内存/GC/运行时）

实时操作（对 Pod 执行操作）
├── Pod 基础（只需 Pod 连接）
│   ├── 🖥️ 终端                   [panel-terminal]
│   │   · kubectl exec 交互 Shell
│   ├── 📂 文件下载                [panel-filebrowser]
│   │   · Pod 内文件浏览、下载
│   └── 📊 Pod 监控                [panel-monitor]
│       · CPU/内存/进程/网络实时指标
└── JVM 诊断（需 Arthas 连接）
    ├── 🔥 采样工具                [panel-profiler]
    │   · async-profiler / JFR / Thread Dump / Heap Dump
    ├── 🔧 在线修复                [panel-hotswap]
    │   · jad → 编辑 → mc → retransform 四步工作流
    └── 🧵 线程诊断                [panel-thread-diagnosis]
        · 线程列表、死锁检测、堆栈查看

工具箱（离线工具管理 + 分发）
├── 📦 二进制工具                   [工具箱 - 二进制工具卡片组]
│   · Arthas JAR / async-profiler 等上传、校验、分发
├── 🐍 脚本工具                    [工具箱 - 脚本工具卡片组]
│   · Shell/Python/Node 脚本编辑、执行
├── ⚡ 快捷操作                    [工具箱 - 快捷操作卡片组]
│   · 预设 Arthas 命令一键执行
└── 📤 分发管理                    [工具箱 - 分发历史]
    · 工具分发记录、批量分发入口

任务中心
├── 📋 任务列表                    [panel-task-center - definitions]
│   · 任务定义、创建、编辑
├── ⏱ 调度管理                    [panel-task-center - schedules]
│   · 定时任务配置
└── 📊 执行记录                    [panel-task-center - logs]
    · 任务执行历史、日志查看

系统管理（仅管理员可见）
├── 👥 用户管理                    [panel-user-management]
├── 📋 审计日志                    [panel-audit-logs]
├── 🔔 告警中心                    [panel-alerts]
├── ⚡ Skill 管理                  [panel-skill-management]
├── ⚙️ 模型配置                    [panel-model-config]
└── 🔌 MCP 接入                    [panel-mcp-center]

外部系统
└── (动态加载外部链接)
```

### 变化说明

| 变化 | 说明 |
|------|------|
| "工具中心" → "实时操作" | 更准确：这些工具都是对 live Pod 执行操作 |
| "工具箱"独立成组 | 从"工具中心"提升为独立组，定位清晰 |
| "控制面板"移入"诊断" | Dashboard 是诊断第一步（全局概览），归入诊断更合理 |
| "线程诊断"移入"实时操作" | 线程诊断是独立的实时操作工具 |
| "脚本库"从任务中心移除 | 脚本在工具箱中管理，任务中心只负责调度执行 |
| "外部系统"保留 | 动态加载，保持灵活性 |

---

## [S3] 工具箱整体架构

### 工具分类模型

```
Toolbox
├── BinaryTool（二进制工具）
│   ├── arthas-boot.jar
│   ├── async-profiler
│   └── jattach
├── ScriptTool（脚本工具）
│   ├── CPU 分析脚本 (Python)
│   ├── 线程 Dump 脚本 (Shell)
│   └── 自定义脚本
└── QuickAction（快捷操作）
    ├── jad 反编译
    ├── thread 分析
    └── memory 检查
```

### 页面结构

```
工具中心 (panel-toolchain-center)
├── Header: 标题 + 刷新 + 批量分发按钮 + 上传工具按钮
├── Summary Bar: 工具包数 | 可用 | 已上传 | 分发次数
├── Content Area (卡片网格):
│   ├── BinaryTool Cards (二进制工具卡片组)
│   ├── ScriptTool Cards (脚本工具卡片组)
│   └── QuickAction Cards (快捷操作卡片组)
└── Batch Distribute Modal (批量分发浮层, 按需弹出)
```

### 与现有模块的关系

| 模块 | 关系 | 说明 |
|------|------|------|
| 连接中心 | 双向入口 | 连接中心可批量选 Pod → 分发工具；工具箱可选工具 → 选 Pod |
| 任务中心 | 下游消费 | 工具箱的脚本工具可注册为任务中心的脚本模板 |
| 诊断中心 | 依赖 | 诊断能力执行时可能需要工具箱中的二进制工具 |
| 终端 | 独立 | 终端直接执行命令，不依赖工具箱 |

---

## [S4] 数据模型

### 新增数据库表

```sql
-- 脚本工具表
CREATE TABLE script_tools (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    runtime TEXT NOT NULL,          -- 'python' | 'shell' | 'node'
    script_body TEXT NOT NULL,
    risk_level TEXT DEFAULT 'low',  -- 'low' | 'medium' | 'high'
    parameters_schema TEXT,         -- JSON schema for params
    capability_id INTEGER,          -- 关联诊断能力（可选）
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (capability_id) REFERENCES diag_capabilities(id)
);

-- 快捷操作表
CREATE TABLE quick_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    category TEXT,                  -- 'jvm' | 'class' | 'method' | 'ognl'
    command_template TEXT NOT NULL, -- 如 'jad {class_name}'
    parameters_schema TEXT,         -- JSON schema for params
    risk_level TEXT DEFAULT 'low',
    description TEXT,
    arthas_doc_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 分发记录表
CREATE TABLE tool_distributions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tool_type TEXT NOT NULL,        -- 'binary' | 'script' | 'quick_action'
    tool_id INTEGER NOT NULL,
    target_cluster TEXT,
    target_namespace TEXT,
    target_pod TEXT,
    target_container TEXT,
    install_path TEXT,
    status TEXT DEFAULT 'pending',  -- 'pending' | 'success' | 'failed'
    error_message TEXT,
    distributed_by INTEGER,
    distributed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (distributed_by) REFERENCES users(id)
);
```

### 扩展现有表

`tool_packages` 表保持不变，已有的字段满足需求。

---

## [S5] 前端组件结构

### 组件模块

```
toolbox.js (主入口)
├── renderToolbox()              -- 渲染整体布局
├── renderBinaryTools()          -- 渲染二进制工具卡片组
├── renderScriptTools()          -- 渲染脚本工具卡片组
├── renderQuickActions()         -- 渲染快捷操作卡片组
├── openBatchDistribute()        -- 打开批量分发浮层
├── executeDistribution()        -- 执行分发（单个/批量）
└── loadDistributionHistory()    -- 加载分发历史
```

### 卡片设计

**二进制工具卡片**：
```
┌──────────────────────────────┐
│ 📦 arthas-boot.jar           │
│ v3.7.2 · 内置 · SHA: a1b2.. │
│ /app/arthas/arthas-boot.jar  │
│ [校验] [分发→] [删除]        │
└──────────────────────────────┘
```

**脚本工具卡片**：
```
┌──────────────────────────────┐
│ 🐍 CPU 分析脚本              │
│ Python · 低风险              │
│ 关联诊断能力: CPU Profiling  │
│ [编辑] [执行→] [删除]        │
└──────────────────────────────┘
```

**快捷操作卡片**：
```
┌──────────────────────────────┐
│ ⚡ jad 反编译                │
│ JVM 基础 · 低风险            │
│ jad {class_name}             │
│ [执行→] [查看文档]           │
└──────────────────────────────┘
```

---

## [S6] 分发工作流

### 单个分发流程（卡片内联）

1. 点击工具卡片上的 [分发→] 按钮
2. 卡片下方展开分发表单：
   - 集群选择（默认当前集群）
   - Namespace 选择
   - Pod 下拉选择
   - 容器选择（可选）
   - 安装路径
   - [确认分发] [取消]
3. 点击确认 → 显示进度 → 完成后更新分发历史

### 批量分发流程（浮层）

**触发方式**：
- A. 工具箱顶部 [📦 批量分发] 按钮
- B. 连接中心 → 多选 Pod → 右键/批量菜单 → "分发工具"

**浮层 Step 1: 选择工具**
```
┌─────────────────────────────────────────────────┐
│ Step 1: 选择工具包                                │
│ ☑ arthas-boot.jar v3.7.2  (SHA: a1b2c3...)     │
│ ☐ async-profiler v2.9     (SHA: d4e5f6...)     │
│ ☑ jattach                  (SHA: g7h8i9...)     │
│                                                  │
│ [全选] [清空]  已选: 2 个工具                     │
└─────────────────────────────────────────────────┘
```

**浮层 Step 2: 选择目标 Pod**
```
┌─────────────────────────────────────────────────┐
│ Step 2: 选择目标 Pod                              │
│ 集群: [生产集群 ▾]  Namespace: [default ▾]       │
│                                                  │
│ [全部] [仅 Java Pod] [仅已连接]  ← 快捷筛选      │
│                                                  │
│ ☑ pod-a-7cc5f  Running  Java 11  Pod+Arthas  ✅ │
│ ☑ pod-b-8d2e1  Running  Java 8   Pod-only    ⚠️ │
│ ☐ pod-c-3f4a2  Running  Go 1.21  Pod-only    ❌ │
│ ☑ pod-d-9e1b3  Running  Java 17  Pod-only    ⚠️ │
│                                                  │
│ 状态说明:                                        │
│  ✅ = 工具可直接分发并使用                         │
│  ⚠️ = 工具可分发，但需先升级 Arthas 才能使用       │
│  ❌ = 工具不兼容此 Pod（非 Java）                  │
│                                                  │
│ 已选: 3 个 Pod (2 个 Java, 1 个非 Java)           │
│ ⚠️ pod-c 将被跳过（非 Java Pod）                  │
└─────────────────────────────────────────────────┘
```

**浮层 Step 3: 确认并执行**
```
┌─────────────────────────────────────────────────┐
│ Step 3: 确认分发                                  │
│ 将 2 个工具分发到 3 个 Pod (共 6 次分发操作)       │
│ 安装路径: /app/arthas/arthas-boot.jar             │
│ [确认分发]  [取消]                                │
├─────────────────────────────────────────────────┤
│ 分发进度 (实时更新)                               │
│ ✅ arthas → pod-a  (2.3s)                        │
│ ✅ arthas → pod-b  (1.8s)                        │
│ ⏳ arthas → pod-d  (进行中...)                    │
│ ✅ jattach → pod-a (0.9s)                        │
│ ⏳ jattach → pod-b (等待中)                       │
│ ⏳ jattach → pod-d (等待中)                       │
│ [取消剩余]                                       │
└─────────────────────────────────────────────────┘
```

### 连接中心批量入口

在连接中心的连接记录表格中，增加批量操作：

```
连接记录
[全选] [按能力筛选: ▾] [批量分发工具] [批量健康检查] [批量断开]
                      ↓
                [全部连接]
                [仅 Pod+Arthas]
                [仅 Pod-only]
                [仅 Java Pod]
```

---

## [S7] 能力感知分发

### 工具与 Pod 能力匹配规则

| 工具类型 | Pod 需要的能力 | 不匹配时的行为 |
|---------|---------------|--------------|
| Arthas JAR | Java 进程 + exec 权限 | 跳过 + 标记"非 Java Pod" |
| async-profiler | Java 进程 + exec 权限 | 跳过 + 标记"非 Java Pod" |
| jattach | Java 进程 | 跳过 + 标记"非 Java Pod" |
| 通用脚本 | exec 权限 | 正常分发 |

### Pod 能力检测

通过 `kubectl exec` 执行 `java -version` 检测 Pod 能力：

```json
POST /api/tools/detect-capability
{
  "cluster": "prod",
  "namespace": "default",
  "pod": "pod-a",
  "container": ""
}

Response:
{
  "has_java": true,
  "java_version": "11.0.18",
  "has_arthas": true,
  "arthas_version": "3.7.2",
  "has_exec": true,
  "capability_level": "pod+arthas"
}
```

### 能力级别定义

| 级别 | 含义 | 可用工具 |
|------|------|---------|
| `pod+arthas` | Pod 连接 + Arthas 已启动 | 全部工具 |
| `pod-only` | Pod 连接，Arthas 未启动 | Pod 基础工具 + 可分发 Arthas |
| `non-java` | Pod 连接，非 Java 进程 | 仅 Pod 基础工具 |
| `no-exec` | 无 exec 权限 | 无工具可用 |

---

## [S8] API 设计

### 工具箱 CRUD

```
GET    /api/tools/binary              二进制工具列表
POST   /api/tools/binary              上传二进制工具
PUT    /api/tools/binary/:id          更新二进制工具
DELETE /api/tools/binary/:id          删除二进制工具
POST   /api/tools/binary/:id/verify   校验 SHA256

GET    /api/tools/scripts             脚本工具列表
POST   /api/tools/scripts             创建脚本工具
PUT    /api/tools/scripts/:id         更新脚本工具
DELETE /api/tools/scripts/:id         删除脚本工具

GET    /api/tools/quick-actions       快捷操作列表
POST   /api/tools/quick-actions       创建快捷操作
PUT    /api/tools/quick-actions/:id   更新快捷操作
DELETE /api/tools/quick-actions/:id   删除快捷操作
```

### 分发操作

```
POST   /api/tools/distribute          单个分发
POST   /api/tools/batch-distribute    批量分发
GET    /api/tools/distributions       分发历史
GET    /api/tools/distributions/:id   分发详情
```

### Pod 能力检测

```
POST   /api/tools/detect-capability   检测 Pod 能力
```

### 批量分发请求/响应

**请求**：
```json
POST /api/tools/batch-distribute
{
  "tool_ids": [1, 3],
  "tool_type": "binary",
  "targets": [
    { "cluster": "prod", "namespace": "default", "pod": "pod-a", "container": "" },
    { "cluster": "prod", "namespace": "default", "pod": "pod-b", "container": "app" }
  ],
  "install_path": "/app/arthas/arthas-boot.jar"
}
```

**响应**：
```json
{
  "batch_id": "batch-20260615-001",
  "total": 4,
  "results": [
    { "tool": "arthas-boot.jar", "pod": "pod-a", "status": "success", "duration_ms": 2300 },
    { "tool": "arthas-boot.jar", "pod": "pod-b", "status": "success", "duration_ms": 1800 },
    { "tool": "jattach", "pod": "pod-a", "status": "success", "duration_ms": 900 },
    { "tool": "jattach", "pod": "pod-b", "status": "failed", "error": "non-java pod" }
  ],
  "summary": { "success": 3, "failed": 1, "skipped": 0 }
}
```

---

## [S9] 实现计划

### 任务拆分

| 任务 | 内容 | 复杂度 |
|------|------|--------|
| T1 | 侧边栏菜单重构（分组重命名 + 调整） | 低 |
| T2 | 数据库新增 script_tools / quick_actions / tool_distributions 表 | 低 |
| T3 | 后端 API：二进制工具 CRUD + 上传 + 校验 | 中 |
| T4 | 后端 API：脚本工具 CRUD | 低 |
| T5 | 后端 API：快捷操作 CRUD | 低 |
| T6 | 后端 API：Pod 能力检测 | 中 |
| T7 | 后端 API：单个分发 + 批量分发 + 分发历史 | 高 |
| T8 | 前端：工具箱卡片布局重构（三类工具卡片组） | 高 |
| T9 | 前端：单个分发表单（卡片内联展开） | 中 |
| T10 | 前端：批量分发浮层（Step 1-3 向导） | 高 |
| T11 | 前端：连接中心批量分发入口 | 中 |
| T12 | 前端：分发历史展示 | 低 |

### 执行顺序

```
Phase 1: 基础设施（T1 + T2）
  ↓
Phase 2: 后端 API（T3 + T4 + T5 + T6）
  ↓
Phase 3: 分发核心（T7 + T9 + T10）
  ↓
Phase 4: 集成完善（T8 + T11 + T12）
```

### 关键技术决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 文件上传方式 | multipart/form-data | 二进制工具需要上传文件 |
| 批量分发并发 | 串行（3 个并发） | 避免 Pod 资源争抢，可控性强 |
| Pod 能力检测 | kubectl exec + java -version | 最可靠，但有 exec 开销 |
| 分发进度推送 | WebSocket | 实时性好，已有基础设施 |
| 脚本执行方式 | 服务端执行 | 安全可控，不暴露 Pod shell |
