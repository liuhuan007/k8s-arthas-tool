# Tunnel Server vs Port-Forward 架构冲突分析与解决方案
# (Tunnel 方案仅为对比分析，未采纳，不落地)

> 解决 k8s-arthas-tool 项目中两套 Arthas 连接通道方案的架构冲突
> 
> **文档状态**: [对比分析] Tunnel 方案未采纳，不混入主架构
> **P0 采用方案**: Port-Forward 模式（简单直接，无额外依赖）
> **最后更新**: 2026-05-28

---

## 1. 冲突背景

当前 `02-connection-center.md` 中，Arthas 连接建立依赖 `kubectl port-forward` 本地进程，但项目同时存在 **Tunnel Server**（WebSocket 隧道代理）的设计意图，导致两套通道方案职责重叠、状态机冲突。

```
方案A: kubectl port-forward (P0 已采纳)
+-- 依赖本地进程管理（subprocess）
+-- 端口分配/释放需手动控制
+-- 服务重启后 port-forward 丢失
+-- 多标签页共享同一端口转发（需 BroadcastChannel 同步）

方案B: Tunnel Server (WebSocket 隧道) [对比方案，未采纳]
+-- 不依赖 kubectl port-forward
+-- 通过 WebSocket 转发 Arthas HTTP API
+-- 服务重启后可恢复隧道
+-- 天然支持多客户端共享同一 Tunnel 连接

冲突：连接状态机只覆盖方案A，方案B 无对应状态节点
```

**P0 最终选择（2026-05-27）**：**方案 A — kubectl port-forward（Port-Forward 模式）**

> [WARN] Tunnel 方案（方案 B/D）仅为对比分析，暂不落地。
> 原因：引入 JDK 依赖，增加运维复杂度；当前 P0 阶段 Pod 网络可达，无需 Tunnel。

---

## 2. 冲突明细（对比分析）

| 冲突点 | Port-Forward 方案 (P0) | Tunnel Server 方案（官方）[对比] | 影响 |
|--------|-------------------|-------------------|------|
| **连接建立** | 启动本地 `kubectl` 进程 | 启动官方 Tunnel Server Jar | 状态机需同时支持两种路径 |
| **端口管理** | 需分配/释放本地端口 | 不需要本地端口 | `connections.port_forward_port` 字段对 Tunnel 方案无意义 |
| **服务重启恢复** | 需重建 port-forward 进程 | 可恢复 WebSocket 连接 | 恢复逻辑不统一 |
| **多标签页同步** | BroadcastChannel 同步端口状态 | WebSocket 天然支持多客户端 | 同步机制冲突 |
| **权限控制** | 依赖 K8s RBAC | **官方 Tunnel 无权限管理**，需 Python 后端代理鉴权 | 需额外设计权限层 |

---

## 3. Tunnel 方案对比分析（未采纳）

> 本节仅为 Tunnel 方案的优缺点对比，不代表采纳。
> 当前 P0 架构使用 **Port-Forward 模式**。

### 3.1 各 Tunnel 方案对比

#### 方案 D：官方 Tunnel Server + Python 进程管理 [对比方案，未采纳]

| 优点 | 缺点 |
|------|------|
| [OK] **使用官方 Tunnel Server，协议兼容性有保障** | [FAIL] 需要 JDK 环境（机器上安装 JDK） |
| [OK] **Python 后端统一鉴权**，解决官方 Tunnel 无权限管理的问题 | [FAIL] Tunnel Server 与 k8s-arthas-tool 竞争 CPU/内存 |
| [OK] **简化网络**：本地访问，无需 K8s Port-Forward 或外部负载均衡 | [FAIL] 单点故障：Tunnel Server 挂了影响 k8s-arthas-tool（可缓解：健康检查 + 自动重启） |
| [OK] **低延迟**：本地 HTTP 调用，延迟 <1ms | [FAIL] 日志混合：两个服务的日志混在一起（可缓解：配置不同日志路径） |
| [OK] **无 SPDY 处理复杂度**：使用官方 Tunnel Server | |
| [OK] **无 kubectl / K8s SDK 依赖** | |
| [OK] **官方文档支持**，社区验证 | |
| [OK] **部署简单**：共部署，一个 Pod 管理两个容器 | |

#### 方案 C：K8s Port-Forward API（Python SDK）[对比方案，未采纳]

| 优点 | 缺点 |
|------|------|
| [OK] 无 Pod 侵入 | [WARN] Python SPDY 流处理较复杂（需 `websocket-client` 库） |
| [OK] 不需要本地端口管理 | [WARN] K8s Python SDK 的 port-forward 示例较少 |
| [OK] 无 kubectl 子进程依赖 | [FAIL] **需要自研与官方 Arthas Agent 的 WebSocket 协议对接（风险高）** |
| [OK] 服务重启后可编程恢复（有 API） | |
| [OK] 天然支持多客户端（Flask 统一管理） | |

### 3.2 官方安全警告与应对（Tunnel 方案风险）

> 官方文档明确说明：**"强烈建议不要将 Tunnel Server 直接暴露到公网"**

| 风险 | 官方说明 | Tunnel 方案应对措施（如采纳） |
|------|---------|---------|
| 无内置认证/授权 | "当前版本未内置完善的权限管理能力" | [OK] Python 后端统一鉴权，用户只能访问自己的 Pod |
| 管理页面无访问限制 | "管理页面无任何访问限制" | [OK] 关闭管理页面（`arthas.enable-detail-pages=false`） |
| Agent 无权限隔离 | 无细粒度权限控制 | [OK] Python 后端过滤 `/actuator/arthas` 返回结果 |

### 3.3 Tunnel 方案未采纳原因

| 原因 | 说明 |
|------|------|
| 引入 JDK 依赖 | 机器需安装 JDK，增加运维复杂度 |
| 进程管理复杂度 | Python 需管理 Java 子进程生命周期 |
| 资源竞争 | Tunnel Server 与 k8s-arthas-tool 竞争 CPU/内存 |
| 官方安全警告 | Tunnel Server 无内置权限管理，需额外加固 |
| 当前无跨网络需求 | P0 阶段 Pod 网络可达，无需 Tunnel |

### 3.4 未来何时考虑采纳 Tunnel 方案

- 生产环境有网络隔离，Pod 无法访问外部
- 需要支持跨网络诊断（防火墙后）
- 团队有能力维护 JDK + Python 混合部署

---

## 4. P0 采用方案：Port-Forward 模式

> 本节描述当前已采纳的 P0 方案（Port-Forward 模式）。

### 4.1 最终架构（Port-Forward 模式）

```
+-----------------------------+
|  Browser (前端)             |
|  WebSocket 连接到后端        |
+-------------+--------------+
              |
              | WebSocket
              v
+-------------+--------------+
|  k8s-arthas-tool (Python) |
|  - 启动 kubectl port-forward |
|  - 管理本地端口分配          |
|  - 代理 WebSocket 到 Pod    |
+-------------+--------------+
              |
              | kubectl port-forward (SPDY)
              v
+-------------+--------------+
|  K8s API Server             |
|  - portforward 子资源        |
+-------------+--------------+
              |
              | K8s 内部网络
              v
+-------------+--------------+
|  Pod (目标 JVM)             |
|  - Arthas HTTP :3658        |
+-----------------------------+
```

### 4.2 Port-Forward 模式决策理由（P0 采纳）

| 理由 | 说明 |
|------|------|
| **简单直接** | 无需额外部署，使用 K8s 原生能力 |
| **无额外依赖** | 只需要 kubectl + K8s RBAC，无需 JDK |
| **适合快速交付** | P0 阶段优先交付，Tunnel 作为后续优化 |
| **社区验证** | kubectl port-forward 是 K8s 标准能力 |

### 4.3 实施计划（Port-Forward 模式，P0）

| 阶段 | 内容 | 工期 | 产出 |
|------|------|------|------|
| **Phase 1** | 实现 `K8sPortForward` 类（Python SDK） | 1 天 | `services/k8s_portforward.py` |
| **Phase 2** | 修改连接状态机（增加 PortForward 状态） | 1 天 | `models/connection.py` |
| **Phase 3** | 实现前端连接管理（WebSocket 代理） | 1 天 | `static/js/components/connection-manager.js` |
| **Phase 4** | 测试与优化 | 1 天 | 测试报告 |

---

## 5. 决策记录

| 字段 | 内容 |
|------|------|
| **P0 决策** | 采用方案 A：kubectl port-forward（Port-Forward 模式） |
| **对比方案** | 方案 B（Sidecar）、方案 C（K8s API）、方案 D（官方 Tunnel） |
| **决策者** | 架构评审组 |
| **决策时间** | 2026-05-27 |
| **Tunnel 方案状态** | [对比分析] 未采纳，仅作技术对比 |

---

## 6. 后续行动（仅 Port-Forward 方案）

- [x] 完成方案对比报告（v2.0）
- [x] 确认 P0 采用方案 A（Port-Forward 模式）
- [ ] 实现 `services/k8s_portforward.py`（K8s Port-Forward API 封装）
- [ ] 更新 `02-connection-center.md`（明确 Port-Forward 为 P0 方案）
- [ ] Tunnel 方案（方案 D）留作对比参考，暂不落地
- [ ] 更新 `review/architecture-review.md` 同步评审结果

---

## 7. 附录：Tunnel 方案技术细节（对比参考）

> 本节仅为 Tunnel 方案的技术细节记录，不实施。

### 7.1 官方 Tunnel Server 部署模式（对比）

| 模式 | 说明 | 适用场景 | 状态 |
|------|------|---------|------|
| 本地模式 | 单机启动 Tunnel Server | 开发测试 | 对比 |
| 共部署模式 | 与 k8s-arthas-tool 共部署，Python 管理进程 | 复杂网络环境 | **对比（未落地）** |
| K8s 集群内部署 | 部署到 K8s 内，通过 K8s API | 生产环境 | 对比 |

**对比报告**：`docs/reports/tunnel-solution-comparison.md`（方案 D）

**当前架构使用**：Port-Forward 模式（简单直接，无额外依赖）

### 7.2 Tunnel Server 连接条件（对比）

| 条件 | 说明 | 是否必须 |
|------|------|---------|
| JDK 环境 | 服务器上安装 JDK | [FAIL] 必须（如采纳 Tunnel） |
| 官方 Tunnel Server Jar | 下载 `arthas-tunnel-server.jar` | [FAIL] 必须（如采纳 Tunnel） |
| Python `requests` 库 | 调用 Tunnel Server HTTP API | [FAIL] 必须（如采纳 Tunnel） |
| Python `subprocess`（标准库） | 管理 Tunnel Server 进程 | [FAIL] 必须（如采纳 Tunnel） |

> **关键**：k8s-arthas-tool 是 Python 应用，**不需要 pom.xml 依赖**。与 Tunnel Server 通过 HTTP API 交互。

### 7.3 Client 端配置与依赖说明（对比）

#### 前端（JavaScript）客户端 [对比]

| 配置项 | 说明 | 默认值 |
|------|------|---------|
| `TUNNEL_WS_URL` | Tunnel Server WebSocket 地址 | `wss://{host}/tunnel/ws/{connection_id}` |
| `CONNECTION_ID` | 连接标识符（从后端获取） | 无默认值，必须 |
| `HEARTBEAT_INTERVAL` | WebSocket 心跳间隔（毫秒） | `30000` |
| `RECONNECT_INTERVAL` | 断线重连间隔（毫秒） | `3000` |
| `REQ_TIMEOUT` | 请求超时（毫秒） | `30000` |

**依赖包**：
- 原生 WebSocket，无需额外依赖
- 可选：`reconnecting-websocket`（自动重连）

#### 后端（Python）Tunnel Server 依赖 [对比]

```
# requirements.txt (仅当采纳 Tunnel 方案时需要)
requests>=2.31.0              # 调用 Tunnel Server HTTP API
psutil>=5.9.0                 # 可选：进程管理
```

**没有 Java 依赖！**

#### 集群内 RBAC 配置（如采纳 K8s 内部署模式）[对比]

```yaml
# deploy/rbac-tunnel.yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: k8s-arthas-tunnel
rules:
  - resources: ["pods/portforward"]
    verbs: ["create"]
  - resources: ["pods"]
    verbs: ["get", "list", "watch"]
```

> **注意**：如果使用共部署模式（Tunnel Server 不部署在 K8s 集群内），则 **不需要** 以上 RBAC 配置。

---

[END] Tunnel 方案仅为对比分析，不混入主架构。P0 采用 Port-Forward 模式。
