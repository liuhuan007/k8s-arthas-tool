# Superpowers Documentation Layout

本目录按 Superpowers 开发流程组织文档，避免 PRD、设计、实施计划和参考资料混放。

## 目录规范

| 目录 | 用途 | 命名规范 |
|---|---|---|
| `specs/` | 需求、PRD、设计方案、架构设计 | `YYYY-MM-DD-<feature-name>-design.md`；PRD 可使用 `YYYY-MM-DD-<feature-name>-prd.md` |
| `plans/` | 可执行实施计划、任务拆解 | `YYYY-MM-DD-<feature-name>-implementation-plan.md` |
| `references/` | 数据库结构、运行手册、背景材料等辅助资料 | 使用稳定语义名，例如 `database-schema.md` |

## 当前文档

| 类型 | 文件 |
|---|---|
| 产品与系统设计 | `specs/2026-05-02-arthas-k8s-platform-system-design.md` |
| 连接管理设计 | `specs/2026-04-18-connection-management-design.md` |
| 连接管理实施计划 | `plans/2026-04-18-connection-management-implementation-plan.md` |
| 数据库参考 | `references/database-schema.md` |

## 使用流程

1. 先在 `specs/` 中沉淀需求或设计文档。
2. 设计确认后，在 `plans/` 中生成实施计划。
3. 实施过程中需要引用但不属于执行计划的资料，放入 `references/`。
4. 新增文档应优先遵循日期前缀和 kebab-case 文件名。
