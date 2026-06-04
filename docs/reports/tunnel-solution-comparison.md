# K8s Arthas Tool — Tunnel 连接方案对比报告

| 属性 | 值 |
|---|---|
| 项目名称 | K8s Arthas 智能诊断平台 |
| 报告类型 | 架构决策对比（ADR） |
| 方案主题 | Tunnel Server vs Port-Forward 连接方案 |
| 文档版本 | v2.0 |
| 生成时间 | 2026-05-27 |
| 状态 | **对比分析（未采纳）** |

---

## 1. 背景与问题陈述

### 1.1 当前问题

K8s Arthas Tool 需要建立**浏览器 → Flask 后端 → K8s Pod 内 Arthas** 的通信链路。

当前 `02-connection-center.md` 中设计的方案依赖 `kubectl port-forward` 子进程，存在以下架构问题：

```
┌──────────────────────────────────────────────────────┐
│         当前方案（kubectl port-forward）              │
├──────────────────────────────────────────────────────┤
│  Flask 后端                                       │
│  ├── 启动 kubectl port-forward 子进程             │
│  ├── 管理本地端口分配 / 释放                     │
│  ├── 服务重启后需要重建 port-forward              │
│  └── 多标签页共享同一端口转发（需要 BroadcastChannel）│
│                                                      │
│  问题：                                             │
│  ❌ 依赖本地进程管理，不稳定                      │
│  ❌ 端口资源竞争                                   │
│  ❌ 服务重启后连接状态丢失                         │
│  ❌ 多标签页同步机制复杂                           │
└──────────────────────────────────────────────────────┘
```

### 1.2 决策目标

选择一种**稳定、可恢复、易维护、权限可控**的 Tunnel 方案，满足以下要求：

1. 支持浏览器通过 WebSocket 与 Pod 内 Arthas 通信
2. 服务重启后可恢复连接
3. 多标签页可共享同一 Tunnel
4. 最小化端口管理和进程管理复杂度
5. **权限隔离**：用户只能访问自己 namespace 下的 Pod
6. **不将 Tunnel Server 暴露到公网**（官方安全建议）

---

## 2. 候选方案

### 方案 A：kubectl port-forward（当前方案，基线）

```
┌──────────────────────────────────────────────────────────┐
│  浏览器                                             │
│     │  WebSocket (wss://...)                         │
│     ▼                                                │
│  ┌──────────────────────────────────────────────────┐  │
│  │  Flask Tunnel Server (集群外部署)                │  │
│  │  ├── 为每个连接启动 kubectl port-forward       │  │
│  │  │   (子进程)                                  │  │
│  │  ├── 分配本地端口 (localhost:随机)             │  │
│  │  └── 代理 WebSocket ↔ localhost:端口          │  │
│  └────────────┬─────────────────────────────────┘  │
│                   │ kubectl port-forward              │
│                   ▼                                  │
│  ┌──────────────────────────────────────────────────┐  │
│  │  K8s API Server                                │  │
│  │  └── portforward 子资源 (SPDY 流)            │  │
│  └────────────┬─────────────────────────────────┘  │
│                   ▼                                  │
│  ┌──────────────────────────────────────────────────┐  │
│  │  Pod (目标 JVM)                                │  │
│  │  └── Arthas HTTP :3658                        │  │
│  └──────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

**连接条件**：

| 条件 | 说明 | 是否必须 |
|---|---|---|
| K8s API Server 可达 | Flask 能访问 K8s API Server | ✅ 必须 |
| kubectl 二进制 | 服务器上安装 kubectl | ✅ 必须 |
| kubeconfig / Token | 认证凭据 | ✅ 必须 |
| RBAC: pods/portforward | ServiceAccount 权限 | ✅ 必须 |
| 本地端口空闲 | 分配 localhost 端口 | ✅ 必须 |
| 进程管理能力 | 追踪子进程生命周期 | ✅ 必须 |

---

### 方案 B：Tunnel Sidecar（Pod 内注入）

```
┌──────────────────────────────────────────────────────────┐
│  Pod (目标 JVM + Sidecar)                           │
│  ┌──────────────────┐  ┌──────────────────────────┐  │
│  │ 业务容器           │  │ Tunnel Sidecar            │  │
│  │ ├── JVM           │  │ ├── WebSocket Server    │  │
│  │ └── Arthas :3658 │  │ ├── 代理到 localhost  │  │
│  │                    │  │ └── :3658              │  │
│  └──────────────────┘  └────────┬─────────────────┘  │
│                                  localhost:3658 ▲       │
│                                 同一 Pod 内网络          │
└──────────────────────────────────┬───────────────────────┘
                                   │ K8s Service (NodePort)
                                   ▼
┌──────────────────────────────────────────────────────────┐
│  浏览器                                             │
│     │  wss://node-ip:30080/tunnel/ws/{conn_id}     │
│     ▼                                                │
│  ┌──────────────────────────────────────────────────┐  │
│  │  K8s Service → Sidecar WebSocket Server         │  │
│  └──────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

**连接条件**：

| 条件 | 说明 | 是否必须 |
|---|---|---|
| Pod 注入 Sidecar | 修改 Deployment / StatefulSet | ✅ 必须（侵入性强） |
| Sidecar 镜像 | 自定义 Tunnel Sidecar 容器镜像 | ✅ 必须 |
| K8s Service | 暴露 Sidecar 端口（NodePort / LoadBalancer） | ✅ 必须 |
| RBAC | 不需要 pods/portforward（Sidecar 在 Pod 内） | ❌ 不需要 |
| 网络：浏览器 → Node IP | 防火墙 / 安全组放行 | ✅ 必须 |
| Pod 重启感知 | Sidecar 随 Pod 重启，需要重连机制 | ✅ 必须 |

---

### 方案 C：K8s Port-Forward API（Flask 直连）

> **修正说明**：之前报告中提到的 "K8s API Proxy" 实际应为 **K8s Port-Forward API**（`/api/v1/namespaces/{ns}/pods/{pod}/portforward`），通过 SPDY / WebSocket 双向流实现，不依赖本地端口转发。

```
┌──────────────────────────────────────────────────────────┐
│  浏览器                                             │
│     │  WebSocket (wss://flask/tunnel/ws/{conn_id})  │
│     ▼                                                │
│  ┌──────────────────────────────────────────────────┐  │
│  │  Flask Tunnel Server (自研，基于 K8s SDK)       │  │
│  │  ├── WebSocket 前端连接管理                      │  │
│  │  ├── K8s Python SDK                           │  │
│  │  │   stream.connect_get_namespaced_pod_         │  │
│  │  │   portforward(...)                          │  │
│  │  ├── SPDY/WebSocket 双向流处理                 │  │
│  │  └── 将 K8s port-forward 流桥接到前端 WS     │  │
│  └────────────┬─────────────────────────────────┘  │
│                   │ K8s Port-Forward API (SPDY)      │
│                   ▼                                  │
│  ┌──────────────────────────────────────────────────┐  │
│  │  K8s API Server                                │  │
│  │  └── /api/v1/.../pods/{pod}/portforward     │  │
│  └────────────┬─────────────────────────────────┘  │
│                   │ SPDY 流 → kubelet → Pod         │
│                   ▼                                  │
│  ┌──────────────────────────────────────────────────┐  │
│  │  Pod (目标 JVM)                                │  │
│  │  └── Arthas HTTP :3658                        │  │
│  └──────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

**连接条件**：

| 条件 | 说明 | 是否必须 |
|---|---|---|
| K8s API Server 可达 | Flask 能访问 API Server | ✅ 必须 |
| K8s Python SDK | `pip install kubernetes` | ✅ 必须 |
| RBAC: pods/portforward | ServiceAccount 权限 | ✅ 必须 |
| SPDY 支持 | Python `requests` 不支持，需用 `websocket-client` 或 Go SDK | ⚠️ 注意 |
| 网络：API Server → kubelet | K8s 控制平面自带，通常已通 | ✅ 自动满足 |

**方案 C 关键风险**：需要自研 SPDY 流处理，与官方 Arthas Agent 的 WebSocket 协议兼容性未经验证。

---

### 方案 D：官方 Tunnel Server + Python 进程管理 ✅ **最终选择**

> **核心思路**：使用官方 `arthas-tunnel-server.jar`，与 k8s-arthas-tool **共部署在同一台机器**，由 Python 后端通过 `subprocess` 管理其生命周期。

```
┌─────────────────────────────────────────────────────────────────────┐
│  浏览器                                             │
│     │  HTTP/WebSocket (经过 Python 鉴权)                      │
│     ▼                                                        │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Python 后端 (k8s-arthas-tool)                        │  │
│  │  ├── 鉴权网关 (用户只能访问自己的 Pod)                │  │
│  │  ├── 代理转发到 Tunnel Server (localhost:8080)       │  │
│  │  ├── 管理 Tunnel Server 进程                          │  │
│  │  │   (subprocess: start/stop/health_check)          │  │
│  │  └── 权限过滤 (/actuator/arthas 返回结果过滤)       │  │
│  └────────────┬─────────────────────────────────────────┘  │
│                 │ localhost:8080 (仅内网/localhost 访问)    │
│                 ▼                                            │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  官方 Arthas Tunnel Server (Java Spring Boot)          │  │
│  │  ├── Web Console:  localhost:8080                    │  │
│  │  ├── Agent 接入:    localhost:7777/ws               │  │
│  │  ├── Actuator:     /actuator/health                │  │
│  │  └── Agent 列表:   /actuator/arthas                │  │
│  └────────────┬─────────────────────────────────────────┘  │
│                 │ WebSocket (7777)                           │
│                 ▼                                            │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Pod 内 Arthas Agent                                 │  │
│  │  └── 启动命令:                                       │  │
│  │       java -jar arthas-boot.jar                        │  │
│  │       --tunnel-server ws://<host>:7777/ws             │  │
│  │       --agent-id <connection-id>                      │  │
│  │       --app-name <namespace>-<pod>                    │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

**部署方式**：Tunnel Server 与 k8s-arthas-tool **共部署**（同一 Pod 的两个容器，或同一台物理机）。

**连接条件**：

| 条件 | 说明 | 是否必须 |
|---|---|---|
| JDK 环境 | 机器上安装 JDK 8+ | ✅ 必须 |
| `arthas-tunnel-server.jar` | 官方 Jar 包 | ✅ 必须 |
| Python `requests` 库 | 调用 Tunnel Server HTTP API | ✅ 必须 |
| Python `subprocess` | 管理 Tunnel Server 进程（标准库，无需安装） | ✅ 必须 |
| 本地端口可用 | localhost:8080 + :7777 未被占用 | ✅ 必须 |
| **❌ 不需要 kubectl** | 无 kubectl 依赖 | ❌ 不需要 |
| **❌ 不需要 K8s Python SDK** | 无 SPDY 处理 | ❌ 不需要 |
| **❌ 不需要 pods/portforward RBAC** | 不通过 K8s API 做 port-forward | ❌ 不需要 |

---

## 3. 四种方案详细对比

### 3.1 架构对比表

| 维度 | 方案 A（port-forward） | 方案 B（Sidecar） | 方案 C（K8s API） | 方案 D（官方 Tunnel） |
|---|---|---|---|---|
| **部署位置** | Flask 在集群外 | Sidecar 在 Pod 内 | Flask 在集群内/外 | **共部署（同一机器）** |
| **Tunnel Server** | 自研（Python） | 自研（Go/Python） | 自研（Python + SPDY） | **官方 Jar（Spring Boot）** |
| **连接建立方式** | kubectl 子进程 | Sidecar WebSocket | K8s SDK port-forward | **Agent → Tunnel WS** |
| **本地端口依赖** | ✅ 需要 | ❌ 不需要 | ❌ 不需要 | ❌ 不需要（localhost 内部） |
| **SPDY 处理** | kubectl 内部处理 | 不需要 | ⚠️ Python 侧处理（复杂） | ❌ 不需要（官方处理） |
| **Pod 侵入性** | ❌ 无侵入 | ❌ 高侵入 | ❌ 无侵入 | ❌ 无侵入 |
| **服务重启恢复** | ❌ 差 | ⭐ 中 | ⭐ 中 | ✅ 好（进程可重启） |
| **多标签页共享** | ⚠️ 复杂 | ✅ 天然支持 | ✅ 天然支持 | ✅ 天然支持 |
| **官方兼容性** | ⚠️ 需要自研协议 | ⚠️ 需要自研协议 | ⚠️ 需要自研协议 | ✅ 官方协议 |
| **复杂度** | ⭐ 中 | ⭐ 高 | ❌ 高（SPDY） | ⭐ 低 |

### 3.2 优缺点总结

#### 方案 A：kubectl port-forward（当前方案）

| 优点 | 缺点 |
|---|---|
| ✅ 无 Pod 侵入，不需要修改业务 Deployment | ❌ 依赖本地 kubectl 二进制 |
| ✅ 兼容所有 K8s 集群（只要有 kubeconfig） | ❌ 需要管理本地端口分配 / 释放 |
| ✅ 实现简单（直接调用 kubectl） | ❌ 服务重启后需要重建所有 port-forward |
| | ❌ 多标签页共享同一连接机制复杂 |
| | ❌ 子进程生命周期管理复杂（孤儿进程风险） |

#### 方案 B：Tunnel Sidecar

| 优点 | 缺点 |
|---|---|
| ✅ 不需要 kubectl / K8s API 代理 | ❌ 侵入性强，需要修改业务 Pod 定义 |
| ✅ 网络路径最短（浏览器 → NodePort → Sidecar） | ❌ 需要维护 Sidecar 容器镜像 |
| ✅ 不需要管理 port-forward 流 | ❌ 每个业务 Pod 都需要注入 Sidecar（资源开销） |
| ✅ 天然支持多客户端 WebSocket 连接 | ❌ 业务团队配合成本高 |
| | ❌ 托管集群 NodePort 暴露需要额外安全配置 |

#### 方案 C：K8s Port-Forward API

| 优点 | 缺点 |
|---|---|
| ✅ 无 Pod 侵入 | ⚠️ Python SPDY 流处理较复杂（需 `websocket-client` 库） |
| ✅ 不需要本地端口管理 | ⚠️ K8s Python SDK 的 port-forward 示例较少 |
| ✅ 无 kubectl 子进程依赖 | ❌ **需要自研与官方 Arthas Agent 的 WebSocket 协议对接（风险高）** |
| ✅ 服务重启后可编程恢复（有 API） | |
| ✅ 天然支持多客户端（Flask 统一管理） | |

#### 方案 D：官方 Tunnel Server + Python 进程管理 ✅

| 优点 | 缺点 |
|---|---|
| ✅ **使用官方 Tunnel Server，协议兼容性有保障** | ❌ 需要 JDK 环境（机器上安装 JDK） |
| ✅ **Python 后端统一鉴权，解决官方 Tunnel 无权限管理的问题** | ❌ Tunnel Server 与 k8s-arthas-tool 竞争 CPU/内存 |
| ✅ **简化网络**：本地访问，无需 K8s Port-Forward 或外部负载均衡 | ❌ 单点故障：Tunnel Server 挂了影响 k8s-arthas-tool（可缓解：健康检查 + 自动重启） |
| ✅ **低延迟**：本地 HTTP 调用，延迟 <1ms | ❌ 日志混合：两个服务的日志混在一起（可缓解：配置不同日志路径） |
| ✅ **无 SPDY 处理复杂度**：使用官方 Tunnel Server | |
| ✅ **无 kubectl / K8s SDK 依赖** | |
| ✅ **官方文档支持**，社区验证 | |
| ✅ **部署简单**：共部署，一个 Pod 管理两个容器 | |

### 3.3 依赖资源对比

| 依赖项 | 方案 A | 方案 B | 方案 C | 方案 D |
|---|---|---|---|---|
| **kubectl 二进制** | ✅ 必须 | ❌ 不需要 | ❌ 不需要 | ❌ 不需要 |
| **K8s Python SDK** | ❌ 不需要 | ❌ 不需要 | ✅ 必须 | ❌ 不需要 |
| **SPDY 客户端库** | ❌ 不需要 | ❌ 不需要 | ✅ 必须 | ❌ 不需要 |
| **Pod Sidecar 注入** | ❌ 不需要 | ✅ 必须 | ❌ 不需要 | ❌ 不需要 |
| **K8s Service (NodePort)** | ❌ 不需要 | ✅ 必须 | ❌ 不需要 | ❌ 不需要 |
| **JDK 环境** | ❌ 不需要 | ❌ 不需要 | ❌ 不需要 | ✅ 必须 |
| **官方 Tunnel Server Jar** | ❌ 不需要 | ❌ 不需要 | ❌ 不需要 | ✅ 必须 |
| **Python `requests` 库** | ❌ 不需要 | ❌ 不需要 | ✅ 必须 | ✅ 必须 |
| **Python `subprocess`（标准库）** | ❌ 不需要 | ❌ 不需要 | ❌ 不需要 | ✅ 必须 |
| **RBAC: pods/portforward** | ✅ 必须 | ❌ 不需要 | ✅ 必须 | ❌ 不需要 |
| **pom.xml Java 依赖** | ❌ 不需要 | ❌ 不需要 | ❌ 不需要 | ❌ **不需要** |

> **关键**：k8s-arthas-tool 是 Python 应用，**不需要 pom.xml 依赖**。与 Tunnel Server 通过 HTTP API 交互。

---

## 4. 方案对比总结（未采纳任何方案）

> **DECISION: Port-Forward (方案A) 为 P0 方案。Tunnel 方案 (方案D) 仅作对比参考，暂不采纳。**
>
> 本文档仅为技术对比分析，Tunnel 方案暂不落地。
> 当前 P0 架构使用 **方案 A（Port-Forward 模式）**，简单直接，无额外依赖。

### 4.1 各方案结论

| 方案 | 结论 | 当前状态 |
|------|------|---------|
| 方案 A（port-forward） | **P0 采用** | 已实现 |
| 方案 B（Sidecar） | 不采纳 | 运维复杂 |
| 方案 C（K8s API） | 不采纳 | 需自研 SPDY 协议 |
| 方案 D（官方 Tunnel） | **暂不采纳** | 引入 JDK 依赖 |

### 4.2 未采纳 Tunnel 方案（方案 D）的原因

| 原因 | 说明 |
|------|------|
| 引入 JDK 依赖 | 机器需安装 JDK，增加运维复杂度 |
| 进程管理复杂度 | Python 需管理 Java 子进程生命周期 |
| 资源竞争 | Tunnel Server 与 k8s-arthas-tool 竞争 CPU/内存 |
| 官方安全警告 | Tunnel Server 无内置权限管理，需额外加固 |
| 当前无跨网络需求 | P0 阶段 Pod 网络可达，无需 Tunnel |

### 4.3 未来何时考虑采纳 Tunnel 方案

- 生产环境有网络隔离，Pod 无法访问外部
- 需要支持跨网络诊断（防火墙后）
- 团队有能力维护 JDK + Python 混合部署

---

## 5. 决策记录

| 字段 | 内容 |
|---|---|
| **P0 决策** | 采用方案 A：kubectl port-forward（Port-Forward 模式） |
| **对比方案** | 方案 B（Sidecar）、方案 C（K8s API）、方案 D（官方 Tunnel） |
| **决策者** | 架构评审组 |
| **决策时间** | 2026-05-27 |
| **Tunnel 方案状态** | ❌ **未采纳，仅对比分析** |

---

## 6. 后续行动（仅 Port-Forward 方案）

- [x] 完成方案对比报告（v2.0）
- [x] 确认 P0 采用方案 A（Port-Forward 模式）
- [ ] 实现 `services/k8s_portforward.py`（K8s Port-Forward API 封装）
- [ ] 更新 `02-connection-center.md`（明确 Port-Forward 为 P0 方案）
- [ ] Tunnel 方案（方案 D）留作对比参考，暂不落地
- [ ] 更新 `review/architecture-review.md` 同步评审结果

---

## 7. Client 端配置与依赖说明

### 7.1 前端（JavaScript）客户端

#### 启动配置

| 配置项 | 说明 | 默认值 |
|---|---|---|
| `TUNNEL_WS_URL` | Tunnel Server WebSocket 地址 | `wss://{host}/tunnel/ws/{connection_id}` |
| `CONNECTION_ID` | 连接标识符（从后端获取） | 无默认值，必须 |
| `HEARTBEAT_INTERVAL` | WebSocket 心跳间隔（毫秒） | `30000` |
| `RECONNECT_INTERVAL` | 断线重连间隔（毫秒） | `3000` |
| `REQ_TIMEOUT` | 请求超时（毫秒） | `30000` |

#### 依赖包

**浏览器原生支持 WebSocket**，不需要额外依赖包。

如果使用较老的浏览器（IE10 以下），需要 polyfill：

```html
<!-- 可选：WebSocket polyfill（IE9 及以下） -->
<script src="https://cdn.jsdelivr.net/npm/web-socket-polyfill@0.0.2/dist/web-socket-polyfill.min.js"></script>
```

#### 完整配置示例

```javascript
// static/js/components/tunnel-client.js

class TunnelClient {
    /**
     * @param {string} connectionId - 连接 ID（从后端 /api/connections 获取）
     * @param {Object} options - 可选配置
     * @param {string} options.baseUrl - Tunnel Server 地址（默认自动检测）
     * @param {number} options.heartbeatInterval - 心跳间隔 ms（默认 30000）
     * @param {number} options.reconnectInterval - 重连间隔 ms（默认 3000）
     */
    constructor(connectionId, options = {}) {
        this.connectionId = connectionId;
        this.baseUrl = options.baseUrl || this._detectBaseUrl();
        this.heartbeatInterval = options.heartbeatInterval || 30000;
        this.reconnectInterval = options.reconnectInterval || 3000;
        this.ws = null;
        this.onMessage = null;       // 消息回调
        this.onConnect = null;       // 连接成功回调
        this.onDisconnect = null;    // 断开连接回调
        this._heartbeatTimer = null;
    }

    _detectBaseUrl() {
        // 自动检测 Tunnel Server 地址
        const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        return `${protocol}//${location.host}`;
    }

    async connect() {
        const wsUrl = `${this.baseUrl}/tunnel/ws/${this.connectionId}`;
        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = () => {
            console.log(`[Tunnel] Connected: ${this.connectionId}`);
            this._startHeartbeat();
            if (this.onConnect) this.onConnect();
        };

        this.ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.type === 'heartbeat') {
                return; // 心跳响应，忽略
            }
            if (this.onMessage) {
                this.onMessage(data);
            }
        };

        this.ws.onclose = () => {
            console.log(`[Tunnel] Disconnected: ${this.connectionId}`);
            this._stopHeartbeat();
            if (this.onDisconnect) this.onDisconnect();
            // 自动重连
            setTimeout(() => this.connect(), this.reconnectInterval);
        };

        this.ws.onerror = (error) => {
            console.error('[Tunnel] Error:', error);
        };
    }

    _startHeartbeat() {
        this._heartbeatTimer = setInterval(() => {
            if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                this.ws.send(JSON.stringify({ type: 'heartbeat' }));
            }
        }, this.heartbeatInterval);
    }

    _stopHeartbeat() {
        if (this._heartbeatTimer) {
            clearInterval(this._heartbeatTimer);
            this._heartbeatTimer = null;
        }
    }

    /**
     * 发送诊断请求到 Pod 内 Arthas
     * @param {string} arthasPath - Arthas HTTP API 路径（如 /arthas/http/json/execute）
     * @param {string} method - HTTP 方法（GET/POST）
     * @param {Object} body - POST 请求体
     * @returns {Promise<Object>} Arthas 响应
     */
    async sendRequest(arthasPath, method = 'POST', body = {}) {
        return new Promise((resolve, reject) => {
            const requestId = Date.now().toString();
            const handler = (data) => {
                if (data.request_id === requestId) {
                    this.onMessage = null;
                    if (data.error) {
                        reject(new Error(data.error));
                    } else {
                        resolve(data.result);
                    }
                }
            };
            this.onMessage = handler;

            this.ws.send(JSON.stringify({
                request_id: requestId,
                path: arthasPath,
                method: method,
                body: body
            }));

            // 超时处理
            setTimeout(() => {
                if (this.onMessage === handler) {
                    this.onMessage = null;
                    reject(new Error('Request timeout'));
                }
            }, 30000);
        });
    }

    disconnect() {
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
        this._stopHeartbeat();
    }
}

// 使用示例
// const tunnel = new TunnelClient('conn-12345');
// tunnel.onMessage = (data) => console.log('Received:', data);
// await tunnel.connect();
// const result = await tunnel.sendRequest('/arthas/http/json/version', 'GET');
// console.log(result);
```

---

### 7.2 后端（Python）Tunnel Server 依赖

#### pip 依赖包（requirements.txt）

```txt
# Web 框架
Flask>=3.0.0                 # Web 框架
flask-cors>=4.0.0            # 跨域支持

# HTTP 客户端（调用 Tunnel Server API）
requests>=2.31.0              # 必须

# K8s 相关（用于 Pod 内启动 Arthas）
kubernetes>=28.1.0            # 可选：如果需要通过 K8s API 启动 Arthas

# 可选：异步支持
aiohttp>=3.9.0               # 可选
```

> **注意**：不需要 `websocket-client`、`flask-sock` 等 WebSocket 库，因为 WebSocket 连接由官方 Tunnel Server 处理，Python 后端只做 HTTP 代理。

#### TunnelManager 实现（进程管理）

```python
# services/tunnel_manager.py
import subprocess
import requests
import time
import logging
from flask import current_app

logger = logging.getLogger(__name__)

class TunnelManager:
    """管理 Arthas Tunnel Server 生命周期（官方 Jar 包）"""
    
    TUNNEL_JAR = "/opt/arthas/arthas-tunnel-server.jar"
    DEFAULT_WEB_PORT = 8080
    DEFAULT_AGENT_PORT = 7777
    
    def __init__(self):
        self.process = None
        self.web_port = self.DEFAULT_WEB_PORT
        self.agent_port = self.DEFAULT_AGENT_PORT
    
    def start(self, web_port: int = None, agent_port: int = None) -> bool:
        """启动 Tunnel Server"""
        self.web_port = web_port or self.DEFAULT_WEB_PORT
        self.agent_port = agent_port or self.DEFAULT_AGENT_PORT
        
        cmd = [
            'java', '-jar', self.TUNNEL_JAR,
            f'--server.port={self.web_port}',
            f'--arthas.agent-port={self.agent_port}',
            '--arthas.enable-detail-pages=false'  # 安全：关闭管理页面
        ]
        
        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            logger.info(f"Tunnel Server 启动中 (PID: {self.process.pid})")
            
            # 等待启动完成（检查 Actuator 端点）
            return self._wait_for_ready(timeout=30)
        except Exception as e:
            logger.error(f"启动 Tunnel Server 失败: {e}")
            return False
    
    def stop(self) -> bool:
        """停止 Tunnel Server"""
        if not self.process:
            logger.warning("Tunnel Server 未运行")
            return True
        
        try:
            self.process.terminate()
            self.process.wait(timeout=10)
            logger.info("Tunnel Server 已停止")
            return True
        except subprocess.TimeoutExpired:
            logger.warning("Tunnel Server 未及时停止，强制终止")
            self.process.kill()
            return True
        except Exception as e:
            logger.error(f"停止 Tunnel Server 失败: {e}")
            return False
    
    def restart(self) -> bool:
        """重启 Tunnel Server"""
        self.stop()
        return self.start()
    
    def get_status(self) -> dict:
        """获取 Tunnel Server 状态"""
        try:
            resp = requests.get(
                f'http://127.0.0.1:{self.web_port}/actuator/health',
                timeout=3
            )
            health = resp.json()
            return {
                'running': True,
                'pid': self.process.pid if self.process else None,
                'health': health,
                'web_port': self.web_port,
                'agent_port': self.agent_port
            }
        except requests.exceptions.RequestException:
            return {
                'running': False,
                'pid': None,
                'health': None
            }
    
    def list_agents(self) -> list:
        """获取已连接的 Agent 列表（过滤用户权限）"""
        try:
            # 注意：官方 Tunnel Server 无鉴权，需要 Python 后端过滤
            resp = requests.get(
                f'http://127.0.0.1:{self.web_port}/actuator/arthas',
                auth=('arthas', self._get_actuator_password()),
                timeout=5
            )
            all_agents = resp.json()
            
            # TODO: 根据用户权限过滤（只返回用户有权限的 Agent）
            # user_namespaces = self._get_user_namespaces(user_id)
            # return [a for a in all_agents if a['appName'].split('-')[0] in user_namespaces]
            return all_agents
        except Exception as e:
            logger.error(f"获取 Agent 列表失败: {e}")
            return []
    
    def _wait_for_ready(self, timeout: int = 30) -> bool:
        """等待 Tunnel Server 就绪"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                resp = requests.get(
                    f'http://127.0.0.1:{self.web_port}/actuator/health',
                    timeout=2
                )
                if resp.status_code == 200:
                    logger.info("Tunnel Server 启动成功")
                    return True
            except:
                pass
            time.sleep(1)
        
        logger.error(f"Tunnel Server 启动超时 ({timeout}s)")
        return False
    
    def _get_actuator_password(self) -> str:
        """从 Tunnel Server 日志中读取 Actuator 密码"""
        # 实际实现：解析日志文件或环境变量
        return current_app.config.get('TUNNEL_ACTUATOR_PASSWORD', 'password')
```

#### 初始化配置

```python
# services/tunnel/__init__.py
"""
Tunnel 模块初始化
需要以下配置（从 Flask app.config 读取）：
- TUNNEL_SERVER_URL: Tunnel Server 地址（默认 http://localhost:8080）
- TUNNEL_AGENT_URL: Agent 接入地址（默认 ws://localhost:7777/ws）
"""

def init_tunnel(app):
    """初始化 Tunnel 模块"""
    from .tunnel_manager import TunnelManager
    
    # 初始化 Tunnel Manager
    tunnel_manager = TunnelManager()
    app.tunnel_manager = tunnel_manager
    
    # 启动时自动启动 Tunnel Server
    if app.config.get('AUTO_START_TUNNEL', True):
        tunnel_manager.start()
    
    return app
```

---

### 7.3 集群内 RBAC 配置（仅用于 Pod 内启动 Arthas）

> **注意**：如果使用方案 D，Tunnel Server 不部署在 K8s 集群内，而是与 k8s-arthas-tool 共部署在同一台机器，则 **不需要** 以下 RBAC 配置。

如果使用 K8s API 在 Pod 内启动 Arthas（可选功能），需要：

```yaml
# deploy/rbac-tunnel.yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: k8s-arthas-tool
  namespace: default
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: k8s-arthas-tool-role
rules:
  # 需要访问 Pod 和 Exec
  - apiGroups: [""]
    resources: ["pods", "pods/log"]
    verbs: ["get", "list", "watch"]
  - apiGroups: [""]
    resources: ["pods/exec"]
    verbs: ["create"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: k8s-arthas-tool-binding
subjects:
  - kind: ServiceAccount
    name: k8s-arthas-tool
    namespace: default
roleRef:
  kind: ClusterRole
  name: k8s-arthas-tool-role
  apiGroup: rbac.authorization.k8s.io
```

**应用配置**：

```bash
kubectl apply -f deploy/rbac-tunnel.yaml
```

---

### 7.4 启动配置检查清单

| 检查项 | 命令/方法 | 期望结果 |
|---|---|---|
| JDK 已安装 | `java -version` | 显示 Java 8+ 版本 |
| Tunnel Server Jar 存在 | `ls -l /opt/arthas/arthas-tunnel-server.jar` | 文件存在 |
| 本地端口可用 | `netstat -tlnp \| grep 8080` | 未监听（或已是我们自己的） |
| Tunnel Server 启动成功 | `curl http://localhost:8080/actuator/health` | `{"status":"UP"}` |
| Python 依赖已安装 | `pip list \| grep requests` | 显示版本 |
| 前端可访问 WebSocket | 浏览器 F12 → Network → WS | 状态码 101 |
| 权限控制生效 | 用普通用户调用 `/api/tunnel/agents` | 只返回有权限的 Agent |

---

## 8. Pod 内 Arthas 连接 Tunnel Server 配置

### 8.1 启动命令

```bash
# 在 Pod 内启动 Arthas，连接到 Tunnel Server
java -jar /opt/arthas/arthas-boot.jar \
  --tunnel-server ws://<tunnel-server-host>:7777/ws \
  --agent-id <connection-id> \
  --app-name <namespace>-<pod-name>
```

### 8.2 通过 K8s API 自动启动（可选）

```python
# services/arthas_launcher.py
class ArthasLauncher:
    """通过 K8s API 在 Pod 内启动 Arthas"""
    
    def __init__(self, k8s_config_path: str = None):
        if k8s_config_path:
            config.load_kube_config(config_file=k8s_config_path)
        else:
            config.load_incluster_config()
        self.api = client.CoreV1Api()
        self.tunnel_server_url = "ws://k8s-arthas-tool:7777/ws"
    
    def launch(self, pod_name: str, namespace: str, connection_id: str):
        """在 Pod 内启动 Arthas 并连接到 Tunnel Server"""
        # 1. 检查 Arthas 是否已启动
        check_cmd = ["ps", "aux", "|", "grep", "arthas-boot"]
        if not self._exec_in_pod(pod_name, namespace, check_cmd):
            # 2. 启动 Arthas
            start_cmd = [
                "java", "-jar", "/opt/arthas/arthas-boot.jar",
                "--tunnel-server", self.tunnel_server_url,
                "--agent-id", connection_id,
                "--app-name", f"{namespace}-{pod_name}",
                "--target-ip", "127.0.0.1",
                "--telnet-port", "3658",
                "--http-port", "8563",
                "&"
            ]
            self._exec_in_pod(pod_name, namespace, start_cmd)
        
        return True
    
    def _exec_in_pod(self, pod_name: str, namespace: str, command: list) -> str:
        """在 Pod 内执行命令"""
        resp = stream(self.api.connect_get_namespaced_pod_exec,
                      pod_name, namespace,
                      command=command,
                      stderr=True, stdin=False, stdout=True, tty=False)
        return resp
```

---

*报告结束*
