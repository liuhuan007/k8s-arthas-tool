# K8s Arthas 智能诊断平台 — Agent SDK 集成架构设计

> 基于Agent SDK的智能诊断系统架构，支持多SDK切换

**文档版本**: v3.0
**创建日期**: 2026-05-23
**状态**: 设计完成
**优先级**: **P0**

---

## 0. P0范围定义

### 0.1 P0必须实现的功能

| 模块 | P0范围 | 说明 |
|------|--------|------|
| **Agent抽象接口** | AgentInterface抽象类 | 隔离具体SDK实现 |
| **Agent适配器** | CodeBuddyAgent、FallbackAgent | 支持多SDK切换 |
| **Agent工厂** | AgentFactory自动降级 | 配置驱动，自动降级 |
| **Agent Tool Gateway** | 受控工具暴露、权限控制 | 只允许白名单工具 |
| **会话管理** | SessionManager持久化 | 支持服务重启恢复 |
| **资源控制** | AsyncTaskManager | 超时、取消、并发限制 |

### 0.2 P0不包含的功能

| 功能 | 说明 | 阶段 |
|------|------|------|
| Agent自主诊断 | Agent完全自主执行诊断 | P1 |
| 多Agent协作 | 多个Agent协作诊断 | P2 |
| Agent学习 | Agent从历史诊断中学习 | P2 |

---

## 目录

1. [架构概述](#1-架构概述)
2. [与现有系统整合](#2-与现有系统整合)
3. [Agent诊断引擎设计](#3-agent诊断引擎设计)
4. [工具集设计](#4-工具集设计)
5. [前端交互设计](#5-前端交互设计)
6. [API设计](#6-api设计)
7. [实施计划](#7-实施计划)

---

## 目录

1. [架构概述](#1-架构概述)
2. [配置管理方案](#2-配置管理方案)
3. [与现有系统整合](#3-与现有系统整合)
4. [Agent诊断引擎设计](#4-agent诊断引擎设计)
5. [工具集设计](#5-工具集设计)
6. [前端交互设计](#6-前端交互设计)
7. [API设计](#7-api设计)
8. [实施计划](#8-实施计划)

---

## 1. 架构概述

### 1.1 系统架构图

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                        前端界面层                                           │
│                                                                                             │
│   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐             │
│   │   诊断中心   │    │   连接中心   │    │   任务中心   │    │   AI 助手    │             │
│   │  (Agent SDK) │    │              │    │              │    │              │             │
│   └──────┬───────┘    └──────┬───────┘    └──────┬───────┘    └──────┬───────┘             │
│          │                   │                   │                   │                     │
│          └───────────────────┴───────────────────┴───────────────────┘                     │
│                                          │                                                  │
│                                          ▼                                                  │
│                              HTTP / WebSocket                                               │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
                                          │
                                          │
                                          ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                        API 网关层                                           │
│                                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────────────────────┐  │
│   │                           Flask REST API                                             │  │
│   │                                                                                     │  │
│   │   /api/diagnosis/agent/*     /api/arthas/*     /api/ai/*     /api/tasks/*           │  │
│   └─────────────────────────────────────────────────────────────────────────────────────┘  │
│                                          │                                                  │
│          ┌───────────────────┬───────────┴───────────┬───────────────────┐                │
│          │                   │                       │                   │                │
│          ▼                   ▼                       ▼                   ▼                │
│   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐          │
│   │   会话管理   │    │   权限控制   │    │   审计日志   │    │   配置管理   │          │
│   │              │    │              │    │              │    │              │          │
│   └──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘          │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
                                          │
                                          │
                                          ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                     Agent 诊断引擎层                                        │
│                                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────────────────────┐  │
│   │                     CodeBuddy Agent SDK (核心引擎)                                   │  │
│   │                                                                                     │  │
│   │   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐            │  │
│   │   │  诊断 Agent │   │  工具管理器 │   │  会话管理器 │   │   钩子系统  │            │  │
│   │   │             │   │             │   │             │   │             │            │  │
│   │   └──────┬──────┘   └──────┬──────┘   └──────┬──────┘   └──────┬──────┘            │  │
│   │          │                 │                 │                 │                    │  │
│   │          └─────────────────┴─────────────────┴─────────────────┘                    │  │
│   │                                    │                                                 │  │
│   │                                    ▼                                                 │  │
│   │                    ┌─────────────────────────────────┐                               │  │
│   │                    │    Agent Tool Gateway           │                               │  │
│   │                    │    (受控工具网关)                │                               │  │
│   │                    │                                 │                               │  │
│   │                    │  ┌─────────────────────────┐   │                               │  │
│   │                    │  │  execute_capability     │   │                               │  │
│   │                    │  │  get_pod_status         │   │                               │  │
│   │                    │  │  get_pod_metrics        │   │                               │  │
│   │                    │  │  list_capabilities      │   │                               │  │
│   │                    │  └─────────────────────────┘   │                               │  │
│   │                    └─────────────────────────────────┘                               │  │
│   └─────────────────────────────────────────────────────────────────────────────────────┘  │
│                                          │                                                  │
│                                          │ 只能调用受控工具                                  │
│                                          ▼                                                  │
├─────────────────────────────────────────────────────────────────────────────────────────────┤
│                                     Skill 编排层                                           │
│                                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────────────────────┐  │
│   │                      Workflow Engine (技能编排器)                                  │  │
│   │                                                                                     │  │
│   │   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐            │  │
│   │   │  DSL解析    │   │  步骤执行   │   │  条件分支   │   │  执行记录   │            │  │
│   │   └─────────────┘   └─────────────┘   └─────────────┘   └─────────────┘            │  │
│   └─────────────────────────────────────────────────────────────────────────────────────┘  │
│                                          │                                                  │
│                                          ▼                                                  │
├─────────────────────────────────────────────────────────────────────────────────────────────┤
│                                     Skill 注册层                                           │
│                                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────────────────────┐  │
│   │                      Skill Registry (技能注册中心)                                    │  │
│   │                                                                                     │  │
│   │   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐            │  │
│   │   │  导入       │   │  校验       │   │  版本化     │   │  发布       │            │  │
│   │   └─────────────┘   └─────────────┘   └─────────────┘   └─────────────┘            │  │
│   └─────────────────────────────────────────────────────────────────────────────────────┘  │
│                                          │                                                  │
│                                          ▼                                                  │
├─────────────────────────────────────────────────────────────────────────────────────────────┤
│                                     统一执行层                                             │
│                                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────────────────────┐  │
│   │                      ArthasCommandExecutor (统一执行器)                               │  │
│   └─────────────────────────────────────────────────────────────────────────────────────┘  │
│                                          │                                                  │
│                                          │ kubectl exec / Arthas HTTP                     │
│                                          ▼                                                  │
├─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                        目标环境层                                           │
│                                                                                             │
│   ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐    ┌─────────────┐    │
│   │     Pod A       │    │     Pod B       │    │     Pod C       │    │     ...     │    │
│   │                 │    │                 │    │                 │    │             │    │
│   │  ┌───────────┐  │    │  ┌───────────┐  │    │  ┌───────────┐  │    │             │    │
│   │  │ Java App  │  │    │  │ Java App  │  │    │  │ Java App  │  │    │             │    │
│   │  │ + Arthas  │  │    │  │ + Arthas  │  │    │  │ + Arthas  │  │    │             │    │
│   │  └───────────┘  │    │  └───────────┘  │    │  └───────────┘  │    │             │    │
│   └─────────────────┘    └─────────────────┘    └─────────────────┘    └─────────────┘    │
│                                                                                             │
└─────────────────────────────────────────────────────────────────────────────────────────────┘


═════════════════════════════════════════════════════════════════════════════════════════════
                                         数据流向
═════════════════════════════════════════════════════════════════════════════════════════════

  用户操作                                                              Pod 执行
     │                                                                     │
     │  1. 选择诊断类型                                                    │
     ▼                                                                     │
  ┌──────────┐                                                             │
  │ 前端界面 │                                                             │
  └────┬─────┘                                                             │
       │                                                                   │
       │  2. POST /api/diagnosis/agent/start                               │
       ▼                                                                   │
  ┌──────────┐                                                             │
  │ API 网关 │                                                             │
  └────┬─────┘                                                             │
       │                                                                   │
       │  3. 调用 Agent SDK                                                │
       ▼                                                                   │
  ┌──────────┐                                                             │
  │ Agent    │  4. 调用受控工具                                             │
  │ 诊断引擎 │─────────────────────────────────────────────────────────────┤
  └────┬─────┘                                                             │
       │                                                                   │
       │  5. Agent Tool Gateway 校验并执行                                 │
       ▼                                                                   │
  ┌──────────┐                                                             │
  │ Gateway  │  6. 调用 Workflow Engine                                 │
  └────┬─────┘                                                             │
       │                                                                   │
       │  7. 执行Skill步骤                                                 │
       ▼                                                                   │
  ┌──────────┐   kubectl exec   ┌──────────┐   Arthas 命令   ┌──────────┐│
  │ Orchestr │─────────────────▶│  Pod A   │◀────────────────│ Arthas   ││
  └──────────┘                  └──────────┘                 └──────────┘│
       │                                                                   │
       │  8. 收集结果并记录                                                │
       ▼                                                                   │
  ┌──────────┐                                                             │
  │ Agent    │  9. 分析并生成报告                                           │
  │ 诊断引擎 │◀────────────────────────────────────────────────────────────┘
  └────┬─────┘                                                             │
       │                                                                   │
       │  10. 返回诊断结果                                                 │
       ▼                                                                   │
  ┌──────────┐                                                             │
  │ 前端界面 │  11. 展示诊断报告                                            │
  └──────────┘                                                             │
```

### 1.2 核心组件

| 组件 | 职责 | 技术栈 |
|------|------|--------|
| **Agent诊断引擎** | 自主诊断、多步骤推理 | CodeBuddy Agent SDK |
| **Agent Tool Gateway** | 受控工具暴露、权限控制、审计 | Python + Flask |
| **Workflow Engine** | DSL步骤编排、条件分支、执行记录 | Python |
| **Skill Registry** | Skill导入、校验、版本化、发布 | Python + SQLite |
| **统一执行器** | Arthas命令执行、超时控制、脱敏 | Python + subprocess |

---

## 2. 技术风险与应对策略

### 2.1 技术成熟度风险

| 风险 | 应对策略 |
|------|---------|
| SDK生产环境验证 | 选择有大规模用户基础的SDK，进行充分测试 |
| SDK重大bug | 抽象接口层，支持快速切换 |
| SDK停止维护 | 保留多个SDK选项，配置驱动切换 |
| 备用方案切换 | 自动降级机制，无需手动干预 |

### 2.2 依赖耦合风险

**解决方案：Agent抽象接口层**

```python
# services/agent/base_agent.py

from abc import ABC, abstractmethod
from typing import AsyncIterator, Dict, Any, List

class AgentInterface(ABC):
    """Agent抽象接口 - 隔离具体SDK实现"""
    
    @abstractmethod
    async def initialize(self, config: Dict[str, Any]) -> None:
        """初始化Agent"""
        pass
    
    @abstractmethod
    async def query(self, prompt: str, tools: List[str] = None) -> AsyncIterator[Dict]:
        """执行查询"""
        pass
    
    @abstractmethod
    async def execute_tool(self, tool_name: str, params: Dict) -> Dict:
        """执行工具"""
        pass
    
    @abstractmethod
    async def get_session(self, session_id: str) -> Any:
        """获取会话"""
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """关闭Agent"""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """检查Agent是否可用"""
        pass


# services/agent/codebuddy_agent.py

class CodeBuddyAgent(AgentInterface):
    """CodeBuddy Agent实现"""
    
    def __init__(self):
        self.client = None
        self.config = None
    
    async def initialize(self, config: Dict[str, Any]) -> None:
        from codebuddy_agent_sdk import CodeBuddySDKClient, CodeBuddyAgentOptions
        
        options = CodeBuddyAgentOptions(
            model=config.get('model', 'deepseek-v3.1'),
            permission_mode=config.get('permission_mode', 'default')
        )
        self.client = CodeBuddySDKClient(options=options)
        self.config = config
    
    async def query(self, prompt: str, tools: List[str] = None) -> AsyncIterator[Dict]:
        async with self.client as client:
            await client.query(prompt)
            async for message in client.receive_response():
                yield self._format_message(message)
    
    async def execute_tool(self, tool_name: str, params: Dict) -> Dict:
        # 调用Agent Tool Gateway
        return await self.tool_gateway.execute_tool(tool_name, params)
    
    def is_available(self) -> bool:
        try:
            from codebuddy_agent_sdk import CodeBuddySDKClient
            return True
        except ImportError:
            return False


# services/agent/claude_agent.py

class ClaudeAgent(AgentInterface):
    """Claude Agent实现（备用方案）"""
    
    def __init__(self):
        self.client = None
    
    async def initialize(self, config: Dict[str, Any]) -> None:
        from claude_agent_sdk import ClaudeSDKClient
        
        self.client = ClaudeSDKClient(
            api_key=config.get('api_key'),
            model=config.get('model', 'claude-3-opus')
        )
    
    async def query(self, prompt: str, tools: List[str] = None) -> AsyncIterator[Dict]:
        # Claude SDK实现
        pass
    
    def is_available(self) -> bool:
        try:
            from claude_agent_sdk import ClaudeSDKClient
            return True
        except ImportError:
            return False


# services/agent/fallback_agent.py

class FallbackAgent(AgentInterface):
    """降级Agent - 无SDK时使用直接LLM调用"""
    
    def __init__(self):
        self.llm_client = None
    
    async def initialize(self, config: Dict[str, Any]) -> None:
        # 使用直接LLM调用（OpenAI兼容API）
        import openai
        self.llm_client = openai.AsyncOpenAI(
            api_key=config.get('api_key'),
            base_url=config.get('base_url')
        )
    
    async def query(self, prompt: str, tools: List[str] = None) -> AsyncIterator[Dict]:
        # 直接LLM调用，不支持工具
        response = await self.llm_client.chat.completions.create(
            model=self.config.get('model'),
            messages=[{"role": "user", "content": prompt}]
        )
        yield {"type": "text", "content": response.choices[0].message.content}
    
    def is_available(self) -> bool:
        return True  # 总是可用
```

### 2.3 Agent工厂（自动降级）

```python
# services/agent/agent_factory.py

class AgentFactory:
    """Agent工厂 - 根据配置自动选择和降级"""
    
    AGENT_REGISTRY = {
        'codebuddy': CodeBuddyAgent,
        'claude': ClaudeAgent,
        'fallback': FallbackAgent
    }
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.preferred_agent = config.get('preferred_agent', 'codebuddy')
        self.fallback_order = config.get('fallback_order', ['codebuddy', 'claude', 'fallback'])
    
    async def create_agent(self) -> AgentInterface:
        """创建Agent（自动降级）"""
        
        for agent_type in self.fallback_order:
            agent_class = self.AGENT_REGISTRY.get(agent_type)
            if not agent_class:
                continue
            
            agent = agent_class()
            
            # 检查Agent是否可用
            try:
                await agent.initialize(self.config.get(agent_type, {}))
                if agent.is_available():
                    log.info(f"Using agent: {agent_type}")
                    return agent
                else:
                    log.warning(f"Agent {agent_type} not available, trying next...")
            except Exception as e:
                log.error(f"Agent {agent_type} initialization failed: {e}")
                continue
        
        # 所有Agent都不可用，使用降级方案
        log.warning("All agents unavailable, using fallback")
        agent = FallbackAgent()
        await agent.initialize(self.config.get('fallback', {}))
        return agent


# 使用示例
async def get_agent():
    config = {
        'preferred_agent': 'codebuddy',
        'fallback_order': ['codebuddy', 'claude', 'fallback'],
        'codebuddy': {
            'model': 'deepseek-v3.1',
            'permission_mode': 'default'
        },
        'claude': {
            'api_key': 'xxx',
            'model': 'claude-3-opus'
        },
        'fallback': {
            'api_key': 'xxx',
            'base_url': 'https://api.openai.com/v1',
            'model': 'gpt-4'
        }
    }
    
    factory = AgentFactory(config)
    return await factory.create_agent()
```

### 2.4 备用方案切换机制

```
┌─────────────────────────────────────────────────────────────────┐
│                    Agent降级策略                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  优先级1: CodeBuddy Agent SDK                                   │
│     │                                                          │
│     ├── 可用 → 使用CodeBuddy                                   │
│     │                                                          │
│     └── 不可用 → 降级到优先级2                                  │
│                                                                 │
│  优先级2: Claude Agent SDK                                      │
│     │                                                          │
│     ├── 可用 → 使用Claude                                      │
│     │                                                          │
│     └── 不可用 → 降级到优先级3                                  │
│                                                                 │
│  优先级3: 直接LLM调用（降级方案）                               │
│     │                                                          │
│     └── 总是可用 → 使用直接LLM调用                             │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**切换时机**：
- **自动降级**：SDK初始化失败、SDK运行时异常、SDK不可用
- **手动切换**：管理员在配置页面切换首选Agent
- **健康检查**：定期检测Agent可用性，自动切换

### 2.5 并发与资源管理

#### 2.5.1 会话持久化（P0）

> **问题修复**：明确Agent会话持久化、上下文恢复、连接绑定机制。

**agent_sessions表定义**：

```sql
CREATE TABLE agent_sessions (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    connection_id TEXT NOT NULL,
    capability_id INTEGER,
    status TEXT DEFAULT 'active',  -- active/suspended/completed/failed
    context_json TEXT,  -- 存储对话历史摘要
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,  -- 会话过期时间
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (connection_id) REFERENCES connections(id)
);

CREATE INDEX idx_agent_sessions_user ON agent_sessions(user_id);
CREATE INDEX idx_agent_sessions_status ON agent_sessions(status);
```

**会话管理器实现**：

```python
class SessionManager:
    """会话管理器 - 支持持久化"""
    
    def __init__(self):
        self.memory_sessions = {}  # 内存缓存
        self.session_timeout = 3600  # 会话超时时间（秒）
    
    async def create_session(self, user_id: int, connection_id: str) -> str:
        """创建会话"""
        session_id = str(uuid.uuid4())
        
        # 1. 写入数据库
        db.insert('agent_sessions', {
            'id': session_id,
            'user_id': user_id,
            'connection_id': connection_id,
            'status': 'active',
            'context_json': json.dumps([]),  # 空对话历史
            'created_at': datetime.now(),
            'expires_at': datetime.now() + timedelta(seconds=self.session_timeout)
        })
        
        # 2. 缓存到内存
        self.memory_sessions[session_id] = {
            'agent': await self._create_agent(),
            'context': [],
            'created_at': datetime.now()
        }
        
        return session_id
    
    async def get_session(self, session_id: str) -> Optional[Dict]:
        """获取会话"""
        
        # 1. 先从内存获取
        if session_id in self.memory_sessions:
            session = self.memory_sessions[session_id]
            # 检查是否过期
            if datetime.now() - session['created_at'] < timedelta(seconds=self.session_timeout):
                return session
            else:
                # 会话过期
                await self.close_session(session_id)
                return None
        
        # 2. 从数据库恢复
        session_db = db.fetch_one(
            "SELECT * FROM agent_sessions WHERE id = ? AND status = 'active'",
            (session_id,)
        )
        
        if session_db:
            # 检查是否过期
            if session_db['expires_at'] and datetime.fromisoformat(session_db['expires_at']) < datetime.now():
                await self.close_session(session_id)
                return None
            
            # 重建Agent实例
            agent = await self._restore_agent(session_db)
            context = json.loads(session_db['context_json']) if session_db['context_json'] else []
            
            self.memory_sessions[session_id] = {
                'agent': agent,
                'context': context,
                'created_at': session_db['created_at']
            }
            return self.memory_sessions[session_id]
        
        return None
    
    async def update_context(self, session_id: str, message: dict):
        """更新会话上下文"""
        session = await self.get_session(session_id)
        if session:
            session['context'].append(message)
            
            # 持久化到数据库
            db.update('agent_sessions', {
                'context_json': json.dumps(session['context']),
                'updated_at': datetime.now()
            }, 'id = ?', (session_id,))
    
    async def close_session(self, session_id: str):
        """关闭会话"""
        # 更新数据库状态
        db.update('agent_sessions', {
            'status': 'completed',
            'updated_at': datetime.now()
        }, 'id = ?', (session_id,))
        
        # 从内存移除
        self.memory_sessions.pop(session_id, None)
    
    async def on_connection_lost(self, connection_id: str):
        """连接断开时处理"""
        # 查找该连接的所有活跃会话
        sessions = db.fetch_all(
            "SELECT id FROM agent_sessions WHERE connection_id = ? AND status = 'active'",
            (connection_id,)
        )
        
        for session in sessions:
            # 标记为挂起
            db.update('agent_sessions', {
                'status': 'suspended',
                'updated_at': datetime.now()
            }, 'id = ?', (session['id'],))
            
            # 从内存移除
            self.memory_sessions.pop(session['id'], None)
```

**会话状态说明**：

| 状态 | 说明 | 触发条件 |
|------|------|---------|
| `active` | 活跃状态 | 创建会话 |
| `suspended` | 挂起状态 | 连接断开 |
| `completed` | 已完成 | 主动关闭或超时 |
| `failed` | 失败状态 | Agent异常 |

**上下文快照**：每次工具调用时，保存当前上下文快照到`context_json`字段。

#### 2.5.2 长时间任务处理

```python
# 任务超时和取消机制
class AsyncTaskManager:
    """异步任务管理器"""
    
    def __init__(self):
        self.tasks = {}  # task_id -> TaskInfo
        self.max_concurrent = 10  # 最大并发数
        self.task_timeout = 300  # 任务超时时间（秒）
    
    async def submit_task(self, task_func, *args, **kwargs) -> str:
        """提交任务"""
        
        # 1. 检查并发数
        if len(self.tasks) >= self.max_concurrent:
            raise ConcurrencyError("任务队列已满，请稍后重试")
        
        task_id = str(uuid.uuid4())
        
        # 2. 创建任务
        task = asyncio.create_task(
            self._run_with_timeout(task_func, *args, **kwargs)
        )
        
        self.tasks[task_id] = {
            'task': task,
            'status': 'running',
            'started_at': datetime.now(),
            'user_id': kwargs.get('user_id')
        }
        
        # 3. 设置超时回调
        task.add_done_callback(lambda t: self._on_task_complete(task_id, t))
        
        return task_id
    
    async def _run_with_timeout(self, func, *args, **kwargs):
        """带超时的任务执行"""
        try:
            return await asyncio.wait_for(func(*args, **kwargs), timeout=self.task_timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(f"任务执行超时（{self.task_timeout}秒）")
    
    def _on_task_complete(self, task_id: str, task: asyncio.Task):
        """任务完成回调"""
        if task_id in self.tasks:
            info = self.tasks[task_id]
            if task.cancelled():
                info['status'] = 'cancelled'
            elif task.exception():
                info['status'] = 'failed'
                info['error'] = str(task.exception())
            else:
                info['status'] = 'completed'
            
            info['completed_at'] = datetime.now()
            
            # 从内存中移除
            del self.tasks[task_id]
    
    async def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        if task_id in self.tasks:
            task = self.tasks[task_id]['task']
            task.cancel()
            return True
        return False
```

#### 2.5.3 资源控制

```python
# 资源控制配置
RESOURCE_LIMITS = {
    'max_concurrent_sessions': 10,      # 最大并发会话数
    'max_concurrent_tasks': 5,          # 最大并发任务数
    'task_timeout': 300,                # 任务超时时间（秒）
    'session_timeout': 3600,            # 会话超时时间（秒）
    'max_tokens_per_request': 4000,     # 每次请求最大token数
    'rate_limit_per_minute': 60,        # 每分钟请求限制
}

# 资源监控
class ResourceMonitor:
    """资源监控器"""
    
    def __init__(self):
        self.active_sessions = 0
        self.active_tasks = 0
        self.request_count = 0
    
    def can_create_session(self) -> bool:
        """检查是否可以创建新会话"""
        return self.active_sessions < RESOURCE_LIMITS['max_concurrent_sessions']
    
    def can_start_task(self) -> bool:
        """检查是否可以启动新任务"""
        return self.active_tasks < RESOURCE_LIMITS['max_concurrent_tasks']
    
    def record_request(self):
        """记录请求"""
        self.request_count += 1
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            'active_sessions': self.active_sessions,
            'active_tasks': self.active_tasks,
            'request_count': self.request_count
        }
```

---

## 3. 配置管理方案

### 3.1 设计原则

**复用数据库已有配置，不创建新的配置文件！**

### 3.2 现有数据库配置

**表名**：`ai_config`（已有）

| 字段 | 类型 | 说明 |
|------|------|------|
| `user_id` | INTEGER | 用户ID（主键） |
| `api_key` | TEXT | API密钥 |
| `base_url` | TEXT | API地址 |
| `model` | TEXT | 模型名称 |
| `provider` | TEXT | 提供商（openai/codebuddy/ollama/custom） |
| `system_prompt` | TEXT | 系统提示词 |

### 3.3 自定义模型接入（参考 OpenVibeCoding models.json 方案）

> **新增设计**：支持接入本地部署LLM、私有网关等自定义模型。

**新增文件**：`services/agent/models.json`

```json
{
  "models": [
    {
      "id": "codebuddy:deepseek-v3.1",
      "name": "DeepSeek V3.1",
      "vendor": "codebuddy",
      "supportsToolCall": true,
      "supportsImages": false
    },
    {
      "id": "custom:local-llama3",
      "name": "Local LLAMA 3",
      "vendor": "custom",
      "apiKey": "${LOCAL_LLM_API_KEY}",
      "baseURL": "http://localhost:11434/v1/chat/completions",
      "supportsToolCall": true,
      "supportsImages": false
    }
  ],
  "defaultAgent": "codebuddy"
}
```

**注意**：`vendor` 不要写 `codebuddy`，避免被同步覆盖。自定义模型使用 `vendor: "custom"`。

### 3.4 配置复用方案

```
┌─────────────────────────────────────────────────────────────────┐
│                    数据库 ai_config 表（已有）                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  user_id | api_key | base_url | model | provider        │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                              ▼ 复用                             │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │               AgentSDKConfig.get_config(user_id)                      │   │
│  │  ├── 读取ai_config表                                     │   │
│  │  ├── 添加Agent SDK默认配置                               │   │
│  │  └── 返回统一配置                                        │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                              ▼                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    Agent SDK / 直接LLM调用                                  │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 3.5 配置管理器

**文件位置**：`services/agent_sdk_config.py`

```python
from services.agent_sdk_config import agent_sdk_config

# 获取Agent SDK配置（复用数据库）
options = agent_sdk_config.get_agent_sdk_options(user_id=current_user.id)

# 检查Agent SDK是否可用
available = agent_sdk_config.is_agent_sdk_available(user_id=current_user.id)
```

### 3.6 使用场景

| 场景 | provider配置 | 说明 |
|------|-------------|------|
| **Agent SDK模式** | `provider="codebuddy"` | 使用Agent SDK |
| **直接LLM模式** | `provider="openai"` | 使用直接LLM调用（备用） |
| **Ollama模式** | `provider="ollama"` | 使用本地模型 |
| **自定义模型** | `provider="custom"` | 使用自定义模型（如本地LLaMA） |

### 3.7 前端Agent切换入口

> **新增设计**：在诊断中心页面添加Agent类型和模型选择。

**UI设计**：

```
┌─────────────────────────────────────────────────────────────────┐
│  🧠 诊断配置                                                 │
│  Agent类型: [CodeBuddy ▼]  模型: [deepseek-v3.1 ▼]          │
│  诊断模式: (●) 自主诊断  (○) 手动诊断                       │
│  [测试连接]  [保存配置]                                        │
└─────────────────────────────────────────────────────────────────┘
```

**前端实现**：

```javascript
// static/js/components/agent-config.js

class AgentConfig {
    constructor() {
        this.agentType = 'codebuddy';
        this.model = 'deepseek-v3.1';
        this.diagnosisMode = 'autonomous'; // autonomous / manual
    }

    async loadAvailableAgents() {
        const response = await fetch('/api/diagnosis/agent/types');
        const data = await response.json();
        this.renderAgentTypes(data.types);
    }

    async loadAvailableModels(agentType) {
        const response = await fetch(`/api/diagnosis/agent/models?type=${agentType}`);
        const data = await response.json();
        this.renderModels(data.models);
    }

    async saveConfig() {
        await fetch('/api/diagnosis/agent/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                agent_type: this.agentType,
                model: this.model,
                diagnosis_mode: this.diagnosisMode
            })
        });
    }

    render() {
        return `
        <div class="agent-config">
            <div class="form-group">
                <label>Agent类型:</label>
                <select id="agent-type" onchange="agentConfig.onAgentTypeChange()">
                    <option value="codebuddy">CodeBuddy</option>
                    <option value="claude">Claude</option>
                    <option value="custom">自定义</option>
                </select>
            </div>
            <div class="form-group">
                <label>模型:</label>
                <select id="model">
                    <!-- 动态加载 -->
                </select>
            </div>
            <div class="form-group">
                <label>诊断模式:</label>
                <label><input type="radio" name="mode" value="autonomous" checked> 自主诊断</label>
                <label><input type="radio" name="mode" value="manual"> 手动诊断</label>
            </div>
            <button onclick="agentConfig.saveConfig()">保存配置</button>
        </div>
        `;
    }
}
```

### 3.8 用户配置流程

```
用户在"模型配置"页面设置：
┌─────────────────────────────────────────────────────────────────┐
│  🤖 模型配置                                                    │
├─────────────────────────────────────────────────────────────────┤
│  提供商: [CodeBuddy ▼]                                          │
│  API密钥: [********************]                                │
│  模型: [deepseek-v3.1]                                          │
│  网络环境: [内部网络 ▼]                                          │
│                                                                 │
│  [保存配置]  [测试连接]                                          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼ 保存到数据库
                       ai_config表（已有）
                              │
                              ▼ 复用
                    Agent SDK配置
```

---

## 3. 与现有系统整合

### 2.1 现有系统分析

| 模块 | 现有实现 | Agent SDK整合方案 |
|------|---------|------------------|
| **LLM直接调用** | `api/ai_chat.py` | 保留作为备用，Agent SDK优先 |
| **MCP集成** | `api/mcp_proxy.py` | 通过Agent SDK的MCP配置整合 |
| **诊断能力** | `backend/core/diagnosis_capabilities.py` | 转换为Agent工具定义 |
| **Arthas执行** | `backend/core/arthas_executor.py` | 封装为Agent工具 |
| **任务中心** | `api/task_center.py` | Agent执行结果写入task_logs |

### 2.2 整合策略

```
┌─────────────────────────────────────────────────────────────────┐
│                    现有系统                                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐            │
│  │  ai_chat.py │  │ mcp_proxy.py│  │ diagnosis_  │            │
│  │  (LLM调用)  │  │ (MCP集成)   │  │ capabilities│            │
│  └─────────────┘  └─────────────┘  └─────────────┘            │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼ 整合
┌─────────────────────────────────────────────────────────────────┐
│                    Agent SDK统一层                               │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  CodeBuddy Agent SDK                                     │   │
│  │  ├── 保留LLM调用作为备用                                 │   │
│  │  ├── MCP通过SDK配置整合                                  │   │
│  │  └── 诊断能力转换为Agent工具                             │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 2.3 整合清单

| 整合项 | 现状 | 改进方案 | 优先级 |
|--------|------|---------|--------|
| LLM调用 | 直接HTTP调用 | Agent SDK封装，保留备用 | P0 |
| MCP集成 | 独立代理 | Agent SDK MCP配置 | P0 |
| 诊断能力 | 硬编码Python | 转换为@tool装饰器 | P0 |
| Arthas执行 | subprocess | Agent工具封装 | P0 |
| 任务日志 | task_logs表 | Agent执行结果写入 | P1 |
| 权限控制 | Flask-Login | Agent SDK canUseTool | P1 |
| 审计日志 | audit_logs表 | Agent Hook记录 | P1 |

---

## 3. Agent诊断引擎设计

### 3.1 诊断Agent定义

```python
# services/agent/diagnosis_agent.py

from codebuddy_agent_sdk import (
    query, 
    CodeBuddySDKClient, 
    CodeBuddyAgentOptions,
    AssistantMessage,
    TextBlock,
    ToolUseBlock
)
from typing import AsyncIterator, Dict, Any
import json

class DiagnosisAgent:
    """诊断Agent - 基于CodeBuddy Agent SDK"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.options = CodeBuddyAgentOptions(
            model=config.get('model', 'deepseek-v3.1'),
            permission_mode=config.get('permission_mode', 'default'),
            max_turns=config.get('max_turns', 50),
            setting_sources=config.get('setting_sources', ['project'])
        )
    
    async def diagnose(
        self, 
        pod_name: str,
        namespace: str,
        issue_type: str,
        context: Dict[str, Any] = None
    ) -> AsyncIterator[Dict[str, Any]]:
        """执行诊断"""
        
        prompt = self._build_diagnosis_prompt(
            pod_name, namespace, issue_type, context
        )
        
        async with CodeBuddySDKClient(options=self.options) as client:
            await client.query(prompt)
            async for message in client.receive_response():
                yield self._format_message(message)
    
    def _build_diagnosis_prompt(
        self,
        pod_name: str,
        namespace: str,
        issue_type: str,
        context: Dict[str, Any]
    ) -> str:
        """构建诊断提示词"""
        
        return f"""
你是一个Java应用性能诊断专家。请诊断以下Pod的问题：

## 目标信息
- Pod名称: {pod_name}
- 命名空间: {namespace}
- 问题类型: {issue_type}

## 诊断步骤
1. 首先检查Pod状态和基本信息
2. 如果是Arthas连接，执行Arthas诊断命令
3. 分析诊断结果
4. 给出根因分析和优化建议

## 可用工具（受控工具）
- execute_capability: 执行预定义诊断能力（只能调用已注册的能力）
- get_pod_status: 获取Pod状态
- get_pod_metrics: 获取Pod指标
- list_capabilities: 列出可用诊断能力
- analyze_thread_dump: 分析线程转储（纯分析，不执行命令）
- analyze_gc_log: 分析GC日志（纯分析，不执行命令）

## 禁止的工具（安全约束）
- ❌ execute_kubectl: 任意kubectl命令（禁止）
- ❌ execute_arthas_command: 任意Arthas命令（禁止）
- ❌ execute_shell: 任意Shell命令（禁止）

## 输出格式
请按以下格式输出诊断结果：
1. 问题概述
2. 证据链（命令输出）
3. 根本原因分析
4. 优化建议
5. 下一步诊断方向

{f'## 额外上下文\n{json.dumps(context, ensure_ascii=False)}' if context else ''}
"""
    
    def _format_message(self, message) -> Dict[str, Any]:
        """格式化消息"""
        result = {
            "type": getattr(message, 'type', 'unknown'),
            "content": "",
            "tool_calls": []
        }
        
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    result["content"] += block.text
                elif isinstance(block, ToolUseBlock):
                    result["tool_calls"].append({
                        "tool": block.name,
                        "input": block.input
                    })
        
        return result
```

### 3.2 会话管理

```python
# services/agent/session_manager.py

from codebuddy_agent_sdk import CodeBuddySDKClient, CodeBuddyAgentOptions
from typing import Dict, Any, Optional
from datetime import datetime
import json

class SessionManager:
    """会话管理器 - 管理诊断会话"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.sessions: Dict[str, Dict[str, Any]] = {}
    
    async def create_session(
        self, 
        session_id: str,
        pod_name: str,
        namespace: str
    ) -> CodeBuddySDKClient:
        """创建诊断会话"""
        
        options = CodeBuddyAgentOptions(
            model=self.config.get('model', 'deepseek-v3.1'),
            permission_mode=self.config.get('permission_mode', 'default')
        )
        
        client = CodeBuddySDKClient(options=options)
        
        self.sessions[session_id] = {
            "client": client,
            "pod_name": pod_name,
            "namespace": namespace,
            "created_at": datetime.now(),
            "status": "active"
        }
        
        return client
    
    async def resume_session(self, session_id: str) -> Optional[CodeBuddySDKClient]:
        """恢复会话"""
        
        session = self.sessions.get(session_id)
        if session and session["status"] == "active":
            return session["client"]
        return None
    
    async def close_session(self, session_id: str):
        """关闭会话"""
        
        session = self.sessions.get(session_id)
        if session:
            session["status"] = "closed"
            await session["client"].disconnect()
```

---

## 4. Agent Tool Gateway（受控工具网关）

### 4.1 设计原则

| 原则 | 说明 |
|------|------|
| **只暴露受控工具** | Agent只能调用预定义的工具，不能执行任意命令 |
| **禁止任意命令** | 禁止execute_kubectl、execute_arthas_command等 |
| **参数校验** | 所有工具调用必须经过参数校验 |
| **审计记录** | 所有工具调用必须写入audit_logs |

### 4.2 受控工具清单

| 工具名 | 说明 | 参数 | 风险 |
|--------|------|------|------|
| `execute_capability` | 执行预定义诊断能力 | capability_id, params, connection_id | 受控 |
| `get_pod_status` | 获取Pod状态 | connection_id | 只读 |
| `get_pod_metrics` | 获取Pod指标 | connection_id | 只读 |
| `list_capabilities` | 列出可用能力 | category, level | 只读 |
| `get_diagnosis_history` | 获取诊断历史 | connection_id | 只读 |
| `analyze_output` | 分析命令输出 | output, context | 只读 |

### 4.3 禁止的工具

| 工具名 | 原因 |
|--------|------|
| `execute_kubectl` | 任意kubectl命令，安全风险 |
| `execute_arthas_command` | 任意Arthas命令，安全风险 |
| `execute_shell` | 任意Shell命令，安全风险 |
| `modify_connection` | 修改连接状态，超出范围 |
| `delete_pod` | 删除Pod，高风险操作 |

### 4.4 Gateway实现

```python
class AgentToolGateway:
    """Agent工具网关 - 控制Agent可调用的工具"""
    
    # 注册的受控工具
    REGISTERED_TOOLS = {
        'execute_capability': {
            'handler': self._execute_capability,
            'params_schema': {...},
            'risk_level': 'medium',
            'requires_confirmation': True
        },
        'get_pod_status': {
            'handler': self._get_pod_status,
            'params_schema': {...},
            'risk_level': 'low',
            'requires_confirmation': False
        },
        # ... 其他工具
    }
    
    def register_tool(self, name: str, handler: callable, schema: dict, risk: str):
        """注册工具"""
        self.REGISTERED_TOOLS[name] = {
            'handler': handler,
            'params_schema': schema,
            'risk_level': risk
        }
    
    async def execute_tool(self, tool_name: str, params: dict, user_id: int) -> dict:
        """执行工具调用"""
        
        # 1. 检查工具是否注册
        if tool_name not in self.REGISTERED_TOOLS:
            return {'error': f'Tool {tool_name} not registered'}
        
        tool = self.REGISTERED_TOOLS[tool_name]
        
        # 2. 参数校验
        if not self._validate_params(params, tool['params_schema']):
            return {'error': 'Invalid parameters'}
        
        # 3. 权限检查
        if not self._check_permission(tool_name, user_id):
            return {'error': 'Permission denied'}
        
        # 4. 执行工具
        result = await tool['handler'](params)
        
        # 5. 记录审计日志
        AuditService.log_agent_tool_call(
            tool_name=tool_name,
            params=params,
            result=result,
            user_id=user_id
        )
        
        return result
    
    async def _execute_capability(self, params: dict) -> dict:
        """执行诊断能力"""
        return await SkillOrchestrator(
            skill_id=params['capability_id'],
            connection_id=params['connection_id'],
            params=params.get('params', {})
        ).execute()
```

### 4.5 与Agent SDK集成

```python
# 通过Agent SDK的MCP配置注册工具
from codebuddy_agent_sdk import CodeBuddyAgentOptions

options = CodeBuddyAgentOptions(
    model="deepseek-v3.1",
    permission_mode="default",  # P0: 不使用bypassPermissions
    mcp_servers={
        "diagnosis": {
            "type": "stdio",
            "command": "python",
            "args": ["-m", "services.agent.tool_gateway"],
        }
    }
)

# Agent只能调用注册的工具
# 不能执行任意命令
```
    "namespace": str
})
async def get_pod_status(args: Dict[str, Any]) -> Dict[str, Any]:
    """获取Pod状态"""
    
    cmd = [
        "kubectl", "get", "pod", 
        "-n", args["namespace"], 
        args["pod_name"],
        "-o", "json"
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            pod_info = json.loads(result.stdout)
            return {
                "status": pod_info.get("status", {}).get("phase", "Unknown"),
                "node": pod_info.get("spec", {}).get("nodeName", "Unknown"),
                "containers": [
                    c["name"] for c in pod_info.get("spec", {}).get("containers", [])
                ],
                "restart_count": sum(
                    cs.get("restartCount", 0) 
                    for cs in pod_info.get("status", {}).get("containerStatuses", [])
                )
            }
        return {"error": result.stderr}
    except Exception as e:
        return {"error": str(e)}
```

> **安全约束**：不暴露 `execute_kubectl(command)` 这类任意命令工具，只暴露 `get_pod_status(connection_id)` 等受控工具。所有工具调用必须写入 `task_logs` 和 `audit_logs`。

---

## 5. 前端交互设计

### 5.1 诊断中心页面

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  🧠 诊断中心 - 智能诊断                                                        │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │  📋 诊断配置                                                             │   │
│  │  ┌─────────────────────────────────────────────────────────────────┐   │   │
│  │  │  Pod选择: [下拉选择Pod                                          ]│   │   │
│  │  │  命名空间: [production                                          ]│   │   │
│  │  │  问题类型: [CPU飙高 ▼] [内存泄漏 ▼] [死锁检测 ▼] [慢方法 ▼]    │   │   │
│  │  │  诊断模式: (●) 自主诊断 (Agent SDK)  (○) 手动诊断               │   │   │
│  │  └─────────────────────────────────────────────────────────────────┘   │   │
│  │                                                                         │   │
│  │  [🚀 开始诊断]  [📊 查看历史]  [⚙️ 配置]                               │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │  📊 诊断进度                                                             │   │
│  │  ┌─────────────────────────────────────────────────────────────────┐   │   │
│  │  │  进度: ████████████████░░░░░░░░░░░░░░░░░░░░░░ 60% (3/5)         │   │   │
│  │  └─────────────────────────────────────────────────────────────────┘   │   │
│  │                                                                         │   │
│  │  ┌─────────────────────────────────────────────────────────────────┐   │   │
│  │  │  步骤 1/5: 获取Pod状态                                    ✅    │   │   │
│  │  │  ┌─────────────────────────────────────────────────────────┐   │   │   │
│  │  │  │  $ kubectl get pod my-app-pod -o json                   │   │   │   │
│  │  │  │  状态: Running, 节点: node-1, 重启次数: 0               │   │   │   │
│  │  │  └─────────────────────────────────────────────────────────┘   │   │   │
│  │  │  🤖 Agent分析: Pod状态正常                                    │   │   │
│  │  └─────────────────────────────────────────────────────────────────┘   │   │
│  │                                                                         │   │
│  │  ┌─────────────────────────────────────────────────────────────────┐   │   │
│  │  │  步骤 2/5: 执行Arthas dashboard                            ✅    │   │   │
│  │  │  ┌─────────────────────────────────────────────────────────┐   │   │   │
│  │  │  │  $ arthas-boot.jar -c "dashboard -n 1"                  │   │   │   │
│  │  │  │  ID   NAME                    GROUP   Prio  State       │   │   │   │
│  │  │  │  1    main                    main    5     RUNNABLE    │   │   │   │
│  │  │  │  23   pool-1-thread-3         main    5     RUNNABLE    │   │   │   │
│  │  │  └─────────────────────────────────────────────────────────┘   │   │   │
│  │  │  🤖 Agent分析: 发现热点线程pool-1-thread-3                    │   │   │
│  │  └─────────────────────────────────────────────────────────────────┘   │   │
│  │                                                                         │   │
│  │  ┌─────────────────────────────────────────────────────────────────┐   │   │
│  │  │  步骤 3/5: 分析线程堆栈                                    ✅    │   │   │
│  │  │  🤖 Agent分析: CPU占用85%，计算密集型问题                    │   │   │
│  │  └─────────────────────────────────────────────────────────────────┘   │   │
│  │                                                                         │   │
│  │  ┌─────────────────────────────────────────────────────────────────┐   │   │
│  │  │  步骤 4/5: 追踪慢方法                                    ⏳    │   │   │
│  │  │  正在执行: trace com.example.Service process                 │   │   │
│  │  └─────────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │  🤖 AI 诊断摘要                                                        │   │
│  │  ┌─────────────────────────────────────────────────────────────────┐   │   │
│  │  │  **问题类型**: 计算密集型                                       │   │   │
│  │  │  **根本原因**: Service.process()方法中的循环逻辑导致CPU占用过高 │   │   │
│  │  │  **严重程度**: 中等                                             │   │   │
│  │  │  **置信度**: 87%                                                │   │   │
│  │  │                                                                 │   │   │
│  │  │  **建议**:                                                     │   │   │
│  │  │  1. 检查Service.process()中的循环逻辑                          │   │   │
│  │  │  2. 考虑使用异步处理或增加线程池大小                            │   │   │
│  │  │  3. 添加性能监控，设置CPU使用率告警                             │   │   │
│  │  └─────────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                 │
│  [📋 生成报告]  [💾 保存诊断]  [🔄 重新诊断]  [📤 导出结果]                    │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 5.2 前端组件设计

```javascript
// static/js/components/agent-diagnosis.js

class AgentDiagnosis {
    constructor(container) {
        this.container = container;
        this.sessionId = null;
        this.ws = null;
        this.render();
    }
    
    async startDiagnosis(podName, namespace, issueType) {
        // 创建诊断会话
        const response = await fetch('/api/diagnosis/agent/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({
                pod_name: podName,
                namespace: namespace,
                issue_type: issueType
            })
        });
        
        const result = await response.json();
        this.sessionId = result.session_id;
        
        // 连接WebSocket接收实时进度
        this.connectWebSocket(result.websocket_url);
    }
    
    connectWebSocket(url) {
        this.ws = new WebSocket(url);
        
        this.ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            this.handleMessage(data);
        };
    }
    
    handleMessage(data) {
        switch (data.type) {
            case 'step_start':
                this.showStepStart(data.step, data.description);
                break;
            case 'step_complete':
                this.showStepComplete(data.step, data.result);
                break;
            case 'tool_call':
                this.showToolCall(data.tool, data.input, data.output);
                break;
            case 'agent_analysis':
                this.showAgentAnalysis(data.analysis);
                break;
            case 'diagnosis_complete':
                this.showDiagnosisComplete(data.summary);
                break;
        }
    }
    
    showStepStart(step, description) {
        const stepsContainer = this.container.querySelector('.steps-list');
        const stepElement = document.createElement('div');
        stepElement.className = 'step-item running';
        stepElement.innerHTML = `
            <div class="step-header">
                <span class="step-number">${step}</span>
                <span class="step-description">${description}</span>
                <span class="step-status">⏳</span>
            </div>
        `;
        stepsContainer.appendChild(stepElement);
    }
    
    showToolCall(tool, input, output) {
        // 显示工具调用详情
        console.log(`Tool: ${tool}, Input: ${input}, Output: ${output}`);
    }
    
    showAgentAnalysis(analysis) {
        // 显示Agent分析结果
        const analysisContainer = this.container.querySelector('.agent-analysis');
        analysisContainer.innerHTML = `
            <div class="analysis-content">
                ${analysis}
            </div>
        `;
    }
}
```

---

## 6. API设计

### 6.1 诊断API

```python
# api/diagnosis_agent.py

from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from services.agent.diagnosis_agent import DiagnosisAgent
from services.agent.session_manager import SessionManager

diagnosis_agent_bp = Blueprint('diagnosis_agent', __name__)

# 会话管理器
session_manager = SessionManager(config={
    'model': 'deepseek-v3.1',
    'permission_mode': 'default'
})

@diagnosis_agent_bp.route('/api/diagnosis/agent/start', methods=['POST'])
@login_required
def start_diagnosis():
    """启动智能诊断"""
    
    data = request.json
    pod_name = data.get('pod_name')
    namespace = data.get('namespace')
    issue_type = data.get('issue_type')
    
    if not all([pod_name, namespace, issue_type]):
        return jsonify({'error': 'Missing required parameters'}), 400
    
    # 创建会话
    session_id = f"{current_user.id}_{pod_name}_{int(time.time())}"
    
    # 创建Agent
    agent = DiagnosisAgent(config={
        'model': 'deepseek-v3.1',
        'permission_mode': 'default'
    })
    
    # 启动异步诊断
    import asyncio
    asyncio.create_task(run_diagnosis(session_id, agent, pod_name, namespace, issue_type))
    
    return jsonify({
        'session_id': session_id,
        'websocket_url': f'ws://localhost:5001/api/diagnosis/agent/stream/{session_id}'
    })


async def run_diagnosis(session_id, agent, pod_name, namespace, issue_type):
    """运行诊断"""
    
    async for message in agent.diagnose(pod_name, namespace, issue_type):
        # 通过WebSocket推送消息
        await send_websocket_message(session_id, message)


@diagnosis_agent_bp.route('/api/diagnosis/agent/stream/<session_id>')
def diagnosis_stream(session_id):
    """WebSocket流式输出"""
    
    from flask_sockets import Sockets
    
    @sockets.route(f'/api/diagnosis/agent/stream/{session_id}')
    def ws_handler(ws):
        while not ws.closed:
            message = ws.receive()
            if message:
                ws.send(message)
```

---

## 7. 实施计划

### 7.1 阶段划分

| 阶段 | 内容 | 工期 | 产出 |
|------|------|------|------|
| **Phase 1** | Agent SDK集成基础 | 1周 | Agent引擎、工具定义 |
| **Phase 2** | 诊断工具开发 | 2周 | Arthas工具、kubectl工具 |
| **Phase 3** | 诊断流程实现 | 2周 | CPU诊断、内存诊断、死锁检测 |
| **Phase 4** | 前端集成 | 1周 | 诊断中心界面、实时反馈 |
| **Phase 5** | 测试优化 | 1周 | 测试、性能优化 |

### 7.2 文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `services/agent/__init__.py` | 新增 | Agent模块初始化 |
| `services/agent/diagnosis_agent.py` | 新增 | 诊断Agent |
| `services/agent/session_manager.py` | 新增 | 会话管理器 |
| `services/agent/tools/__init__.py` | 新增 | 工具模块初始化 |
| `services/agent/tools/arthas_tools.py` | 新增 | Arthas工具 |
| `services/agent/tools/kubectl_tools.py` | 新增 | kubectl工具 |
| `api/diagnosis_agent.py` | 新增 | 诊断API |
| `static/js/components/agent-diagnosis.js` | 新增 | 前端组件 |
| `tools/config/agent-sdk-config.json` | 新增 | SDK配置 |

---

**文档结束**
