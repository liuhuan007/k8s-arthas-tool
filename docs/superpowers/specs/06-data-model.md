# K8s Arthas 智能诊断平台 — 数据模型设计


**文档版本**: v1.0
**创建日期**: 2026-05-23
**状态**: 设计完成

---

## 目录

1. [核心表清单](#1-核心表清单)
2. [新增表](#2-新增表)
3. [统一执行日志表](#3-统一执行日志表)
4. [现有表扩展](#4-现有表扩展)
5. [表关系图](#5-表关系图)
6. [数据初始化策略](#6-数据初始化策略)
7. [完整数据字典](#7-完整数据字典)

---

## 1. 核心表清单

| 表 | 用途 | 来源 |
|----|------|------|
| `users` | 用户账号、密码哈希、角色、启停状态 | 已有 |
| `user_clusters` | 用户与集群授权关系 | 已有 |
| `connections` | Pod/Arthas 连接记录 | 已有，需扩展 |
| `arthas_commands` | Arthas 命令执行历史 | 已有，需扩展 |
| `audit_logs` | 操作审计 | 已有 |
| `profiler_tasks` | 采样任务历史 | 已有，需扩展 |
| `profiler_logs` | 采样运行日志 | 已有 |

---

## 2. 新增表

### 2.1 P0 必做表

| 表名 | 用途 | 说明 |
|------|------|------|
| `skill_registry` | Skill注册表（**管理态**） | 管理Skill的导入、校验、版本、发布 |
| `diagnosis_capabilities` | 诊断能力元数据（**生产执行态**） | 从skill_registry发布，用于实际执行 |
| `step_logs` | 步骤级日志 | 记录每个步骤的命令和输出 |
| `tool_packages` | 工具包管理 | Arthas JAR 管理 |

> **核心设计决策**：
> - **skill_registry** = 管理态（草稿箱）：Skill的定义、校验、版本管理
> - **diagnosis_capabilities** = 生产执行态：从skill_registry发布，用于实际执行
> - **task_logs** = run级日志：记录一次诊断执行的总体信息
> - **step_logs** = step级日志：记录每个步骤的命令和输出

### 2.2 状态定义

| 表 | 状态 | 说明 |
|----|------|------|
| `skill_registry` | draft/validated/testing/published/archived | Skill生命周期状态 |
| `diagnosis_capabilities` | active/inactive | 能力启用状态 |
| `task_logs` | pending/running/success/failed/cancelled | 任务执行状态 |
| `step_logs` | pending/running/success/failed/skipped | 步骤执行状态 |

### 2.3 skill_registry 表（Skill管理态）

> **优化说明**: 删除了 `definition_body` 和 `definition_path` 两个冗余字段。
> - `definition_body` 的内容已分散到 `dsl`、`arthas_command`、`handler` 字段
> - `definition_path` 在导入后应解析到具体字段，不需要保留路径

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

### 2.4 状态转换流程

```
skill_registry (管理态)
    │
    │ 1. 创建Skill (status=draft)
    │ 2. 校验Skill (status=validated)
    │ 3. 测试Skill (status=testing)
    │ 4. 发布Skill (status=published)
    │
    ▼
diagnosis_capabilities (生产执行态)
    │
    │ 5. 执行诊断
    ▼
task_logs (run级日志)
    │
    │ 6. 记录每个步骤
    ▼
step_logs (step级日志)
```

### 2.5 step_logs 表（步骤级日志）

> **优化说明**: 删除了 `llm_analysis` 字段。LLM分析结果统一存储在 `task_logs.ai_analysis_result` 中。

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

CREATE INDEX idx_step_logs_run_id ON step_logs(run_id);
```

### 2.6 日志层级关系

```
task_logs (run级)
├── id = "run-uuid-xxx"
├── capability_id = 123
├── connection_id = "conn-xxx"
├── status = "success"
├── snapshot_json = {...}  -- 执行时的能力快照
│
└── step_logs (step级)
    ├── run_id = "run-uuid-xxx"
    ├── step_number = 1
    ├── command = "dashboard -n 1"
    ├── output = "ID NAME GROUP..."
    ├── status = "success"
    │
    ├── step_number = 2
    ├── command = "thread -n 5"
    ├── output = "pool-1-thread-3..."
    ├── status = "success"
    │
    └── step_number = 3
        ├── command = "stack com.example.Service process"
        ├── output = "..."
        ├── status = "success"
        └── llm_analysis = "发现热点方法..."
```

### 2.7 DSL受约束的step type

| step_type | 说明 | 安全约束 |
|-----------|------|---------|
| `arthas_command` | 执行Arthas命令 | 只允许白名单命令 |
| `llm_analysis` | 大模型分析 | 仅分析，不执行 |
| `get_pod_status` | 获取Pod状态 | 只读操作 |
| `get_pod_metrics` | 获取Pod指标 | 只读操作 |

> **禁止的step_type**：
> - ❌ `kubectl_exec` - 任意kubectl命令
> - ❌ `shell_exec` - 任意Shell命令
> - ❌ `sql_exec` - 任意SQL命令

### 2.8 安全防护机制

#### 2.8.1 命令注入防护

**问题**：参数替换时，用户输入可能包含恶意字符（如 `; rm -rf /` 或 `$(malicious_command)`）。

**解决方案**：

```python
import re
from typing import Dict, Any

# 参数白名单正则表达式
PARAM_PATTERNS = {
    'class': r'^[A-Za-z_$][\w.$]*$',      # Java类名
    'method': r'^[\w*]+$',                  # 方法名（支持通配符*）
    'namespace': r'^[a-z0-9-]+$',           # K8s命名空间
    'pod_name': r'^[a-z0-9]([-a-z0-9]*[a-z0-9])?$',  # Pod名称
    'container': r'^[a-z0-9]([-a-z0-9]*[a-z0-9])?$',  # 容器名
    'default': r'^[a-zA-Z0-9_./-]+$'       # 默认：只允许字母、数字、下划线、点、斜杠、横杠
}

# 禁止的危险字符
FORBIDDEN_CHARS = r'[;|&$`\\{}\[\]<>()!#~]'

def validate_parameter(name: str, value: str) -> tuple[bool, str]:
    """校验参数值，返回 (是否合法, 错误信息)"""
    
    # 1. 检查禁止字符
    if re.search(FORBIDDEN_CHARS, value):
        return False, f"参数 {name} 包含禁止字符"
    
    # 2. 检查长度限制
    if len(value) > 200:
        return False, f"参数 {name} 长度超过200字符"
    
    # 3. 检查白名单模式
    pattern = PARAM_PATTERNS.get(name, PARAM_PATTERNS['default'])
    if not re.match(pattern, value):
        return False, f"参数 {name} 格式不合法"
    
    return True, ""

def safe_render_command(template: str, params: Dict[str, str]) -> tuple[str, list]:
    """安全的命令渲染，返回 (渲染后的命令, 错误列表)"""
    
    errors = []
    rendered = template
    
    for name, value in params.items():
        # 校验参数
        valid, error = validate_parameter(name, value)
        if not valid:
            errors.append(error)
            continue
        
        # 安全替换（使用占位符，不是字符串拼接）
        placeholder = f'${{{name}}}'
        if placeholder in rendered:
            # 对特殊字符进行转义
            safe_value = escape_shell_arg(value)
            rendered = rendered.replace(placeholder, safe_value)
    
    return rendered, errors

def escape_shell_arg(value: str) -> str:
    """转义Shell参数"""
    # 使用shlex.quote进行安全转义
    import shlex
    return shlex.quote(value)
```

**参数校验规则**：

| 参数类型 | 正则模式 | 说明 |
|---------|---------|------|
| `class` | `^[A-Za-z_$][\w.$]*$` | Java类名 |
| `method` | `^[\w*]+$` | 方法名（支持通配符） |
| `namespace` | `^[a-z0-9-]+$` | K8s命名空间 |
| `pod_name` | `^[a-z0-9]([-a-z0-9]*[a-z0-9])?$` | Pod名称 |
| `default` | `^[a-zA-Z0-9_./-]+$` | 默认白名单 |

**禁止字符**：`; | & $ ` \ { } [ ] < > ( ) ! # ~`

#### 2.8.2 白名单维护机制

**问题**：Arthas命令有40+个，每个命令有多个参数组合，手动维护白名单成本高。

**解决方案**：

```python
# arthas_commands_config.json - 从Arthas文档自动提取
{
  "version": "3.7.2",
  "last_updated": "2026-05-24",
  "commands": {
    "dashboard": {
      "risk_level": "low",
      "description": "实时监控面板",
      "params": ["-n", "-i", "--interval"],
      "timeout": 10
    },
    "thread": {
      "risk_level": "low",
      "description": "线程信息",
      "params": ["-n", "-b", "-i", "--state", "--all"],
      "timeout": 10
    },
    "trace": {
      "risk_level": "medium",
      "description": "方法调用追踪",
      "params": ["-n", "#cost", "-j", "#path"],
      "timeout": 30
    },
    "watch": {
      "risk_level": "medium",
      "description": "方法观测",
      "params": ["-x", "-n", "#cost", "-b", "-s", "-e"],
      "timeout": 20
    },
    "redefine": {
      "risk_level": "high",
      "description": "热更新代码",
      "params": [],
      "timeout": 60,
      "requires_confirmation": true
    }
  }
}
```

**白名单同步机制**：

```python
class ArthasCommandWhitelist:
    """Arthas命令白名单管理"""
    
    def __init__(self, config_path: str):
        self.config_path = config_path
        self.config = self._load_config()
    
    def _load_config(self) -> dict:
        """加载白名单配置"""
        with open(self.config_path, 'r') as f:
            return json.load(f)
    
    def sync_from_arthas(self, arthas_version: str):
        """从Arthas版本同步白名单"""
        # 1. 下载Arthas文档
        # 2. 解析命令列表
        # 3. 更新白名单配置
        # 4. 记录版本号
        pass
    
    def is_command_allowed(self, command: str, risk_level: str) -> bool:
        """检查命令是否在白名单中"""
        cmd_name = command.split()[0]
        if cmd_name not in self.config['commands']:
            return False
        
        cmd_config = self.config['commands'][cmd_name]
        return cmd_config['risk_level'] <= risk_level
    
    def get_command_config(self, command: str) -> dict:
        """获取命令配置"""
        cmd_name = command.split()[0]
        return self.config['commands'].get(cmd_name, {})
```

**白名单更新流程**：

```
Arthas版本更新
    │
    ▼
自动同步脚本
    │
    ├── 下载新版本Arthas文档
    │
    ├── 解析命令列表
    │
    ├── 对比现有白名单
    │
    ├── 生成差异报告
    │
    └── 更新白名单配置
            │
            ├── 新增命令：标记为"待审核"
            ├── 删除命令：标记为"废弃"
            └── 参数变更：更新参数列表
```

#### 2.8.3 条件执行安全性

**问题**：DSL中的条件表达式如果使用eval()执行，存在代码注入风险。

**解决方案**：使用安全的表达式解析器，禁止任意代码执行。

```python
# 安全的条件表达式解析器
class SafeConditionEvaluator:
    """安全的条件表达式评估器"""
    
    # 允许的操作符
    ALLOWED_OPERATORS = {
        '==', '!=', '>', '<', '>=', '<=',
        'and', 'or', 'not', 'in', 'not in',
        'contains', 'startswith', 'endswith'
    }
    
    # 允许的函数
    ALLOWED_FUNCTIONS = {
        'len', 'str', 'int', 'float', 'bool'
    }
    
    # 禁止的模式
    FORBIDDEN_PATTERNS = [
        r'__import__', r'exec', r'eval',
        r'os\.', r'sys\.', r'subprocess',
        r'open\(', r'file\(',
        r'import\s', r'from\s.*import'
    ]
    
    def evaluate(self, expression: str, context: dict) -> bool:
        """安全评估条件表达式"""
        
        # 1. 检查禁止模式
        for pattern in self.FORBIDDEN_PATTERNS:
            if re.search(pattern, expression):
                raise SecurityError(f"条件表达式包含禁止模式: {pattern}")
        
        # 2. 使用AST解析，不执行代码
        try:
            tree = ast.parse(expression, mode='eval')
        except SyntaxError:
            raise SecurityError("条件表达式语法错误")
        
        # 3. 检查AST节点类型
        self._validate_ast(tree)
        
        # 4. 使用安全的评估器
        return self._safe_eval(tree, context)
    
    def _validate_ast(self, node):
        """验证AST节点"""
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                # 检查函数调用
                if isinstance(child.func, ast.Name):
                    if child.func.id not in self.ALLOWED_FUNCTIONS:
                        raise SecurityError(f"禁止调用函数: {child.func.id}")
            elif isinstance(child, ast.Attribute):
                # 检查属性访问
                if isinstance(child.value, ast.Name):
                    if child.value.id in ['os', 'sys', 'subprocess']:
                        raise SecurityError(f"禁止访问模块: {child.value.id}")
    
    def _safe_eval(self, tree, context):
        """安全评估AST"""
        # 使用ast.literal_eval或自定义评估器
        # 不使用eval()
        pass
```

**条件表达式白名单**：

| 表达式类型 | 示例 | 安全性 |
|-----------|------|--------|
| 字符串比较 | `step2.output == 'RUNNABLE'` | ✅ 安全 |
| 字符串包含 | `step2.output contains 'BLOCKED'` | ✅ 安全 |
| 数值比较 | `step1.duration > 10` | ✅ 安全 |
| 布尔组合 | `step2.output contains 'A' and step3.status == 'success'` | ✅ 安全 |
| 函数调用 | `len(step2.output) > 100` | ✅ 安全 |
| 模块导入 | `__import__('os').system('...')` | ❌ 禁止 |
| 代码执行 | `exec('...')` | ❌ 禁止 |
| 文件操作 | `open('/etc/passwd')` | ❌ 禁止 |

**DSL条件表达式安全规则**：

```yaml
# 安全的条件表达式
steps:
  - id: step1
    condition: "step2.output contains 'RUNNABLE'"  # ✅ 安全
    # condition: "step1.status == 'success' and step2.duration < 30"  # ✅ 安全
    
  # 禁止的条件表达式
  # condition: "__import__('os').system('rm -rf /')"  # ❌ 禁止
  # condition: "exec('malicious_code')"  # ❌ 禁止
  # condition: "open('/etc/passwd').read()"  # ❌ 禁止
```

### 2.9 P1/P2 扩展表（推迟）

| 表名 | 用途 | 所属业务 | 推迟原因 |
|------|------|---------|---------|
| `anomaly_rules` | 异常检测规则 | 异常自动感知 | 当前先做手动触发诊断 |
| `anomaly_events` | 异常事件记录 | 异常自动感知 | 依赖 anomaly_rules |
| `metric_baselines` | 指标基线数据 | 异常自动感知 | 需大量历史数据积累 |
| `diagnosis_cases` | 诊断案例库 | 知识沉淀 | 诊断能力跑通后才有案例可沉淀 |
| `solution_playbooks` | 解决方案库 | 知识沉淀 | 配套 diagnosis_cases |
| `diagnosis_reports` | 诊断报告 | 报告生成 | 依赖 LLM 集成 |
| `schema_version` | 数据库迁移版本 | 迁移管理 | 当前 try/except 方式够用 |
| `tool_runtime_processes` | 本地工具运行进程 | Tunnel Server | 可选增强 |
| `external_menu_links` | 外部系统链接 | 外部资源入口 | 可选增强 |

---

## 3. 统一执行日志表（关键决策）

**架构评审改进**：废弃 `diagnosis_execution_logs`，统一使用 `task_logs`。

```sql
-- 重命名原 task_runs 为 task_logs
ALTER TABLE task_runs RENAME TO task_logs;

-- 扩展字段
ALTER TABLE task_logs ADD COLUMN capability_id INTEGER REFERENCES diagnosis_capabilities(id);
ALTER TABLE task_logs ADD COLUMN execution_type TEXT;  -- diagnosis | script | pod_exec | node_exec
ALTER TABLE task_logs ADD COLUMN capability_name TEXT;  -- 冗余，防止能力被删除后丢失
ALTER TABLE task_logs ADD COLUMN rendered_command TEXT;  -- 参数替换后的实际命令
ALTER TABLE task_logs ADD COLUMN run_type TEXT DEFAULT 'script';
ALTER TABLE task_logs ADD COLUMN anomaly_event_id INTEGER REFERENCES anomaly_events(id);
ALTER TABLE task_logs ADD COLUMN connection_snapshot_json TEXT;
ALTER TABLE task_logs ADD COLUMN capability_snapshot_json TEXT;
ALTER TABLE task_logs ADD COLUMN ai_analysis_result TEXT;  -- JSON

-- 索引
CREATE INDEX idx_task_logs_capability_id ON task_logs(capability_id);
CREATE INDEX idx_task_logs_execution_mode ON task_logs(execution_mode);
CREATE INDEX idx_task_logs_execution_type ON task_logs(execution_type);
CREATE INDEX idx_task_logs_cluster_ns_pod ON task_logs(cluster_name, namespace, pod_name);
```

**执行模式统一**：

| 执行来源 | execution_mode | capability_id | task_id |
|---------|----------------|---------------|---------|
| 即时诊断 | `immediate` | ✅ 有 | ❌ NULL |
| 定时任务 | `scheduled` | 可选 | ✅ 有 |
| 手动任务 | `manual` | ❌ NULL | ✅ 有 |

---

## 4. 现有表扩展

| 表 | 新增字段 | 目的 |
|----|---------|------|
| `connections` | `container_name`, `java_pid`, `arthas_version`, `last_ping_at` | 多容器、多进程、健康检查 |
| `arthas_commands` | `template_type`, `risk_level`, `duration_ms`, `exit_status`, `masked_output`, `run_id` | 模板检索、风险审计、脱敏、串联场景步骤 |
| `profiler_tasks` | `artifact_size`, `artifact_sha256`, `max_duration`, `cancel_reason` | 产物完整性和任务治理 |
| `script_templates` | `capability_id` | 关联诊断能力 |

---

## 5. 表关系图

```
diagnosis_capabilities (扁平主表，category 字段区分类型)
├── category='quick'/'tool'  → arthas_command + parameters_schema
├── category='scenario'      → steps_json + parameters_schema
└── category='ai'            → handler + parameters_schema

task_logs (统一执行日志)
├── capability_id → diagnosis_capabilities.id
└── task_id → task_definitions.id (可选)

arthas_command_logs.run_id → task_logs.id (串联场景步骤命令)

anomaly_events.rule_id → anomaly_rules.id
anomaly_events.diagnosis_id → task_logs.id

diagnosis_cases (知识库，独立)
solution_playbooks (方案库，独立)
```

---

## 6. 数据初始化策略

所有诊断能力通过管理员后台配置，预制数据包括：

- 5 个快捷工具（JVM Dashboard、线程清单、死锁检测、VM 参数、类信息）
- 5 个诊断模板（Trace、Watch、Stack、Monitor、Jad）
- 3 个场景方案（接口响应慢、CPU 飙升、OOM 内存泄漏）
- 1 个 AI 诊断（一键性能诊断）

---

## 7. 完整数据字典

### 7.1 diagnosis_capabilities

> **优化说明**: 
> - 删除了 `visibility`（P0阶段不需要）
> - 删除了 `version`（版本管理在skill_registry中）

| 字段名 | 类型 | 约束 | 默认值 | 说明 |
|--------|------|------|--------|------|
| id | INTEGER | PK AUTO | - | 能力 ID |
| name | TEXT | NOT NULL | - | 能力名称 |
| category | TEXT | NOT NULL | - | quick / tool / scenario / ai |
| level | INTEGER | NOT NULL | 1 | 1=快捷工具 2=诊断模板 3=场景方案 4=智能诊断 |
| description | TEXT | - | NULL | 能力描述 |
| arthas_command | TEXT | - | NULL | Arthas 命令模板（支持 `${param}` 参数替换） |
| parameters_schema | TEXT | - | '{}' | 参数 Schema（JSON 数组） |
| risk_level | TEXT | - | 'low' | low / medium / high |
| estimated_duration | INTEGER | - | 10 | 预计执行时长（秒） |
| prerequisites | TEXT | - | '[]' | 前置条件 |
| related_capabilities | TEXT | - | '[]' | 关联能力 ID |
| steps_json | TEXT | - | NULL | 场景方案步骤（category=scenario 时使用） |
| handler | TEXT | - | NULL | AI 处理器路径（category=ai 时使用） |
| confirm_required | INTEGER | - | 0 | 是否需要二次确认 |
| created_by | INTEGER | FK → users | NULL | 创建人 |
| created_at | TIMESTAMP | - | CURRENT_TIMESTAMP | - |
| updated_at | TIMESTAMP | - | CURRENT_TIMESTAMP | - |

索引：`idx_diag_caps_category_level(category, level)`

### 7.2 task_logs（统一执行日志）

> **优化说明**: 
> - 删除了 `capability_name`（冗余，快照中已包含）
> - 删除了 `rendered_command`（冗余，命令输出在stdout中）
> - 删除了 `run_type`（合并到execution_type）
> - 删除了 `target_json`（与快照字段重叠）
> - 删除了 `log_path`（P0阶段不需要）
> - 删除了 `retention_days`（归档逻辑在应用层）
> - 删除了 `is_archived`（归档逻辑在应用层）
> - 新增了 `progress`（执行进度）
> - 新增了 `current_step`（当前步骤号）

| 字段名 | 类型 | 约束 | 默认值 | 说明 |
|--------|------|------|--------|------|
| id | TEXT | PK (UUID) | - | 执行日志 ID |
| task_id | INTEGER | FK → task_definitions | NULL | 即时诊断时为 NULL |
| capability_id | INTEGER | FK → diagnosis_capabilities | NULL | 即时诊断时不为 NULL |
| user_id | INTEGER | FK → users | NULL | 执行人 |
| execution_mode | TEXT | NOT NULL | - | immediate / scheduled / manual |
| execution_type | TEXT | NOT NULL | - | diagnosis / script / pod_exec / node_exec |
| anomaly_event_id | INTEGER | FK → anomaly_events | NULL | 关联异常事件 |
| connection_snapshot_json | TEXT | - | NULL | 执行开始时的连接快照 |
| capability_snapshot_json | TEXT | - | NULL | 执行开始时的能力快照 |
| ai_analysis_result | TEXT | - | NULL | AI 分析结果（JSON） |
| capability_version | INTEGER | - | NULL | 能力版本号 |
| params_json | TEXT | - | '{}' | 执行参数 |
| status | TEXT | NOT NULL | 'pending' | pending / running / success / failed / cancelled |
| progress | REAL | - | 0.0 | 执行进度（0.0-1.0） |
| current_step | INTEGER | - | NULL | 当前步骤号 |
| stdout | TEXT | - | NULL | 标准输出 |
| stderr | TEXT | - | NULL | 标准错误 |
| exit_code | INTEGER | - | NULL | 退出码 |
| result_json | TEXT | - | NULL | 结构化结果 |
| error_message | TEXT | - | NULL | 错误信息 |
| duration_ms | INTEGER | - | NULL | 执行时长 |
| started_at | TIMESTAMP | - | NULL | - |
| finished_at | TIMESTAMP | - | NULL | - |
| created_at | TIMESTAMP | - | CURRENT_TIMESTAMP | - |

索引：task_id, capability_id, user_id, execution_mode, status, started_at

---

**文档结束**
### 2.10 SQLite 性能优化

#### 2.10.1 WAL模式启用

```python
# 启用WAL模式，提高并发读写性能
db.execute("PRAGMA journal_mode=WAL")
db.execute("PRAGMA synchronous=NORMAL")
db.execute("PRAGMA cache_size=10000")  # 10MB缓存
db.execute("PRAGMA temp_store=MEMORY")
```

**WAL模式优势**：
- 读写可以并发执行
- 写入操作不阻塞读取
- 崩溃恢复更快

#### 2.10.2 异步写入队列

```python
# 非关键日志异步写入
import asyncio
from queue import Queue
from threading import Thread

class AsyncLogWriter:
    """异步日志写入器"""
    
    def __init__(self, db):
        self.db = db
        self.queue = Queue()
        self.worker = Thread(target=self._worker, daemon=True)
        self.worker.start()
    
    def _worker(self):
        """后台写入线程"""
        while True:
            table, data = self.queue.get()
            try:
                self.db.insert(table, data)
            except Exception as e:
                log.error(f"Async write failed: {e}")
            self.queue.task_done()
    
    def write_async(self, table: str, data: dict):
        """异步写入"""
        self.queue.put((table, data))

# 使用示例
async_log_writer = AsyncLogWriter(db)

# audit_logs使用异步写入
async_log_writer.write_async('audit_logs', {
    'action': 'diagnosis.execute',
    'user_id': user_id,
    'timestamp': datetime.now()
})

# task_logs使用同步写入（关键数据）
db.insert('task_logs', {...})
```

#### 2.10.3 数据归档策略

```python
# 自动归档30天前的数据
class DataArchiver:
    """数据归档器"""
    
    def __init__(self, db, retention_days=30):
        self.db = db
        self.retention_days = retention_days
    
    def archive_old_data(self):
        """归档旧数据"""
        cutoff_date = datetime.now() - timedelta(days=self.retention_days)
        
        # 1. 归档task_logs
        old_logs = self.db.fetch_all(
            "SELECT * FROM task_logs WHERE created_at < ?",
            (cutoff_date,)
        )
        
        if old_logs:
            # 写入归档表
            for log in old_logs:
                self.db.insert('task_logs_archive', log)
            
            # 删除旧数据
            self.db.execute(
                "DELETE FROM task_logs WHERE created_at < ?",
                (cutoff_date,)
            )
            
            log.info(f"Archived {len(old_logs)} task_logs")
        
        # 2. 归档step_logs
        # 3. 归档audit_logs
```

#### 2.10.4 查询性能优化

```sql
-- 创建索引优化查询
CREATE INDEX idx_task_logs_created_at ON task_logs(created_at);
CREATE INDEX idx_task_logs_status ON task_logs(status);
CREATE INDEX idx_step_logs_run_id ON step_logs(run_id);
CREATE INDEX idx_audit_logs_user_id ON audit_logs(user_id);
CREATE INDEX idx_audit_logs_created_at ON audit_logs(created_at);

-- 分页查询优化
SELECT * FROM task_logs 
ORDER BY created_at DESC 
LIMIT 20 OFFSET 0;
```

#### 2.10.5 数据量评估

| 表 | 30天数据量 | 1年数据量 | 性能影响 |
|----|-----------|----------|---------|
| task_logs | 15,000条 | 180,000条 | 低（有索引） |
| step_logs | 75,000条 | 900,000条 | 中（需归档） |
| audit_logs | 300,000条 | 3,600,000条 | 高（必须归档） |

**建议**：
- task_logs：保留30天，归档到文件
- step_logs：保留7天，归档到文件
- audit_logs：保留90天，归档到文件

#### 2.10.6 迁移路径

如果未来需要迁移到PostgreSQL/MySQL：

1. **ORM层隔离**：使用SQLAlchemy或类似ORM
2. **SQL方言兼容**：使用ORM的方言抽象
3. **数据迁移脚本**：编写迁移脚本

```python
# 使用SQLAlchemy隔离数据库差异
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# SQLite
engine = create_engine('sqlite:///arthas.db')

# PostgreSQL（未来迁移）
# engine = create_engine('postgresql://user:pass@localhost/arthas')

Session = sessionmaker(bind=engine)
```
