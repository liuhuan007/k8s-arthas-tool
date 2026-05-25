# 数据模型实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 实现数据模型设计，包括新增表结构、现有表扩展、索引优化、数据迁移脚本和数据初始化策略。

**Architecture:** 数据模型作为系统基础层，为所有业务模块提供数据存储和查询支持。采用 SQLite 数据库，WAL 模式，支持高性能并发读写。

**Tech Stack:** Python, SQLite, pytest

---

## 1. 目标

实现数据模型设计，包括新增表结构、现有表扩展、索引优化、数据迁移脚本和数据初始化策略。

## 2. 架构

数据模型作为系统基础层，为所有业务模块提供数据存储和查询支持。采用 SQLite 数据库，WAL 模式，支持高性能并发读写。

## 3. 核心表清单

### 3.1 已有表（需扩展）

| 表名 | 用途 | 扩展内容 |
|------|------|---------|
| `users` | 用户账号、密码哈希、角色、启停状态 | 无 |
| `user_clusters` | 用户与集群授权关系 | 无 |
| `connections` | Pod/Arthas 连接记录 | 扩展连接快照、健康状态 |
| `arthas_commands` | Arthas 命令执行历史 | 扩展 run_id、capability_id |
| `audit_logs` | 操作审计 | 扩展 resource_id、execution_mode |
| `profiler_tasks` | 采样任务历史 | 扩展 run_id 关联 |
| `profiler_logs` | 采样运行日志 | 无 |

### 3.2 新增表

| 表名 | 用途 | 优先级 |
|------|------|--------|
| `skill_registry` | Skill注册表（管理态） | P0 |
| `diagnosis_capabilities` | 诊断能力元数据（生产执行态） | P0 |
| `step_logs` | 步骤级日志 | P0 |
| `tool_packages` | 工具包管理 | P0 |

## 4. 详细表结构

### 4.1 skill_registry 表（Skill管理态）

```sql
CREATE TABLE skill_registry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    description TEXT,
    category TEXT,  -- performance/stability/security
    level INTEGER,  -- 1/2/3/4
    risk_level TEXT,  -- low/medium/high
    estimated_duration INTEGER,
    source TEXT,  -- builtin/custom/imported
    status TEXT DEFAULT 'draft',  -- draft/validated/testing/published/archived
    dsl TEXT,  -- 执行DSL（场景方案）
    parameters_schema TEXT,  -- 参数schema
    llm_prompt TEXT,  -- 大模型提示词
    arthas_command TEXT,  -- Arthas命令（快捷工具/诊断模板）
    handler TEXT,  -- AI诊断处理器
    created_by INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(name, version)
);
```

### 4.2 diagnosis_capabilities 表（生产执行态）

```sql
CREATE TABLE diagnosis_capabilities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_id INTEGER,  -- 关联skill_registry
    name TEXT NOT NULL,
    type TEXT NOT NULL,  -- arthas_command/scenario/ai_diagnosis
    category TEXT NOT NULL,  -- quick/tool/scenario/ai
    level INTEGER NOT NULL DEFAULT 1,
    risk_level TEXT DEFAULT 'low',
    parameters_schema TEXT DEFAULT '{}',
    description TEXT,
    estimated_duration INTEGER DEFAULT 10,
    enabled INTEGER DEFAULT 1,
    created_by INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (skill_id) REFERENCES skill_registry(id),
    FOREIGN KEY (created_by) REFERENCES users(id)
);
```

### 4.3 step_logs 表（步骤级日志）

```sql
CREATE TABLE step_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,  -- 关联task_logs.id
    step_number INTEGER NOT NULL,
    step_name TEXT,
    step_type TEXT,  -- arthas_command/llm_analysis/get_pod_status
    command TEXT,  -- 实际执行的命令
    output TEXT,  -- 命令输出
    status TEXT DEFAULT 'pending',  -- pending/running/success/failed/skipped
    duration_ms INTEGER,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES task_logs(id)
);
```

### 4.4 tool_packages 表（工具包管理）

```sql
CREATE TABLE tool_packages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    source_type TEXT DEFAULT 'local',
    source_url TEXT,
    version TEXT,
    checksum TEXT,
    tool_type TEXT DEFAULT 'generic',
    file_path TEXT,
    file_name TEXT,
    file_size INTEGER DEFAULT 0,
    sha256 TEXT,
    install_path TEXT,
    is_builtin INTEGER DEFAULT 0,
    last_verified_at TIMESTAMP,
    status TEXT DEFAULT 'active',
    created_by INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (created_by) REFERENCES users(id)
);
```

## 5. 现有表扩展

### 5.1 connections 表扩展

```sql
-- 连接快照字段
ALTER TABLE connections ADD COLUMN snapshot_json TEXT;
ALTER TABLE connections ADD COLUMN health_status TEXT DEFAULT 'unknown';
ALTER TABLE connections ADD COLUMN last_health_check_at TIMESTAMP;
ALTER TABLE connections ADD COLUMN ttl_seconds INTEGER DEFAULT 3600;
```

### 5.2 arthas_commands 表扩展

```sql
-- 执行记录关联
ALTER TABLE arthas_commands ADD COLUMN run_id TEXT;
ALTER TABLE arthas_commands ADD COLUMN capability_id INTEGER;
ALTER TABLE arthas_commands ADD COLUMN execution_mode TEXT;
ALTER TABLE arthas_commands ADD COLUMN status TEXT DEFAULT 'pending';
```

### 5.3 audit_logs 表扩展

```sql
-- 审计字段补强
ALTER TABLE audit_logs ADD COLUMN resource_id TEXT;
ALTER TABLE audit_logs ADD COLUMN execution_mode TEXT;
ALTER TABLE audit_logs ADD COLUMN risk_level TEXT;
ALTER TABLE audit_logs ADD COLUMN duration_ms INTEGER;
```

## 6. 索引优化

### 6.1 新增索引

```sql
-- skill_registry 索引
CREATE INDEX idx_skill_registry_status ON skill_registry(status);
CREATE INDEX idx_skill_registry_category ON skill_registry(category);
CREATE INDEX idx_skill_registry_source ON skill_registry(source);

-- diagnosis_capabilities 索引
CREATE INDEX idx_diag_caps_type ON diagnosis_capabilities(type);
CREATE INDEX idx_diag_caps_category_level ON diagnosis_capabilities(category, level);
CREATE INDEX idx_diag_caps_enabled ON diagnosis_capabilities(enabled);

-- step_logs 索引
CREATE INDEX idx_step_logs_run_id ON step_logs(run_id);
CREATE INDEX idx_step_logs_status ON step_logs(status);

-- tool_packages 索引
CREATE INDEX idx_tool_packages_type ON tool_packages(tool_type);
CREATE INDEX idx_tool_packages_status ON tool_packages(status);
```

### 6.2 现有索引优化

```sql
-- task_logs 索引优化
CREATE INDEX idx_task_logs_execution_mode ON task_logs(execution_mode);
CREATE INDEX idx_task_logs_capability_id ON task_logs(capability_id);
CREATE INDEX idx_task_logs_connection_id ON task_logs(connection_id);
```

## 7. 数据迁移策略

### 7.1 迁移脚本设计

```python
# models/db.py

def migrate_database():
    """数据库迁移主函数"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. 创建新表
    create_skill_registry_table(cursor)
    create_diagnosis_capabilities_table(cursor)
    create_step_logs_table(cursor)
    create_tool_packages_table(cursor)
    
    # 2. 扩展现有表
    extend_connections_table(cursor)
    extend_arthas_commands_table(cursor)
    extend_audit_logs_table(cursor)
    
    # 3. 创建索引
    create_indexes(cursor)
    
    # 4. 数据迁移
    migrate_existing_data(cursor)
    
    # 5. 提交事务
    conn.commit()
    conn.close()
```

### 7.2 幂等性保证

- 使用 `CREATE TABLE IF NOT EXISTS` 防止重复创建
- 使用 `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` 防止重复添加列
- 使用 `CREATE INDEX IF NOT EXISTS` 防止重复创建索引
- 迁移脚本可重复执行，不会产生副作用

### 7.3 回滚方案

```python
def rollback_migration():
    """回滚迁移"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. 删除新表
    cursor.execute("DROP TABLE IF EXISTS skill_registry")
    cursor.execute("DROP TABLE IF EXISTS diagnosis_capabilities")
    cursor.execute("DROP TABLE IF EXISTS step_logs")
    cursor.execute("DROP TABLE IF EXISTS tool_packages")
    
    # 2. 删除新增索引
    cursor.execute("DROP INDEX IF EXISTS idx_skill_registry_status")
    cursor.execute("DROP INDEX IF EXISTS idx_diag_caps_type")
    # ... 其他索引
    
    conn.commit()
    conn.close()
```

## 8. 数据初始化策略

### 8.1 预制 Skill 数据

```python
# 内置Skill定义（随代码发布）
BUILTIN_SKILLS = [
    {
        "name": "jvm-dashboard",
        "version": "1.0.0",
        "source": "builtin",
        "category": "quick",
        "level": 1,
        "description": "查看JVM运行概况",
        "arthas_command": "dashboard -n 1",
        "risk_level": "low"
    },
    {
        "name": "cpu-high-diagnosis",
        "version": "1.0.0",
        "source": "builtin",
        "category": "performance",
        "level": 2,
        "description": "排查CPU飙高问题",
        "dsl": "steps: [...]",
        "risk_level": "medium"
    },
    # ... 更多内置Skill
]
```

### 8.2 预制诊断能力

```python
# 诊断能力初始化
def init_diagnosis_capabilities():
    """初始化诊断能力"""
    capabilities = [
        # 快捷工具（Level 1）
        {"name": "JVM Dashboard", "type": "arthas_command", "category": "quick", "level": 1},
        {"name": "线程清单", "type": "arthas_command", "category": "quick", "level": 1},
        {"name": "死锁检测", "type": "arthas_command", "category": "quick", "level": 1},
        {"name": "VM 参数", "type": "arthas_command", "category": "quick", "level": 1},
        {"name": "类信息", "type": "arthas_command", "category": "quick", "level": 1},
        
        # 诊断模板（Level 2）
        {"name": "Trace 调用链分析", "type": "arthas_command", "category": "tool", "level": 2},
        {"name": "Watch 方法观测", "type": "arthas_command", "category": "tool", "level": 2},
        {"name": "Stack 调用栈定位", "type": "arthas_command", "category": "tool", "level": 2},
        {"name": "Jad 反编译", "type": "arthas_command", "category": "tool", "level": 2},
        {"name": "Monitor 方法统计", "type": "arthas_command", "category": "tool", "level": 2},
        
        # 场景方案（Level 3）
        {"name": "接口响应慢诊断", "type": "scenario", "category": "scenario", "level": 3},
        {"name": "CPU 100% 排查", "type": "scenario", "category": "scenario", "level": 3},
        {"name": "OOM 内存泄漏排查", "type": "scenario", "category": "scenario", "level": 3},
        
        # AI 诊断（Level 4）
        {"name": "一键性能诊断", "type": "ai_diagnosis", "category": "ai", "level": 4},
    ]
    return capabilities
```

## 9. 任务分解

### 任务 1：创建数据库迁移脚本

**Files:**
- Modify: `models/db.py`
- Create: `tests/test_db_migration.py`

**Step 1: Write the failing test**

```python
# tests/test_db_migration.py

import pytest
from models.db import get_db_connection, migrate_database

def test_migrate_database_creates_tables():
    """Test that migrate_database creates all required tables"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 执行迁移
    migrate_database()
    
    # 检查表是否存在
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cursor.fetchall()}
    
    assert 'skill_registry' in tables
    assert 'diagnosis_capabilities' in tables
    assert 'step_logs' in tables
    assert 'tool_packages' in tables
    
    conn.close()

def test_migrate_database_is_idempotent():
    """Test that migrate_database can be run multiple times safely"""
    conn = get_db_connection()
    
    # 执行两次迁移
    migrate_database()
    migrate_database()
    
    # 检查表是否存在
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cursor.fetchall()}
    
    assert 'skill_registry' in tables
    assert 'diagnosis_capabilities' in tables
    
    conn.close()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_db_migration.py::test_migrate_database_creates_tables -v`
Expected: FAIL with "migrate_database not defined"

**Step 3: Write minimal implementation**

```python
# models/db.py

def migrate_database():
    """数据库迁移主函数"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. 创建新表
    create_skill_registry_table(cursor)
    create_diagnosis_capabilities_table(cursor)
    create_step_logs_table(cursor)
    create_tool_packages_table(cursor)
    
    # 2. 扩展现有表
    extend_connections_table(cursor)
    extend_arthas_commands_table(cursor)
    extend_audit_logs_table(cursor)
    
    # 3. 创建索引
    create_indexes(cursor)
    
    # 4. 数据迁移
    migrate_existing_data(cursor)
    
    # 5. 提交事务
    conn.commit()
    conn.close()

def create_skill_registry_table(cursor):
    """创建 skill_registry 表"""
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS skill_registry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            version TEXT NOT NULL,
            description TEXT,
            category TEXT,
            level INTEGER,
            risk_level TEXT,
            estimated_duration INTEGER,
            source TEXT,
            status TEXT DEFAULT 'draft',
            dsl TEXT,
            parameters_schema TEXT,
            llm_prompt TEXT,
            arthas_command TEXT,
            handler TEXT,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(name, version)
        )
    ''')

def create_diagnosis_capabilities_table(cursor):
    """创建 diagnosis_capabilities 表"""
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS diagnosis_capabilities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            skill_id INTEGER,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            category TEXT NOT NULL,
            level INTEGER NOT NULL DEFAULT 1,
            risk_level TEXT DEFAULT 'low',
            parameters_schema TEXT DEFAULT '{}',
            description TEXT,
            estimated_duration INTEGER DEFAULT 10,
            enabled INTEGER DEFAULT 1,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (skill_id) REFERENCES skill_registry(id),
            FOREIGN KEY (created_by) REFERENCES users(id)
        )
    ''')
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_db_migration.py::test_migrate_database_creates_tables -v`
Expected: PASS

**Step 5: Commit**

```bash
git add models/db.py tests/test_db_migration.py
git commit -m "feat: add database migration script"
```

### 任务 2：实现 skill_registry 表

**文件：**
- 修改：`models/db.py`
- 创建：`services/skill_registry.py`

**步骤：**
1. 创建 skill_registry 表
2. 实现 Skill CRUD 操作
3. 实现状态转换逻辑
4. 编写单元测试

### 任务 3：实现 diagnosis_capabilities 表

**文件：**
- 修改：`models/db.py`
- 创建：`services/diagnosis_service.py`

**步骤：**
1. 创建 diagnosis_capabilities 表
2. 实现能力查询和管理
3. 实现能力启用/禁用
4. 编写单元测试

### 任务 4：实现 step_logs 表

**文件：**
- 修改：`models/db.py`
- 创建：`services/step_logger.py`

**步骤：**
1. 创建 step_logs 表
2. 实现步骤日志记录
3. 实现步骤状态更新
4. 编写单元测试

### 任务 5：实现 tool_packages 表

**文件：**
- 修改：`models/db.py`
- 创建：`services/tool_manager.py`

**步骤：**
1. 创建 tool_packages 表
2. 实现工具包 CRUD
3. 实现工具包状态管理
4. 编写单元测试

### 任务 6：扩展现有表

**文件：**
- 修改：`models/db.py`
- 修改：`backend/core/connection_state.py`

**步骤：**
1. 扩展 connections 表字段
2. 扩展 arthas_commands 表字段
3. 扩展 audit_logs 表字段
4. 更新相关查询逻辑
5. 编写迁移测试

### 任务 7：创建索引

**文件：**
- 修改：`models/db.py`

**步骤：**
1. 创建 skill_registry 索引
2. 创建 diagnosis_capabilities 索引
3. 创建 step_logs 索引
4. 创建 tool_packages 索引
5. 验证索引效果

### 任务 8：数据初始化

**文件：**
- 修改：`models/db.py`
- 创建：`data/builtin_skills.json`

**步骤：**
1. 设计预制 Skill 数据格式
2. 实现数据初始化函数
3. 实现幂等性检查
4. 编写初始化测试

## 10. 验收标准

- [ ] 数据库迁移脚本执行成功
- [ ] skill_registry 表创建成功
- [ ] diagnosis_capabilities 表创建成功
- [ ] step_logs 表创建成功
- [ ] tool_packages 表创建成功
- [ ] 现有表扩展完成
- [ ] 索引创建完成
- [ ] 数据初始化完成
- [ ] 迁移脚本幂等性验证通过
- [ ] 回滚方案验证通过
- [ ] 单元测试覆盖率 > 80%

## 11. 风险与缓解措施

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 数据库迁移失败 | 高 | 备份数据库，支持回滚 |
| 旧数据兼容问题 | 中 | 编写数据迁移测试 |
| 索引性能问题 | 中 | 性能测试，优化索引 |
| 并发写入冲突 | 中 | WAL 模式 + 连接池 |

## 12. 后续演进

### P1 阶段

- 支持 PostgreSQL 迁移
- 实现数据版本管理
- 实现数据归档策略

### P2 阶段

- 实现分布式数据库支持
- 实现数据加密存储
- 实现数据备份恢复
