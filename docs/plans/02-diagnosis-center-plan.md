# 诊断中心实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 实现诊断中心，提供能力目录、参数表单、即时执行、场景编排、历史与报告功能，形成完整的诊断闭环。

**Architecture:** 诊断中心作为独立模块，负责能力目录管理、参数校验、即时诊断执行、场景方案编排和历史记录查询。与连接中心、任务中心、工具箱明确边界，不成为新的连接中心或万能工具市场。

**Tech Stack:** Python, Flask, SQLite, 原生 JavaScript, HTML, CSS

---

## 1. 目标

实现诊断中心，提供能力目录、参数表单、即时执行、场景编排、历史与报告功能，形成完整的诊断闭环。

## 2. 架构

诊断中心作为独立模块，负责能力目录管理、参数校验、即时诊断执行、场景方案编排和历史记录查询。与连接中心、任务中心、工具箱明确边界，不成为新的连接中心或万能工具市场。

## 3. 阶段总览

| 阶段 | 名称 | 工期 | 交付物 | 优先级 | 状态 |
|------|------|------|--------|--------|------|
| **Phase 0** | 数据库迁移 | 2 天 | 数据库迁移脚本 + 测试 | P0 | ✅ 已完成 |
| **Phase 1** | 诊断能力框架 | 3 天 | 后端 API + 数据模型 | P0 | ✅ 已完成 |
| **Phase 2** | 统一执行器 | 3 天 | ArthasCommandExecutor | P0 | ✅ 已完成 |
| **Phase 3** | 即时诊断执行 | 3 天 | 即时诊断 API + 前端 | P0 | ✅ 已完成 |
| **Phase 4** | 场景方案执行 | 4 天 | 多步骤执行 + 数据传递 | P0 | ✅ 已完成 |
| **Phase 5** | 定时任务增强 | 3 天 | 连接管理 + 重试策略 | P1 | ✅ 已完成 |
| **Phase 6** | 定时清理机制 | 2 天 | 清理服务 + 定时调度 | P1 | ✅ 已完成 |
| **Phase 7** | 前端集成测试 | 2 天 | 端到端测试 + 优化 | P1 | ⏳ 部分完成 |

**总计**：22 个工作日（约 4.5 周）

## 4. Phase 0：数据库迁移（2 天）

### 4.1 任务清单

| 任务 ID | 任务名称 | 工作量 | 负责人 | 状态 |
|---------|---------|--------|--------|------|
| P0-1 | 创建 `diagnosis_capabilities` 表 | 2h | 后端 | ⏳ |
| P0-2 | 重命名 `task_runs` → `task_logs` | 1h | 后端 | ⏳ |
| P0-3 | 扩展 `task_logs` 表字段 | 2h | 后端 | ⏳ |
| P0-4 | 创建 `arthas_command_templates` 表 | 1h | 后端 | ⏳ |
| P0-5 | 创建 `diagnosis_scenario_steps` 表 | 1h | 后端 | ⏳ |
| P0-6 | 创建 `ai_diagnosis_handlers` 表 | 1h | 后端 | ⏳ |
| P0-7 | 重命名 `arthas_commands` → `arthas_command_logs` | 1h | 后端 | ⏳ |
| P0-8 | 扩展 `arthas_command_logs` 表字段 | 1h | 后端 | ⏳ |
| P0-9 | 添加 `task_id`/`capability_id` 互斥约束 | 1h | 后端 | ⏳ |
| P0-10 | 编写数据库迁移测试 | 3h | 测试 | ⏳ |

### 4.2 详细任务分解

#### 任务 P0-1：创建 `diagnosis_capabilities` 表

**Files:**
- Modify: `models/db.py`
- Create: `tests/test_db_migration.py`

**Step 1: Write the failing test**

```python
# tests/test_db_migration.py

import pytest
from models.db import get_db_connection

def test_diagnosis_capabilities_table_exists():
    """Test that diagnosis_capabilities table exists"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='diagnosis_capabilities'")
    result = cursor.fetchone()
    conn.close()
    assert result is not None

def test_diagnosis_capabilities_table_structure():
    """Test that diagnosis_capabilities table has correct structure"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(diagnosis_capabilities)")
    columns = {row[1]: row[2] for row in cursor.fetchall()}
    conn.close()
    
    assert 'id' in columns
    assert 'name' in columns
    assert 'type' in columns
    assert 'category' in columns
    assert 'level' in columns
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_db_migration.py::test_diagnosis_capabilities_table_exists -v`
Expected: FAIL with "table does not exist"

**Step 3: Write minimal implementation**

```python
# models/db.py

def init_diagnosis_tables(cursor):
    """初始化诊断能力相关表"""
    
    # 1. diagnosis_capabilities
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS diagnosis_capabilities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            type TEXT NOT NULL,
            category TEXT NOT NULL,
            level INTEGER NOT NULL DEFAULT 1,
            risk_level TEXT DEFAULT 'low',
            parameters_schema TEXT DEFAULT '{}',
            description TEXT,
            estimated_duration INTEGER DEFAULT 10,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (created_by) REFERENCES users(id)
        )
    ''')
    
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_diag_caps_type ON diagnosis_capabilities(type)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_diag_caps_category_level ON diagnosis_capabilities(category, level)')
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_db_migration.py::test_diagnosis_capabilities_table_exists -v`
Expected: PASS

**Step 5: Commit**

```bash
git add models/db.py tests/test_db_migration.py
git commit -m "feat: create diagnosis_capabilities table"
```

### 4.2 实施步骤

#### 步骤 1：创建核心表

```sql
-- models/db.py

def init_diagnosis_tables(cursor):
    """初始化诊断能力相关表"""
    
    # 1. diagnosis_capabilities
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS diagnosis_capabilities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            type TEXT NOT NULL,
            category TEXT NOT NULL,
            level INTEGER NOT NULL DEFAULT 1,
            risk_level TEXT DEFAULT 'low',
            parameters_schema TEXT DEFAULT '{}',
            description TEXT,
            estimated_duration INTEGER DEFAULT 10,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (created_by) REFERENCES users(id)
        )
    ''')
    
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_diag_caps_type ON diagnosis_capabilities(type)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_diag_caps_category_level ON diagnosis_capabilities(category, level)')
    
    # 2. arthas_command_templates（完整字段）
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS arthas_command_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            capability_id INTEGER NOT NULL UNIQUE,
            command_name TEXT NOT NULL,
            command_category TEXT,
            arthas_command TEXT NOT NULL,
            syntax TEXT,
            description TEXT,
            params_json TEXT DEFAULT '[]',
            options_json TEXT DEFAULT '[]',
            examples TEXT,
            doc_url TEXT,
            min_version TEXT,
            tags TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (capability_id) REFERENCES diagnosis_capabilities(id) ON DELETE CASCADE
        )
    ''')
    
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_arthas_cmd_templates_name ON arthas_command_templates(command_name)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_arthas_cmd_templates_category ON arthas_command_templates(command_category)')
```

#### 步骤 2：迁移现有表

```sql
-- 重命名 task_runs → task_logs
ALTER TABLE task_runs RENAME TO task_logs;

-- 新增字段
ALTER TABLE task_logs ADD COLUMN capability_id INTEGER REFERENCES diagnosis_capabilities(id);
ALTER TABLE task_logs ADD COLUMN execution_type TEXT;
ALTER TABLE task_logs ADD COLUMN retention_days INTEGER DEFAULT 30;
ALTER TABLE task_logs ADD COLUMN is_archived INTEGER DEFAULT 0;

-- 添加互斥约束
ALTER TABLE task_logs ADD CONSTRAINT chk_task_source CHECK (
    (task_id IS NULL AND capability_id IS NOT NULL) OR
    (task_id IS NOT NULL)
);

-- 重命名 arthas_commands → arthas_command_logs
ALTER TABLE arthas_commands RENAME TO arthas_command_logs;

-- 新增字段
ALTER TABLE arthas_command_logs ADD COLUMN template_id INTEGER REFERENCES arthas_command_templates(id);
ALTER TABLE arthas_command_logs ADD COLUMN step_order INTEGER;
ALTER TABLE arthas_command_logs ADD COLUMN command_type TEXT;
ALTER TABLE arthas_command_logs ADD COLUMN duration_ms INTEGER;
```

#### 步骤 3：创建扩展表

```sql
-- diagnosis_scenario_steps
CREATE TABLE diagnosis_scenario_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    capability_id INTEGER NOT NULL,
    step_order INTEGER NOT NULL,
    command TEXT NOT NULL,
    desc TEXT,
    timeout_ms INTEGER DEFAULT 60000,
    fail_fast INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (capability_id) REFERENCES diagnosis_capabilities(id) ON DELETE CASCADE,
    UNIQUE(capability_id, step_order)
);

-- ai_diagnosis_handlers
CREATE TABLE ai_diagnosis_handlers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    capability_id INTEGER NOT NULL UNIQUE,
    handler TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (capability_id) REFERENCES diagnosis_capabilities(id) ON DELETE CASCADE,
    CHECK(handler LIKE 'performance_diagnose.%')
);
```

### 4.3 验收标准

- [ ] 所有表创建成功
- [ ] 索引创建成功
- [ ] 外键约束生效
- [ ] 互斥约束生效
- [ ] 数据迁移测试通过
- [ ] 旧数据无损迁移

## 5. Phase 1：诊断能力框架（3 天）

### 5.1 任务清单

| 任务 ID | 任务名称 | 工作量 | 负责人 | 状态 |
|---------|---------|--------|--------|------|
| P1-1 | 实现 `diagnosis_capabilities` CRUD API | 4h | 后端 | ⏳ |
| P1-2 | 实现扩展表 CRUD API | 4h | 后端 | ⏳ |
| P1-3 | 实现能力目录查询 API | 2h | 后端 | ⏳ |
| P1-4 | 实现参数校验引擎 | 3h | 后端 | ⏳ |
| P1-5 | 编写单元测试 | 3h | 测试 | ⏳ |

### 5.2 实施步骤

#### 步骤 1：能力管理 API

```python
# api/task_center.py

@app.route('/api/tasks/capabilities', methods=['GET'])
def list_capabilities():
    """查询诊断能力目录"""
    pass

@app.route('/api/tasks/capabilities', methods=['POST'])
def create_capability():
    """创建诊断能力"""
    pass

@app.route('/api/tasks/capabilities/<int:cap_id>', methods=['PUT'])
def update_capability(cap_id):
    """更新诊断能力"""
    pass

@app.route('/api/tasks/capabilities/<int:cap_id>', methods=['DELETE'])
def delete_capability(cap_id):
    """删除诊断能力"""
    pass
```

#### 步骤 2：参数校验引擎

```python
# backend/core/parameter_validator.py

class ParameterValidator:
    """参数校验引擎"""
    
    @staticmethod
    def validate(schema_str, params):
        """校验参数"""
        if not schema_str or schema_str == '{}':
            return None
        
        schema = json.loads(schema_str)
        
        for field in schema:
            field_name = field['name']
            value = params.get(field_name)
            
            # 1. 必填项检查
            if field.get('required') and field_name not in params:
                return f"缺少必填参数: {field.get('label', field_name)}"
            
            # 2. 类型检查
            # 3. 长度限制
            # 4. 正则校验
            # 5. 枚举值校验
            # 6. 数值范围
        
        return None
```

### 5.3 验收标准

- [ ] 能力 CRUD API 正常工作
- [ ] 扩展表 CRUD API 正常工作
- [ ] 能力目录查询支持过滤（type/category/level）
- [ ] 参数校验引擎支持 6 种校验规则
- [ ] 单元测试覆盖率 > 80%

## 6. Phase 2：统一执行器（3 天）

### 6.1 任务清单

| 任务 ID | 任务名称 | 工作量 | 负责人 | 状态 |
|---------|---------|--------|--------|------|
| P2-1 | 创建 `backend/core/arthas_executor.py` | 4h | 后端 | ⏳ |
| P2-2 | 实现 `execute()` 单条命令执行 | 3h | 后端 | ⏳ |
| P2-3 | 实现 `execute_batch()` 批量执行 | 3h | 后端 | ⏳ |
| P2-4 | 实现高危命令检查 | 2h | 后端 | ⏳ |
| P2-5 | 实现自动超时配置 | 2h | 后端 | ⏳ |
| P2-6 | 改造现有模块复用执行器 | 2h | 后端 | ⏳ |
| P2-7 | 编写单元测试 | 4h | 测试 | ⏳ |

### 6.2 实施步骤

#### 步骤 1：统一执行器（异步 + 线程池）

```python
# backend/core/arthas_executor.py

import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import partial

# 线程池（全局共享）
_executor = ThreadPoolExecutor(max_workers=10)

class ArthasCommandExecutor:
    """统一的 Arthas 命令执行器（异步封装）"""
    
    _COMMAND_TIMEOUT_CONFIG = {
        'dashboard': 15000,
        'thread': 30000,
        'trace': 60000,
        'watch': 60000,
        'profiler': 120000,
        'heapdump': 120000,
    }
    
    _HIGH_RISK_COMMANDS = {
        'redefine', 'retransform', 'heapdump', 'profiler', 'logger'
    }
    
    @staticmethod
    async def execute(connection, command, timeout_ms=None, skip_audit=False, skip_history=False, confirmed=False):
        """执行单条 Arthas 命令（异步封装）"""
        loop = asyncio.get_event_loop()
        
        # 在线程池中执行同步代码
        result = await loop.run_in_executor(
            _executor,
            partial(
                ArthasCommandExecutor._execute_sync,
                connection, command, timeout_ms, skip_audit, skip_history, confirmed
            )
        )
        
        return result
    
    @staticmethod
    def _execute_sync(connection, command, timeout_ms, skip_audit, skip_history, confirmed):
        """同步执行逻辑（在线程池中运行）"""
        # 1. 高危命令检查
        # 2. 自动超时配置
        # 3. 执行命令
        # 4. 脱敏处理
        # 5. 记录命令历史
        # 6. 记录审计日志
        pass
    
    @staticmethod
    async def execute_batch(connection, commands, timeout_ms=None, fail_fast=True):
        """批量执行 Arthas 命令（异步封装）"""
        loop = asyncio.get_event_loop()
        
        result = await loop.run_in_executor(
            _executor,
            partial(
                ArthasCommandExecutor._execute_batch_sync,
                connection, commands, timeout_ms, fail_fast
            )
        )
        
        return result
    
    @staticmethod
    def _execute_batch_sync(connection, commands, timeout_ms, fail_fast):
        """批量执行同步逻辑（在线程池中运行）"""
        # 1. 逐步执行命令列表
        # 2. 支持 fail_fast
        # 3. 记录总体审计日志
        pass
```

### 6.3 验收标准

- [ ] 统一执行器正常工作
- [ ] 高危命令检查生效
- [ ] 自动超时配置生效
- [ ] 现有模块成功复用执行器
- [ ] 单元测试覆盖率 > 85%

## 7. Phase 3：即时诊断执行（3 天）

### 7.1 任务清单

| 任务 ID | 任务名称 | 工作量 | 负责人 | 状态 |
|---------|---------|--------|--------|------|
| P3-1 | 实现即时诊断执行 API | 4h | 后端 | ⏳ |
| P3-2 | 实现能力加载器 `load_extension()` | 2h | 后端 | ⏳ |
| P3-3 | 实现命令构建器 `build_command()` | 2h | 后端 | ⏳ |
| P3-4 | 实现执行结果记录 | 2h | 后端 | ⏳ |
| P3-5 | 前端能力卡片展示 | 3h | 前端 | ⏳ |
| P3-6 | 前端参数表单动态生成 | 3h | 前端 | ⏳ |
| P3-7 | 编写集成测试 | 4h | 测试 | ⏳ |

### 7.2 实施步骤

#### 步骤 1：即时诊断 API

```python
# api/task_center.py

@app.route('/api/diagnosis/execute', methods=['POST'])
async def execute_diagnosis():
    """即时诊断执行"""
    data = request.json
    
    # 1. 获取能力定义
    capability = db.fetch_one(
        'SELECT * FROM diagnosis_capabilities WHERE id = ?',
        (data['capability_id'],)
    )
    
    # 2. 加载扩展数据
    extension = load_extension(capability['type'], capability['id'])
    
    # 3. 参数校验
    error = ParameterValidator.validate(capability['parameters_schema'], data.get('params', {}))
    if error:
        return jsonify({'error': error}), 400
    
    # 4. 执行诊断
    if capability['type'] == 'arthas_command':
        result = await execute_arthas_command(capability, extension, data)
    elif capability['type'] == 'diagnosis_scenario':
        result = await execute_scenario(capability, extension, data)
    elif capability['type'] == 'ai_diagnosis':
        result = await execute_ai_diagnosis(capability, extension, data)
    
    # 5. 记录执行日志（task_logs）
    log_id = str(uuid4())
    db.insert('task_logs', {
        'id': log_id,
        'task_id': None,  # 即时诊断为空
        'capability_id': capability['id'],
        'user_id': session['user_id'],
        'execution_mode': 'immediate',
        'execution_type': 'diagnosis',
        'status': 'success',
        'result_json': json.dumps(result),
        'duration_ms': result.get('duration_ms', 0),
        'started_at': datetime.now(),
        'finished_at': datetime.now(),
    })
    
    return jsonify({'ok': True, 'log_id': log_id, 'result': result})
```

### 7.3 验收标准

- [ ] 即时诊断 API 正常工作
- [ ] 能力加载器支持 4 种类型
- [ ] 参数校验生效
- [ ] 执行日志正确记录到 `task_logs`
- [ ] 前端能力卡片正常展示
- [ ] 参数表单动态生成
- [ ] 集成测试通过

## 8. Phase 4：场景方案执行（4 天）

### 8.1 任务清单

| 任务 ID | 任务名称 | 工作量 | 负责人 | 状态 |
|---------|---------|--------|--------|------|
| P4-1 | 实现场景方案执行器 | 4h | 后端 | ⏳ |
| P4-2 | 实现 `${stepN.field}` 跨步数据传递 | 4h | 后端 | ⏳ |
| P4-3 | 实现 `fail_fast` 控制 | 2h | 后端 | ⏳ |
| P4-4 | 实现步骤超时独立配置 | 2h | 后端 | ⏳ |
| P4-5 | 前端场景方案执行进度展示 | 4h | 前端 | ⏳ |
| P4-6 | 编写集成测试 | 4h | 测试 | ⏳ |

### 8.2 实施步骤

#### 步骤 1：场景方案执行器

```python
# api/task_center.py

import re

async def execute_scenario(capability, extension, task_def, connection):
    """执行场景方案（多步骤）"""
    
    # 1. 参数校验
    params = json.loads(task_def.get('params_json', '{}'))
    error = ParameterValidator.validate(capability['parameters_schema'], params)
    if error:
        raise ValueError(error)
    
    # 2. 解析步骤
    steps = extension.get('steps', [])
    if not steps:
        raise ValueError('场景方案未配置步骤')
    
    # 3. 执行步骤（支持跨步数据传递）
    step_outputs = {}
    step_results = []
    
    for step in steps:
        # 构建命令（支持 ${stepN.field} 语法）
        command = build_command(step['command'], params, step_outputs)
        
        # 执行命令
        try:
            result = await ArthasCommandExecutor.execute(
                connection,
                command,
                timeout_ms=step.get('timeout_ms'),
            )
            
            # 记录步骤输出（供后续步骤引用）
            step_outputs[f"step{step['step_order']}"] = result
            
            step_results.append({
                'step_order': step['step_order'],
                'command': command,
                'success': True,
                'result': result,
            })
            
        except Exception as e:
            step_results.append({
                'step_order': step['step_order'],
                'command': command,
                'success': False,
                'error': str(e),
            })
            
            # fail_fast 控制
            if step.get('fail_fast', 1):
                break
    
    # 4. 判断整体状态
    all_success = all(r['success'] for r in step_results)
    status = 'success' if all_success else 'partial'
    
    return {
        'status': status,
        'total_steps': len(steps),
        'completed_steps': len(step_results),
        'steps': step_results,
    }
```

### 8.3 验收标准

- [ ] 场景方案执行器正常工作
- [ ] `${stepN.field}` 跨步数据传递生效
- [ ] `fail_fast` 控制生效
- [ ] 步骤超时独立配置生效
- [ ] 前端执行进度实时展示
- [ ] 集成测试通过

## 9. 后续阶段

### Phase 5：定时任务增强（3 天）
- 连接健康检查
- 自动重连机制
- 重试策略（指数退避）
- 失败告警

### Phase 6：定时清理机制（2 天）
- 归档表创建
- 清理服务实现
- 定时调度配置

### Phase 7：前端集成测试（2 天）
- 端到端测试：即时诊断
- 端到端测试：场景方案
- 端到端测试：定时任务
- 性能测试：并发执行

## 10. 风险评估

| 风险项 | 影响 | 概率 | 缓解措施 |
|--------|------|------|----------|
| 数据库迁移失败 | 高 | 低 | 备份数据库，支持回滚 |
| 旧数据兼容问题 | 中 | 中 | 编写数据迁移测试 |
| 场景方案跨步数据传递实现复杂 | 中 | 高 | 使用 JSONPath 库简化 |
| 定时任务并发冲突 | 高 | 中 | 分布式锁控制 |
| `task_logs` 单表性能瓶颈 | 中 | 低 | 定时清理 + 索引优化 |

## 11. 验收清单

### 11.1 功能验收

- [ ] 诊断能力 CRUD 正常
- [ ] 即时诊断执行正常
- [ ] 场景方案执行正常（含跨步数据传递）
- [ ] 定时任务执行正常（含连接健康检查 + 重试）
- [ ] 定时清理机制正常
- [ ] 前端能力目录展示正常
- [ ] 前端参数表单动态生成正常

### 11.2 性能验收

- [ ] 能力目录查询响应时间 < 500ms
- [ ] 即时诊断执行响应时间 < 5s
- [ ] 场景方案执行响应时间 < 60s
- [ ] 并发 100 用户，系统稳定

### 11.3 数据验收

- [ ] 旧数据无损迁移
- [ ] `task_logs` 互斥约束生效
- [ ] 外键约束生效
- [ ] 定时清理无数据丢失