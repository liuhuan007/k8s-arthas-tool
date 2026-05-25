# K8s Arthas 智能诊断平台 — 工具箱设计


**文档版本**: v1.0
**创建日期**: 2026-05-23
**状态**: 设计完成

---

## 目录

1. [工具包管理](#1-工具包管理)
2. [Arthas JAR分发兼容](#2-arthas-jar分发兼容)
3. [Tunnel Server](#3-tunnel-server)
4. [在线修复](#4-在线修复)

---

## 1. 工具包管理

### 1.1 工具清单

| 工具类型 | 用途 | 分发方式 | 位置 |
|---------|------|---------|------|
| `arthas-boot.jar` | Arthas Agent JAR | kubectl cp / wget | `tools/arthas/` |
| `arthas-tunnel-server.jar` | Tunnel Server JAR | 本地启动 | `tools/arthas/` |
| `async-profiler` | CPU/内存采样 | kubectl cp | `tools/arthas/` |

### 1.2 目录结构

```
tools/
├── arthas/                          # Arthas工具包
│   ├── arthas-boot.jar              # Arthas主程序（离线环境使用）
│   └── arthas-tunnel-server.jar     # Tunnel Server（注册中心）
├── scripts/                         # 辅助脚本
│   ├── install-arthas.sh           # 安装Arthas到Pod
│   ├── start-tunnel-server.sh      # 启动Tunnel Server
│   └── connect-tunnel.sh           # 连接到Tunnel Server
└── README.md                        # 工具说明文档
```

### 1.3 部署模式

| 模式 | 说明 | 工具来源 |
|------|------|---------|
| 离线模式 | 无网络环境 | 使用`tools/arthas/`中的预制包 |
| 在线模式 | 有网络环境 | 从阿里云下载最新版本 |
| 混合模式 | 优先本地，网络备选 | 本地包 + 网络下载 |

### 1.4 工具箱管理

工具箱采用"列表 + 详情页"管理，支持兼容性检查（JDK 版本、CPU 架构）、SHA256 校验和健康检查。

---

## 2. Arthas JAR分发兼容

| 检查点 | 规则 | 失败处理 |
|--------|------|---------|
| JDK 版本 | java -version 解析主版本 | 提示不兼容，允许选择其他版本 |
| CPU 架构 | uname -m 识别 | 没有匹配包时禁止分发 |
| 文件完整性 | SHA256 校验 | 最多重试 3 次 |

---

## 3. Tunnel Server

### 3.1 核心功能

Tunnel Server作为Arthas连接的**注册中心**，统一管理所有Pod的Arthas连接：

```
┌─────────────────────────────────────────────────────────────────┐
│                    Tunnel Server (注册中心)                      │
│                    ws://127.0.0.1:7777/ws                       │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │ Pod A       │  │ Pod B       │  │ Pod C       │             │
│  │ app-name:   │  │ app-name:   │  │ app-name:   │             │
│  │ my-app-pod  │  │ order-svc   │  │ user-svc    │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 部署模式

| 模式 | 说明 | 适用场景 |
|------|------|---------|
| 本地模式 | 单机启动Tunnel Server | 开发测试、单节点部署 |
| 集群模式 | 多实例部署，共享注册信息 | 生产环境、高可用 |
| 嵌入模式 | 集成到平台后端 | 轻量部署、统一管理 |

### 3.3 启动方式

```bash
# 默认端口7777
java -jar arthas-tunnel-server.jar --server.port=7777

# 自定义配置
java -jar arthas-tunnel-server.jar \
  --server.port=7777 \
  --arthas.server.port=7778 \
  --spring.config.location=./application.yml
```

### 3.4 Pod连接方式

Pod中的Arthas Agent通过`--app-name`参数连接到Tunnel Server：

```bash
# app-name建议与Pod名称一致
java -jar arthas-boot.jar \
  --tunnel-server 'ws://127.0.0.1:7777/ws' \
  --app-name <pod-name>
```

### 3.5 Web控制台

Tunnel Server提供Web控制台，用于：
- 查看所有已连接的Pod
- 监控连接状态和健康度
- 统一执行诊断命令
- 查看执行历史记录

访问地址：`http://<tunnel-server-ip>:7777`

### 3.6 管理功能

- 本地启动 `arthas-tunnel-server.jar`，展示可访问 IP 和端口
- Agent attach 时可勾选注册远程
- 同一平台实例默认只运行一个进程
- 异常退出时更新状态并提示重启
- 支持多用户同时访问
- 支持连接健康检查和自动重连

### 3.7 连接模式决策树（P0）

> **问题修复**：明确Port-Forward和Tunnel Server两种模式的适用场景和优先级。

```
┌─────────────────────────────────────────────────────────────────┐
│                    连接模式决策树                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  是否有网络限制（Pod无法访问外部）？                              │
│       │                                                         │
│       ├── 否 ──→ 使用 Port-Forward（简单直接，P0默认）           │
│       │         • 平台主动建立连接                                │
│       │         • 无需额外部署                                    │
│       │         • 适合开发测试和简单生产环境                      │
│       │                                                         │
│       └── 是 ──→ 是否已部署 Tunnel Server？                      │
│                    │                                            │
│                    ├── 否 ──→ 提示部署 Tunnel Server            │
│                    │         或使用 kubectl exec 作为降级       │
│                    │                                            │
│                    └── 是 ──→ 使用 Tunnel Server                │
│                              • Pod主动注册                       │
│                              • 支持跨网络访问                    │
│                              • 适合复杂网络环境                  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**优先级**：Port-Forward（P0）> Tunnel Server（P1）

### 3.8 连接提供者抽象接口（P0）

> **问题修复**：定义统一的连接提供者接口，支持两种模式无缝切换。

```python
from abc import ABC, abstractmethod
from typing import Optional
from dataclasses import dataclass

@dataclass
class PodTarget:
    """Pod目标"""
    cluster_name: str
    namespace: str
    pod_name: str
    container_name: Optional[str] = None

@dataclass
class Connection:
    """连接信息"""
    connection_id: str
    level: str  # pod / arthas
    status: str  # pending / connecting / ready / failed / disconnected
    port_forward_port: Optional[int] = None
    arthas_version: Optional[str] = None

class ConnectionProvider(ABC):
    """连接提供者抽象接口"""
    
    @abstractmethod
    async def connect(self, pod_target: PodTarget) -> Connection:
        """建立连接"""
        pass
    
    @abstractmethod
    async def disconnect(self, connection_id: str) -> bool:
        """断开连接"""
        pass
    
    @abstractmethod
    async def health_check(self, connection_id: str) -> bool:
        """健康检查"""
        pass
    
    @abstractmethod
    def get_provider_type(self) -> str:
        """获取提供者类型"""
        pass

class PortForwardProvider(ConnectionProvider):
    """Port-Forward连接提供者（P0默认）"""
    
    def get_provider_type(self) -> str:
        return "port_forward"

class TunnelServerProvider(ConnectionProvider):
    """Tunnel Server连接提供者（P1）"""
    
    def get_provider_type(self) -> str:
        return "tunnel_server"
```

---

## 4. 在线修复

### 4.1 在线修复流程

使用 Arthas `jad → mc → redefine` 链路实现轻量热更新闭环：

```text
用户选择目标 → jad 查看源码 → 在线编辑/上传 .java/.class → mc 编译 → redefine 生效 → 验证
```

### 4.2 技术限制用户告知

**强制确认流程**：

```
┌─────────────────────────────────────────────────────────┐
│  ⚠️ 在线修复警告                                          │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  以下限制请确认知晓：                                     │
│  • 不能增减方法参数/字段                                  │
│  • 不能修改继承关系                                       │
│  • JDK 17+ 可能受限                                      │
│  • Spring Bean 不更新代理                                │
│                                                         │
│  修改类: com.example.OrderService                        │
│  修改方法: createOrder                                   │
│  SHA256: abc123def456...                                 │
│                                                         │
│  ⚠️ 此操作不可逆，请确认已备份原始代码                     │
│                                                         │
│  请输入 "CONFIRM" 继续: [________]                       │
│                                                         │
│  [取消]  [确认执行]                                       │
└─────────────────────────────────────────────────────────┘
```

### 4.3 回滚机制

**自动备份**：redefine前自动备份原始class文件

```python
class HotfixManager:
    """在线修复管理器"""
    
    def backup_class(self, connection_id: str, class_name: str) -> str:
        """备份原始class文件"""
        
        # 1. 使用jad导出原始代码
        jad_output = self.arthas_executor.execute(
            f"jad --source-only {class_name}",
            connection_id
        )
        
        # 2. 保存备份
        backup_path = f"/tmp/hotfix_backup/{class_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.java"
        self._save_to_pod(connection_id, backup_path, jad_output)
        
        # 3. 记录备份信息
        db.insert('hotfix_backups', {
            'connection_id': connection_id,
            'class_name': class_name,
            'backup_path': backup_path,
            'sha256': self._calculate_sha256(jad_output),
            'created_at': datetime.now()
        })
        
        return backup_path
    
    def rollback(self, connection_id: str, backup_id: int) -> bool:
        """回滚到备份版本"""
        
        backup = db.fetch_one(
            "SELECT * FROM hotfix_backups WHERE id = ?",
            (backup_id,)
        )
        
        if not backup:
            return False
        
        # 1. 从备份恢复代码
        original_code = self._load_from_pod(connection_id, backup['backup_path'])
        
        # 2. 重新编译和redefine
        compile_result = self._compile_class(original_code)
        if compile_result['success']:
            redefine_result = self._redefine_class(
                connection_id, 
                backup['class_name'], 
                compile_result['class_bytes']
            )
            return redefine_result
        
        return False
```

### 4.4 审计与合规

**审计日志记录**：

```json
{
  "event": "hotfix.execute",
  "timestamp": "2026-05-24T15:00:00Z",
  "user_id": 123,
  "user_name": "admin",
  "connection_id": "conn-xxx",
  "class_name": "com.example.OrderService",
  "method_name": "createOrder",
  "original_sha256": "abc123...",
  "new_sha256": "def456...",
  "backup_id": 789,
  "status": "success",
  "risk_level": "high",
  "requires_approval": true,
  "approved_by": "admin"
}
```

**管理员审批流程**：

| 风险等级 | 审批要求 |
|---------|---------|
| 高危（redefine） | 需要管理员审批 |
| 中危（jad/mc） | 记录审计日志 |
| 低危（查看源码） | 无需审批 |

### 4.5 验证自动化

| 层级 | 内容 | P0/P1 策略 |
|------|------|-----------|
| L0 目标确认 | 展示连接/PID/类名/SHA256/风险提示 | P0 必做 |
| L1 技术验证 | redefine 后自动 jad 确认代码变化 | P0 必做 |
| L2 诊断验证 | 用户选择 trace/watch 模板验证 | P1 建议做 |
| L3 业务验证 | 调用业务接口比对结果 | P2 |

**L1技术验证实现**：

```python
def verify_hotfix(self, connection_id: str, class_name: str, expected_sha256: str) -> bool:
    """验证redefine是否生效"""
    
    # 1. 使用jad获取当前代码
    current_code = self.arthas_executor.execute(
        f"jad --source-only {class_name}",
        connection_id
    )
    
    # 2. 计算SHA256
    current_sha256 = self._calculate_sha256(current_code)
    
    # 3. 比较是否与预期一致
    if current_sha256 == expected_sha256:
        log.info(f"Hotfix verification passed for {class_name}")
        return True
    else:
        log.warning(f"Hotfix verification failed for {class_name}")
        return False
```