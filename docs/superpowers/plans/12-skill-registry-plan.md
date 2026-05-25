# Skill Registry 实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 实现 Skill Registry + Workflow Engine + Agent Tool Gateway，包括导入、校验、版本化、发布、DSL 执行、受控工具暴露等。

**Architecture:** 系统核心抽象层，定义诊断能力的注册、执行和安全暴露。采用分层设计，支持管理态和生产执行态分离。

**Tech Stack:** Python, SQLite, 异步编程, DSL 执行引擎

---

## 1. 目标

实现 Skill Registry + Workflow Engine + Agent Tool Gateway，包括导入、校验、版本化、发布、DSL 执行、受控工具暴露等。

## 2. 架构

系统核心抽象层，定义诊断能力的注册、执行和安全暴露。采用分层设计，支持管理态和生产执行态分离。

## 3. 核心模块

### 3.1 Skill Registry（技能注册中心）

```python
class SkillRegistry:
    """技能注册中心 - 管理态核心"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
    
    async def import_skill(self, skill_data: Dict[str, Any]) -> int:
        """导入 Skill"""
        # 1. 校验格式
        validated = self._validate_skill(skill_data)
        
        # 2. 存储到 skill_registry
        skill_id = self._store_skill(validated)
        
        # 3. 记录审计日志
        self._log_audit("import_skill", skill_id, skill_data)
        
        return skill_id
    
    async def validate_skill(self, skill_id: int) -> bool:
        """校验 Skill"""
        skill = self._get_skill(skill_id)
        if not skill:
            raise ValueError(f"Skill {skill_id} not found")
        
        # 1. 校验参数 schema
        if not self._validate_parameters_schema(skill):
            return False
        
        # 2. 校验命令白名单
        if not self._validate_command_whitelist(skill):
            return False
        
        # 3. 更新状态
        self._update_skill_status(skill_id, "validated")
        
        return True
    
    async def publish_skill(self, skill_id: int) -> bool:
        """发布 Skill 到 diagnosis_capabilities"""
        skill = self._get_skill(skill_id)
        if not skill:
            raise ValueError(f"Skill {skill_id} not found")
        
        # 1. 检查状态
        if skill["status"] != "validated":
            raise ValueError(f"Skill status must be 'validated', got '{skill['status']}'")
        
        # 2. 创建 diagnosis_capability
        capability_id = self._create_capability(skill)
        
        # 3. 更新状态
        self._update_skill_status(skill_id, "published")
        
        # 4. 记录审计日志
        self._log_audit("publish_skill", skill_id, {"capability_id": capability_id})
        
        return True
    
    def _validate_skill(self, skill_data: Dict[str, Any]) -> Dict[str, Any]:
        """校验 Skill 格式"""
        required_fields = ["name", "version", "category", "level"]
        for field in required_fields:
            if field not in skill_data:
                raise ValueError(f"Missing required field: {field}")
        
        # 校验 category
        valid_categories = ["quick", "tool", "scenario", "ai"]
        if skill_data["category"] not in valid_categories:
            raise ValueError(f"Invalid category: {skill_data['category']}")
        
        # 校验 level
        if skill_data["level"] not in [1, 2, 3, 4]:
            raise ValueError(f"Invalid level: {skill_data['level']}")
        
        return skill_data
    
    def _validate_parameters_schema(self, skill: Dict[str, Any]) -> bool:
        """校验参数 Schema"""
        if "parameters_schema" not in skill:
            return True
        
        try:
            schema = json.loads(skill["parameters_schema"])
            # 校验 JSON Schema 格式
            return "type" in schema or "properties" in schema
        except json.JSONDecodeError:
            return False
    
    def _validate_command_whitelist(self, skill: Dict[str, Any]) -> bool:
        """校验命令白名单"""
        if "arthas_command" not in skill:
            return True
        
        # Arthas 命令白名单
        whitelist = [
            "dashboard", "thread", "jad", "watch", "trace", "stack",
            "monitor", "profiler", "heapdump", "vmoption", "sc", "sm"
        ]
        
        command = skill["arthas_command"].split()[0]
        return command in whitelist
    
    def _store_skill(self, skill_data: Dict[str, Any]) -> int:
        """存储 Skill"""
        db = sqlite3.connect(self.db_path)
        cursor = db.execute(
            """INSERT INTO skill_registry 
               (name, version, description, category, level, risk_level,
                source, status, dsl, parameters_schema, llm_prompt,
                arthas_command, handler, created_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (skill_data["name"], skill_data["version"],
             skill_data.get("description"), skill_data["category"],
             skill_data["level"], skill_data.get("risk_level", "low"),
             skill_data.get("source", "custom"), "draft",
             skill_data.get("dsl"), skill_data.get("parameters_schema"),
             skill_data.get("llm_prompt"), skill_data.get("arthas_command"),
             skill_data.get("handler"), skill_data.get("created_by"))
        )
        db.commit()
        skill_id = cursor.lastrowid
        db.close()
        return skill_id
    
    def _get_skill(self, skill_id: int) -> Optional[Dict[str, Any]]:
        """获取 Skill"""
        db = sqlite3.connect(self.db_path)
        row = db.execute(
            "SELECT * FROM skill_registry WHERE id = ?", (skill_id,)
        ).fetchone()
        db.close()
        
        if row:
            return {
                "id": row[0], "name": row[1], "version": row[2],
                "description": row[3], "category": row[4], "level": row[5],
                "risk_level": row[6], "estimated_duration": row[7],
                "source": row[8], "status": row[9], "dsl": row[10],
                "parameters_schema": row[11], "llm_prompt": row[12],
                "arthas_command": row[13], "handler": row[14],
                "created_by": row[15], "created_at": row[16],
                "updated_at": row[17]
            }
        return None
    
    def _update_skill_status(self, skill_id: int, status: str):
        """更新 Skill 状态"""
        db = sqlite3.connect(self.db_path)
        db.execute(
            "UPDATE skill_registry SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (status, skill_id)
        )
        db.commit()
        db.close()
    
    def _create_capability(self, skill: Dict[str, Any]) -> int:
        """创建诊断能力"""
        db = sqlite3.connect(self.db_path)
        cursor = db.execute(
            """INSERT INTO diagnosis_capabilities 
               (skill_id, name, type, category, level, risk_level,
                parameters_schema, description, estimated_duration, enabled)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (skill["id"], skill["name"], self._get_capability_type(skill),
             skill["category"], skill["level"], skill.get("risk_level", "low"),
             skill.get("parameters_schema"), skill.get("description"),
             skill.get("estimated_duration", 10), 1)
        )
        db.commit()
        capability_id = cursor.lastrowid
        db.close()
        return capability_id
    
    def _get_capability_type(self, skill: Dict[str, Any]) -> str:
        """获取能力类型"""
        if skill.get("arthas_command"):
            return "arthas_command"
        elif skill.get("dsl"):
            return "scenario"
        elif skill.get("handler"):
            return "ai_diagnosis"
        return "unknown"
    
    def _log_audit(self, action: str, skill_id: int, details: Any):
        """记录审计日志"""
        # 实现审计日志记录
        pass
```

### 3.2 Workflow Engine（工作流引擎）

```python
class WorkflowEngine:
    """工作流引擎 - DSL步骤执行"""
    
    def __init__(self, executor, db_path: str):
        self.executor = executor
        self.db_path = db_path
    
    async def execute_skill(self, capability_id: int, params: Dict[str, Any],
                            connection_id: str) -> str:
        """执行 Skill"""
        # 1. 获取能力定义
        capability = self._get_capability(capability_id)
        if not capability:
            raise ValueError(f"Capability {capability_id} not found")
        
        # 2. 创建执行记录
        run_id = self._create_run(capability_id, connection_id, params)
        
        # 3. 执行 DSL
        try:
            if capability.get("dsl"):
                await self._execute_dsl(run_id, capability["dsl"], params, connection_id)
            elif capability.get("arthas_command"):
                await self._execute_command(run_id, capability["arthas_command"], params, connection_id)
            elif capability.get("handler"):
                await self._execute_handler(run_id, capability["handler"], params, connection_id)
            
            # 4. 更新状态
            self._update_run_status(run_id, "success")
            
        except Exception as e:
            self._update_run_status(run_id, "failed", str(e))
            raise
        
        return run_id
    
    async def _execute_dsl(self, run_id: str, dsl: str, params: Dict[str, Any],
                           connection_id: str):
        """执行 DSL"""
        steps = self._parse_dsl(dsl)
        
        for i, step in enumerate(steps):
            # 记录步骤开始
            step_id = self._create_step(run_id, i + 1, step)
            
            try:
                # 参数替换
                command = self._substitute_params(step["command"], params)
                
                # 执行命令
                output = await self.executor.execute(command, connection_id)
                
                # 记录步骤完成
                self._update_step_status(step_id, "success", output)
                
                # 传递步骤结果
                params[f"step{i + 1}"] = {"output": output}
                
            except Exception as e:
                self._update_step_status(step_id, "failed", error=str(e))
                
                # 检查失败策略
                if step.get("on_failure") == "fail_fast":
                    raise
                elif step.get("on_failure") == "continue":
                    continue
    
    async def _execute_command(self, run_id: str, command: str, params: Dict[str, Any],
                               connection_id: str):
        """执行单条命令"""
        step_id = self._create_step(run_id, 1, {"command": command})
        
        try:
            # 参数替换
            full_command = self._substitute_params(command, params)
            
            # 执行命令
            output = await self.executor.execute(full_command, connection_id)
            
            # 记录步骤完成
            self._update_step_status(step_id, "success", output)
            
        except Exception as e:
            self._update_step_status(step_id, "failed", error=str(e))
            raise
    
    async def _execute_handler(self, run_id: str, handler: str, params: Dict[str, Any],
                               connection_id: str):
        """执行 Handler"""
        step_id = self._create_step(run_id, 1, {"handler": handler})
        
        try:
            # 动态导入 Handler
            module_path, function_name = handler.rsplit(".", 1)
            module = importlib.import_module(module_path)
            handler_func = getattr(module, function_name)
            
            # 执行 Handler
            output = await handler_func(params, connection_id)
            
            # 记录步骤完成
            self._update_step_status(step_id, "success", output)
            
        except Exception as e:
            self._update_step_status(step_id, "failed", error=str(e))
            raise
    
    def _parse_dsl(self, dsl: str) -> List[Dict[str, Any]]:
        """解析 DSL"""
        # 简单 YAML 解析
        import yaml
        data = yaml.safe_load(dsl)
        return data.get("steps", [])
    
    def _substitute_params(self, template: str, params: Dict[str, Any]) -> str:
        """参数替换"""
        result = template
        for key, value in params.items():
            if isinstance(value, dict) and "output" in value:
                result = result.replace(f"${{{key}.output}}", value["output"])
            else:
                result = result.replace(f"${{{key}}}", str(value))
        return result
    
    def _create_run(self, capability_id: int, connection_id: str,
                    params: Dict[str, Any]) -> str:
        """创建执行记录"""
        run_id = str(uuid.uuid4())
        
        db = sqlite3.connect(self.db_path)
        db.execute(
            """INSERT INTO task_logs 
               (id, capability_id, connection_id, status, params_json, execution_mode)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (run_id, capability_id, connection_id, "running",
             json.dumps(params), "immediate")
        )
        db.commit()
        db.close()
        
        return run_id
    
    def _create_step(self, run_id: str, step_number: int,
                     step_data: Dict[str, Any]) -> int:
        """创建步骤记录"""
        db = sqlite3.connect(self.db_path)
        cursor = db.execute(
            """INSERT INTO step_logs 
               (run_id, step_number, step_name, step_type, command, status)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (run_id, step_number, step_data.get("name"),
             step_data.get("type", "arthas_command"),
             step_data.get("command"), "running")
        )
        db.commit()
        step_id = cursor.lastrowid
        db.close()
        
        return step_id
    
    def _update_step_status(self, step_id: int, status: str,
                            output: str = None, error: str = None):
        """更新步骤状态"""
        db = sqlite3.connect(self.db_path)
        db.execute(
            """UPDATE step_logs 
               SET status = ?, output = ?, error_message = ?
               WHERE id = ?""",
            (status, output, error, step_id)
        )
        db.commit()
        db.close()
    
    def _update_run_status(self, run_id: str, status: str, error: str = None):
        """更新执行状态"""
        db = sqlite3.connect(self.db_path)
        db.execute(
            """UPDATE task_logs 
               SET status = ?, error_message = ?
               WHERE id = ?""",
            (status, error, run_id)
        )
        db.commit()
        db.close()
    
    def _get_capability(self, capability_id: int) -> Optional[Dict[str, Any]]:
        """获取能力定义"""
        db = sqlite3.connect(self.db_path)
        row = db.execute(
            "SELECT * FROM diagnosis_capabilities WHERE id = ?", (capability_id,)
        ).fetchone()
        db.close()
        
        if row:
            return {
                "id": row[0], "skill_id": row[1], "name": row[2],
                "type": row[3], "category": row[4], "level": row[5],
                "risk_level": row[6], "parameters_schema": row[7],
                "description": row[8], "estimated_duration": row[9],
                "enabled": row[10]
            }
        return None
```

### 3.3 Agent Tool Gateway

```python
class AgentToolGateway:
    """Agent 工具网关 - 受控工具暴露"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
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

## 4. 任务分解

### 任务 1：实现 Skill Registry

**文件：**
- 创建：`services/skill_registry.py`

**步骤：**
1. 实现导入功能
2. 实现校验功能
3. 实现发布功能
4. 实现状态管理
5. 编写单元测试

### 任务 2：实现 Workflow Engine

**文件：**
- 创建：`services/workflow_engine.py`

**步骤：**
1. 实现 DSL 解析
2. 实现步骤执行
3. 实现参数替换
4. 实现错误处理
5. 编写单元测试

### 任务 3：实现 Agent Tool Gateway

**文件：**
- 创建：`services/agent_tool_gateway.py`

**步骤：**
1. 实现工具注册
2. 实现权限控制
3. 实现工具执行
4. 实现审计日志
5. 编写单元测试

### 任务 4：实现 Skill 管理 API

**文件：**
- 创建：`api/skills.py`
- 修改：`server.py`

**步骤：**
1. 实现导入 API
2. 实现校验 API
3. 实现发布 API
4. 实现查询 API
5. 编写单元测试

### 任务 5：实现预制 Skill 数据

**文件：**
- 创建：`data/builtin_skills.json`
- 修改：`models/db.py`

**步骤：**
1. 设计预制 Skill 格式
2. 实现数据初始化
3. 实现幂等性检查
4. 编写单元测试

### 任务 6：实现 Skill 管理中心前端

**文件：**
- 创建：`static/skill-management.html`
- 创建：`static/js/components/skill-management.js`

**步骤：**
1. 设计 Skill 列表页面
2. 实现 Skill 详情页面
3. 实现 Skill 编辑功能
4. 编写样式

### 任务 7：集成测试

**文件：**
- 创建：`tests/test_skill_system.py`

**步骤：**
1. 编写 Skill 导入测试
2. 编写 Skill 校验测试
3. 编写 Skill 发布测试
4. 编写 DSL 执行测试
5. 编写 Agent 工具测试

## 5. 验收标准

- [ ] Skill Registry 实现完成
- [ ] Workflow Engine 实现完成
- [ ] Agent Tool Gateway 实现完成
- [ ] Skill 管理 API 实现完成
- [ ] 预制 Skill 数据实现完成
- [ ] Skill 管理中心前端实现完成
- [ ] 集成测试通过
- [ ] 单元测试覆盖率 > 80%

## 6. 风险与缓解措施

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| DSL 解析错误 | 中 | 严格校验 + 错误提示 |
| 参数注入 | 高 | 白名单校验 + 转义 |
| 执行超时 | 中 | 超时控制 + 取消 |
| 状态不一致 | 中 | 事务 + 幂等性 |

## 7. 后续演进

### P1 阶段

- 实现 Skill 版本管理
- 实现 Skill 回滚
- 实现 Skill 市场

### P2 阶段

- 实现 Skill 可视化编排
- 实现 Skill 自动测试
- 实现 Skill 智能推荐
