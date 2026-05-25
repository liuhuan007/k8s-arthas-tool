#!/usr/bin/env python3
"""
诊断工具测试脚本
测试 Arthas 诊断工具定义
"""

import asyncio
import subprocess
from typing import Any

# ═══════════════════════════════════════════════════════════════════════════════
# 诊断工具定义（使用 CodeBuddy Agent SDK）
# ═══════════════════════════════════════════════════════════════════════════════

from codebuddy_agent_sdk import tool


@tool("execute_kubectl", "Execute kubectl command", {
    "command": str,
    "namespace": str
})
async def execute_kubectl(args: dict[str, Any]) -> dict[str, Any]:
    """执行kubectl命令"""
    cmd = f"kubectl -n {args['namespace']} {args['command']}"
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {"error": "Command timed out"}
    except Exception as e:
        return {"error": str(e)}


@tool("get_pod_status", "Get Pod status", {
    "pod_name": str,
    "namespace": str
})
async def get_pod_status(args: dict[str, Any]) -> dict[str, Any]:
    """获取Pod状态"""
    cmd = f"kubectl get pod -n {args['namespace']} {args['pod_name']} -o json"
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        return {"output": result.stdout}
    except Exception as e:
        return {"error": str(e)}


@tool("analyze_cpu_issue", "Analyze CPU high usage issue", {
    "thread_output": str
})
async def analyze_cpu_issue(args: dict[str, Any]) -> dict[str, Any]:
    """分析CPU飙高问题"""
    output = args["thread_output"]
    
    analysis = {
        "has_high_cpu": False,
        "high_cpu_threads": [],
        "suggestions": []
    }
    
    # 分析线程输出
    lines = output.split('\n')
    for line in lines:
        if 'RUNNABLE' in line:
            analysis["has_high_cpu"] = True
            analysis["high_cpu_threads"].append(line.strip())
    
    # 生成建议
    if analysis["has_high_cpu"]:
        analysis["suggestions"].append("检查热点线程的堆栈")
        analysis["suggestions"].append("使用trace命令追踪慢方法")
    
    return analysis


@tool("analyze_deadlock", "Analyze thread deadlock", {
    "thread_output": str
})
async def analyze_deadlock(args: dict[str, Any]) -> dict[str, Any]:
    """分析死锁问题"""
    output = args["thread_output"]
    
    analysis = {
        "has_deadlock": False,
        "deadlock_threads": [],
        "suggestions": []
    }
    
    # 检测死锁
    if "BLOCKED" in output and "waiting to lock" in output:
        analysis["has_deadlock"] = True
        analysis["suggestions"].append("发现死锁，需要检查锁顺序")
        analysis["suggestions"].append("使用thread -b命令获取详细信息")
    
    return analysis


# ═══════════════════════════════════════════════════════════════════════════════
# 测试函数
# ═══════════════════════════════════════════════════════════════════════════════

async def test_tools():
    """测试所有诊断工具"""
    print("\n" + "🔧"*30)
    print("诊断工具测试")
    print("🔧"*30)
    
    results = {}
    
    # 测试 kubectl 工具
    print("\n" + "-"*40)
    print("测试 kubectl 工具")
    print("-"*40)
    
    try:
        result = await execute_kubectl({
            "command": "get nodes",
            "namespace": "default"
        })
        print(f"✅ kubectl工具执行成功")
        print(f"   返回码: {result.get('returncode', 'N/A')}")
        results["kubectl"] = True
    except Exception as e:
        print(f"❌ kubectl工具执行失败: {e}")
        results["kubectl"] = False
    
    # 测试 CPU 分析工具
    print("\n" + "-"*40)
    print("测试 CPU 分析工具")
    print("-"*40)
    
    try:
        sample_output = """
"main" Id=1 RUNNABLE
"pool-1-thread-3" Id=23 RUNNABLE
  at com.example.Service.process(Service.java:42)
"""
        result = await analyze_cpu_issue({"thread_output": sample_output})
        print(f"✅ CPU分析工具执行成功")
        print(f"   发现高CPU线程: {len(result.get('high_cpu_threads', []))}个")
        results["cpu_analysis"] = True
    except Exception as e:
        print(f"❌ CPU分析工具执行失败: {e}")
        results["cpu_analysis"] = False
    
    # 测试死锁分析工具
    print("\n" + "-"*40)
    print("测试死锁分析工具")
    print("-"*40)
    
    try:
        deadlock_output = """
"main" Id=1 BLOCKED
  waiting to lock <0x000000076b3a1a40> (a java.lang.Object)
  held by thread 23
"""
        result = await analyze_deadlock({"thread_output": deadlock_output})
        print(f"✅ 死锁分析工具执行成功")
        print(f"   发现死锁: {result.get('has_deadlock', False)}")
        results["deadlock_analysis"] = True
    except Exception as e:
        print(f"❌ 死锁分析工具执行失败: {e}")
        results["deadlock_analysis"] = False
    
    # 输出测试结果
    print("\n" + "="*60)
    print("测试结果汇总")
    print("="*60)
    
    for tool_name, passed in results.items():
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"{tool_name}: {status}")
    
    return all(results.values())


def main():
    """主函数"""
    success = asyncio.run(test_tools())
    return 0 if success else 1


if __name__ == "__main__":
    exit(main())
