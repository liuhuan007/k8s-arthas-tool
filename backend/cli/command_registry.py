from typing import Dict, List, Optional


KUBECTL_COMMANDS = {
    "get_pods": {
        "name": "get_pods",
        "command": "get pods -o wide",
        "description": "获取 Pod 列表和状态",
        "when_to_use": ["查看 Pod 运行状态", "检查 Pod 是否正常"],
        "risk_level": "read",
        "params": {"namespace": "default", "label": ""},
        "examples": ["kubectl get pods -n default", "kubectl get pods -o wide --all-namespaces"],
    },
    "describe_pod": {
        "name": "describe_pod",
        "command": "describe pod {name}",
        "description": "获取 Pod 详细信息",
        "when_to_use": ["Pod 异常时查看详情"],
        "risk_level": "read",
        "params": {"name": "required", "namespace": "default"},
        "examples": ["kubectl describe pod nginx -n default"],
    },
    "get_pod_logs": {
        "name": "get_pod_logs",
        "command": "logs {name} [--previous]",
        "description": "获取 Pod 容器日志",
        "when_to_use": ["查看应用日志", "排查 CrashLoopBackOff"],
        "risk_level": "read",
        "params": {"name": "required", "previous": False},
        "examples": ["kubectl logs nginx -n default", "kubectl logs nginx --previous"],
    },
    "exec_in_pod": {
        "name": "exec_in_pod",
        "command": "exec {name} -- {shell_cmd}",
        "description": "在 Pod 内执行命令",
        "when_to_use": ["检查文件", "执行诊断命令"],
        "risk_level": "low",
        "params": {"name": "required", "shell_cmd": "required"},
        "examples": ["kubectl exec nginx -- ls /app", "kubectl exec -it nginx -- /bin/sh"],
    },
    "delete_pod": {
        "name": "delete_pod",
        "command": "delete pod {name}",
        "description": "删除 Pod（会触发重建）",
        "when_to_use": ["Pod 卡死需要重启"],
        "risk_level": "high",
        "requires_confirmation": True,
        "params": {"name": "required", "namespace": "default"},
        "examples": ["kubectl delete pod nginx -n default"],
    },
    "top_pods": {
        "name": "top_pods",
        "command": "top pods --no-headers",
        "description": "获取 Pod CPU/内存使用",
        "when_to_use": ["查看资源使用"],
        "risk_level": "read",
        "params": {"namespace": ""},
        "examples": ["kubectl top pods -n default"],
    },
    "top_nodes": {
        "name": "top_nodes",
        "command": "top nodes --no-headers",
        "description": "获取 Node CPU/内存使用",
        "when_to_use": ["查看节点资源"],
        "risk_level": "read",
        "params": {},
        "examples": ["kubectl top nodes"],
    },
    "get_events": {
        "name": "get_events",
        "command": "get events --sort-by='.lastTimestamp'",
        "description": "获取资源相关事件",
        "when_to_use": ["排查问题时间线"],
        "risk_level": "read",
        "params": {"namespace": ""},
        "examples": ["kubectl get events -n default --sort-by='.lastTimestamp'"],
    },
    "get_nodes": {
        "name": "get_nodes",
        "command": "get nodes -o wide",
        "description": "获取 Node 列表和状态",
        "when_to_use": ["查看节点状态"],
        "risk_level": "read",
        "params": {},
        "examples": ["kubectl get nodes -o wide"],
    },
    "cluster_info": {
        "name": "cluster_info",
        "command": "cluster-info",
        "description": "获取集群基本信息",
        "when_to_use": ["检查集群连通性"],
        "risk_level": "read",
        "params": {},
        "examples": ["kubectl cluster-info"],
    },
}

ARTHAS_COMMANDS = {
    "thread": {
        "name": "thread",
        "command": "thread -n {top_n}",
        "description": "获取线程快照，按 CPU 使用排序",
        "when_to_use": ["CPU 飙高排查", "线程阻塞分析"],
        "risk_level": "read",
        "params": {"top_n": 5},
        "examples": ["thread -n 5", "thread --state BLOCKED"],
    },
    "thread_deadlock": {
        "name": "thread_deadlock",
        "command": "thread -b",
        "description": "检测死锁线程",
        "when_to_use": ["怀疑死锁"],
        "risk_level": "read",
        "params": {},
        "examples": ["thread -b"],
    },
    "dashboard": {
        "name": "dashboard",
        "command": "dashboard -n 1",
        "description": "获取 JVM 实时指标快照",
        "when_to_use": ["快速评估 JVM 状态"],
        "risk_level": "read",
        "params": {"n": 1},
        "examples": ["dashboard -n 1"],
    },
    "trace": {
        "name": "trace",
        "command": "trace {class_pattern} {method_pattern} -n {sample_count}",
        "description": "追踪方法调用链耗时",
        "when_to_use": ["接口慢排查", "方法耗时分析"],
        "risk_level": "read",
        "params": {"class_pattern": "required", "method_pattern": "required", "sample_count": 5},
        "examples": ["trace com.example.Service process -n 5"],
    },
    "jad": {
        "name": "jad",
        "command": "jad {class_pattern}",
        "description": "反编译类源码",
        "when_to_use": ["查看类实现", "排查类冲突"],
        "risk_level": "read",
        "params": {"class_pattern": "required"},
        "examples": ["jad com.example.MyClass"],
    },
    "heapdump": {
        "name": "heapdump",
        "command": "heapdump --live {path}",
        "description": "导出堆转储",
        "when_to_use": ["OOM 排查"],
        "risk_level": "high",
        "requires_confirmation": True,
        "params": {"path": "/tmp/heap.hprof"},
        "examples": ["heapdump --live /tmp/heap.hprof"],
    },
    "profiler": {
        "name": "profiler",
        "command": "profiler start --event {event} --duration {duration}",
        "description": "启动性能采样",
        "when_to_use": ["CPU 热点分析"],
        "risk_level": "medium",
        "requires_confirmation": True,
        "params": {"event": "cpu", "duration": 30},
        "examples": ["profiler start --event cpu --duration 30"],
    },
    "sc": {
        "name": "sc",
        "command": "sc -d {class_pattern}",
        "description": "搜索类加载信息",
        "when_to_use": ["确认类是否存在"],
        "risk_level": "read",
        "params": {"class_pattern": "required"},
        "examples": ["sc -d com.example.MyClass"],
    },
    "watch": {
        "name": "watch",
        "command": "watch {class_pattern} {method_pattern} '{expr}' -e -x 2",
        "description": "观测方法入参和返回值",
        "when_to_use": ["方法参数查看"],
        "risk_level": "read",
        "params": {"class_pattern": "required", "method_pattern": "required", "expr": "{params,returnObj}"},
        "examples": ["watch com.example.Service process '{params,returnObj}' -e -x 2"],
    },
}

ALL_COMMANDS = {
    "kubectl": KUBECTL_COMMANDS,
    "arthas": ARTHAS_COMMANDS,
}


class CommandRegistry:
    @classmethod
    def get_commands(cls, cli: str) -> List[Dict]:
        return list(ALL_COMMANDS.get(cli, {}).values())

    @classmethod
    def get_help(cls, cli: str, command: str) -> Optional[Dict]:
        cmds = ALL_COMMANDS.get(cli, {})
        return cmds.get(command)
