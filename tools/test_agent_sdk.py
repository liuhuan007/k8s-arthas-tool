#!/usr/bin/env python3
"""
Agent SDK 测试脚本
测试 CodeBuddy Agent SDK 和 Claude Agent SDK
"""

import asyncio
import sys
from typing import Any

# ═══════════════════════════════════════════════════════════════════════════════
# 测试 CodeBuddy Agent SDK
# ═══════════════════════════════════════════════════════════════════════════════

def test_codebuddy_sdk():
    """测试 CodeBuddy Agent SDK"""
    print("\n" + "="*60)
    print("测试 CodeBuddy Agent SDK")
    print("="*60)
    
    try:
        from codebuddy_agent_sdk import query, tool, AssistantMessage, TextBlock
        print("✅ CodeBuddy Agent SDK 导入成功")
        
        # 定义一个简单的工具
        @tool("add", "Add two numbers", {"a": float, "b": float})
        async def add(args: dict[str, Any]) -> dict[str, Any]:
            return {"result": args["a"] + args["b"]}
        
        print("✅ 工具定义成功")
        
        # 测试工具执行
        async def test_tool():
            result = await add({"a": 10, "b": 20})
            print(f"✅ 工具执行结果: {result}")
            return result
        
        asyncio.run(test_tool())
        
        print("\n✅ CodeBuddy Agent SDK 测试通过!")
        return True
        
    except ImportError as e:
        print(f"❌ CodeBuddy Agent SDK 导入失败: {e}")
        return False
    except Exception as e:
        print(f"❌ CodeBuddy Agent SDK 测试失败: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# 测试 Claude Agent SDK
# ═══════════════════════════════════════════════════════════════════════════════

def test_claude_sdk():
    """测试 Claude Agent SDK"""
    print("\n" + "="*60)
    print("测试 Claude Agent SDK")
    print("="*60)
    
    try:
        from claude_agent_sdk import query, tool, SdkMcpTool
        print("✅ Claude Agent SDK 导入成功")
        
        # Claude SDK 使用不同的工具定义方式
        # 这里只测试导入和基本功能
        print("✅ 工具类导入成功")
        
        print("\n✅ Claude Agent SDK 测试通过!")
        print("   提示: 需要配置 ANTHROPIC_API_KEY 环境变量才能进行完整测试")
        return True
        
    except ImportError as e:
        print(f"❌ Claude Agent SDK 导入失败: {e}")
        print("   提示: 需要配置 ANTHROPIC_API_KEY 环境变量")
        return False
    except Exception as e:
        print(f"❌ Claude Agent SDK 测试失败: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# 主测试函数
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    """主测试函数"""
    print("\n" + "🧪"*30)
    print("Agent SDK 测试")
    print("🧪"*30)
    
    results = {}
    
    # 测试 CodeBuddy SDK
    results["codebuddy"] = test_codebuddy_sdk()
    
    # 测试 Claude SDK
    results["claude"] = test_claude_sdk()
    
    # 输出测试结果
    print("\n" + "="*60)
    print("测试结果汇总")
    print("="*60)
    
    for sdk, passed in results.items():
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"{sdk}: {status}")
    
    # 返回是否有失败
    return all(results.values())


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
