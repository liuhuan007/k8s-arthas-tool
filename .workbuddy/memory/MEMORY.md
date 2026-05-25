# MEMORY.md - 长期记忆

## 用户偏好
- 中文交流
- Java后端工程师/技术负责人
- 偏好结论优先、结构化、表格化表达
- 先给方案和判断，再执行
- 偏好最小化、能落地的实现，反感复杂空泛方案
- 指定#007AFF为主色
- 代码优先响应（单代码块），最小化解释

## 项目信息
- 项目：K8s Arthas Tool，Java性能诊断平台
- 技术栈：Python, Flask, SQLite, kubectl, Arthas, 原生JavaScript
- 架构：三层后端（server.py, profiler_backend.py, pod_monitor.py）
- 数据库：SQLite（arthas.db）
- 前端：原生JavaScript + CSS
- 部署：Docker, deploy.sh
- Phase 5：连接中心增强（已完成）
- Phase 6：异常检测 + 告警（已完成）

## 当前进度
- Phase 0: 数据库迁移 + 框架搭建 ✅ 已完成
- Phase 1: Skill系统（P0）✅ 已完成
- Phase 2: 诊断能力（后端）✅ 已完成
- Phase 3: Agent SDK集成（P0）✅ 已完成
- Phase 4: 诊断能力（前端）✅ 已完成
- Phase 5: 连接中心增强 ✅ 已完成
- Phase 6: 异常检测 + 告警 ✅ 已完成
- 工具箱中心（P0-5.x）✅ 已完成
- Phase 7: 现有模块迁移 ⏳ 待开始
- Phase 8: AI辅助分析 ⏳ 待开始
- Phase 9: 知识沉淀 ⏳ 待开始
- 实现偏差分析：Phase 0-6所有任务均按架构设计完成，无偏差

## 关键决策
- 使用原生JavaScript而非React/Vue（保持轻量）
- 使用SQLite而非PostgreSQL（简化部署）
- 使用HTTP轮询而非WebSocket（P0阶段）
- 采用增量开发模式，按Phase逐步推进
- Phase 5完成：连接中心增强（健康检查、TTL清理、多标签页同步、连接切换确认）

## 文件结构
- server.py: Flask REST API入口
- profiler_backend.py: 核心诊断引擎（5层架构）
- pod_monitor.py: Pod指标收集
- auth.py: 认证工具
- services/: 业务逻辑服务
- api/: API路由
- models/: 数据模型
- static/: 前端静态文件
- tests/: 测试文件
- Phase 5新增文件：
  - services/health_check_service.py
  - services/connection_ttl_config.py
  - services/connection_recovery_service.py
  - services/connection_switch_service.py
  - api/connection_detail.py
  - static/js/components/broadcast-channel-manager.js
  - static/js/components/connection-ttl-config.js
  - static/js/components/connection-switch-confirm.js

## 技术规范
- 所有API端点需要@login_required
- 管理员端点需要@admin_required
- 数据隔离：非管理员用户只看到分配的集群
- Arthas JAR检测优先级：/app/arthas/arthas-boot.jar > /opt/arthas/ > /arthas/ > /home/admin/
- Profiler输出命名：{type}-{identifier}-{podName}-{YYYYMMDDHHmmss}.{ext}
- Phase 5新增：健康检查、TTL清理、多标签页同步、连接切换确认

## 经验教训
- 使用BroadcastChannel实现多标签页同步
- 使用sessionStorage存储临时状态
- 使用TTL机制清理过期连接
- 健康检查使用定时器实现
- 连接状态恢复需要持久化到数据库
- Phase 5实现：连接详情页、健康检查、TTL清理、多标签页同步、连接切换确认
- 工具箱中心实现：工具包分发标准化、内置诊断模板、任务执行审计
- 实现偏差分析：Phase 0-6所有任务均按架构设计完成，无偏差