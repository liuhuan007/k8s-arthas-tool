#!/usr/bin/env python3
"""
诊断Agent Demo - 基于CodeBuddy Agent SDK
"""

import asyncio
import os
from typing import Any, Dict

# 设置环境变量（需要替换为实际的API Key）
# os.environ["CODEBUDDY_API_KEY"] = "your-api-key"
# os.environ["CODEBUDDY_INTERNET_ENVIRONMENT"] = "internal"

from codebuddy_agent_sdk import (
    query,
    CodeBuddySDKClient,
    CodeBuddyAgentOptions,
    tool,
    AssistantMessage,
    TextBlock,
    ToolUseBlock
)


# ═══════════════════════════════════════════════════════════════════════════════
# 诊断工具定义
# ═══════════════════════════════════════════════════════════════════════════════

@tool("execute_kubectl", "Execute kubectl command", {
    "command": str,
    "namespace": str
})
async def execute_kubectl(args: Dict[str, Any]) -> Dict[str, Any]:
    """执行kubectl命令"""
    import subprocess
    
    cmd = f"kubectl -n {args['namespace']} {args['command']}"
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        return {
            "stdout": result.stdout[:2000],  # 限制输出长度
            "stderr": result.stderr[:1000],
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {"error": "Command timed out"}
    except Exception as e:
        return {"error": str(e)}


@tool("get_pod_status", "Get Pod status and basic info", {
    "pod_name": str,
    "namespace": str
})
async def get_pod_status(args: Dict[str, Any]) -> Dict[str, Any]:
    """获取Pod状态"""
    import subprocess
    import json
    
    cmd = f"kubectl get pod -n {args['namespace']} {args['pod_name']} -o json"
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            pod_info = json.loads(result.stdout)
            return {
                "status": pod_info.get("status", {}).get("phase", "Unknown"),
                "node": pod_info.get("spec", {}).get("nodeName", "Unknown"),
                "restart_count": sum(
                    cs.get("restartCount", 0)
                    for cs in pod_info.get("status", {}).get("containerStatuses", [])
                )
            }
        return {"error": result.stderr}
    except Exception as e:
        return {"error": str(e)}


@tool("analyze_cpu_issue", "Analyze CPU high usage issue", {
    "thread_output": str
})
async def analyze_cpu_issue(args: Dict[str, Any]) -> Dict[str, Any]:
    """分析CPU飙高问题"""
    output = args["thread_output"]
    
    analysis = {
        "has_high_cpu": False,
        "high_cpu_threads": [],
        "suggestions": []
    }
    
    lines = output.split('\n')
    for line in lines:
        if 'RUNNABLE' in line:
            analysis["has_high_cpu"] = True
            analysis["high_cpu_threads"].append(line.strip()[:100])
    
    if analysis["has_high_cpu"]:
        analysis["suggestions"].extend([
            "检查热点线程的堆栈",
            "使用trace命令追踪慢方法",
            "考虑优化算法或增加缓存"
        ])
    
    return analysis


# ═══════════════════════════════════════════════════════════════════════════════
# Demo测试
# ═══════════════════════════════════════════════════════════════════════════════

async def demo_simple_query():
    """Demo 1: 简单查询"""
    print("\n" + "="*60)
    print("Demo 1: 简单查询")
    print("="*60)
    
    options = CodeBuddyAgentOptions(
        permission_mode="bypassPermissions",
        model="deepseek-v3.1"
    )
    
    print("\n🤖 正在发送查询...")
    
    async for message in query(
        prompt="请简要解释什么是Java中的死锁，以及如何检测死锁？",
        options=options
    ):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    print(block.text)


async def demo_with_tools():
    """Demo 2: 带工具的查询"""
    print("\n" + "="*60)
    print("Demo 2: 带工具的查询")
    print("="*60)
    
    options = CodeBuddyAgentOptions(
        permission_mode="bypassPermissions",
        model="deepseek-v3.1"
    )
    
    prompt = """
请帮我检查当前K8s集群的节点状态。
使用get_pod_status工具查看节点信息。
"""
    
    print("\n🤖 正在执行诊断...")
    
    async for message in query(
        prompt=prompt,
        options=options
    ):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    print(block.text)
                elif isinstance(block, ToolUseBlock):
                    print(f"\n🔧 工具调用: {block.name}")
                    print(f"   参数: {block.input}")


async def demo_session():
    """Demo 3: 多轮对话"""
    print("\n" + "="*60)
    print("Demo 3: 多轮对话会话")
    print("="*60)
    
    options = CodeBuddyAgentOptions(
        permission_mode="bypassPermissions",
        model="deepseek-v3.1"
    )
    
    print("\n🤖 创建会话...")
    
    async with CodeBuddySDKClient(options=options) as client:
        # 第一轮
        print("\n📝 第一轮: 询问问题")
        await client.query("什么是JVM中的Metaspace？")
        
        print("\n📥 接收响应...")
        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        print(block.text)
        
        # 第二轮
        print("\n📝 第二轮: 追问")
        await client.query("Metaspace OOM的常见原因有哪些？")
        
        print("\n📥 接收响应...")
        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        print(block.text)


async def main():
    """主函数"""
    print("\n" + "🧪"*30)
    print("诊断Agent Demo - CodeBuddy Agent SDK")
    print("🧪"*30)
    
    print("\n⚠️  注意: 需要配置CODEBUDDY_API_KEY环境变量")
    print("   获取地址: https://copilot.tencent.com/profile/")
    print("")
    print("   设置方式:")
    print("   export CODEBUDDY_API_KEY='your-api-key'")
    print("   export CODEBUDDY_INTERNET_ENVIRONMENT='internal'")
    
    # 运行Demo
    try:
        await demo_simple_query()
        # await demo_with_tools()  # 需要kubectl环境
        # await demo_session()     # 多轮对话
    except Exception as e:
        print(f"\n❌ Demo执行失败: {e}")
        print("   请确保已配置正确的API Key")


if __name__ == "__main__":
    asyncio.run(main())
