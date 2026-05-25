# API 设计实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 实现 API 设计，包括诊断中心 API、异常检测 API、知识库 API、连接中心 API、工具箱 API、外部链接 API 等。

**Architecture:** API 层作为前端与后端的桥梁，提供 RESTful 接口，支持 JSON 格式数据交换。采用 Flask Blueprint 组织路由，支持版本控制和中间件。

**Tech Stack:** Python, Flask, RESTful API, JSON

---

## 1. 目标

实现 API 设计，包括诊断中心 API、异常检测 API、知识库 API、连接中心 API、工具箱 API、外部链接 API 等。

## 2. 架构

API 层作为前端与后端的桥梁，提供 RESTful 接口，支持 JSON 格式数据交换。采用 Flask Blueprint 组织路由，支持版本控制和中间件。

## 3. API 清单

### 3.1 现有接口（保留）

| 域 | 典型接口 | 说明 |
|----|---------|------|
| 健康检查 | `GET /api/health` | 系统健康状态 |
| 集群 | `/api/clusters/*` | 集群管理 |
| Arthas | `/api/arthas/connect`、`/api/arthas/exec` | Arthas 连接和执行 |
| 采样 | `/api/profile/start`、`/api/profile/<task_id>` | 性能采样 |
| 监控 | `/api/monitor/*` | Pod 监控 |
| Pod | `/api/pod/exec`、`/api/pod/files*` | Pod 操作 |
| 管理 | `/api/auth/*`、`/api/users/*`、`/api/audit/*` | 认证授权审计 |

### 3.2 新增接口

#### 3.2.1 诊断中心 API

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/diagnosis/capabilities` | 能力目录查询 |
| `POST` | `/api/diagnosis/capabilities/{id}/execute` | 即时执行诊断能力 |
| `GET` | `/api/diagnosis/runs/{run_id}/status` | 查询运行状态 |
| `POST` | `/api/diagnosis/runs/{run_id}/cancel` | 取消运行 |

#### 3.2.2 异常检测 API

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/diagnosis/anomalies` | 查询异常事件 |
| `POST` | `/api/diagnosis/anomalies/{id}/acknowledge` | 确认异常 |
| `POST` | `/api/diagnosis/anomalies/{id}/ignore` | 忽略异常 |
| `POST` | `/api/diagnosis/anomalies/{id}/diagnose` | 触发诊断 |
| `POST` | `/api/diagnosis/rca` | 执行根因分析 |
| `GET` | `/api/diagnosis/rca/{diagnosis_id}` | 查询分析结果 |

#### 3.2.3 知识库 API

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/diagnosis/cases/similar` | 查询相似案例 |
| `POST` | `/api/diagnosis/cases` | 创建案例 |
| `POST` | `/api/diagnosis/cases/{id}/verify` | 验证案例 |
| `POST` | `/api/diagnosis/reports/generate` | 生成诊断报告 |
| `GET` | `/api/diagnosis/reports/{id}/download` | 下载报告 |

#### 3.2.4 连接中心 API

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/arthas/connections/{id}/ping` | 主动探活 |
| `GET` | `/api/arthas/connections` | 查询可用连接 |

#### 3.2.5 工具箱 API

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/tools/packages` | 工具包列表 |
| `GET` | `/api/tools/packages/{id}` | 工具包详情 |
| `POST` | `/api/tools/packages/sync` | 同步官方源 |
| `POST` | `/api/tools/arthas/install` | 分发 JAR 到 Pod |
| `POST` | `/api/tools/arthas/bootstrap` | 兜底启动 |
| `POST` | `/api/tools/tunnel-server/start` | 启动 Tunnel Server |
| `GET` | `/api/tools/tunnel-server/status` | 查询状态 |
| `POST` | `/api/tools/tunnel-server/stop` | 停止 |

#### 3.2.6 在线修复 API

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/hotfix/jad` | 一键查看源码 |
| `POST` | `/api/hotfix/upload` | 上传 .java/.class |
| `POST` | `/api/hotfix/compile` | mc 编译 |
| `POST` | `/api/hotfix/redefine` | redefine 生效 |
| `GET` | `/api/hotfix/artifacts` | 查看产物 |

#### 3.2.7 外部链接 API

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/external-menu/groups` | 查询启用的外部链接菜单 |
| `POST` | `/api/admin/external-menu/links` | 管理员新增链接 |
| `PUT` | `/api/admin/external-menu/links/{id}` | 管理员编辑链接 |
| `DELETE` | `/api/admin/external-menu/links/{id}` | 管理员删除链接 |
| `POST` | `/api/admin/external-menu/links/{id}/toggle` | 启停 |

## 4. 接口详细设计

### 4.1 诊断中心 API 详细设计

#### 4.1.1 能力目录查询

**请求：**
```
GET /api/diagnosis/capabilities?type=arthas_command&category=tool&level=2
```

**响应：**
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

#### 4.1.2 即时执行诊断能力

**请求：**
```
POST /api/diagnosis/capabilities/{capability_id}/execute
Content-Type: application/json

{
  "connection_id": "cluster/default/pod/arthas",
  "params": {
    "class": "com.example.OrderService",
    "method": "createOrder"
  },
  "source": "manual|anomaly|ai-chat|mcp"
}
```

**响应：**
```json
{
  "ok": true,
  "run_id": "uuid-xxx",
  "execution_id": "exec-xxx"
}
```

#### 4.1.3 查询运行状态

**请求：**
```
GET /api/diagnosis/runs/{run_id}/status
```

**响应：**
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

#### 4.1.4 取消运行

**请求：**
```
POST /api/diagnosis/runs/{run_id}/cancel
```

**响应：**
```json
{
  "ok": true,
  "message": "运行已取消"
}
```

### 4.2 异常检测 API 详细设计

#### 4.2.1 查询异常事件

**请求：**
```
GET /api/diagnosis/anomalies?pod_id=xxx&status=open
```

**响应：**
```json
{
  "anomalies": [
    {
      "id": 1,
      "pod_id": "xxx",
      "type": "cpu_high",
      "severity": "high",
      "status": "open",
      "created_at": "2026-05-24T10:00:00Z"
    }
  ]
}
```

#### 4.2.2 确认异常

**请求：**
```
POST /api/diagnosis/anomalies/{id}/acknowledge
```

**响应：**
```json
{
  "ok": true,
  "message": "异常已确认"
}
```

### 4.3 知识库 API 详细设计

#### 4.3.1 查询相似案例

**请求：**
```
GET /api/diagnosis/cases/similar?symptoms=high_cpu,slow_api&top_k=5
```

**响应：**
```json
{
  "cases": [
    {
      "id": 1,
      "title": "CPU 飙高排查",
      "symptoms": ["high_cpu"],
      "solution": "使用 thread 命令查看线程状态",
      "similarity": 0.85
    }
  ]
}
```

### 4.4 工具箱 API 详细设计

#### 4.4.1 工具包列表

**请求：**
```
GET /api/tools/packages
```

**响应：**
```json
{
  "packages": [
    {
      "id": 1,
      "name": "arthas-boot",
      "version": "3.7.0",
      "tool_type": "arthas",
      "status": "active"
    }
  ]
}
```

## 5. 错误处理

### 5.1 错误响应格式

```json
{
  "ok": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "参数校验失败",
    "details": {
      "field": "connection_id",
      "reason": "连接不存在"
    }
  }
}
```

### 5.2 错误码定义

| 错误码 | HTTP 状态码 | 说明 |
|--------|------------|------|
| `VALIDATION_ERROR` | 400 | 参数校验失败 |
| `UNAUTHORIZED` | 401 | 未授权 |
| `FORBIDDEN` | 403 | 禁止访问 |
| `NOT_FOUND` | 404 | 资源不存在 |
| `CONFLICT` | 409 | 资源冲突 |
| `INTERNAL_ERROR` | 500 | 内部错误 |

## 6. 任务分解

### 任务 1：实现诊断中心 API

**文件：**
- 创建：`api/diagnosis.py`
- 修改：`server.py`

**步骤：**
1. 创建诊断中心 Blueprint
2. 实现能力目录查询接口
3. 实现即时执行接口
4. 实现运行状态查询接口
5. 实现取消运行接口
6. 编写单元测试

### 任务 2：实现异常检测 API

**文件：**
- 创建：`api/anomaly.py`
- 修改：`server.py`

**步骤：**
1. 创建异常检测 Blueprint
2. 实现异常事件查询接口
3. 实现确认异常接口
4. 实现忽略异常接口
5. 实现触发诊断接口
6. 实现根因分析接口
7. 编写单元测试

### 任务 3：实现知识库 API

**文件：**
- 创建：`api/knowledge.py`
- 修改：`server.py`

**步骤：**
1. 创建知识库 Blueprint
2. 实现相似案例查询接口
3. 实现创建案例接口
4. 实现验证案例接口
5. 实现生成报告接口
6. 实现下载报告接口
7. 编写单元测试

### 任务 4：实现连接中心 API

**文件：**
- 修改：`api/arthas.py`
- 修改：`server.py`

**步骤：**
1. 实现主动探活接口
2. 实现查询可用连接接口
3. 编写单元测试

### 任务 5：实现工具箱 API

**文件：**
- 创建：`api/tools.py`
- 修改：`server.py`

**步骤：**
1. 创建工具箱 Blueprint
2. 实现工具包管理接口
3. 实现 Arthas JAR 分发接口
4. 实现 Tunnel Server 接口
5. 编写单元测试

### 任务 6：实现在线修复 API

**文件：**
- 创建：`api/hotfix.py`
- 修改：`server.py`

**步骤：**
1. 创建在线修复 Blueprint
2. 实现 jad 接口
3. 实现上传接口
4. 实现编译接口
5. 实现 redefine 接口
6. 实现产物查询接口
7. 编写单元测试

### 任务 7：实现外部链接 API

**文件：**
- 创建：`api/external_menu.py`
- 修改：`server.py`

**步骤：**
1. 创建外部链接 Blueprint
2. 实现查询接口
3. 实现管理接口
4. 编写单元测试

### 任务 8：实现错误处理

**文件：**
- 创建：`api/errors.py`
- 修改：`server.py`

**步骤：**
1. 定义错误码
2. 实现错误响应格式
3. 实现全局错误处理器
4. 编写单元测试

## 7. 验收标准

- [ ] 诊断中心 API 实现完成
- [ ] 异常检测 API 实现完成
- [ ] 知识库 API 实现完成
- [ ] 连接中心 API 实现完成
- [ ] 工具箱 API 实现完成
- [ ] 在线修复 API 实现完成
- [ ] 外部链接 API 实现完成
- [ ] 错误处理实现完成
- [ ] 单元测试覆盖率 > 80%
- [ ] API 文档完整

## 8. 风险与缓解措施

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 接口设计不合理 | 中 | 代码审查，用户反馈 |
| 性能问题 | 中 | 性能测试，优化查询 |
| 安全漏洞 | 高 | 安全审查，渗透测试 |
| 兼容性问题 | 中 | 版本控制，向后兼容 |

## 9. 后续演进

### P1 阶段

- 实现 WebSocket 实时推送
- 实现 API 版本控制
- 实现 API 限流

### P2 阶段

- 实现 GraphQL 接口
- 实现 gRPC 接口
- 实现 API 网关
