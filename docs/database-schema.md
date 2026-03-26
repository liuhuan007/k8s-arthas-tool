# K8s Arthas Tool - 数据库表结构文档

## 概述

K8s Arthas Tool 使用 SQLite 数据库 (`arthas.db`) 存储连接记录、命令历史、采样任务和日志。

数据库文件位置：`{workspace}/arthas.db`

---

## 表结构

### 1. connections（连接记录表）

存储 K8s Arthas 连接信息。

| 字段 | 类型 | 说明 | 约束 |
|------|------|------|------|
| id | TEXT | 连接唯一标识，格式：`{cluster}/{namespace}/{pod}` | PRIMARY KEY |
| cluster_name | TEXT | 集群名称 | NOT NULL |
| namespace | TEXT | 命名空间 | NOT NULL |
| pod_name | TEXT | Pod 名称 | NOT NULL |
| local_port | INTEGER | 本地端口（用于端口转发） | - |
| created_at | TIMESTAMP | 创建时间 | DEFAULT CURRENT_TIMESTAMP |
| updated_at | TIMESTAMP | 更新时间 | DEFAULT CURRENT_TIMESTAMP |

**索引**：
- 主键索引：`id`
- 联合索引：`(cluster_name, namespace, pod_name)`（隐式）

**使用场景**：
- 保存 Arthas 连接记录
- 切换连接时查询连接信息
- 作为其他表的外键关联

---

### 2. arthas_commands（Arthas 命令历史表）

存储 Arthas 命令执行历史。

| 字段 | 类型 | 说明 | 约束 |
|------|------|------|------|
| id | INTEGER | 自增主键 | PRIMARY KEY AUTOINCREMENT |
| connection_id | TEXT | 关联的连接 ID | NOT NULL, FOREIGN KEY |
| command | TEXT | 执行的命令 | NOT NULL |
| output | TEXT | 命令输出 | - |
| error | TEXT | 错误信息（如果有） | - |
| timestamp | TIMESTAMP | 执行时间 | DEFAULT CURRENT_TIMESTAMP |

**外键约束**：
```sql
FOREIGN KEY (connection_id) REFERENCES connections(id) ON DELETE CASCADE
```

**索引**：
- 主键索引：`id`
- 外键索引：`connection_id`

**使用场景**：
- 每次执行 Arthas 命令时自动保存历史
- 页面刷新后加载历史命令记录
- 命令按时间倒序显示（最新的在上面）

---

### 3. profiler_tasks（采样任务历史表）

存储采样工具的任务记录（CPU Profiler、JFR、Dump 等）。

| 字段 | 类型 | 说明 | 约束 |
|------|------|------|------|
| id | TEXT | 任务唯一标识（UUID） | PRIMARY KEY |
| connection_id | TEXT | 关联的连接 ID | NOT NULL, FOREIGN KEY |
| mode | TEXT | 采样模式：`cpu`/`jfr`/`dump`/`heapdump` | NOT NULL |
| event | TEXT | 采样事件（CPU Profiler 使用） | - |
| duration | INTEGER | 采样时长（秒） | - |
| status | TEXT | 任务状态：`running`/`completed`/`failed` | - |
| output_path | TEXT | 输出文件路径 | - |
| timestamp | TIMESTAMP | 任务开始时间 | DEFAULT CURRENT_TIMESTAMP |

**外键约束**：
```sql
FOREIGN KEY (connection_id) REFERENCES connections(id) ON DELETE CASCADE
```

**索引**：
- 主键索引：`id`
- 外键索引：`connection_id`

**使用场景**：
- 记录每次采样任务
- 历史记录标签显示所有任务
- 本地历史标签只显示当前连接的任务

---

### 4. profiler_logs（采样日志表）

存储采样工具的运行日志。

| 字段 | 类型 | 说明 | 约束 |
|------|------|------|------|
| id | INTEGER | 自增主键 | PRIMARY KEY AUTOINCREMENT |
| connection_id | TEXT | 关联的连接 ID | NOT NULL, FOREIGN KEY |
| message | TEXT | 日志消息内容 | NOT NULL |
| level | TEXT | 日志级别：`info`/`dim`/`ok`/`error`/`warn`/`success` | DEFAULT 'info' |
| timestamp | TIMESTAMP | 日志时间 | DEFAULT CURRENT_TIMESTAMP |

**外键约束**：
```sql
FOREIGN KEY (connection_id) REFERENCES connections(id) ON DELETE CASCADE
```

**索引**：
- 主键索引：`id`
- 外键索引：`connection_id`
- 复合索引：`(connection_id, timestamp)` - 用于按时间顺序查询

**使用场景**：
- 采样过程中实时记录日志
- 切换连接时加载该连接的日志
- 避免日志串台（通过 connection_id 隔离）

---

## ER 图

```
┌─────────────────────┐
│   connections       │
├─────────────────────┤
│ id (PK)             │◄──────────────┐
│ cluster_name        │               │
│ namespace           │               │
│ pod_name            │               │
│ local_port          │               │
│ created_at          │               │
│ updated_at          │               │
└─────────────────────┘               │
                                    │
        ┌───────────────────────────┴──────────────────────────┐
        │                                                   │
        ▼                                                   ▼
┌─────────────────────┐                           ┌─────────────────────┐
│ arthas_commands    │                           │ profiler_tasks     │
├─────────────────────┤                           ├─────────────────────┤
│ id (PK, AI)         │                           │ id (PK)             │
│ connection_id (FK)  │                           │ connection_id (FK) │
│ command             │                           │ mode                │
│ output              │                           │ event               │
│ error               │                           │ duration            │
│ timestamp           │                           │ status              │
└─────────────────────┘                           │ output_path         │
                                                │ timestamp           │
                                                └─────────────────────┘
                                                        │
                                                        ▼
                                                ┌─────────────────────┐
                                                │ profiler_logs       │
                                                ├─────────────────────┤
                                                │ id (PK, AI)         │
                                                │ connection_id (FK)  │
                                                │ message             │
                                                │ level               │
                                                │ timestamp           │
                                                └─────────────────────┘

图例：
PK  - Primary Key (主键)
FK  - Foreign Key (外键)
AI  - Auto Increment (自增)
```

---

## 数据初始化

数据库在首次启动时自动创建，无需手动初始化。

初始化代码位置：`server.py` → `_init_db()` 函数

```python
def _init_db():
    conn = sqlite3.connect(str(DB_FILE))
    cursor = conn.cursor()
    # 创建表...
    conn.commit()
    conn.close()
```

---

## 数据维护

### 清理策略

目前无自动清理策略，建议手动维护：

```sql
-- 清理 30 天前的命令历史
DELETE FROM arthas_commands WHERE timestamp < datetime('now', '-30 days');

-- 清理 30 天前的采样任务
DELETE FROM profiler_tasks WHERE timestamp < datetime('now', '-30 days');

-- 清理 30 天前的采样日志
DELETE FROM profiler_logs WHERE timestamp < datetime('now', '-30 days');
```

### 删除连接

删除连接时会级联删除关联的所有数据（命令、任务、日志）：

```sql
DELETE FROM connections WHERE id = 'cluster/ns/pod';
```

---

## API 接口

### connections

| 方法 | 路径 | 说明 |
|------|------|------|
| - | 内部函数 | 保存连接：`_save_connection()` |
| - | 内部函数 | 查询连接：`_get_connection()` |

### arthas_commands

| 方法 | 路径 | 说明 |
|------|------|------|
| - | 内部函数 | 保存命令：`_save_arthas_command()` |
| GET | `/api/arthas/commands?connection_id=xxx&limit=50` | 获取命令历史 |

### profiler_tasks

| 方法 | 路径 | 说明 |
|------|------|------|
| - | 内部函数 | 保存任务（在 profiler_backend.py 中） |
| GET | `/api/profile/tasks` | 获取所有任务 |
| GET | `/api/profile/tasks?connection_id=xxx` | 获取指定连接的任务 |

### profiler_logs

| 方法 | 路径 | 说明 |
|------|------|------|
| - | 内部函数 | 保存日志：`_save_profiler_log()` |
| - | 内部函数 | 查询日志：`_get_profiler_logs()` |
| - | 内部函数 | 清空日志：`_clear_profiler_logs()` |
| POST | `/api/profile/logs` | 保存日志 |
| GET | `/api/profile/logs/<conn_id>` | 获取连接的日志 |
| DELETE | `/api/profile/logs/<conn_id>` | 清空连接的日志 |

---

## 版本历史

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-03-26 | v1.2 | 新增 `profiler_logs` 表，实现采样日志持久化 |
| 2026-03-26 | v1.1 | 新增 `profiler_tasks` 表 |
| 2026-03-26 | v1.0 | 初始版本，包含 `connections` 和 `arthas_commands` 表 |

---

## 注意事项

1. **连接 ID 格式**：`{cluster}/{namespace}/{pod}`，用 `/` 分隔
2. **级联删除**：删除连接会自动删除关联的所有数据
3. **时间戳**：所有时间字段使用 SQLite 的 `CURRENT_TIMESTAMP`
4. **并发控制**：后端使用 `sqlite3.connect(timeout=10)` 处理并发访问
5. **JSON 格式**：`profiler_logs.message` 和 `arthas_commands.output` 可能包含 JSON 字符串

---

## 扩展建议

未来可能添加的表：

### metrics_history（指标历史表）
存储 Pod 监控指标数据。

### gc_logs（GC 日志表）
存储 GC 日志内容和分析结果。

### sessions（会话表）
管理长期 Arthas session 会话。
