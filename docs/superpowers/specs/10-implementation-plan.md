# K8s Arthas 智能诊断平台 — 实施计划与路线图


**文档版本**: v1.0
**创建日期**: 2026-05-23
**状态**: 设计完成

---

## 目录

1. [现有架构迁移方案](#1-现有架构迁移方案)
2. [实施规划](#2-实施规划)
3. [风险与成功指标](#3-风险与成功指标)
4. [架构决策记录](#4-架构决策记录)
5. [诊断能力清单示例](#5-诊断能力清单示例)

---

## 1. 现有架构迁移方案

### 1.1 迁移原则

```
保留核心逻辑，重构组织方式
├── 性能诊断逻辑 → 注册为 AI 诊断能力（Level 4）
├── AI 工具函数 → 复用诊断能力执行引擎
├── MCP 工具 → 转发到诊断能力平台
└── 规则引擎 → 增强后供 v2.0 使用
```

### 1.2 需改造模块

| 模块 | 文件 | 问题 | 改造方式 |
|------|------|------|---------|
| 性能诊断 | `api/performance_diagnose.py` | 硬编码流程 | 注册为 AI 诊断能力 |
| AI 对话 | `api/ai_chat.py` | 工具定义分散 | 统一到 diagnosis_capabilities |
| MCP 代理 | `api/mcp_proxy.py` | 重复实现诊断逻辑 | 转发到诊断能力平台 |
| 规则引擎 | `backend/core/rule_engine.py` | 仅支持基础阈值 | 增强支持复杂规则 |

### 1.3 迁移路径

```
Phase 0（1 周）：准备
  ├─ 创建 v2.0 数据库表
  ├─ 搭建新架构框架
  └─ 编写迁移测试

Phase 1（2 周）：性能诊断迁移
  ├─ 将 _run_diagnosis() 注册为能力
  ├─ 定义 parameters_schema
  └─ 测试新旧接口并行

Phase 2（2 周）：AI 工具整合
  ├─ 迁移 ai_chat.py 工具函数
  ├─ 统一工具定义到 diagnosis_capabilities
  └─ 删除重复代码

Phase 3（1 周）：MCP 工具适配
  ├─ mcp_proxy.py 转发到诊断能力平台
  └─ 删除重复实现

Phase 4（1 周）：规则引擎增强
  ├─ 支持复杂规则
  ├─ 集成异常检测引擎
  └─ 性能优化

Phase 5（1 周）：下线旧接口
  ├─ 前端切换到新架构
  ├─ 旧接口标记 deprecated
  └─ 完全移除旧代码
```

### 1.4 回滚方案

- 迁移前备份 `arthas.db` 到 `arthas.db.bak-{yyyyMMddHHmmss}`
- 恢复旧 API 路由
- 禁用新能力：`UPDATE diagnosis_capabilities SET enabled = 0`
- `git revert <migration_commit>`

---

## 2. 实施规划

### 2.1 P0 收敛范围

P0 交付"可用、可审计、可解释"的手动/半自动诊断闭环，**包含Agent SDK集成**：

| 能力 | P0 范围 | 推迟内容 |
|------|---------|---------|
| **诊断入口** | 统一菜单、能力卡片、参数表单、连接选择器 | 能力市场、拖拽编排 |
| **执行记录** | 复用 task_logs + step_logs，固化连接快照 | 新建独立日志体系 |
| **AI 分析** | 对已有诊断结果做摘要和建议 | 自动执行高危命令 |
| **Agent SDK** | Agent抽象接口、多SDK适配、Agent Tool Gateway | Agent自主诊断、多Agent协作 |
| **Skill系统** | Skill Registry、Workflow Engine、Skill管理 | Skill版本管理、回滚 |
| **异常感知** | 支持人工从指标触发诊断 | 持续巡检和自动触发 |
| **知识沉淀** | 手动归档案例 | 自动学习和置信度更新 |

### 2.2 分阶段实施

| 阶段 | 模块 | 工期 | 核心交付 |
|------|------|------|---------|
| Phase 0 | 数据库迁移 + 框架搭建 | 1 周 | 统一 task_logs/step_logs、诊断能力表、预制数据 |
| Phase 1 | Skill系统（P0） | 2 周 | Skill Registry + Workflow Engine + Skill管理 |
| Phase 2 | 诊断能力（后端） | 2 周 | 能力框架 + 统一执行器 + 连接选择器 |
| Phase 3 | Agent SDK集成（P0） | 2 周 | Agent抽象接口 + Agent Tool Gateway + 多SDK适配 |
| Phase 4 | 诊断能力（前端） | 2 周 | 能力卡片 + 参数表单 + 执行记录 |
| Phase 5 | 连接中心增强 | 2 周 | 连接详情页 + 健康检查 + TTL 清理 |
| Phase 6 | 异常检测 + 简单告警 | 2 周 | 阈值检测 + 告警卡片 |
| Phase 7 | 现有模块迁移 | 2 周 | 性能诊断/AI 工具/MCP 转发到能力平台 |
| Phase 8 | AI 辅助分析 | 2 周 | LLM 集成 + 降级策略 + 诊断报告 |
| Phase 9 | 知识沉淀 | 2 周 | 案例库 + 匹配算法 + 反馈学习 |

**总计**：约 20 周（~5 个月）

### 2.3 P0核心交付清单

| 模块 | P0交付 | 验收标准 |
|------|--------|---------|
| **Skill Registry** | 导入、校验、发布 | 能够导入Skill并发布到capabilities |
| **Workflow Engine** | DSL步骤执行 | 能够执行Skill的DSL步骤 |
| **Agent Tool Gateway** | 受控工具暴露 | Agent只能调用白名单工具 |
| **Agent SDK集成** | 多SDK适配、自动降级 | 支持CodeBuddy/Fallback切换 |
| **诊断能力** | 能力卡片、参数表单 | 用户可以选择能力并执行 |
| **执行记录** | task_logs + step_logs | 完整的执行日志记录 |

### 2.3 迁移验证清单

**功能验证**：
- [ ] 诊断能力 API 正常工作
- [ ] AI 对话工具调用正常
- [ ] MCP 工具调用正常
- [ ] 异常检测引擎正常触发
- [ ] 根因分析生成正确报告
- [ ] 相似案例推荐准确

**兼容性验证**：
- [ ] 旧 API 仍可访问（标记 deprecated）
- [ ] 前端无缝切换到新能力卡片
- [ ] 历史诊断数据可查询

**性能验证**：
- [ ] 诊断执行耗时 < 30s
- [ ] 异常检测延迟 < 1min
- [ ] LLM 调用超时处理正常

---

## 3. 风险与成功指标

### 3.1 风险评估

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|---------|
| LLM 输出不稳定 | 高 | 中 | 低温度 + JSON Schema + 后处理验证 |
| 误报率高 | 中 | 高 | 基线学习 + 持续时间检测 + 用户反馈 |
| 案例库冷启动 | 中 | 高 | 预制案例 + 手动导入历史数据 |
| 数据模型冲突 | 高 | 中 | 统一 task_logs + 迁移脚本幂等 |
| 连接状态隔离 | 中 | 中 | ConnectionStateManager 仅编排状态 |

### 3.2 成功指标

| 指标 | 目标 | 测量方式 |
|------|------|---------|
| 异常检测准确率 | > 85% | 误报率/漏报率统计 |
| 根因定位准确率 | > 80% | 用户验证反馈 |
| 诊断耗时 | < 30s | 执行日志统计 |
| 案例复用率 | > 30% | 案例匹配成功次数 |
| 用户满意度 | > 4.0/5.0 | 用户评分 |

---

## 4. 架构决策记录

| 决策点 | 决策 | 来源 | 理由 |
|--------|------|------|------|
| 执行记录模型 | 统一为 task_logs | 架构评审改进 | 避免双表并存，统一查询 |
| 场景方案执行 | HTTP 轮询（非 WebSocket） | 架构评审改进 | 当前无 WebSocket 基础设施 |
| AI 处理器安全 | 数据库驱动注册表 | 架构评审改进 | 新增能力无需改代码 |
| 前端状态管理 | DiagnosisContext | 架构评审改进 | 管理共享状态，连接切换取消执行 |
| 步骤数据传递 | 解析引擎支持 ${stepN.field} | 架构评审改进 | 明确步骤间引用机制 |
| 连接层级 | Pod 连接 / Arthas 连接分层 | 系统设计 | 避免 Pod 运维被迫启动 Arthas |
| 连接管理 | 独立一级模块 | 连接交互重构 | 解耦侧栏，列表→详情→工作页 |
| 菜单架构 | 连接中心 + 诊断中心 + 任务中心 + 工具箱 | 诊断中心 v2.0 | 统一入口，管理和使用分离 |
| 定时任务限制 | 不支持 Arthas 连接模式 | 任务中心重构 | port-forward 依赖用户在线 |

---

## 5. 诊断能力清单示例

### 5.1 快捷工具（Level 1，5 个）

| 名称 | 命令 | 风险 |
|------|------|------|
| JVM Dashboard | `dashboard -n 1` | low |
| 线程清单 | `thread -n 15` | low |
| 死锁检测 | `thread -b` | low |
| VM 参数 | `vmoption` | low |
| 类信息 | `sc -d ${class}` | low |

### 5.2 诊断模板（Level 2，5 个）

| 名称 | 命令 | 风险 |
|------|------|------|
| Trace 调用链分析 | `trace ${class} ${method} -n 10 '#cost > .5'` | medium |
| Watch 方法观测 | `watch ${class} ${method} '{params,returnObj,throwExp}' -x 3 -n 5` | medium |
| Stack 调用栈定位 | `stack ${class} ${method} -n 5` | low |
| Jad 反编译 | `jad --source-only ${class}` | low |
| Monitor 方法统计 | `monitor ${class} ${method} -c 5` | low |

### 5.3 场景方案（Level 3，3 个）

| 名称 | 步骤 | 风险 |
|------|------|------|
| 接口响应慢诊断 | trace → watch → profiler | medium |
| CPU 100% 排查 | thread → profiler → thread | low |
| OOM 内存泄漏排查 | dashboard → heapdump → vmoption | high |

### 5.4 AI 诊断（Level 4，1 个）

| 名称 | Handler | 风险 |
|------|---------|------|
| 一键性能诊断 | `performance_diagnose.run_diagnosis` | low |

---

**文档结束**