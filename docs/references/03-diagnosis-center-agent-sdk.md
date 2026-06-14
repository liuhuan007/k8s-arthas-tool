# K8s Arthas 智能诊断平台 — Agent SDK 集成方案

> 基于Agent SDK实现智能诊断，替代直接LLM调用

**文档版本**: v1.0
**创建日期**: 2026-05-23
**状态**: 调研完成

---

## 目录

1. [调研概述](#1-调研概述)
2. [主流Agent SDK对比](#2-主流agent-sdk对比)
3. [推荐方案](#3-推荐方案)
4. [架构设计](#4-架构设计)
5. [实现计划](#5-实现计划)

---

## 1. 调研概述

### 1.1 背景

传统直接调用LLM API的方式存在以下问题：
- 需要手动管理对话上下文
- 工具调用需要自行实现
- 缺乏自主决策能力
- 无法处理复杂的多步骤诊断流程

### 1.2 目标

使用Agent SDK实现：
- **自主诊断**：Agent可以自主执行诊断流程
- **工具调用**：Agent可以调用Arthas命令、kubectl等工具
- **多步骤推理**：Agent可以进行复杂的诊断推理
- **上下文管理**：自动管理对话和诊断上下文

---

## 2. 主流Agent SDK对比

### 2.1 Claude Agent SDK (Anthropic)

| 项目 | 说明 |
|------|------|
| **提供商** | Anthropic |
| **语言** | Python |
| **版本** | 2026年最新版 |
| **GitHub** | github.com/anthropics/claude-agent-sdk-python |
| **文档** | code.claude.com/docs/en/agent-sdk/python |

**核心特性**：
- ✅ 自定义工具（Tool）
- ✅ 安全钩子（Safety Hooks）
- ✅ 子代理（Subagents）
- ✅ MCP集成
- ✅ 权限控制

**安装方式**：
```bash
pip install claude-agent-sdk
```

**代码示例**：
```python
from claude_agent_sdk import query, tool

@tool("execute_arthas", "Execute Arthas command", {"command": str})
async def execute_arthas(args):
    # 执行Arthas命令
    result = await run_arthas_command(args["command"])
    return {"output": result}

async for message in query(
    prompt="诊断CPU飙高问题",
    tools=[execute_arthas]
):
    print(message)
```

### 2.2 CodeBuddy Agent SDK (腾讯)

| 项目 | 说明 |
|------|------|
| **提供商** | 腾讯 |
| **语言** | Python / TypeScript |
| **版本** | v0.3.147 (2026-05-11) |
| **PyPI** | pypi.org/project/codebuddy-agent-sdk |
| **文档** | staging-codebuddy.tencent.com/docs/cli/sdk-python |

**核心特性**：
- ✅ 自定义工具（Tool）
- ✅ 权限控制（Permission Mode）
- ✅ 会话管理（Session）
- ✅ MCP服务器
- ✅ 多模型支持

**安装方式**：
```bash
# 推荐使用uv
uv add codebuddy-agent-sdk

# 或使用pip
pip install codebuddy-agent-sdk
```

**代码示例**：
```python
from codebuddy_agent_sdk import query, tool
from typing import Any

@tool("execute_arthas", "Execute Arthas command", {"command": str})
async def execute_arthas(args: dict[str, Any]) -> dict[str, Any]:
    result = await run_arthas_command(args["command"])
    return {"output": result}

async for message in query(
    prompt="诊断CPU飙高问题",
    options={"permission_mode": "bypassPermissions"}
):
    if hasattr(message, 'content'):
        for block in message.content:
            if hasattr(block, 'text'):
                print(block.text)
```

### 2.3 其他Agent框架

| 框架 | 特点 | 适用场景 |
|------|------|---------|
| **LangChain Agent** | 生态丰富，工具多 | 通用Agent开发 |
| **AutoGPT** | 自主性强，适合复杂任务 | 高度自主场景 |
| **CrewAI** | 多Agent协作 | 团队协作场景 |
| **MetaGPT** | 多角色协作 | 复杂项目 |

---

## 3. 推荐方案

### 3.1 方案选择

**推荐使用 CodeBuddy Agent SDK**

理由：
1. **国内支持**：腾讯出品，国内访问稳定
2. **Python原生**：与现有Flask后端无缝集成
3. **权限控制**：支持细粒度权限管理
4. **会话管理**：支持多轮对话和会话恢复
5. **多模型支持**：可切换不同LLM模型

### 3.2 备选方案

**Claude Agent SDK 作为备选**

理由：
1. **功能强大**：支持子代理、安全钩子
2. **生态完善**：MCP集成、工具市场
3. **稳定性高**：Anthropic官方维护

---

## 4. 架构设计

### 4.1 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    诊断中心（前端）                               │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    诊断API（Flask）                              │
│  /api/diagnosis/*                                               │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Agent诊断引擎                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Agent SDK (CodeBuddy / Claude)                         │   │
│  │  ├── 诊断Agent                                          │   │
│  │  ├── 工具集                                              │   │
│  │  └── 会话管理                                            │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    工具层                                         │
│  ├── Arthas工具（arthas-boot.jar）                              │
│  ├── kubectl工具                                               │
│  ├── 日志分析工具                                               │
│  └── 指标查询工具                                               │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    目标Pod                                       │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 Agent工具定义

```python
# tools/diagnosis_tools.py

from codebuddy_agent_sdk import tool
from typing import Any

@tool("execute_arthas_command", "Execute Arthas command in Pod", {
    "pod_name": str,
    "namespace": str,
    "command": str,
    "container": str
})
async def execute_arthas_command(args: dict[str, Any]) -> dict[str, Any]:
    """执行Arthas命令"""
    import subprocess
    
    cmd = f"kubectl exec -n {args['namespace']} {args['pod_name']} -- {args['command']}"
    if args.get('container'):
        cmd = f"kubectl exec -n {args['namespace']} {args['pod_name']} --container {args['container']} -- {args['command']}"
    
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return {
        "stdout": result.stdout,
        "stderr": result.stderr,
        "returncode": result.returncode
    }

@tool("get_pod_status", "Get Pod status and metrics", {
    "pod_name": str,
    "namespace": str
})
async def get_pod_status(args: dict[str, Any]) -> dict[str, Any]:
    """获取Pod状态"""
    import subprocess
    
    cmd = f"kubectl get pod -n {args['namespace']} {args['pod_name']} -o json"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return {"output": result.stdout}

@tool("analyze_thread_dump", "Analyze thread dump for deadlock or high CPU", {
    "thread_output": str
})
async def analyze_thread_dump(args: dict[str, Any]) -> dict[str, Any]:
    """分析线程转储"""
    # 分析线程转储，识别死锁、高CPU等问题
    output = args["thread_output"]
    
    analysis = {
        "has_deadlock": "BLOCKED" in output and "waiting to lock" in output,
        "high_cpu_threads": [],
        "summary": ""
    }
    
    # 解析线程信息
    lines = output.split('\n')
    for line in lines:
        if 'RUNNABLE' in line and 'cpu' in line.lower():
            analysis["high_cpu_threads"].append(line.strip())
    
    return analysis
```

### 4.3 诊断Agent实现

```python
# services/diagnosis_agent.py

from codebuddy_agent_sdk import query, CodeBuddySDKClient, CodeBuddyAgentOptions
from typing import AsyncIterator
import json

class DiagnosisAgent:
    def __init__(self, config: dict):
        self.config = config
        self.options = CodeBuddyAgentOptions(
            model=config.get('model', 'deepseek-v3.1'),
            permission_mode=config.get('permission_mode', 'bypassPermissions')
        )
    
    async def diagnose(self, pod_name: str, namespace: str, issue_type: str) -> AsyncIterator[dict]:
        """执行诊断"""
        
        prompt = f"""
你是一个Java应用性能诊断专家。请诊断以下Pod的问题：

Pod名称: {pod_name}
命名空间: {namespace}
问题类型: {issue_type}

请按照以下步骤进行诊断：
1. 首先检查Pod状态和基本信息
2. 如果是Arthas连接，执行Arthas诊断命令
3. 分析诊断结果
4. 给出根因分析和优化建议

请使用提供的工具执行诊断。
"""
        
        async with CodeBuddySDKClient(options=self.options) as client:
            await client.query(prompt)
            async for message in client.receive_response():
                yield self._format_message(message)
    
    def _format_message(self, message) -> dict:
        """格式化消息"""
        return {
            "type": getattr(message, 'type', 'unknown'),
            "content": getattr(message, 'content', ''),
            "tool_calls": getattr(message, 'tool_calls', [])
        }
```

---

## 5. 实现计划

### 5.1 阶段划分

| 阶段 | 内容 | 工期 | 产出 |
|------|------|------|------|
| Phase 1 | SDK集成基础 | 1周 | Agent SDK集成、工具定义 |
| Phase 2 | 诊断工具开发 | 2周 | Arthas工具、kubectl工具 |
| Phase 3 | 诊断流程实现 | 2周 | CPU诊断、内存诊断、死锁检测 |
| Phase 4 | 前端集成 | 1周 | 诊断中心界面、实时反馈 |
| Phase 5 | 测试优化 | 1周 | 测试、性能优化 |

### 5.2 关键任务

**Phase 1: SDK集成基础**
1. 安装CodeBuddy Agent SDK
2. 配置认证信息
3. 创建基础Agent框架
4. 定义工具接口

**Phase 2: 诊断工具开发**
1. 实现Arthas命令执行工具
2. 实现kubectl命令执行工具
3. 实现日志分析工具
4. 实现指标查询工具

**Phase 3: 诊断流程实现**
1. 实现CPU飙高诊断流程
2. 实现内存泄漏诊断流程
3. 实现死锁检测流程
4. 实现慢方法追踪流程

### 5.3 依赖关系

```
Phase 1 (SDK集成)
    │
    ├──→ Phase 2 (工具开发)
    │         │
    │         └──→ Phase 3 (诊断流程)
    │                   │
    │                   └──→ Phase 4 (前端集成)
    │
    └──→ Phase 5 (测试优化)
```

---

## 6. 技术选型建议

### 6.1 SDK选择

| 场景 | 推荐SDK | 理由 |
|------|---------|------|
| **生产环境** | CodeBuddy Agent SDK | 国内稳定、权限控制好 |
| **开发测试** | Claude Agent SDK | 功能强大、文档完善 |
| **混合使用** | 两者都支持 | 根据场景切换 |

### 6.2 工具目录结构

```
tools/
├── arthas/                          # Arthas工具包
│   ├── arthas-boot.jar              # Arthas主程序
│   └── arthas-tunnel-server.jar     # Tunnel Server
├── agent-sdk/                       # Agent SDK
│   ├── codebuddy-agent-sdk/         # CodeBuddy SDK
│   └── claude-agent-sdk/            # Claude SDK（备选）
├── scripts/                         # 辅助脚本
│   ├── install-arthas.sh           # 安装Arthas到Pod
│   ├── start-tunnel-server.sh      # 启动Tunnel Server
│   ├── connect-tunnel.sh           # 连接到Tunnel Server
│   └── setup-agent-sdk.sh          # 安装Agent SDK
└── README.md                        # 工具说明文档
```

---

**文档结束**
