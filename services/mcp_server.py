"""
MCP Standard Server — 将 K8s Arthas 诊断平台能力暴露为标准 MCP Tools

支持两种传输模式：
  - stdio:  Claude Desktop / Cursor 等本地客户端
  - HTTP:   远程客户端通过 /mcp/{token} 端点连接

每个 MCP Tool 对应一个诊断能力，内部调用已有的 ArthasCommandExecutor / ProfilerWorkflow。
"""
import json
import logging
import asyncio
from typing import Any, Dict, List, Optional
from datetime import datetime

log = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# MCP Tool 定义（与 diagnosis_capabilities 对齐）
# ═══════════════════════════════════════════════════════════════════════════════

TOOLS = [
    # ── Level 1: 快捷工具 ──
    {
        "name": "jvm_dashboard",
        "description": "获取 JVM 实时仪表板：线程列表、内存各区域、GC 统计、系统信息。问题排查第一步。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "connection_id": {"type": "string", "description": "Arthas 连接 ID (格式: cluster/namespace/pod)"},
                "refresh_count": {"type": "integer", "default": 1, "description": "刷新次数"}
            },
            "required": ["connection_id"]
        }
    },
    {
        "name": "thread_top",
        "description": "查看 CPU 占用最高的 N 个线程及其堆栈。用于 CPU 飙高排查。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "connection_id": {"type": "string", "description": "连接 ID"},
                "count": {"type": "integer", "default": 10, "description": "显示线程数"}
            },
            "required": ["connection_id"]
        }
    },
    {
        "name": "deadlock_detect",
        "description": "检测线程死锁和持锁阻塞。用于接口无响应、请求堆积场景。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "connection_id": {"type": "string", "description": "连接 ID"}
            },
            "required": ["connection_id"]
        }
    },
    {
        "name": "memory_info",
        "description": "查看 JVM 内存各区域使用情况（heap/nonheap/buffer），定位内存泄漏区域。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "connection_id": {"type": "string", "description": "连接 ID"}
            },
            "required": ["connection_id"]
        }
    },
    {
        "name": "jvm_info",
        "description": "查看 JVM 详细信息：JDK 版本、GC 算法、启动参数、classpath。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "connection_id": {"type": "string", "description": "连接 ID"}
            },
            "required": ["connection_id"]
        }
    },
    # ── Level 2: 诊断工具 ──
    {
        "name": "trace_method",
        "description": "追踪方法调用链路及各节点耗时，精准定位性能瓶颈在哪个子调用。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "connection_id": {"type": "string", "description": "连接 ID"},
                "class_name": {"type": "string", "description": "全限定类名 (如 com.example.UserService)"},
                "method": {"type": "string", "default": "*", "description": "方法名 (支持通配符)"},
                "count": {"type": "integer", "default": 5, "description": "追踪次数"},
                "min_cost_ms": {"type": "number", "default": 0, "description": "只追踪耗时超过此值的调用 (ms)"}
            },
            "required": ["connection_id", "class_name"]
        }
    },
    {
        "name": "watch_method",
        "description": "观测方法入参、返回值、异常信息。用于排查偶发异常、查看业务数据。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "connection_id": {"type": "string", "description": "连接 ID"},
                "class_name": {"type": "string", "description": "全限定类名"},
                "method": {"type": "string", "default": "*", "description": "方法名"},
                "express": {"type": "string", "default": "{params,returnObj,throwExp}", "description": "OGNL 表达式"},
                "count": {"type": "integer", "default": 5, "description": "观测次数"},
                "expand": {"type": "integer", "default": 2, "description": "对象展开层级"}
            },
            "required": ["connection_id", "class_name"]
        }
    },
    {
        "name": "jad_class",
        "description": "反编译查看运行时源码，确认线上代码版本。用于排查热修复是否生效。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "connection_id": {"type": "string", "description": "连接 ID"},
                "class_name": {"type": "string", "description": "全限定类名"},
                "method": {"type": "string", "default": "", "description": "方法名 (可选，只看指定方法)"}
            },
            "required": ["connection_id", "class_name"]
        }
    },
    {
        "name": "search_class",
        "description": "搜索已加载的类，查看来源 JAR、ClassLoader。用于排查类冲突。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "connection_id": {"type": "string", "description": "连接 ID"},
                "pattern": {"type": "string", "description": "类名模式 (支持通配符如 *UserService*)"},
                "detail": {"type": "boolean", "default": True, "description": "显示详细信息"}
            },
            "required": ["connection_id", "pattern"]
        }
    },
    {
        "name": "stack_trace",
        "description": "查看方法调用栈，定位某个方法被谁调用的。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "connection_id": {"type": "string", "description": "连接 ID"},
                "class_name": {"type": "string", "description": "全限定类名"},
                "method": {"type": "string", "default": "*", "description": "方法名"},
                "count": {"type": "integer", "default": 5, "description": "采样次数"}
            },
            "required": ["connection_id", "class_name"]
        }
    },
    {
        "name": "monitor_method",
        "description": "统计方法调用 QPS、RT、成功率。适合接口压测时监控。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "connection_id": {"type": "string", "description": "连接 ID"},
                "class_name": {"type": "string", "description": "全限定类名"},
                "method": {"type": "string", "default": "*", "description": "方法名"},
                "interval": {"type": "integer", "default": 5, "description": "统计周期(秒)"},
                "count": {"type": "integer", "default": 6, "description": "统计轮次"}
            },
            "required": ["connection_id", "class_name"]
        }
    },
    # ── Level 3: 采样分析 ──
    {
        "name": "profiler_cpu",
        "description": "async-profiler CPU 采样，生成火焰图。低开销，所有 JDK 版本可用。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "connection_id": {"type": "string", "description": "连接 ID"},
                "duration": {"type": "integer", "default": 30, "description": "采样时长(秒)"},
                "event": {"type": "string", "default": "cpu", "enum": ["cpu", "alloc", "lock", "wall"], "description": "采样事件类型"}
            },
            "required": ["connection_id"]
        }
    },
    {
        "name": "thread_dump",
        "description": "导出线程 Dump，分析死锁/卡顿。等价于 jstack。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "connection_id": {"type": "string", "description": "连接 ID"}
            },
            "required": ["connection_id"]
        }
    },
    # ── 只读工具 ──
    {
        "name": "pod_status",
        "description": "获取 Pod 运行状态、容器信息、重启次数。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "connection_id": {"type": "string", "description": "连接 ID"}
            },
            "required": ["connection_id"]
        }
    },
    {
        "name": "pod_metrics",
        "description": "获取 Pod 的 CPU/内存/网络/进程指标。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "connection_id": {"type": "string", "description": "连接 ID"}
            },
            "required": ["connection_id"]
        }
    },
    {
        "name": "execute_arthas",
        "description": "执行任意 Arthas 命令（受白名单限制）。用于上述工具未覆盖的诊断场景。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "connection_id": {"type": "string", "description": "连接 ID"},
                "command": {"type": "string", "description": "Arthas 命令 (如 'logger', 'sysprop java.version')"}
            },
            "required": ["connection_id", "command"]
        }
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# Tool 执行器
# ═══════════════════════════════════════════════════════════════════════════════

# 命令白名单（安全控制）
ALLOWED_COMMANDS = {
    "dashboard", "thread", "jvm", "memory", "sysprop", "sysenv", "vmoption",
    "sc", "sm", "jad", "classloader", "stack", "monitor", "tt", "logger",
    "trace", "watch", "profiler", "heapdump", "vmtool",
    "cat", "pwd", "version", "history", "perfcounter", "ss",
}
BLOCKED_COMMANDS = {"redefine", "retransform", "ognl", "reset", "shutdown"}


def _check_command_safety(command: str) -> Optional[str]:
    """检查命令安全性，返回错误信息或 None"""
    cmd_base = command.strip().split()[0].lower() if command.strip() else ""
    if cmd_base in BLOCKED_COMMANDS:
        return f"命令 '{cmd_base}' 被安全策略禁止"
    if cmd_base not in ALLOWED_COMMANDS:
        return f"命令 '{cmd_base}' 不在白名单中。允许: {', '.join(sorted(ALLOWED_COMMANDS))}"
    return None


def _get_connection(connection_id: str):
    """获取 Arthas 连接对象"""
    try:
        from backend.app_context import connections, connections_lock
        with connections_lock:
            entry = connections.get(connection_id)
        if entry and entry.get('conn'):
            conn = entry['conn']
            if hasattr(conn, 'http_client') and conn.http_client:
                return conn
        return None
    except Exception as e:
        log.error("获取连接失败: %s", e)
        return None


def _format_result(result: Any) -> str:
    """格式化执行结果为文本"""
    if isinstance(result, dict):
        body = result.get("body", "")
        state = result.get("state", "")
        if body:
            return body if isinstance(body, str) else json.dumps(body, ensure_ascii=False, indent=2)
        return json.dumps(result, ensure_ascii=False, indent=2)
    return str(result)


async def execute_tool(tool_name: str, arguments: Dict[str, Any]) -> str:
    """执行 MCP Tool，返回文本结果"""
    conn_id = arguments.get("connection_id", "")
    conn = _get_connection(conn_id)
    if not conn:
        return f"错误: 连接 {conn_id} 不可用。请先在 Web 界面建立 Arthas 连接。"

    try:
        from backend.core.arthas_executor import ArthasCommandExecutor

        # ── 快捷工具 ──
        if tool_name == "jvm_dashboard":
            n = arguments.get("refresh_count", 1)
            cmd = f"dashboard -n {n}"
            result = ArthasCommandExecutor.execute(conn, cmd)
            return _format_result(result)

        elif tool_name == "thread_top":
            count = arguments.get("count", 10)
            cmd = f"thread -n {count}"
            result = ArthasCommandExecutor.execute(conn, cmd)
            return _format_result(result)

        elif tool_name == "deadlock_detect":
            result = ArthasCommandExecutor.execute(conn, "thread -b")
            return _format_result(result)

        elif tool_name == "memory_info":
            result = ArthasCommandExecutor.execute(conn, "memory")
            return _format_result(result)

        elif tool_name == "jvm_info":
            result = ArthasCommandExecutor.execute(conn, "jvm")
            return _format_result(result)

        # ── 诊断工具 ──
        elif tool_name == "trace_method":
            cls = arguments["class_name"]
            method = arguments.get("method", "*")
            count = arguments.get("count", 5)
            min_cost = arguments.get("min_cost_ms", 0)
            cond = f" '#cost > {min_cost}'" if min_cost > 0 else ""
            cmd = f"trace {cls} {method} -n {count}{cond}"
            result = ArthasCommandExecutor.execute(conn, cmd)
            return _format_result(result)

        elif tool_name == "watch_method":
            cls = arguments["class_name"]
            method = arguments.get("method", "*")
            express = arguments.get("express", "{params,returnObj,throwExp}")
            count = arguments.get("count", 5)
            expand = arguments.get("expand", 2)
            cmd = f"watch {cls} {method} '{express}' -x {expand} -n {count}"
            result = ArthasCommandExecutor.execute(conn, cmd)
            return _format_result(result)

        elif tool_name == "jad_class":
            cls = arguments["class_name"]
            method = arguments.get("method", "")
            cmd = f"jad --source-only {cls}" + (f" {method}" if method else "")
            result = ArthasCommandExecutor.execute(conn, cmd)
            return _format_result(result)

        elif tool_name == "search_class":
            pattern = arguments["pattern"]
            detail = arguments.get("detail", True)
            cmd = f"sc -d {pattern}" if detail else f"sc {pattern}"
            result = ArthasCommandExecutor.execute(conn, cmd)
            return _format_result(result)

        elif tool_name == "stack_trace":
            cls = arguments["class_name"]
            method = arguments.get("method", "*")
            count = arguments.get("count", 5)
            cmd = f"stack {cls} {method} -n {count}"
            result = ArthasCommandExecutor.execute(conn, cmd)
            return _format_result(result)

        elif tool_name == "monitor_method":
            cls = arguments["class_name"]
            method = arguments.get("method", "*")
            interval = arguments.get("interval", 5)
            count = arguments.get("count", 6)
            cmd = f"monitor {cls} {method} -c {interval} -n {count}"
            result = ArthasCommandExecutor.execute(conn, cmd)
            return _format_result(result)

        # ── 采样分析 ──
        elif tool_name == "profiler_cpu":
            from backend.core.profiler import ProfilerWorkflow
            from backend.config import Config
            workflow = ProfilerWorkflow(conn)
            duration = arguments.get("duration", 30)
            event = arguments.get("event", "cpu")
            result = workflow.run(
                duration=duration, fmt="html",
                output_dir=Config.OUTPUT_DIR,
                mode="profiler", event=event
            )
            local_file = result.get("local_file", "")
            msg = result.get("message", "")
            return f"采样完成。\n事件: {event}\n时长: {duration}s\n结果: {msg}\n文件: {local_file}"

        elif tool_name == "thread_dump":
            from backend.core.profiler import ProfilerWorkflow
            from backend.config import Config
            workflow = ProfilerWorkflow(conn)
            result = workflow.run(
                duration=0, fmt="html",
                output_dir=Config.OUTPUT_DIR,
                mode="threaddump"
            )
            local_file = result.get("local_file", "")
            body = result.get("message", "")
            return f"线程 Dump 完成。\n文件: {local_file}\n{body}"

        # ── 只读工具 ──
        elif tool_name == "pod_status":
            target = conn.target
            info = {
                "cluster": target.cluster_name,
                "namespace": target.namespace,
                "pod": target.pod_name,
                "container": target.container,
                "connection_id": conn_id,
                "alive": conn.is_alive() if hasattr(conn, 'is_alive') else 'unknown',
                "java_pid": getattr(conn, 'java_pid', None),
                "arthas_version": getattr(conn, 'arthas_version', None),
            }
            return json.dumps(info, ensure_ascii=False, indent=2)

        elif tool_name == "pod_metrics":
            from backend.pod_monitor import collect_pod_snapshot, KubectlRunner
            target = conn.target
            runner = conn.executor
            snapshot = collect_pod_snapshot(runner, target.namespace, target.pod_name, target.container)
            # 提取关键指标
            cm = snapshot.get("container_metrics", {})
            top = snapshot.get("top_metrics", {})
            procs = snapshot.get("processes", [])
            summary = {
                "cpu": top.get("cpu_millicores", "N/A"),
                "memory": top.get("memory_bytes", "N/A"),
                "memory_limit": cm.get("cgroup_mem_limit_bytes", "N/A"),
                "process_count": len(procs),
                "top_processes": [
                    {"pid": p.get("pid"), "cpu": p.get("cpu"), "mem": p.get("mem"), "cmd": p.get("cmd", "")[:60]}
                    for p in procs[:5]
                ],
            }
            return json.dumps(summary, ensure_ascii=False, indent=2)

        elif tool_name == "execute_arthas":
            command = arguments.get("command", "").strip()
            err = _check_command_safety(command)
            if err:
                return f"安全拒绝: {err}"
            result = ArthasCommandExecutor.execute(conn, command)
            return _format_result(result)

        else:
            return f"未知工具: {tool_name}"

    except Exception as e:
        log.error("MCP tool '%s' 执行失败: %s", tool_name, e, exc_info=True)
        return f"执行失败: {e}"


# ═══════════════════════════════════════════════════════════════════════════════
# MCP Server (基于 mcp SDK)
# ═══════════════════════════════════════════════════════════════════════════════

def create_mcp_server():
    """创建 MCP Server 实例"""
    try:
        from mcp.server import Server
        from mcp.types import Tool, TextContent
    except ImportError:
        log.error("mcp SDK 未安装。请运行: pip install mcp")
        raise

    server = Server("arthas-diagnosis")

    @server.list_tools()
    async def list_tools():
        return [
            Tool(
                name=t["name"],
                description=t["description"],
                inputSchema=t["inputSchema"],
            )
            for t in TOOLS
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        result = await execute_tool(name, arguments)
        return [TextContent(type="text", text=result)]

    return server


# ═══════════════════════════════════════════════════════════════════════════════
# 入口：stdio 模式
# ═══════════════════════════════════════════════════════════════════════════════

async def run_stdio():
    """以 stdio 模式运行 MCP Server（供 Claude Desktop / Cursor 调用）"""
    try:
        from mcp.server.stdio import stdio_server
    except ImportError:
        log.error("mcp SDK 未安装。请运行: pip install mcp")
        return

    server = create_mcp_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_stdio())
