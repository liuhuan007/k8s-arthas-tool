# 工具箱实施计划

| 项目 | 内容 |
|---|---|
| 文档状态 | 基于 2026-04-30 Arthas K8s 工作台实施计划整理 |
| 创建日期 | 2026-05-22 |
| 版本 | v1.0 |
| 状态 | 实施计划 |

## 1. 目标

工具箱中心负责登记工具包（toolbox packages）：工具类型、版本、来源地址、本地缓存、安装路径、校验信息和启停状态。不包含"工具自动升级/Arthas 版本升级/Tunnel 升级"等升级能力。Arthas JAR 分发只作为"安装/补齐工具"能力，不做版本升级闭环。

## 2. 架构

工具箱中心作为独立模块，负责工具包的生命周期管理，包括工具包登记、版本管理、兼容性检查、健康检查和分发记录。与任务中心、诊断中心明确边界。

## 3. 工具包表设计

### 3.1 `tool_packages` 表

工具包表，由 `api/task_center.py::init_task_tables()` 初始化。

当前代码已支持 `tool_type` 为 `arthas`、`async-profiler`、`jattach`、`generic`。规划中的工具箱中心继续复用该表承载 Arthas Boot、Arthas Tunnel Server、jattach 等工具包；其中 jattach 默认纳入 `v2.2`，并按 x86_64/arm64 两种架构分别登记下载源和本地缓存。

| 字段 | 类型 | 约束/默认值 | 说明 |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | 工具包 ID |
| `name` | TEXT | NOT NULL UNIQUE | 工具包名称 |
| `description` | TEXT | NULL | 描述 |
| `source_type` | TEXT | DEFAULT `'local'` | 来源类型 |
| `source_url` | TEXT | NULL | 来源 URL |
| `version` | TEXT | NULL | 版本 |
| `checksum` | TEXT | NULL | 兼容旧字段的校验值 |
| `tool_type` | TEXT | DEFAULT `'generic'` | 工具类型 |
| `file_path` | TEXT | NULL | 本地文件路径 |
| `file_name` | TEXT | NULL | 文件名 |
| `file_size` | INTEGER | DEFAULT 0 | 文件大小 |
| `sha256` | TEXT | NULL | SHA-256 |
| `install_path` | TEXT | NULL | 安装路径 |
| `is_builtin` | INTEGER | DEFAULT 0 | 是否内置工具 |
| `last_verified_at` | TIMESTAMP | NULL | 最近校验时间 |
| `status` | TEXT | DEFAULT `'active'` | 状态 |
| `created_by` | INTEGER | FK → `users.id` ON DELETE SET NULL | 创建用户 |
| `created_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| `updated_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | 更新时间 |

迁移逻辑：`tool_type`、`file_path`、`file_name`、`file_size`、`sha256`、`install_path`、`is_builtin`、`last_verified_at` 缺失时逐列 `ALTER TABLE` 补齐。

### 3.2 建议字段

工具箱中心产品化时，建议继续补充兼容性与健康检查字段：

| 建议字段 | 类型 | 说明 |
|---|---|---|
| `min_jdk_version` | TEXT | 最低 JDK 版本要求 |
| `max_jdk_version` | TEXT | 最高 JDK 版本要求 |
| `arch` | TEXT | CPU 架构（x86_64/arm64） |
| `health_status` | TEXT | 健康状态（healthy/failed/unknown） |
| `download_url` | TEXT | 官方下载地址 |
| `last_health_check_at` | TIMESTAMP | 最近健康检查时间 |

## 4. 任务分解

### 任务 P0-5.1：工具包分发结果标准化

**文件：**
- 修改：`api/task_center.py`
- 修改：`static/js/app-ui.js`
- 测试：`tests/test_task_center_toolchain.py`

**需求：**
- 分发返回 install_path、sha256、pod 校验结果
- UI 展示最近分发状态
- 失败时展示 kubectl stderr
- 不实现工具升级流程，只记录当前分发文件和校验结果

### 任务 P0-5.2：内置诊断模板补齐 P0 清单

**文件：**
- 修改：`api/task_center.py`
- 测试：`tests/test_task_center_toolchain.py`

**模板：**
- CPU 高负载一键诊断
- Trace 调用链耗时分析
- Watch 方法现场观测
- 在线反编译 jad
- CPU 火焰图
- Arthas jad/retransform 热更新工作流
- Pod Python 文件下载服务

### 任务 P0-5.3：任务执行与审计打通

**文件：**
- 修改：`api/task_center.py`
- 修改：`services/audit_service.py`
- 测试：`tests/test_task_audit.py`

**需求：**
- 每次任务执行写 audit_logs
- 记录 user_id、目标 Pod、任务名、执行模式、状态

## 5. 执行顺序

### Sprint 3：工具链 + 任务 + 审计 + Namespace 授权

本 Sprint 不加入升级能力；重点是工具链/任务稳定性、审计闭环，以及账号到 namespace 的精细授权。

1. P0-7.1 设计并迁移用户 Namespace 授权表
2. P0-7.2 新增 Namespace 授权 API
3. P0-7.3 统一 Namespace 权限校验函数
4. P0-7.4 用户管理页面支持 Namespace 授权配置
5. P0-7.5 Namespace 授权审计
6. P0-5.1 工具包分发结果标准化（不做升级能力）
7. P0-5.2 内置诊断模板补齐
8. P0-5.3 任务执行与审计打通
9. P0-6.1 敏感命令确认机制
10. P0-6.2 审计字段补强

## 6. 验收标准

- [ ] 工具包分发结果标准化完成
- [ ] 内置诊断模板补齐 P0 清单
- [ ] 任务执行与审计打通
- [ ] 敏感命令确认机制实现
- [ ] 审计字段补强完成
- [ ] Namespace 授权功能完整

## 7. 后续演进

### Phase P1：增强体验与金融级安全能力

- 方法 monitor / stack 支持
- 诊断模板保存与复用
- 热修复审批和回滚
- 历史趋势和诊断报告

### Phase P2：生态扩展

- Arthas Tunnel Server 模式
- 批量诊断
- 外部系统集成（TAPD/工单集成、IDE 插件协议）