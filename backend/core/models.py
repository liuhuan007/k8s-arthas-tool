"""
数据模型 - ClusterConfig, PodTarget 等
"""
from dataclasses import dataclass
from typing import Optional

# Arthas 配置
ARTHAS_DEFAULT_JAR = "/app/arthas/arthas-boot.jar"
ARTHAS_HTTP_PORT = 8563
ARTHAS_TELNET_PORT = 3658


@dataclass
class ClusterConfig:
    name: str
    kubeconfig: str
    context: str = ""


@dataclass
class PodTarget:
    cluster_name: str
    namespace: str
    pod_name: str
    container: str = ""
    arthas_jar: str = ARTHAS_DEFAULT_JAR
    arthas_http_port: int = ARTHAS_HTTP_PORT
    arthas_telnet_port: int = ARTHAS_TELNET_PORT