"""
连接选择器 - 根据诊断需求自动选择 Pod 连接或 Arthas 连接

架构设计：
  ConnectionSelector 根据能力定义（category / arthas_command / steps）
  判断需要哪种连接类型，并提供统一的连接获取接口。

  连接类型：
    - ARTHAS: 需要 Arthas HTTP API（诊断工具、场景方案、AI 诊断）
    - POD:    仅需 kubectl exec（容器内部指标采集、进程列表）
    - NONE:   无需连接（纯前端操作）

使用方式：
    from backend.core.connection_selector import ConnectionSelector, ConnectionType

    selector = ConnectionSelector()
    conn_type = selector.resolve_type(capability)
    # conn_type == ConnectionType.ARTHAS
"""
from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# 连接类型枚举
# ═══════════════════════════════════════════════════════════════════════════════

class ConnectionType(Enum):
    """连接类型"""
    ARTHAS = "arthas"      # 需要 Arthas HTTP API
    POD = "pod"             # 仅需 kubectl exec
    NONE = "none"           # 无需连接


# ═══════════════════════════════════════════════════════════════════════════════
# 需要 Arthas 连接的命令列表
# ═══════════════════════════════════════════════════════════════════════════════

_ARTHAS_REQUIRED_COMMANDS = {
    'dashboard', 'thread', 'jvm', 'sysprop', 'sysenv', 'vmoption',
    'sc', 'sm', 'jad', 'classloader', 'logger',
    'trace', 'watch', 'stack', 'monitor', 'tt',
    'ognl', 'profiler', 'heapdump', 'jfr', 'dump',
    'redefine', 'retransform', 'mc', 'version', 'session',
    'perfcounter', 'ss', 'memory', 'heap', 'gc',
}

# 需要 Arthas 连接的类别
_ARTHAS_REQUIRED_CATEGORIES = {'quick', 'tool', 'scenario', 'ai'}

# 需要 Pod 连接但不需要 Arthas 的操作（容器内指标采集等）
_POD_ONLY_CATEGORIES = {'pod_monitor', 'container_metrics'}


# ═══════════════════════════════════════════════════════════════════════════════
# 连接选择器
# ═══════════════════════════════════════════════════════════════════════════════

class ConnectionSelector:
    """连接选择器 - 根据诊断能力定义自动选择连接类型

    决策逻辑：
    1. 如果 capability 有 steps_json（场景方案）→ ARTHAS
    2. 如果 capability 有 arthas_command 且命令在 Arthas 命令白名单中 → ARTHAS
    3. 如果 capability category 属于 POD_ONLY 类别 → POD
    4. 如果 capability category 属于 ARTHAS 类别 → ARTHAS
    5. 兜底 → NONE
    """

    @staticmethod
    def resolve_type(capability: Optional[Dict[str, Any]] = None) -> ConnectionType:
        """根据能力定义判断需要的连接类型

        Args:
            capability: 能力定义字典，包含 category, arthas_command, steps_json 等字段
                        如果为 None，返回 NONE

        Returns:
            ConnectionType: 需要的连接类型
        """
        if not capability:
            return ConnectionType.NONE

        # 1. 场景方案（有 DSL steps）→ 必须有 Arthas
        if capability.get('steps_json'):
            try:
                import json
                dsl = json.loads(capability['steps_json'])
                if dsl.get('steps'):
                    return ConnectionType.ARTHAS
            except (json.JSONDecodeError, TypeError, AttributeError):
                pass

        # 2. 有 arthas_command → 检查是否需要 Arthas
        arthas_cmd = capability.get('arthas_command', '')
        if arthas_cmd:
            cmd_name = arthas_cmd.strip().split()[0] if arthas_cmd.strip() else ''
            if cmd_name in _ARTHAS_REQUIRED_COMMANDS:
                return ConnectionType.ARTHAS

        # 3. 类别判断
        category = capability.get('category', '')
        if category in _POD_ONLY_CATEGORIES:
            return ConnectionType.POD
        if category in _ARTHAS_REQUIRED_CATEGORIES:
            return ConnectionType.ARTHAS

        # 4. 有 handler（AI 诊断）→ 通常需要 Arthas
        if capability.get('handler'):
            return ConnectionType.ARTHAS

        # 5. 兜底
        return ConnectionType.NONE

    @staticmethod
    def resolve_type_for_command(command: str) -> ConnectionType:
        """根据命令字符串判断需要的连接类型

        Args:
            command: Arthas 命令或 kubectl 命令

        Returns:
            ConnectionType: 需要的连接类型
        """
        if not command:
            return ConnectionType.NONE

        cmd_name = command.strip().split()[0] if command.strip() else ''

        # Arthas 命令
        if cmd_name in _ARTHAS_REQUIRED_COMMANDS:
            return ConnectionType.ARTHAS

        # kubectl 命令 → Pod 连接
        if cmd_name in ('kubectl', 'exec', 'cat', 'ps', 'top', 'df', 'ls', 'mount'):
            return ConnectionType.POD

        # 兜底
        return ConnectionType.NONE

    @staticmethod
    def validate_connection(connection, required_type: ConnectionType) -> Optional[str]:
        """验证连接是否满足要求

        Args:
            connection: ArthasConnection 或 PodConnection 对象
            required_type: 需要的连接类型

        Returns:
            str 或 None: 验证失败返回错误信息，成功返回 None
        """
        if required_type == ConnectionType.NONE:
            return None

        if connection is None:
            return "连接不存在"

        if required_type == ConnectionType.ARTHAS:
            # 检查 Arthas 是否就绪
            client = getattr(connection, 'http_client', None)
            if not client:
                return "Arthas HTTP 客户端不可用，可能未建立 Arthas 连接"
            # 检查 port-forward 是否存活
            pf_proc = getattr(connection, '_pf_proc', None)
            if pf_proc and pf_proc.poll() is not None:
                return "Arthas port-forward 进程已退出"
            return None

        if required_type == ConnectionType.POD:
            # 检查 Pod 连接是否就绪
            pod_conn = getattr(connection, 'pod_conn', None)
            if pod_conn and hasattr(pod_conn, 'is_alive'):
                if not pod_conn.is_alive():
                    return "Pod 连接不可用"
            return None

        return None

    @staticmethod
    def get_connection_info(connection) -> Dict[str, Any]:
        """获取连接摘要信息（用于日志/调试）

        Args:
            connection: 连接对象

        Returns:
            dict: 连接摘要
        """
        if connection is None:
            return {'type': 'none', 'status': 'not_connected'}

        info = {
            'connection_id': getattr(connection, 'connection_id', None),
            'cluster_name': getattr(connection, 'cluster_name', '') or
                            getattr(getattr(connection, 'target', None), 'cluster_name', ''),
            'namespace': getattr(connection, 'namespace', '') or
                         getattr(getattr(connection, 'target', None), 'namespace', ''),
            'pod_name': getattr(connection, 'pod_name', '') or
                        getattr(getattr(connection, 'target', None), 'pod_name', ''),
        }

        # 判断连接类型
        if hasattr(connection, 'http_client') and connection.http_client:
            info['type'] = 'arthas'
            info['arthas_ready'] = getattr(connection, '_arthas_ready', False)
            info['local_port'] = getattr(connection, 'local_port', 0)
            info['arthas_version'] = getattr(connection, 'arthas_version', None)
        elif hasattr(connection, 'pod_conn'):
            info['type'] = 'pod'
            info['pod_connected'] = getattr(connection, '_pod_connected', False)
        else:
            info['type'] = 'unknown'

        return info
