# docs/ 目录结构说明

本目录存放项目的所有设计文档、需求文档、分析报表和图表文件。

## 目录概览

| 目录 | 用途 | 说明 |
|------|------|------|
| `prd/` | 产品需求文档 | 各阶段增量 PRD |
| `design/` | 架构设计文档 | 系统架构设计、分阶段架构设计 |
| `analysis/` | 分析报表 | 实现偏差分析等 |
| `diagrams/` | 图表文件 | Mermaid 类图、时序图 |
| `reports/` | 阶段完成报告 | 各 Phase 完成总结 |
| `guides/` | 项目指南 | 贡献指南等 |
| `superpowers/` | 实施计划与规范 | 详细实施计划、技术规范、评审记录 |

---

## 各目录详情

### `prd/` — 产品需求文档

| 文件 | 说明 |
|------|------|
| `Phase5_Incremental_PRD.md` | Phase 5（连接中心增强）增量产品需求文档 |
| `Phase7_Incremental_PRD.md` | Phase 7（现有模块迁移）增量产品需求文档 |

### `design/` — 架构设计文档

| 文件 | 说明 |
|------|------|
| `system_design.md` | 系统总架构设计（Phase 0-6） |
| `phase7-architecture.md` | Phase 7 架构设计（现有模块迁移） |

### `analysis/` — 分析报表

| 文件 | 说明 |
|------|------|
| `implementation-gap-analysis.md` | 实现偏差分析（Phase 0-6 实际实现与架构设计对比） |

### `diagrams/` — 图表文件

| 文件 | 说明 |
|------|------|
| `class-diagram.mermaid` | 系统类图（Mermaid 格式） |
| `sequence-diagram.mermaid` | 系统时序图（Mermaid 格式） |

### `reports/` — 阶段完成报告

| 文件 | 说明 |
|------|------|
| `phase5-completion-report.md` | Phase 5 完成报告（团队分工、交付文件清单） |

### `guides/` — 项目指南

| 文件 | 说明 |
|------|------|
| `CONTRIBUTING.md` | 项目贡献指南 |

### `superpowers/` — 实施计划与规范

| 子目录 | 用途 |
|--------|------|
| `plans/` | 分阶段实施计划（00-17） |
| `specs/` | 技术规范与接口设计（01-14） |
| `references/` | 参考资料（Arthas 命令、数据库 Schema、部署指南等） |
| `review/` | 架构评审记录与检查清单 |

---

## 文件命名规范

- **PRD 文件**：`Phase{N}_Incremental_PRD.md`
- **架构设计**：`phase{N}-architecture.md`
- **完成报告**：`phase{N}-completion-report.md`
- **分析文件**：`{topic}-analysis.md`
- **图表文件**：`{topic}-class-diagram.mermaid` / `{topic}-sequence-diagram.mermaid`

---

## 更新记录

| 日期 | 变更内容 |
|------|----------|
| 2026-05-26 | 创建目录结构说明；将根目录零散文档归入对应子目录 |
| 2026-05-26 | 新增 `prd/`、`design/`、`analysis/`、`diagrams/`、`reports/`、`guides/` 分类目录 |
