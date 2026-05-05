# 任务中心重构实施计划

> 基于设计文档：[2026-05-04-task-center-diagnosis-refactor.md](../specs/2026-05-04-task-center-diagnosis-refactor.md)

**文档版本**: v1.0  
**创建日期**: 2026-05-04  
**状态**: 待评审  
**预计工期**: 4 周（20 个工作日）

---

## 1. 实施概述

### 1.1 核心目标

- ✅ 搭建诊断能力框架（Capability + Extension 模式）
- ✅ 实现即时诊断直接执行
- ✅ 实现统一执行器 `ArthasCommandExecutor`
- ✅ 实现场景方案步骤间数据传递（P0）
- ✅ 实现定时任务连接健康检查 + 重试策略
- ✅ 实现 `task_logs` 定时清理机制

### 1.2 不兼容项

- ❌ 不兼容旧版 `task_definitions` + `task_runs` 架构
- ❌ 不兼容 `_USER_CASE_CAPABILITIES` 硬编码预制模板
- ❌ 不兼容旧的 `arthas_commands` 表结构（需迁移）

### 1.3 实施原则

1. **框架先行**：先搭建数据模型和核心框架，再逐步填充功能
2. **向后兼容**：旧版 `arthas_commands` 通过重命名保留数据
3. **渐进式迁移**：先新后旧，逐步替换现有模块
4. **测试驱动**：每个阶段必须通过单元测试

---

## 2. 阶段划分

| 阶段 | 名称 | 工期 | 交付物 | 优先级 |
|------|------|------|--------|--------|
| **Phase 0** | 数据库迁移 | 2 天 | 数据库迁移脚本 + 测试 | P0 |
| **Phase 1** | 诊断能力框架 | 3 天 | 后端 API + 数据模型 | P0 |
| **Phase 2** | 统一执行器 | 3 天 | ArthasCommandExecutor | P0 |
| **Phase 3** | 即时诊断执行 | 3 天 | 即时诊断 API + 前端 | P0 |
| **Phase 4** | 场景方案执行 | 4 天 | 多步骤执行 + 数据传递 | P0 |
| **Phase 5** | 定时任务增强 | 3 天 | 连接管理 + 重试策略 | P1 |
| **Phase 6** | 定时清理机制 | 2 天 | 清理服务 + 定时调度 | P1 |
| **Phase 7** | 前端集成测试 | 2 天 | 端到端测试 + 优化 | P1 |

**总计**：22 个工作日（约 4.5 周）

---

## 3. Phase 0：数据库迁移（2 天）

### 3.1 任务清单

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

### 3.2 实施步骤

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
-- arthas_command_templates
CREATE TABLE arthas_command_templates (
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
);

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

-- script_templates 扩展
ALTER TABLE script_templates ADD COLUMN capability_id INTEGER REFERENCES diagnosis_capabilities(id);
```

### 3.3 验收标准

- [ ] 所有表创建成功
- [ ] 索引创建成功
- [ ] 外键约束生效
- [ ] 互斥约束生效
- [ ] 数据迁移测试通过
- [ ] 旧数据无损迁移

---

## 4. Phase 1：诊断能力框架（3 天）

### 4.1 任务清单

| 任务 ID | 任务名称 | 工作量 | 负责人 | 状态 |
|---------|---------|--------|--------|------|
| P1-1 | 实现 `diagnosis_capabilities` CRUD API | 4h | 后端 | ⏳ |
| P1-2 | 实现扩展表 CRUD API | 4h | 后端 | ⏳ |
| P1-3 | 实现能力目录查询 API | 2h | 后端 | ⏳ |
| P1-4 | 实现参数校验引擎 | 3h | 后端 | ⏳ |
| P1-5 | 编写单元测试 | 3h | 测试 | ⏳ |

### 4.2 实施步骤

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

### 4.3 验收标准

- [ ] 能力 CRUD API 正常工作
- [ ] 扩展表 CRUD API 正常工作
- [ ] 能力目录查询支持过滤（type/category/level）
- [ ] 参数校验引擎支持 6 种校验规则
- [ ] 单元测试覆盖率 > 80%

---

## 5. Phase 2：统一执行器（3 天）

### 5.1 任务清单

| 任务 ID | 任务名称 | 工作量 | 负责人 | 状态 |
|---------|---------|--------|--------|------|
| P2-1 | 创建 `backend/core/arthas_executor.py` | 4h | 后端 | ⏳ |
| P2-2 | 实现 `execute()` 单条命令执行 | 3h | 后端 | ⏳ |
| P2-3 | 实现 `execute_batch()` 批量执行 | 3h | 后端 | ⏳ |
| P2-4 | 实现高危命令检查 | 2h | 后端 | ⏳ |
| P2-5 | 实现自动超时配置 | 2h | 后端 | ⏳ |
| P2-6 | 改造现有模块复用执行器 | 2h | 后端 | ⏳ |
| P2-7 | 编写单元测试 | 4h | 测试 | ⏳ |

### 5.2 实施步骤

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
        """执行单条 Arthas 命令（异步封装）
        
        使用 asyncio + 线程池实现异步：
        1. Flask 是同步框架，通过线程池实现异步
        2. 避免阻塞 Flask 主线程
        3. 支持并发执行多个诊断任务
        """
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

#### 步骤 2：改造现有模块

```python
# server.py（改造前）
result = conn.http_client.exec_once(command)

# server.py（改造后）
from backend.core.arthas_executor import ArthasCommandExecutor
result = await ArthasCommandExecutor.execute(conn, command)

# api/performance_diagnose.py（改造后）
dash_resp = await ArthasCommandExecutor.execute(connection, "dashboard -n 1")
thread_resp = await ArthasCommandExecutor.execute(connection, "thread -n 15")
```

### 5.3 验收标准

- [ ] 统一执行器正常工作
- [ ] 高危命令检查生效
- [ ] 自动超时配置生效
- [ ] 现有模块成功复用执行器
- [ ] 单元测试覆盖率 > 85%

---

## 6. Phase 3：即时诊断执行（3 天）

### 6.1 任务清单

| 任务 ID | 任务名称 | 工作量 | 负责人 | 状态 |
|---------|---------|--------|--------|------|
| P3-1 | 实现即时诊断执行 API | 4h | 后端 | ⏳ |
| P3-2 | 实现能力加载器 `load_extension()` | 2h | 后端 | ⏳ |
| P3-3 | 实现命令构建器 `build_command()` | 2h | 后端 | ⏳ |
| P3-4 | 实现执行结果记录 | 2h | 后端 | ⏳ |
| P3-5 | 前端能力卡片展示 | 3h | 前端 | ⏳ |
| P3-6 | 前端参数表单动态生成 | 3h | 前端 | ⏳ |
| P3-7 | 编写集成测试 | 4h | 测试 | ⏳ |

### 6.2 实施步骤

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

#### 步骤 2：前端能力卡片

```javascript
// static/js/components/diagnosis.js

async function renderDiagnosisCapabilities() {
  const capabilities = await safeGet('/tasks/capabilities');
  
  const el = document.getElementById('diagnosisCapList');
  el.innerHTML = capabilities.map(cap => `
    <div class="capability-card">
      <div class="capability-header">
        <h4>${escapeHtml(cap.name)}</h4>
        <div class="badges">
          ${getLevelBadge(cap.level)}
          ${getRiskBadge(cap.risk_level)}
        </div>
      </div>
      
      <p class="capability-desc">${escapeHtml(cap.description || '')}</p>
      
      <div class="capability-meta">
        <span>⏱ 预计 ${cap.estimated_duration || 10}s</span>
        <span>📂 ${getCategoryLabel(cap.category)}</span>
      </div>
      
      <div class="capability-actions">
        ${hasParams(cap) 
          ? `<button class="btn btn-g" onclick="showCapabilityForm(${cap.id})">配置参数</button>`
          : `<button class="btn btn-p" onclick="executeCapability(${cap.id})">执行诊断</button>`
        }
      </div>
    </div>
  `).join('');
}
```

### 6.3 验收标准

- [ ] 即时诊断 API 正常工作
- [ ] 能力加载器支持 4 种类型
- [ ] 参数校验生效
- [ ] 执行日志正确记录到 `task_logs`
- [ ] 前端能力卡片正常展示
- [ ] 参数表单动态生成
- [ ] 集成测试通过

---

## 7. Phase 4：场景方案执行（4 天）

### 7.1 任务清单

| 任务 ID | 任务名称 | 工作量 | 负责人 | 状态 |
|---------|---------|--------|--------|------|
| P4-1 | 实现场景方案执行器 | 4h | 后端 | ⏳ |
| P4-2 | 实现 `${stepN.field}` 跨步数据传递 | 4h | 后端 | ⏳ |
| P4-3 | 实现 `fail_fast` 控制 | 2h | 后端 | ⏳ |
| P4-4 | 实现步骤超时独立配置 | 2h | 后端 | ⏳ |
| P4-5 | 前端场景方案执行进度展示 | 4h | 前端 | ⏳ |
| P4-6 | 编写集成测试 | 4h | 测试 | ⏳ |

### 7.2 实施步骤

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

#### 步骤 2：跨步数据传递

```python
# backend/core/command_builder.py

import re

def build_command(command_template, params, step_outputs=None):
    """构建 Arthas 命令（支持跨步数据传递）
    
    支持的语法：
    - ${param}           → 用户参数
    - ${param:-default}  → 带默认值替换
    - ${step1.output}    → 引用步骤 1 完整输出
    - ${step1.thread_id} → 引用步骤 1 输出的特定字段（支持嵌套：step1.data.cpu_usage）
    """
    command = command_template
    
    # 1. 替换用户参数
    for key, value in params.items():
        command = command.replace(f'${{{key}}}', str(value))
    
    # 2. 处理默认值
    pattern = r'\$\{(\w+):-([^}]*)\}'
    def replace_default(match):
        key = match.group(1)
        default = match.group(2)
        return params.get(key, default)
    
    command = re.sub(pattern, replace_default, command)
    
    # 3. 引用步骤输出（跨步数据传递）
    if step_outputs:
        pattern = r'\$\{step(\d+)\.([\w.]+)\}'
        def replace_step_output(match):
            step_order = match.group(1)
            field_path = match.group(2)
            
            step_key = f"step{step_order}"
            if step_key not in step_outputs:
                return ''
            
            output = step_outputs[step_key]
            
            # 使用原生 Python 提取字段（支持嵌套）
            try:
                return extract_nested_value(output, field_path)
            except Exception:
                return ''
        
        command = re.sub(pattern, replace_step_output, command)
    
    return command


def extract_nested_value(data, field_path):
    """从嵌套字典/列表中提取值
    
    示例：
    - extract_nested_value({'data': {'cpu': 80}}, 'data.cpu') → 80
    - extract_nested_value({'threads': [{'id': 1}]}, 'threads.0.id') → 1
    """
    keys = field_path.split('.')
    current = data
    
    for key in keys:
        if isinstance(current, dict):
            current = current[key]
        elif isinstance(current, list):
            current = current[int(key)]
        else:
            raise KeyError(f"Cannot access '{key}' on {type(current)}")
    
    return current
```

**说明**：
- ✅ 无需外部依赖，使用原生 Python 实现
- ✅ 支持嵌套字典/列表访问
- ✅ 支持数组索引（`threads.0.id`）

### 7.3 验收标准

- [ ] 场景方案执行器正常工作
- [ ] `${stepN.field}` 跨步数据传递生效
- [ ] `fail_fast` 控制生效
- [ ] 步骤超时独立配置生效
- [ ] 前端执行进度实时展示
- [ ] 集成测试通过

---

## 8. Phase 5：定时任务增强（3 天）

### 8.1 任务清单

| 任务 ID | 任务名称 | 工作量 | 负责人 | 状态 |
|---------|---------|--------|--------|------|
| P5-1 | 扩展 `task_schedules` 表字段 | 1h | 后端 | ⏳ |
| P5-2 | 实现连接健康检查 | 3h | 后端 | ⏳ |
| P5-3 | 实现自动重连机制 | 3h | 后端 | ⏳ |
| P5-4 | 实现重试策略（指数退避） | 3h | 后端 | ⏳ |
| P5-5 | 实现失败告警（邮件/钉钉/企业微信） | 4h | 后端 | ⏳ |
| P5-6 | 实现分布式锁（并发控制） | 3h | 后端 | ⏳ |
| P5-7 | 编写集成测试 | 3h | 测试 | ⏳ |

### 8.2 实施步骤

#### 步骤 1：扩展调度表

```sql
ALTER TABLE task_schedules ADD COLUMN connection_ttl INTEGER DEFAULT 300;
ALTER TABLE task_schedules ADD COLUMN retry_policy TEXT DEFAULT '{"max_retries": 3, "backoff": "exponential", "initial_delay_ms": 1000}';
ALTER TABLE task_schedules ADD COLUMN alert_channels TEXT DEFAULT '["email"]';
```

#### 步骤 2：连接健康检查

```python
# backend/core/task_scheduler.py

import threading
import time

class TaskScheduler:
    """定时任务调度器"""
    
    # 应用层分布式锁（SQLite 方案）
    _locks = {}
    _lock_mutex = threading.Lock()
    
    @staticmethod
    def acquire_lock(key: str, timeout: int = 3600) -> bool:
        """获取分布式锁（应用层实现，无需 Redis）"""
        with TaskScheduler._lock_mutex:
            if key in TaskScheduler._locks:
                lock_time = TaskScheduler._locks[key]
                if time.time() - lock_time < timeout:
                    return False  # 锁已被占用
            TaskScheduler._locks[key] = time.time()
            return True
    
    @staticmethod
    def release_lock(key: str):
        """释放分布式锁"""
        with TaskScheduler._lock_mutex:
            TaskScheduler._locks.pop(key, None)
    
    async def execute_scheduled_task(self, schedule_id: int):
        """执行定时任务（带连接健康检查）"""
        
        # 1. 获取调度配置
        schedule = db.fetch_one(
            'SELECT * FROM task_schedules WHERE id = ?',
            (schedule_id,)
        )
        
        # 2. 获取分布式锁（应用层）
        lock_key = f"task_schedule:{schedule_id}"
        acquired = self.acquire_lock(lock_key, timeout=3600)
        
        if not acquired:
            logger.warning(f"任务 {schedule_id} 正在执行中，跳过")
            return
        
        try:
            # 3. 获取或创建连接
            connection = await self.get_or_create_connection(schedule)
            
            # 4. 检查连接健康
            if not await self.is_connection_healthy(connection, schedule):
                connection = await self.reconnect(connection, schedule)
            
            # 5. 执行任务（带重试）
            retry_policy = json.loads(schedule['retry_policy'])
            last_error = None
            
            for attempt in range(retry_policy['max_retries']):
                try:
                    result = await self.execute_task(schedule['task_id'], connection)
                    self.log_success(schedule, result)
                    return result
                    
                except Exception as e:
                    last_error = e
                    
                    if attempt < retry_policy['max_retries'] - 1:
                        delay = self.calculate_delay(retry_policy, attempt)
                        await asyncio.sleep(delay)
                        
                        # 重新检查连接
                        if not await self.is_connection_healthy(connection, schedule):
                            connection = await self.reconnect(connection, schedule)
            
            # 6. 所有重试失败，触发告警
            await self.alert_on_failure(schedule, last_error)
            self.log_failure(schedule, last_error)
            raise last_error
            
        finally:
            self.release_lock(lock_key)
    
    async def is_connection_healthy(self, connection, schedule) -> bool:
        """检查连接是否健康"""
        # 1. 检查连接是否过期
        ttl = schedule.get('connection_ttl', 300)
        if connection.created_at + timedelta(seconds=ttl) < datetime.now():
            return False
        
        # 2. 检查 Arthas 是否可达
        try:
            response = await connection.http_client.ping()
            return response.get('state') == 'SUCCEEDED'
        except Exception:
            return False
    
    def calculate_delay(self, retry_policy: dict, attempt: int) -> float:
        """计算重试延迟（指数退避）"""
        backoff = retry_policy.get('backoff', 'exponential')
        initial_delay = retry_policy.get('initial_delay_ms', 1000) / 1000
        max_delay = retry_policy.get('max_delay_ms', 30000) / 1000
        
        if backoff == 'exponential':
            delay = initial_delay * (2 ** attempt)
        else:  # fixed
            delay = initial_delay
        
        return min(delay, max_delay)
```

### 8.3 验收标准

- [ ] 连接健康检查生效
- [ ] 自动重连机制正常
- [ ] 重试策略生效（指数退避）
- [ ] 失败告警正常发送
- [ ] 分布式锁防止并发执行
- [ ] 集成测试通过

---

## 9. Phase 6：定时清理机制（2 天）

### 9.1 任务清单

| 任务 ID | 任务名称 | 工作量 | 负责人 | 状态 |
|---------|---------|--------|--------|------|
| P6-1 | 创建 `task_logs_archive` 归档表 | 1h | 后端 | ⏳ |
| P6-2 | 实现 `TaskLogsCleanupService` | 4h | 后端 | ⏳ |
| P6-3 | 配置定时调度（APScheduler） | 2h | 后端 | ⏳ |
| P6-4 | 实现手动触发清理 API | 2h | 后端 | ⏳ |
| P6-5 | 编写清理测试 | 3h | 测试 | ⏳ |

### 9.2 实施步骤

#### 步骤 0：创建系统配置表（配置化清理策略）

```sql
-- 创建系统配置表
CREATE TABLE IF NOT EXISTS system_configs (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    description TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 插入默认清理策略
INSERT INTO system_configs (key, value, description) VALUES
('task_logs.retention_days', '30', 'task_logs 活跃日志保留天数'),
('task_logs_archive.retention_days', '365', 'task_logs_archive 归档日志保留天数'),
('arthas_command_logs.retention_days', '30', 'arthas_command_logs 保留天数'),
('task_logs.cleanup_cron', '0 3 * * *', 'task_logs 清理定时任务 Cron 表达式'),
('task_logs_archive.cleanup_cron', '0 4 1 * *', 'task_logs_archive 清理定时任务 Cron 表达式');
```

**读取配置**：
```python
# services/task_logs_cleanup_service.py

def get_cleanup_config(key: str, default: str) -> str:
    """从 system_configs 读取清理配置"""
    result = db.fetch_one(
        'SELECT value FROM system_configs WHERE key = ?',
        (key,)
    )
    return result['value'] if result else default

# 使用示例
retention_days = int(get_cleanup_config('task_logs.retention_days', '30'))
cleanup_cron = get_cleanup_config('task_logs.cleanup_cron', '0 3 * * *')
```

#### 步骤 1：创建归档表

```sql
CREATE TABLE task_logs_archive (
    id TEXT PRIMARY KEY,
    task_id INTEGER,
    capability_id INTEGER,
    user_id INTEGER,
    execution_mode TEXT NOT NULL,
    execution_type TEXT NOT NULL,
    target_json TEXT,
    params_json TEXT,
    status TEXT NOT NULL,
    stdout TEXT,
    stderr TEXT,
    exit_code INTEGER,
    result_json TEXT,
    error_message TEXT,
    duration_ms INTEGER,
    work_dir TEXT,
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    created_at TIMESTAMP,
    retention_days INTEGER,
    is_archived INTEGER DEFAULT 1,
    archived_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_task_logs_archive_finished_at ON task_logs_archive(finished_at);
```

#### 步骤 2：清理服务

```python
# services/task_logs_cleanup_service.py

class TaskLogsCleanupService:
    """task_logs 定时清理服务"""
    
    async def cleanup_expired_logs(self):
        """清理过期的 task_logs"""
        
        # 1. 查询过期日志
        expired_logs = db.fetch_all(
            """
            SELECT id FROM task_logs 
            WHERE is_archived = 0 
              AND finished_at < datetime('now', '-' || retention_days || ' days')
            """
        )
        
        if not expired_logs:
            return
        
        # 2. 归档到历史表
        for log in expired_logs:
            await self.archive_log(log['id'])
        
        # 3. 删除过期日志
        db.execute(
            """
            DELETE FROM task_logs 
            WHERE is_archived = 0 
              AND finished_at < datetime('now', '-' || retention_days || ' days')
            """
        )
        
        # 4. 清理关联数据（task_artifacts 级联删除）
        db.execute(
            """
            DELETE FROM task_artifacts 
            WHERE run_id NOT IN (SELECT id FROM task_logs)
            """
        )
        
        # 5. 清理孤立的 arthas_command_logs（独立清理）
        db.execute(
            """
            DELETE FROM arthas_command_logs 
            WHERE connection_id NOT IN (SELECT id FROM connections)
              AND timestamp < datetime('now', '-30 days')
            """
        )
    
    async def archive_log(self, log_id: str):
        """归档日志到历史表"""
        # 1. 复制到历史表
        db.execute(
            """
            INSERT INTO task_logs_archive 
            SELECT *, CURRENT_TIMESTAMP as archived_at
            FROM task_logs WHERE id = ?
            """,
            (log_id,)
        )
        
        # 2. 标记为已归档
        db.execute(
            'UPDATE task_logs SET is_archived = 1 WHERE id = ?',
            (log_id,)
        )
```

#### 步骤 3：配置定时调度

```python
# server.py

from apscheduler.schedulers.background import BackgroundScheduler
from services.task_logs_cleanup_service import TaskLogsCleanupService

scheduler = BackgroundScheduler()

# 每天凌晨 3 点清理过期日志
scheduler.add_job(
    TaskLogsCleanupService().cleanup_expired_logs,
    'cron',
    hour=3,
    minute=0,
    id='cleanup_task_logs'
)

# 每月 1 号清理旧归档
scheduler.add_job(
    TaskLogsCleanupService().cleanup_old_archives,
    'cron',
    day=1,
    hour=4,
    minute=0,
    id='cleanup_old_archives'
)

scheduler.start()
```

### 9.3 验收标准

- [ ] 归档表创建成功
- [ ] 清理服务正常工作
- [ ] 定时调度生效
- [ ] 手动触发清理 API 正常
- [ ] 清理测试通过
- [ ] 数据无损归档

---

## 10. Phase 7：前端集成测试（2 天）

### 10.1 任务清单

| 任务 ID | 任务名称 | 工作量 | 负责人 | 状态 |
|---------|---------|--------|--------|------|
| P7-1 | 端到端测试：即时诊断 | 3h | 测试 | ⏳ |
| P7-2 | 端到端测试：场景方案 | 3h | 测试 | ⏳ |
| P7-3 | 端到端测试：定时任务 | 2h | 测试 | ⏳ |
| P7-4 | 性能测试：并发执行 | 2h | 测试 | ⏳ |
| P7-5 | 兼容性测试：旧数据迁移 | 2h | 测试 | ⏳ |
| P7-6 | 编写测试报告 | 2h | 测试 | ⏳ |

### 10.2 前端组件文件清单

#### 完整文件清单

```
static/js/components/
├── diagnosis.js                # 诊断能力主组件（能力卡片列表）
├── diagnosis-form.js           # 参数表单组件（动态生成表单）
├── diagnosis-result.js         # 执行结果组件（结果展示）
├── diagnosis-progress.js       # 执行进度组件（场景方案步骤进度）
└── diagnosis-history.js        # 历史记录组件（task_logs 查询）

static/css/components/
└── diagnosis.css               # 诊断能力样式

static/js/core/
├── api.js                      # API 请求封装（扩展诊断 API）
└── websocket-client.js         # WebSocket 客户端（实时日志）
```

#### 组件职责说明

| 组件文件 | 职责 | 关键函数 |
|---------|------|----------|
| `diagnosis.js` | 能力卡片展示 | `renderDiagnosisCapabilities()`, `executeCapability()` |
| `diagnosis-form.js` | 参数表单动态生成 | `renderParameterForm(schema)`, `validateForm()` |
| `diagnosis-result.js` | 执行结果展示 | `renderResult(result)`, `downloadArtifact()` |
| `diagnosis-progress.js` | 场景方案进度 | `renderStepProgress(steps)`, `updateStepStatus()` |
| `diagnosis-history.js` | 历史记录查询 | `loadHistory()`, `filterByCapability()` |

#### `diagnosis-form.js` 示例

```javascript
// static/js/components/diagnosis-form.js

/**
 * 渲染参数表单（根据 parameters_schema 动态生成）
 */
function renderParameterForm(capabilityId) {
  // 1. 获取能力定义
  fetch(`/api/tasks/capabilities/${capabilityId}`)
    .then(res => res.json())
    .then(cap => {
      const schema = JSON.parse(cap.parameters_schema || '{}');
      const el = document.getElementById('diagnosisForm');
      
      // 2. 动态生成表单
      el.innerHTML = `
        <form id="capForm-${cap.id}" onsubmit="executeCapabilityWithParams(event, ${cap.id})">
          ${schema.map(field => renderFormField(field)).join('')}
          <button type="submit" class="btn btn-p">执行诊断</button>
        </form>
      `;
    });
}

/**
 * 渲染单个表单字段
 */
function renderFormField(field) {
  const required = field.required ? 'required' : '';
  const placeholder = field.description || '';
  
  switch (field.type) {
    case 'select':
      return `
        <div class="form-group">
          <label>${field.label} ${field.required ? '*' : ''}</label>
          <select name="${field.name}" ${required}>
            ${field.options.map(opt => `<option value="${opt.value}">${opt.label}</option>`).join('')}
          </select>
        </div>
      `;
    case 'textarea':
      return `
        <div class="form-group">
          <label>${field.label} ${field.required ? '*' : ''}</label>
          <textarea name="${field.name}" placeholder="${placeholder}" ${required}></textarea>
        </div>
      `;
    default:  // text, number
      return `
        <div class="form-group">
          <label>${field.label} ${field.required ? '*' : ''}</label>
          <input type="${field.type || 'text'}" name="${field.name}" 
                 placeholder="${placeholder}" 
                 pattern="${field.pattern || ''}" 
                 ${required} />
        </div>
      `;
  }
}

/**
 * 提交表单并执行诊断
 */
async function executeCapabilityWithParams(event, capabilityId) {
  event.preventDefault();
  
  const form = document.getElementById(`capForm-${capabilityId}`);
  const formData = new FormData(form);
  const params = Object.fromEntries(formData.entries());
  
  // 执行诊断
  const result = await fetch('/api/diagnosis/execute', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ capability_id: capabilityId, params }),
  }).then(res => res.json());
  
  // 展示结果
  if (result.ok) {
    renderDiagnosisResult(result.result);
  } else {
    showError(result.error);
  }
}
```

### 10.3 测试场景

#### 场景 1：即时诊断

```
1. 用户选择 "Trace 调用链分析" 能力
2. 填写参数：class=com.example.OrderService, method=createOrder
3. 点击"执行诊断"
4. 验证：
   - task_logs 记录正确（task_id=NULL, capability_id≠NULL）
   - 执行结果正常返回
   - arthas_command_logs 记录命令
```

#### 场景 2：场景方案

```
1. 用户选择 "接口响应慢诊断" 场景
2. 填写参数：controller=com.example.OrderController
3. 点击"执行诊断"
4. 验证：
   - Step 1: trace ${controller} ${method} 执行成功
   - Step 2: watch ${step1.slow_class} ${step1.slow_method} 执行成功（跨步数据传递）
   - Step 3: profiler start 执行成功
   - task_logs 记录整体结果
```

#### 场景 3：定时任务

```
1. 创建定时任务：每天凌晨 2 点执行 "CPU 性能分析"
2. 配置连接 TTL=300s，重试策略=指数退避
3. 等待定时触发
4. 验证：
   - 连接健康检查生效
   - 任务执行成功
   - task_logs 记录正确（task_id≠NULL, execution_mode='scheduled'）
```

### 10.4 验收标准

- [ ] 所有端到端测试通过
- [ ] 性能测试达标（并发 100 用户，响应时间 < 2s）
- [ ] 旧数据无损迁移
- [ ] 测试报告输出

### 10.5 测试覆盖率测量

**测试命令**：
```bash
# 运行测试 + 生成覆盖率报告
pytest tests/ --cov=api --cov=backend --cov=services --cov-report=html --cov-report=term

# 查看覆盖率报告
open htmlcov/index.html
```

**覆盖率目标**：
| 测试类型 | 目标 | 测量范围 |
|---------|------|----------|
| 单元测试 | > 80% | `api/`, `backend/`, `services/` |
| 集成测试 | 核心 API 100% | 诊断执行、场景方案、定时任务 |
| 端到端测试 | 7 个核心场景 | 即时诊断、场景方案、定时任务 |

**核心测试场景**：
1. 即时诊断执行（`test_immediate_diagnosis.py`）
2. 场景方案跨步数据传递（`test_scenario_step_data_passing.py`）
3. 定时任务连接健康检查（`test_scheduled_task_health_check.py`）
4. 定时任务重试策略（`test_scheduled_task_retry.py`）
5. task_logs 定时清理（`test_task_logs_cleanup.py`）
6. arthas_command_logs 独立清理（`test_arthas_command_logs_cleanup.py`）
7. 参数校验引擎（`test_parameter_validator.py`）

---

## 11. 风险评估

| 风险项 | 影响 | 概率 | 缓解措施 |
|--------|------|------|----------|
| 数据库迁移失败 | 高 | 低 | 备份数据库，支持回滚 |
| 旧数据兼容问题 | 中 | 中 | 编写数据迁移测试 |
| 场景方案跨步数据传递实现复杂 | 中 | 高 | 使用 JSONPath 库简化 |
| 定时任务并发冲突 | 高 | 中 | 分布式锁控制 |
| `task_logs` 单表性能瓶颈 | 中 | 低 | 定时清理 + 索引优化 |

---

## 12. 验收清单

### 12.1 功能验收

- [ ] 诊断能力 CRUD 正常
- [ ] 即时诊断执行正常
- [ ] 场景方案执行正常（含跨步数据传递）
- [ ] 定时任务执行正常（含连接健康检查 + 重试）
- [ ] 定时清理机制正常
- [ ] 前端能力目录展示正常
- [ ] 前端参数表单动态生成正常

### 12.2 性能验收

- [ ] 能力目录查询响应时间 < 500ms
- [ ] 即时诊断执行响应时间 < 5s
- [ ] 场景方案执行响应时间 < 60s
- [ ] 并发 100 用户，系统稳定

### 12.3 数据验收

- [ ] 旧数据无损迁移
- [ ] `task_logs` 互斥约束生效
- [ ] 外键约束生效
- [ ] 定时清理无数据丢失

---

## 13. 后续迭代（P2）

| 任务 | 优先级 | 预计工期 |
|------|--------|----------|
| 用户收藏配置功能 | P2 | 2 天 |
| 诊断报告导出（PDF/Markdown） | P2 | 3 天 |
| 清理策略配置化（system_configs 表） | P2 | 1 天 |
| 诊断能力市场（社区共享） | P2 | 5 天 |
| 可视化诊断编排（拖拽） | P2 | 7 天 |

---

## 附录 A：关键文件清单

| 文件路径 | 用途 | 阶段 |
|---------|------|------|
| `models/db.py` | 数据库迁移脚本 | Phase 0 |
| `api/task_center.py` | 任务中心 API | Phase 1-4 |
| `backend/core/arthas_executor.py` | 统一执行器（异步 + 线程池） | Phase 2 |
| `backend/core/parameter_validator.py` | 参数校验引擎 | Phase 1 |
| `backend/core/command_builder.py` | 命令构建器（跨步数据传递） | Phase 4 |
| `backend/core/task_scheduler.py` | 定时任务调度器（应用层锁） | Phase 5 |
| `services/task_logs_cleanup_service.py` | 日志清理服务 | Phase 6 |
| `static/js/components/diagnosis.js` | 诊断能力前端组件 | Phase 3 |
| `static/js/components/diagnosis-form.js` | 参数表单组件 | Phase 3 |
| `static/js/components/diagnosis-result.js` | 执行结果组件 | Phase 3 |
| `static/js/components/diagnosis-progress.js` | 执行进度组件 | Phase 4 |
| `static/js/components/diagnosis-history.js` | 历史记录组件 | Phase 3 |
| `static/css/components/diagnosis.css` | 诊断能力样式 | Phase 3 |
| `tests/test_diagnosis_*.py` | 测试用例 | 各阶段 |

---

**文档结束**
