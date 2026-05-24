# Agent 集成实施计划

| 项目 | 内容 |
|---|---|
| 文档状态 | 基于 11-agent-integration-architecture.md 设计文档整理 |
| 创建日期 | 2026-05-24 |
| 版本 | v1.0 |
| 状态 | 实施计划 |

## 1. 目标

实现 Agent SDK 集成，包括 Agent 抽象接口、适配器、工厂、网关、会话管理、资源控制等。

## 2. 架构

Agent 集成作为系统核心层，提供智能诊断能力。采用抽象接口设计，支持多 SDK 切换，具备自动降级能力。

## 3. 核心模块

### 3.1 Agent 抽象接口

```python
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional

class AgentInterface(ABC):
    """Agent 抽象接口"""
    
    @abstractmethod
    async def initialize(self, config: Dict[str, Any]) -> bool:
        """初始化 Agent"""
        pass
    
    @abstractmethod
    async def start_session(self, context: Dict[str, Any]) -> str:
        """开始会话"""
        pass
    
    @abstractmethod
    async def send_message(self, session_id: str, message: str) -> Dict[str, Any]:
        """发送消息"""
        pass
    
    @abstractmethod
    async def get_response(self, session_id: str) -> Dict[str, Any]:
        """获取响应"""
        pass
    
    @abstractmethod
    async def end_session(self, session_id: str) -> bool:
        """结束会话"""
        pass
    
    @abstractmethod
    async def cleanup(self) -> bool:
        """清理资源"""
        pass
```

### 3.2 Agent 适配器

#### 3.2.1 CodeBuddyAgent

```python
class CodeBuddyAgent(AgentInterface):
    """CodeBuddy Agent 适配器"""
    
    def __init__(self):
        self.sdk = None
        self.sessions = {}
    
    async def initialize(self, config: Dict[str, Any]) -> bool:
        """初始化 CodeBuddy SDK"""
        try:
            # 初始化 CodeBuddy SDK
            self.sdk = await self._init_sdk(config)
            return True
        except Exception as e:
            logger.error(f"Initialize CodeBuddy failed: {e}")
            return False
    
    async def start_session(self, context: Dict[str, Any]) -> str:
        """开始 CodeBuddy 会话"""
        session_id = str(uuid.uuid4())
        session = await self.sdk.create_session(context)
        self.sessions[session_id] = session
        return session_id
    
    async def send_message(self, session_id: str, message: str) -> Dict[str, Any]:
        """发送消息到 CodeBuddy"""
        session = self.sessions.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        response = await session.send_message(message)
        return {"content": response.content, "tools": response.tools}
    
    async def get_response(self, session_id: str) -> Dict[str, Any]:
        """获取 CodeBuddy 响应"""
        session = self.sessions.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        response = await session.get_response()
        return {"content": response.content, "tools": response.tools}
    
    async def end_session(self, session_id: str) -> bool:
        """结束 CodeBuddy 会话"""
        session = self.sessions.pop(session_id, None)
        if session:
            await session.end()
            return True
        return False
    
    async def cleanup(self) -> bool:
        """清理 CodeBuddy 资源"""
        try:
            for session in self.sessions.values():
                await session.end()
            self.sessions.clear()
            if self.sdk:
                await self.sdk.cleanup()
            return True
        except Exception as e:
            logger.error(f"Cleanup CodeBuddy failed: {e}")
            return False
```

#### 3.2.2 FallbackAgent

```python
class FallbackAgent(AgentInterface):
    """Fallback Agent 适配器（直接 LLM 调用）"""
    
    def __init__(self):
        self.llm_client = None
        self.sessions = {}
    
    async def initialize(self, config: Dict[str, Any]) -> bool:
        """初始化 LLM 客户端"""
        try:
            self.llm_client = await self._init_llm(config)
            return True
        except Exception as e:
            logger.error(f"Initialize FallbackAgent failed: {e}")
            return False
    
    async def start_session(self, context: Dict[str, Any]) -> str:
        """开始 LLM 会话"""
        session_id = str(uuid.uuid4())
        self.sessions[session_id] = {"context": context, "history": []}
        return session_id
    
    async def send_message(self, session_id: str, message: str) -> Dict[str, Any]:
        """发送消息到 LLM"""
        session = self.sessions.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        session["history"].append({"role": "user", "content": message})
        
        # 调用 LLM
        response = await self.llm_client.chat(
            messages=session["history"],
            tools=self._get_available_tools()
        )
        
        session["history"].append({"role": "assistant", "content": response.content})
        
        return {"content": response.content, "tools": response.tools}
    
    async def get_response(self, session_id: str) -> Dict[str, Any]:
        """获取 LLM 响应"""
        session = self.sessions.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        # 获取最后一条消息
        if session["history"]:
            last_message = session["history"][-1]
            return {"content": last_message["content"], "tools": []}
        
        return {"content": "", "tools": []}
    
    async def end_session(self, session_id: str) -> bool:
        """结束 LLM 会话"""
        return self.sessions.pop(session_id, None) is not None
    
    async def cleanup(self) -> bool:
        """清理 LLM 资源"""
        try:
            self.sessions.clear()
            if self.llm_client:
                await self.llm_client.cleanup()
            return True
        except Exception as e:
            logger.error(f"Cleanup FallbackAgent failed: {e}")
            return False
    
    def _get_available_tools(self) -> List[Dict[str, Any]]:
        """获取可用工具列表"""
        return [
            {
                "name": "execute_capability",
                "description": "执行诊断能力",
                "parameters": {
                    "capability_id": {"type": "integer", "description": "能力ID"},
                    "params": {"type": "object", "description": "参数"}
                }
            },
            {
                "name": "get_pod_status",
                "description": "获取Pod状态",
                "parameters": {
                    "pod_name": {"type": "string", "description": "Pod名称"}
                }
            }
        ]
```

### 3.3 Agent 工厂

```python
class AgentFactory:
    """Agent 工厂 - 自动降级"""
    
    def __init__(self):
        self.agents = {
            "codebuddy": CodeBuddyAgent,
            "fallback": FallbackAgent
        }
        self.current_agent = None
        self.agent_type = None
    
    async def create_agent(self, config: Dict[str, Any]) -> AgentInterface:
        """创建 Agent（自动降级）"""
        agent_type = config.get("agent_type", "codebuddy")
        
        # 尝试创建指定类型的 Agent
        for try_type in [agent_type, "fallback"]:
            try:
                agent_class = self.agents.get(try_type)
                if not agent_class:
                    continue
                
                agent = agent_class()
                success = await agent.initialize(config)
                
                if success:
                    self.current_agent = agent
                    self.agent_type = try_type
                    logger.info(f"Created agent: {try_type}")
                    return agent
                else:
                    logger.warning(f"Failed to create agent: {try_type}")
            except Exception as e:
                logger.error(f"Error creating agent {try_type}: {e}")
        
        raise RuntimeError("Failed to create any agent")
    
    async def get_agent(self) -> AgentInterface:
        """获取当前 Agent"""
        if not self.current_agent:
            raise RuntimeError("No agent created")
        return self.current_agent
    
    async def cleanup(self):
        """清理所有 Agent"""
        if self.current_agent:
            await self.current_agent.cleanup()
            self.current_agent = None
            self.agent_type = None
```

### 3.4 Agent Tool Gateway

```python
class AgentToolGateway:
    """Agent 工具网关 - 受控工具暴露"""
    
    def __init__(self):
        self.tools = {}
        self.permissions = {}
    
    def register_tool(self, name: str, handler: callable, 
                      description: str, parameters: Dict[str, Any],
                      risk_level: str = "low"):
        """注册工具"""
        self.tools[name] = {
            "handler": handler,
            "description": description,
            "parameters": parameters,
            "risk_level": risk_level
        }
        
        # 设置权限
        self.permissions[name] = {
            "require_confirmation": risk_level in ["medium", "high"],
            "require_audit": risk_level == "high"
        }
    
    async def execute_tool(self, tool_name: str, params: Dict[str, Any],
                           user_id: int, context: Dict[str, Any]) -> Dict[str, Any]:
        """执行工具"""
        tool = self.tools.get(tool_name)
        if not tool:
            raise ValueError(f"Tool {tool_name} not found")
        
        # 检查权限
        permission = self.permissions.get(tool_name, {})
        if permission.get("require_confirmation"):
            # 需要确认
            confirmed = await self._request_confirmation(tool_name, params, user_id)
            if not confirmed:
                return {"error": "用户取消执行"}
        
        if permission.get("require_audit"):
            # 记录审计日志
            self._log_audit(tool_name, params, user_id, context)
        
        # 执行工具
        try:
            result = await tool["handler"](params, context)
            return {"success": True, "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """获取工具定义（供 Agent 使用）"""
        definitions = []
        for name, tool in self.tools.items():
            definitions.append({
                "name": name,
                "description": tool["description"],
                "parameters": tool["parameters"]
            })
        return definitions
    
    async def _request_confirmation(self, tool_name: str, params: Dict[str, Any],
                                    user_id: int) -> bool:
        """请求确认"""
        # 实现确认逻辑
        return True
    
    def _log_audit(self, tool_name: str, params: Dict[str, Any],
                   user_id: int, context: Dict[str, Any]):
        """记录审计日志"""
        # 实现审计日志记录
        pass
```

## 4. 会话管理

### 4.1 SessionManager

```python
class SessionManager:
    """会话管理器 - 持久化"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.sessions = {}
    
    async def create_session(self, user_id: int, agent_type: str,
                             context: Dict[str, Any]) -> str:
        """创建会话"""
        session_id = str(uuid.uuid4())
        
        # 持久化到数据库
        db = sqlite3.connect(self.db_path)
        db.execute(
            """INSERT INTO agent_sessions 
               (id, user_id, agent_type, context, status)
               VALUES (?, ?, ?, ?, ?)""",
            (session_id, user_id, agent_type, json.dumps(context), "active")
        )
        db.commit()
        db.close()
        
        # 内存缓存
        self.sessions[session_id] = {
            "user_id": user_id,
            "agent_type": agent_type,
            "context": context,
            "status": "active",
            "created_at": datetime.now()
        }
        
        return session_id
    
    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取会话"""
        # 先查内存
        if session_id in self.sessions:
            return self.sessions[session_id]
        
        # 再查数据库
        db = sqlite3.connect(self.db_path)
        row = db.execute(
            "SELECT * FROM agent_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        db.close()
        
        if row:
            session = {
                "id": row[0],
                "user_id": row[1],
                "agent_type": row[2],
                "context": json.loads(row[3]),
                "status": row[4],
                "created_at": row[5]
            }
            self.sessions[session_id] = session
            return session
        
        return None
    
    async def end_session(self, session_id: str) -> bool:
        """结束会话"""
        # 更新数据库
        db = sqlite3.connect(self.db_path)
        db.execute(
            "UPDATE agent_sessions SET status = 'ended' WHERE id = ?",
            (session_id,)
        )
        db.commit()
        db.close()
        
        # 更新内存
        if session_id in self.sessions:
            self.sessions[session_id]["status"] = "ended"
            return True
        
        return False
    
    async def cleanup_expired(self, ttl_seconds: int = 3600):
        """清理过期会话"""
        cutoff = datetime.now() - timedelta(seconds=ttl_seconds)
        
        # 清理内存
        expired = [sid for sid, s in self.sessions.items() 
                   if s["created_at"] < cutoff and s["status"] == "active"]
        for sid in expired:
            await self.end_session(sid)
        
        # 清理数据库
        db = sqlite3.connect(self.db_path)
        db.execute(
            """UPDATE agent_sessions 
               SET status = 'expired' 
               WHERE status = 'active' AND created_at < ?""",
            (cutoff.isoformat(),)
        )
        db.commit()
        db.close()
```

## 5. 资源控制

### 5.1 AsyncTaskManager

```python
class AsyncTaskManager:
    """异步任务管理器 - 超时、取消、并发限制"""
    
    def __init__(self, max_concurrent: int = 5, default_timeout: int = 60):
        self.max_concurrent = max_concurrent
        self.default_timeout = default_timeout
        self.tasks = {}
        self.semaphore = asyncio.Semaphore(max_concurrent)
    
    async def execute_with_limit(self, coro, task_id: str, 
                                 timeout: int = None) -> Any:
        """带限制执行任务"""
        timeout = timeout or self.default_timeout
        
        async with self.semaphore:
            task = asyncio.create_task(coro)
            self.tasks[task_id] = task
            
            try:
                result = await asyncio.wait_for(task, timeout=timeout)
                return result
            except asyncio.TimeoutError:
                task.cancel()
                raise TimeoutError(f"Task {task_id} timed out after {timeout}s")
            finally:
                self.tasks.pop(task_id, None)
    
    async def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        task = self.tasks.get(task_id)
        if task and not task.done():
            task.cancel()
            return True
        return False
    
    async def cleanup(self):
        """清理所有任务"""
        for task in self.tasks.values():
            if not task.done():
                task.cancel()
        self.tasks.clear()
```

## 6. 任务分解

### 任务 1：实现 Agent 抽象接口

**文件：**
- 创建：`services/agent_interface.py`

**步骤：**
1. 定义 AgentInterface 抽象类
2. 定义方法签名
3. 编写接口文档
4. 编写单元测试

### 任务 2：实现 CodeBuddyAgent

**文件：**
- 创建：`services/agents/codebuddy_agent.py`

**步骤：**
1. 实现初始化方法
2. 实现会话管理
3. 实现消息发送
4. 实现资源清理
5. 编写单元测试

### 任务 3：实现 FallbackAgent

**文件：**
- 创建：`services/agents/fallback_agent.py`

**步骤：**
1. 实现初始化方法
2. 实现会话管理
3. 实现 LLM 调用
4. 实现工具定义
5. 编写单元测试

### 任务 4：实现 Agent 工厂

**文件：**
- 创建：`services/agent_factory.py`

**步骤：**
1. 实现 Agent 创建
2. 实现自动降级
3. 实现资源清理
4. 编写单元测试

### 任务 5：实现 Agent Tool Gateway

**文件：**
- 创建：`services/agent_tool_gateway.py`

**步骤：**
1. 实现工具注册
2. 实现权限控制
3. 实现工具执行
4. 实现审计日志
5. 编写单元测试

### 任务 6：实现会话管理

**文件：**
- 创建：`services/session_manager.py`

**步骤：**
1. 实现会话创建
2. 实现会话查询
3. 实现会话持久化
4. 实现会话清理
5. 编写单元测试

### 任务 7：实现资源控制

**文件：**
- 创建：`services/async_task_manager.py`

**步骤：**
1. 实现并发限制
2. 实现超时控制
3. 实现任务取消
4. 编写单元测试

### 任务 8：实现 Agent API

**文件：**
- 创建：`api/agent.py`
- 修改：`server.py`

**步骤：**
1. 实现开始会话 API
2. 实现发送消息 API
3. 实现获取响应 API
4. 实现结束会话 API
5. 编写单元测试

## 7. 验收标准

- [ ] Agent 抽象接口实现完成
- [ ] CodeBuddyAgent 实现完成
- [ ] FallbackAgent 实现完成
- [ ] Agent 工厂实现完成
- [ ] Agent Tool Gateway 实现完成
- [ ] 会话管理实现完成
- [ ] 资源控制实现完成
- [ ] Agent API 实现完成
- [ ] 单元测试覆盖率 > 80%
- [ ] 集成测试通过

## 8. 风险与缓解措施

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| Agent SDK 不稳定 | 高 | 自动降级到 FallbackAgent |
| 会话状态丢失 | 中 | 持久化到数据库 |
| 并发资源耗尽 | 中 | 信号量限制 |
| LLM 调用超时 | 中 | 超时控制 + 重试 |

## 9. 后续演进

### P1 阶段

- 实现 Agent 自主诊断
- 实现多 Agent 协作
- 实现 Agent 学习

### P2 阶段

- 实现分布式 Agent
- 实现 Agent 市场
- 实现 Agent 编排
