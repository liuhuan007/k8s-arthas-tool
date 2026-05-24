# K8s Arthas 智能诊断平台文档

## 项目简介

本目录包含 K8s Arthas 智能诊断平台的所有技术文档，涵盖产品设计、架构设计、实施计划、代码审查和参考资料。

## 文档结构

文档按照功能模块组织：

| 目录 | 用途 | 文件数 |
|---|---|---|
| `specs/` | 设计文档（架构source of truth） | 15个 |
| `plans/` | 实施计划（分阶段开发计划、里程碑） | 14个 |
| `review/` | 历史评审（不作为source of truth） | 2个 |
| `references/` | 参考资料（数据库、命令速查、部署指南） | 4个 |

## 文档导航（权威入口）

### specs/ 设计文档（Source of Truth）

| 文件 | 说明 | P0/P1/P2 |
|---|---|---|
| `01-system-overview.md` | **系统总览与背景目标** | P0 |
| `02-connection-center.md` | **连接中心设计** | P0 |
| `03-diagnosis-center.md` | **诊断中心与Skill概念** | P0 |
| `04-task-center.md` | **任务中心与执行日志** | P0 |
| `05-toolbox.md` | 工具箱设计 | P1 |
| `06-data-model.md` | **数据模型设计** | P0 |
| `07-api-design.md` | **API边界设计** | P0 |
| `08-frontend-design.md` | 前端交互设计 | P0 |
| `08-frontend-design-detail.md` | 前端界面详细设计 | P0 |
| `09-security-audit.md` | **安全与审计** | P0 |
| `10-implementation-plan.md` | 实施计划与路线图（参考） | - |
| `11-agent-integration-architecture.md` | **Agent集成架构** | **P0** |
| `12-skill-registry-orchestrator-gateway.md` | **Skill Registry/Orchestrator/Gateway** | **P0** |
| `13-maintainability-design.md` | **可维护性设计**（编码规范、运维支持） | P0 |
| `14-performance-design.md` | **性能设计**（SLA、优化策略） | P0 |

### plans/ 实施计划

| 文件 | 说明 |
|---|---|
| `00-implementation-master-plan.md` | 总体实施计划 |
| `01-connection-center-plan.md` | 连接中心实施计划 |
| `02-diagnosis-center-plan.md` | 诊断中心实施计划 |
| `03-task-center-plan.md` | 任务中心实施计划 |
| `04-toolbox-plan.md` | 工具箱实施计划 |
| `05-milestones.md` | 里程碑与路线图 |
| `06-data-model-plan.md` | 数据模型实施计划 |
| `07-api-design-plan.md` | API设计实施计划 |
| `08-frontend-design-plan.md` | 前端设计实施计划 |
| `09-security-audit-plan.md` | 安全审计实施计划 |
| `11-agent-integration-plan.md` | Agent集成实施计划 |
| `12-skill-registry-plan.md` | Skill Registry实施计划 |
| `13-maintainability-plan.md` | 可维护性实施计划 |
| `14-performance-plan.md` | 性能设计实施计划 |

### review/ 历史评审（⚠️ 不作为Source of Truth）

> **注意**：review/ 目录下的文档是历史评审记录，部分结论已被specs/文档superseded。不作为最终架构口径。

| 文件 | 说明 | 状态 |
|---|---|---|
| `architecture-review.md` | 架构评审汇总 | ⚠️ 部分结论已superseded |
| `review-checklist.md` | 评审检查清单 | 参考用 |

### references/ 参考资料

| 文件 | 说明 |
|---|---|
| `database-schema.md` | 数据库表结构设计 |
| `arthas-commands.md` | Arthas命令速查 |
| `deployment-guide.md` | 部署指南 |
| `03-diagnosis-center-agent-sdk.md` | Agent SDK调研（参考） |

## 核心架构口径

最终统一口径：

| 概念 | 定义 | 阶段 |
|------|------|------|
| **Skill** | 管理态定义，不直接进入生产执行 | **P0** |
| **diagnosis_capability** | 发布后的生产执行态能力 | **P0** |
| **task_logs** | 一次run的总体记录 | **P0** |
| **step_logs** | run内每个步骤的记录 | **P0** |
| **Skill Registry** | 负责导入、校验、测试、发布 | **P0** |
| **Workflow Engine** | 负责执行已发布capability的DSL | **P0** |
| **Agent Tool Gateway** | 让Agent以受控方式调用capability | **P0** |
| **Agent集成** | Agent SDK集成，支持智能诊断 | **P0** |
| **可维护性** | 编码规范、代码质量、运维支持 | **P0** |
| **性能设计** | 性能SLA、优化策略、容量规划 | **P0** |

## 文档维护指南

1. **新增文档**：遵循数字前缀 + 功能名的命名规范
2. **更新文档**：直接修改文件，保持内容最新
3. **归档文档**：不再使用的文档移动到 `archive/` 目录，不删除
4. **审查流程**：重要变更需经过代码审查流程
5. **Source of Truth**：specs/ 目录下的文档是权威设计口径

## 使用流程

1. 先在 `specs/` 中沉淀设计文档
2. 设计确认后，在 `plans/` 中生成实施计划
3. 实施过程中需要引用的参考资料，放入 `references/`
4. 历史评审记录放入 `review/`（不作为source of truth）
5. 新增文档应遵循数字前缀命名规范
