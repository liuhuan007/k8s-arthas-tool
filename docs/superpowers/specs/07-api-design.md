# K8s Arthas 智能诊断平台 — API 设计


**文档版本**: v1.0
**创建日期**: 2026-05-23
**状态**: 设计完成

---

## 目录

1. [现有接口（保留）](#1-现有接口保留)
2. [诊断中心 API](#2-诊断中心-api)
3. [异常检测 API](#3-异常检测-api)
4. [知识库 API](#4-知识库-api)
5. [连接中心 API](#5-连接中心-api)
6. [工具箱 API](#6-工具箱-api)
7. [外部链接 API](#7-外部链接-api)
8. [WebSocket 演进](#8-websocket-演进)

---

## 1. 现有接口（保留）

| 域 | 典型接口 |
|----|---------|
| 健康检查 | `GET /api/health` |
| 集群 | `/api/clusters/*` |
| Arthas | `/api/arthas/connect`、`/api/arthas/exec` |
| 采样 | `/api/profile/start`、`/api/profile/<task_id>` |
| 监控 | `/api/monitor/*` |
| Pod | `/api/pod/exec`、`/api/pod/files*` |
| 管理 | `/api/auth/*`、`/api/users/*`、`/api/audit/*` |

---

## 2. 诊断中心 API

> **API命名统一**：面向产品统一叫"诊断能力"，API统一使用 `/api/diagnosis/capabilities`。

### 2.1 能力目录查询

```
GET /api/diagnosis/capabilities?type=arthas_command&category=tool&level=2
```

**响应示例**：
```json
{
  "capabilities": [
    {
      "id": 1,
      "name": "JVM Dashboard",
      "category": "quick",
      "level": 1,
      "description": "查看 JVM 运行概况",
      "risk_level": "low",
      "estimated_duration": 5
    }
  ]
}
```

### 2.2 即时执行诊断能力

```
POST /api/diagnosis/capabilities/{capability_id}/execute
```

**请求体**：
```json
{
  "connection_id": "cluster/default/pod/arthas",
  "params": {
    "class": "com.example.OrderService",
    "method": "createOrder"
  },
  "source": "manual|anomaly|ai-chat|mcp"
}
```

**响应示例**：
```json
{
  "ok": true,
  "run_id": "uuid-xxx",
  "execution_id": "exec-xxx"
}
```

### 2.3 查询运行状态（轮询）

```
GET /api/diagnosis/runs/{run_id}/status
```

**响应示例**：
```json
{
  "run_id": "uuid-xxx",
  "status": "running",
  "progress": 0.6,
  "current_step": 2,
  "total_steps": 5,
  "last_output": "..."
}
```

> **P0轮询策略**：前端每2秒轮询此接口获取执行状态。

### 2.4 取消运行

```
POST /api/diagnosis/runs/{run_id}/cancel
```

### 2.5 查询执行状态（前端轮询）

```
GET /api/diagnosis/executions/{execution_id}/status
```

**响应示例**：
```json
{
  "status": "running",
  "progress": 0.6,
  "current_step": 2,
  "total_steps": 4,
  "output": "..."
}
```

---

## 3. 异常检测 API

### 3.1 查询异常事件

```
GET /api/diagnosis/anomalies?pod_id=xxx&status=open
```

### 3.2 确认异常

```
POST /api/diagnosis/anomalies/{id}/acknowledge
```

### 3.3 忽略异常

```
POST /api/diagnosis/anomalies/{id}/ignore
```

### 3.4 触发诊断

```
POST /api/diagnosis/anomalies/{id}/diagnose
```

### 3.5 执行根因分析

```
POST /api/diagnosis/rca
```

### 3.6 查询分析结果

```
GET /api/diagnosis/rca/{diagnosis_id}
```

---

## 4. 知识库 API

### 4.1 查询相似案例

```
GET /api/diagnosis/cases/similar?symptoms=high_cpu,slow_api&top_k=5
```

### 4.2 创建案例

```
POST /api/diagnosis/cases
```

### 4.3 验证案例

```
POST /api/diagnosis/cases/{id}/verify
```

### 4.4 生成诊断报告

```
POST /api/diagnosis/reports/generate
```

### 4.5 下载报告

```
GET /api/diagnosis/reports/{id}/download
```

---

## 5. 连接中心 API

### 5.1 主动探活

```
POST /api/arthas/connections/{id}/ping
```

### 5.2 查询可用连接

```
GET /api/arthas/connections?status=ready&level=arthas
```

---

## 6. 工具箱 API

### 6.1 工具包管理

```
GET  /api/tools/packages                   # 工具包列表
GET  /api/tools/packages/{id}              # 工具包详情
POST /api/tools/packages/sync              # 同步官方源
```

### 6.2 Arthas JAR 分发

```
POST /api/tools/arthas/install             # 分发 JAR 到 Pod
POST /api/tools/arthas/bootstrap           # 兜底启动
```

### 6.3 Tunnel Server

```
POST /api/tools/tunnel-server/start        # 启动 Tunnel Server
GET  /api/tools/tunnel-server/status       # 查询状态
POST /api/tools/tunnel-server/stop         # 停止
```

### 6.4 在线修复

```
POST /api/hotfix/jad                       # 一键查看源码
POST /api/hotfix/upload                    # 上传 .java/.class
POST /api/hotfix/compile                   # mc 编译
POST /api/hotfix/redefine                  # redefine 生效
GET  /api/hotfix/artifacts                 # 查看产物
```

---

## 7. 外部链接 API

```
GET  /api/external-menu/groups             # 查询启用的外部链接菜单
POST /api/admin/external-menu/links        # 管理员新增链接
PUT  /api/admin/external-menu/links/{id}   # 管理员编辑链接
DELETE /api/admin/external-menu/links/{id} # 管理员删除链接
POST /api/admin/external-menu/links/{id}/toggle  # 启停
```

---

## 8. WebSocket 演进（P2 目标态）

> **注意**：WebSocket 作为 P2 目标态，P0 阶段统一使用 HTTP 轮询。

**P2 目标态设计**（后续迭代）：

```
/ws/arthas/session/{session_id}    Arthas 长命令输出
/ws/profile/tasks/{task_id}        采样任务日志
/ws/pod/terminal/{session_id}      Pod 终端交互
/ws/diagnosis/stream/{run_id}      诊断执行实时输出
```

**降级策略**：浏览器不支持 WebSocket 时回退到 HTTP 轮询。

**P0 轮询接口**：

| 场景 | 接口 | 间隔 |
|------|------|------|
| 诊断执行状态 | `GET /api/diagnosis/runs/{run_id}/status` | 2秒 |
| 任务执行状态 | `GET /api/tasks/{task_id}/status` | 3秒 |
| 连接健康检查 | `GET /api/arthas/connections/{id}/health` | 30秒 |

---

**文档结束**