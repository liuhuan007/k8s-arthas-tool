# docs/ 目录结构

按 superpowers 技能开发流程组织：**specs → plans → review → references**

---

## 目录概览

| 目录 | 用途 | 文件数 |
|------|------|--------|
| `specs/` | 设计文档（架构 source of truth） | 15 |
| `plans/` | 实施计划（分阶段开发计划、里程碑） | 15 |
| `review/` | 历史评审（不作为 source of truth） | 5 |
| `references/` | 参考资料（Phase 设计、迁移规范、速查） | 10 |

---

## specs/ — 设计文档（Source of Truth）

| 文件 | 说明 | 状态 |
|------|------|------|
| `01-system-overview.md` | 系统总览与背景目标 | P0 |
| `02-connection-center.md` | 连接中心设计 | P0 |
| `03-diagnosis-center.md` | 诊断中心与 Skill 概念 | P0 |
| `04-task-center.md` | 任务中心与执行日志 | P0 |
| `05-toolbox.md` | 工具箱设计 | P1 |
| `06-data-model.md` | 数据模型设计（唯一权威） | P0 |
| `07-api-design.md` | API 边界设计（含错误码体系） | P0 |
| `08-frontend-design.md` | 前端交互设计 | P0 |
| `08b-frontend-design-detail.md` | 前端界面详细设计 | P0 |
| `09-security-audit.md` | 安全与审计 | P0 |
| `11-agent-integration-architecture.md` | Agent 集成架构 | P0 |
| `12-skill-registry-workflow-engine-gateway.md` | Skill Registry/Workflow Engine/Gateway | P0 |
| `13-maintainability-design.md` | 可维护性设计（编码规范、运维支持） | P0 |
| `14-performance-design.md` | 性能设计（SLA、优化策略） | P0 |
| `16b-tunnel-portforward-conflict-resolution.md` | Tunnel vs Port-Forward 冲突分析（未采纳） | 对比 |

---

## plans/ — 实施计划

| 文件 | 说明 |
|------|------|
| `00-implementation-master-plan.md` | 总体实施计划 |
| `01-connection-center-plan.md` | 连接中心实施计划 |
| `02-diagnosis-center-plan.md` | 诊断中心实施计划 |
| `03-task-center-plan.md` | 任务中心实施计划 |
| `04-toolbox-plan.md` | 工具箱实施计划 |
| `05-milestones.md` | 里程碑与路线图 |
| `06-data-model-plan.md` | 数据模型实施计划 |
| `07-api-design-plan.md` | API 设计实施计划 |
| `08-frontend-design-plan.md` | 前端设计实施计划 |
| `09-security-audit-plan.md` | 安全审计实施计划 |
| `10-implementation-plan.md` | 实施计划（详细版） |
| `11-agent-integration-plan.md` | Agent 集成实施计划 |
| `12-skill-registry-plan.md` | Skill Registry 实施计划 |
| `13-maintainability-plan.md` | 可维护性实施计划 |
| `14-performance-plan.md` | 性能设计实施计划 |

---

## review/ — 历史评审

> **注意**：review/ 目录下的文档是历史评审记录，不作为 source of truth。

| 文件 | 说明 | 状态 |
|------|------|------|
| `architecture-review.md` | 架构评审汇总 | 部分结论已 superseded |
| `data-model-review.md` | 数据模型评审 | 参考用 |
| `review-checklist.md` | 评审检查清单 | 参考用 |
| `pydantic-ai-design-inspiration.md` | Pydantic AI 设计灵感 | 参考用 |
| `review-sync-status.md` | 评审同步状态 | 参考用 |

---

## references/ — 参考资料

| 文件 | 说明 |
|------|------|
| `database-schema.md` | 数据库表结构设计 |
| `database-migration-guide.md` | 数据库迁移规范（P0 新增） |
| `arthas-commands.md` | Arthas 命令速查 |
| `deployment-guide.md` | 部署指南 |
| `system_design.md` | 系统设计（早期版本） |
| `03-diagnosis-center-agent-sdk.md` | Agent SDK 调研 |
| `15-phase2-architecture-design.md` | Phase 2 架构设计 |
| `16-phase3-architecture-design.md` | Phase 3 架构设计 |
| `17-phase4-frontend-design.md` | Phase 4 前端设计 |
| `phase7-architecture.md` | Phase 7 架构设计 |

---

## 文档依赖关系

```
01-system-overview.md (总纲)
    ├── 02-connection-center.md
    ├── 03-diagnosis-center.md ──→ 引用 12
    ├── 04-task-center.md
    ├── 05-toolbox.md
    ├── 06-data-model.md ← 所有模块引用
    ├── 07-api-design.md ← 所有模块引用
    ├── 08-frontend-design.md
    ├── 09-security-audit.md
    ├── 11-agent-integration-*.md ──→ 引用 12
    ├── 12-skill-registry-*.md
    ├── 13-maintainability-design.md
    └── 14-performance-design.md
```

---

## 文档维护规则

1. **specs/** 是权威设计口径，其他文档引用
2. **plans/** 按模块编号，与 specs 一一对应
3. **review/** 是历史评审，不作为 source of truth
4. **references/** 放参考资料（速查、部署指南、Phase 设计等）
5. 新增文档遵循数字前缀命名规范
6. **数据模型**以 `06-data-model.md` 为唯一权威来源
7. **Skill 定义格式**以 `12-skill-registry-*.md` §2.2 为准
8. **错误码体系**定义在 `07-api-design.md` §9
9. **数据库迁移规范**见 `references/database-migration-guide.md`
