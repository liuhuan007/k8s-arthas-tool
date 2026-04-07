#!/usr/bin/env python3
"""
K8s Arthas Tool — 后端核心模块

本文件作为兼容层，从 backend.core 模块导入所有组件。
架构：
  backend/core/
    ├── models.py         # 数据模型
    ├── kubectl.py        # kubectl 封装
    ├── arthas_agent.py   # Arthas Agent 管理
    ├── arthas_client.py # Arthas HTTP 客户端
    ├── connection.py    # 连接管理
    └── profiler.py       # 性能分析工作流
"""
import os
import sys

# 确保 backend 包可导入
_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from backend.core import (
    ClusterConfig,
    PodTarget,
    ARTHAS_DEFAULT_JAR,
    ARTHAS_HTTP_PORT,
    KubectlExecutor,
    ArthasAgentManager,
    ArthasHttpClient,
    ArthasConnection,
    PF_BASE_PORT,
    ProfilerWorkflow,
)

__all__ = [
    'ClusterConfig',
    'PodTarget',
    'ARTHAS_DEFAULT_JAR',
    'ARTHAS_HTTP_PORT',
    'KubectlExecutor',
    'ArthasAgentManager',
    'ArthasHttpClient',
    'ArthasConnection',
    'PF_BASE_PORT',
    'ProfilerWorkflow',
]