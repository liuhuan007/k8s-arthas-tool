# Pydantic AI设计启发分析

> **分析日期**: 2026-05-24
> **参考文章**: 《不用 Claude 模型，也能搭一套渐进式 Agent Skills》
> **分析目的**: 提取对我们k8s-arthas-tool项目的设计启发

---

## 1. 文章核心观点

### 1.1 关键洞察

| 洞察 | 说明 | 对我们的启发 |
|------|------|-------------|
| **框架是壳，工具和上下文是命** | 渐进式加载是通用设计模式，不应绑定特定模型 | Agent层应支持多模型切换 |
| **工程化控制 > 黑盒魔法** | 白盒控制比黑盒更适合生产环境 | Skill执行需要精确控制 |
| **Token经济学** | 控制上下文，确保模型只关注必要信息 | Skill执行需要分阶段信息披露 |
| **类型安全** | Pydantic + 静态检查比字符串传参更健壮 | 参数定义需要强类型 |

---

## 2. 架构设计启发

### 2.1 Capability机制（对应我们的Skill）

| Pydantic AI Capability | 我们的Skill | 启发 |
|------------------------|-------------|------|
| 打包工具、指令、配置 | skill_registry表 | Skill应包含完整上下文 |
| 可组合、可复用 | Skill发布到diagnosis_capabilities | Skill应该是模块化的 |
| 生命周期钩子 | 执行前后回调 | 添加执行钩子机制 |

### 2.2 渐进式加载（对应我们的Skill执行）

**文章方案**：
```python
# 方案B（推荐）：按步骤追加指令
before_model_request hook:
    追加系统指令："【阶段二：分类评估】数据已抓取完毕。现在进行分类，不要抓取新数据。"
```

**对我们的启发**：

我们的Skill DSL可以借鉴这个思路，在执行过程中动态追加上下文：

```yaml
# 我们的DSL可以增强为
steps:
  - id: step1
    type: arthas_command
    command: "dashboard -n 1"
    next_context: "JVM状态已获取，接下来分析线程"
    
  - id: step2
    type: arthas_command
    command: "thread -n 5"
    next_context: "线程堆栈已获取，接下来定位热点方法"
    
  - id: step3
    type: llm_analysis
    prompt: "基于以上JVM状态和线程堆栈，分析CPU飙高原因"
```

### 2.3 类型安全依赖注入

**文章方案**：
```python
class 日报依赖:
    数据库连接: 数据库客户端
    飞书Webhook: str

@agent.注册工具
async def 从数据库读取(上下文: RunContext[日报依赖], 日期: str):
    db = 上下文.deps.数据库连接
```

**对我们的启发**：

Skill执行时应注入类型安全的依赖：

```python
class SkillContext:
    """Skill执行上下文"""
    connection_id: str
    pod_target: PodTarget
    arthas_executor: ArthasExecutor
    db: Database
    
async def execute_step(step: Step, ctx: SkillContext):
    """执行步骤（类型安全）"""
    if step.type == 'arthas_command':
        result = await ctx.arthas_executor.execute(step.command)
        return result
```

### 2.4 模型故障转移（FallbackModel）

**文章方案**：
```python
fallback = FallbackModel(
    'deepseek:deepseek-chat',
    'anthropic:claude-sonnet-4-6',
)
agent = Agent(fallback, capabilities=[...])
```

**对我们的启发**：

我们已经有Agent抽象层，可以进一步优化降级策略：

```python
# 我们的降级策略可以更精细
class AgentFactory:
    FALLBACK_CHAIN = [
        ('codebuddy', CodeBuddyAgent),
        ('deepseek', DeepSeekAgent),  # 新增：性价比高
        ('claude', ClaudeAgent),
        ('fallback', FallbackAgent),
    ]
```

---

## 3. 对我们架构的具体改进建议

### 3.1 Skill执行增加上下文传递

**当前设计**：步骤之间通过step_logs传递输出

**改进设计**：增加next_context字段，支持动态上下文追加

```sql
-- step_logs表增加字段
ALTER TABLE step_logs ADD COLUMN next_context TEXT;
```

```yaml
# DSL示例
steps:
  - id: step1
    type: arthas_command
    command: "dashboard -n 1"
    next_context: "JVM状态已获取，CPU使用率{cpu_usage}%"
    
  - id: step2
    type: llm_analysis
    prompt: "基于上下文分析CPU飙高原因"
```

### 3.2 Skill执行增加钩子机制

**文章启发**：before_model_request hook

**我们的实现**：

```python
class SkillOrchestrator:
    """技能编排器（带钩子）"""
    
    def __init__(self):
        self.hooks = {
            'before_step': [],  # 步骤执行前
            'after_step': [],   # 步骤执行后
            'on_error': [],     # 错误发生时
        }
    
    def add_hook(self, event: str, hook: Callable):
        """添加钩子"""
        self.hooks[event].append(hook)
    
    async def execute_step(self, step: Step):
        """执行步骤（带钩子）"""
        # 执行前钩子
        for hook in self.hooks['before_step']:
            await hook(step)
        
        # 执行步骤
        result = await self._do_execute(step)
        
        # 执行后钩子
        for hook in self.hooks['after_step']:
            await hook(step, result)
        
        return result
```

### 3.3 依赖注入优化

**文章启发**：类型安全的依赖注入

**我们的实现**：

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class SkillDependencies:
    """Skill执行依赖"""
    connection_id: str
    cluster_name: str
    namespace: str
    pod_name: str
    arthas_executor: 'ArthasExecutor'
    db: 'Database'
    llm_client: Optional['LLMClient'] = None

class SkillOrchestrator:
    """技能编排器（依赖注入）"""
    
    def __init__(self, deps: SkillDependencies):
        self.deps = deps
    
    async def execute(self, skill_id: int, params: dict):
        """执行Skill"""
        skill = self._load_skill(skill_id)
        
        for step in skill['steps']:
            result = await self._execute_step(step, params, self.deps)
            params['step_output'] = result
```

---

## 4. 成本优化启发

### 4.1 Token经济学

**文章观点**：控制上下文，确保模型只关注必要信息

**对我们的启发**：

| 场景 | 当前做法 | 优化做法 |
|------|---------|---------|
| **LLM分析** | 传递完整输出 | 只传递关键摘要 |
| **多步骤执行** | 每步都调用LLM | 只在关键步骤调用 |
| **诊断报告** | 生成完整报告 | 分阶段生成摘要 |

### 4.2 模型选择策略

**文章观点**：DeepSeek成本约为Claude的1/5

**对我们的启发**：

| 场景 | 推荐模型 | 原因 |
|------|---------|------|
| **简单摘要** | DeepSeek | 成本低，速度快 |
| **复杂分析** | Claude/CodeBuddy | 能力强，准确性高 |
| **降级场景** | 本地模型 | 无网络依赖 |

---

## 5. 实施建议

### 5.1 P0阶段（当前）

1. **保持现有DSL格式**：不急于引入新格式
2. **添加next_context字段**：支持步骤间上下文传递
3. **优化LLM调用策略**：只在关键步骤调用

### 5.2 P1阶段（后续）

1. **引入钩子机制**：支持before_step/after_step钩子
2. **优化依赖注入**：使用dataclass实现类型安全
3. **支持多模型切换**：集成DeepSeek作为备选

### 5.3 P2阶段（远期）

1. **支持Pydantic AI格式**：兼容更多Skill格式
2. **渐进式加载**：动态控制信息披露
3. **成本优化**：自动选择最优模型

---

## 6. 核心启发总结

| 启发 | 我们的改进 |
|------|-----------|
| **框架是壳，工具是命** | Agent层支持多模型，不绑定特定SDK |
| **白盒控制 > 黑盒魔法** | Skill执行需要精确控制每一步 |
| **Token经济学** | 控制上下文传递，优化LLM调用 |
| **类型安全** | 依赖注入使用dataclass |
| **渐进式加载** | DSL增加next_context，动态追加上下文 |

---

**分析完成时间**: 2026-05-24 18:08
**分析人**: AI架构评审助手
