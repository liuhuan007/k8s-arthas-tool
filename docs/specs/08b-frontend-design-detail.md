# K8s Arthas 智能诊断平台 — 前端界面详细设计

> 补充08-frontend-design.md，提供具体的页面原型和组件实现细节

**文档版本**: v1.0
**创建日期**: 2026-05-23
**状态**: 设计完成

---

## 目录

1. [页面原型设计](#1-页面原型设计)
2. [组件详细设计](#2-组件详细设计)
3. [交互流程设计](#3-交互流程设计)
4. [状态管理详细](#4-状态管理详细)
5. [API调用详细](#5-api调用详细)

---

## 1. 页面原型设计

### 1.1 诊断中心主页面

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  K8s Arthas 智能诊断平台                                                         │
├─────────────────────────────────────────────────────────────────────────────────┤
│  [首页] [诊断中心] [任务中心] [报告中心] [知识库] [设置]                           │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  ┌─────────────────┐  ┌─────────────────────────────────────────────────────┐  │
│  │  连接选择器      │  │                                                     │  │
│  │  ┌─────────────┐│  │  ⚡ 快捷工具                                         │  │
│  │  │ 🔍 搜索连接 ││  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐  │  │
│  │  └─────────────┘│  │  │ JVM     │ │ 线程    │ │ 死锁    │ │ VM      │  │  │
│  │                 │  │  │ Dashboard│ │ 清单    │ │ 检测    │ │ 参数    │  │  │
│  │  ▼ production   │  │  │ ⚡ 低风险│ │ ⚡ 低风险│ │ ⚡ 低风险│ │ ⚡ 低风险│  │  │
│  │    my-app-pod   │  │  │ 5s      │ │ 5s      │ │ 5s      │ │ 5s      │  │  │
│  │    ───────────  │  │  │ [使用]  │ │ [使用]  │ │ [使用]  │ │ [使用]  │  │  │
│  │    other-pod    │  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘  │  │
│  │                 │  │                                                     │  │
│  │  ─────────────  │  │  🔍 诊断模板                                         │  │
│  │                 │  │  ┌─────────┐ ┌─────────┐ ┌─────────┐              │  │
│  │  📊 连接状态    │  │  │ Trace   │ │ Watch   │ │ Stack   │              │  │
│  │  ✅ 已连接      │  │  │ 调用链  │ │ 方法    │ │ 调用栈  │              │  │
│  │  Arthas 3.7.0  │  │  │ 分析    │ │ 观测    │ │ 定位    │              │  │
│  │  PID: 1234     │  │  │ 🔍 中风险│ │ 🔍 中风险│ │ ⚡ 低风险│              │  │
│  │                 │  │  │ 30s     │ │ 20s     │ │ 5s      │              │  │
│  │  ─────────────  │  │  │ [使用]  │ │ [使用]  │ │ [使用]  │              │  │
│  │                 │  │  └─────────┘ └─────────┘ └─────────┘              │  │
│  │  🎯 快速诊断    │  │                                                     │  │
│  │  [CPU飙高]     │  │  📋 场景方案                                         │  │
│  │  [内存泄漏]    │  │  ┌─────────────────┐ ┌─────────────────┐           │  │
│  │  [死锁检测]    │  │  │ 接口响应慢诊断   │ │ CPU 100% 排查   │           │  │
│  │                 │  │  │ Step1: trace    │ │ Step1: thread   │           │  │
│  │                 │  │  │ Step2: watch    │ │ Step2: profiler │           │  │
│  │                 │  │  │ Step3: profiler │ │ Step3: thread   │           │  │
│  │                 │  │  │ 🔍 中风险 60s   │ │ ⚡ 低风险 45s    │           │  │
│  │                 │  │  │ [执行] [详情]   │ │ [执行] [详情]   │           │  │
│  │                 │  │  └─────────────────┘ └─────────────────┘           │  │
│  └─────────────────┘  └─────────────────────────────────────────────────────┘  │
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │  📊 最近诊断                                                             │   │
│  │  ┌─────────────────────────────────────────────────────────────────┐   │   │
│  │  │ ID    │ 技能名称      │ 状态    │ 完成时间   │ 操作            │   │   │
│  │  ├─────────────────────────────────────────────────────────────────┤   │   │
│  │  │ D001  │ CPU飙高诊断   │ ✅ 完成 │ 2分钟前   │ [查看] [重试]   │   │   │
│  │  │ D002  │ 内存泄漏诊断  │ ⏳ 运行 │ 进行中    │ [查看] [取消]   │   │   │
│  │  │ D003  │ 死锁检测      │ ✅ 完成 │ 1小时前   │ [查看] [重试]   │   │   │
│  │  └─────────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Skill执行页面

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  CPU飙高诊断 - 执行中                              [暂停] [取消] [返回]          │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  进度: ████████████████░░░░░░░░░░░░░░░░░░░░░░░░ 60% (3/5)                       │
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │  步骤 1/5: dashboard -n 1                                    ✅ 完成   │   │
│  │  ┌─────────────────────────────────────────────────────────────────┐   │   │
│  │  │ $ dashboard -n 1                                                │   │   │
│  │  │                                                                 │   │   │
│  │  │  ID   NAME                    GROUP   Prio  State               │   │   │
│  │  │  1    main                    main    5     RUNNABLE            │   │   │
│  │  │  23   pool-1-thread-3         main    5     RUNNABLE            │   │   │
│  │  │  ...                                                             │   │   │
│  │  └─────────────────────────────────────────────────────────────────┘   │   │
│  │  🤖 AI分析: CPU使用率正常，线程数正常                                   │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │  步骤 2/5: thread -n 5                                       ✅ 完成   │   │
│  │  ┌─────────────────────────────────────────────────────────────────┐   │   │
│  │  │ $ thread -n 5                                                   │   │   │
│  │  │                                                                 │   │   │
│  │  │  "pool-1-thread-3" Id=23 RUNNABLE                               │   │   │
│  │  │    at com.example.Service.process(Service.java:42)              │   │   │
│  │  │    at com.example.Controller.handle(Controller.java:15)         │   │   │
│  │  └─────────────────────────────────────────────────────────────────┘   │   │
│  │  🤖 AI分析: 发现热点线程pool-1-thread-3，CPU占用85%                     │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │  步骤 3/5: thread -b                                         ✅ 完成   │   │
│  │  🤖 AI分析: 未发现死锁，线程状态正常                                   │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │  步骤 4/5: stack com.example.Service process                  ⏳ 执行中  │   │
│  │  ┌─────────────────────────────────────────────────────────────────┐   │   │
│  │  │ $ stack com.example.Service process                             │   │   │
│  │  │ ...                                                             │   │   │
│  │  └─────────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │  步骤 5/5: trace com.example.Service process                   ⏳ 等待中 │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │  🤖 AI 诊断摘要                                                        │   │
│  │  ┌─────────────────────────────────────────────────────────────────┐   │   │
│  │  │ **问题类型**: 计算密集型                                         │   │   │
│  │  │ **根本原因**: Service.process()方法中的循环逻辑导致CPU占用过高    │   │   │
│  │  │ **严重程度**: 中等                                               │   │   │
│  │  │                                                                 │   │   │
│  │  │ **建议**:                                                       │   │   │
│  │  │ 1. 检查Service.process()中的循环逻辑                            │   │   │
│  │  │ 2. 考虑使用异步处理或增加线程池大小                              │   │   │
│  │  │ 3. 添加性能监控，设置CPU使用率告警                               │   │   │
│  │  └─────────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                 │
│  [生成报告] [导出结果] [分享链接]                                                │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 1.3 诊断报告页面

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  诊断报告 - CPU飙高诊断                              [导出PDF] [分享] [返回]     │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │  📋 报告摘要                                                            │   │
│  │  ┌─────────────────────────────────────────────────────────────────┐   │   │
│  │  │  报告ID: RPT-2026-05-23-001                                    │   │   │
│  │  │  诊断时间: 2026-05-23 01:30:45                                  │   │   │
│  │  │  耗时: 45秒                                                      │   │   │
│  │  │  Pod: my-app-pod-7b8d9f4c5-x2j4k                               │   │   │
│  │  │  命名空间: production                                            │   │   │
│  │  └─────────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │  🔍 根本原因分析                                                        │   │
│  │  ┌─────────────────────────────────────────────────────────────────┐   │   │
│  │  │  **问题类型**: 计算密集型                                        │   │   │
│  │  │  **严重程度**: 中等                                              │   │   │
│  │  │  **置信度**: 87%                                                 │   │   │
│  │  │                                                                 │   │   │
│  │  │  **根本原因**:                                                   │   │   │
│  │  │  Service.process()方法中的循环逻辑导致CPU占用过高。              │   │   │
│  │  │  该方法在处理订单时，对每个订单项进行重复计算，                   │   │   │
│  │  │  导致CPU使用率飙升到85%。                                        │   │   │
│  │  └─────────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │  📊 证据链                                                              │   │
│  │  ┌─────────────────────────────────────────────────────────────────┐   │   │
│  │  │  步骤1: dashboard -n 1                                          │   │   │
│  │  │  发现: CPU使用率85%，线程数23                                    │   │   │
│  │  │                                                                 │   │   │
│  │  │  步骤2: thread -n 5                                             │   │   │
│  │  │  发现: pool-1-thread-3线程CPU占用85%                            │   │   │
│  │  │  堆栈: Service.process(Service.java:42)                         │   │   │
│  │  │                                                                 │   │   │
│  │  │  步骤3: thread -b                                               │   │   │
│  │  │  发现: 无死锁                                                   │   │   │
│  │  │                                                                 │   │   │
│  │  │  步骤4: stack com.example.Service process                       │   │   │
│  │  │  发现: 热点方法Service.process()                                 │   │   │
│  │  └─────────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │  💡 优化建议                                                            │   │
│  │  ┌─────────────────────────────────────────────────────────────────┐   │   │
│  │  │  1. **代码层面**: 优化Service.process()中的循环逻辑             │   │   │
│  │  │     - 使用批量处理替代逐项处理                                   │   │   │
│  │  │     - 添加缓存避免重复计算                                       │   │   │
│  │  │                                                                 │   │   │
│  │  │  2. **架构层面**: 考虑异步处理                                    │   │   │
│  │  │     - 使用消息队列解耦订单处理                                   │   │   │
│  │  │     - 增加线程池大小                                             │   │   │
│  │  │                                                                 │   │   │
│  │  │  3. **监控层面**: 添加性能监控                                   │   │   │
│  │  │     - 设置CPU使用率告警阈值                                      │   │   │
│  │  │     - 监控线程池使用情况                                         │   │   │
│  │  └─────────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │  📈 相关指标                                                            │   │
│  │  ┌─────────────────────────────────────────────────────────────────┐   │   │
│  │  │  CPU使用率: 85% ████████████████████░░░░░░░░░░░░░░░░░░░░░░░░    │   │   │
│  │  │  线程数: 23 █████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░    │   │   │
│  │  │  GC次数: 5 █░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░    │   │   │
│  │  │  堆内存: 256MB ████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░    │   │   │
│  │  └─────────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 1.4 首页仪表盘

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  K8s Arthas 智能诊断平台                                                         │
├─────────────────────────────────────────────────────────────────────────────────┤
│  [首页] [诊断中心] [任务中心] [报告中心] [知识库] [设置]                           │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  欢迎回来，管理员！今天是2026年5月24日                                           │
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │  📊 系统状态                                                             │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐ │   │
│  │  │ 已连接   │  │ 运行中   │  │ 今日诊断 │  │ 告警数   │  │ 在线用户 │ │   │
│  │  │ Pod      │  │ 任务     │  │ 次数     │  │          │  │          │ │   │
│  │  │    12    │  │    3     │  │   45     │  │    2     │  │    5     │ │   │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘ │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │  🎯 快速操作                                                             │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐│   │
│  │  │ 🧠 智能诊断  │  │ 🔗 新建连接  │  │ 📋 查看任务  │  │ 🤖 AI 助手  ││   │
│  │  │              │  │              │  │              │  │              ││   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘│   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │  📈 最近诊断                                                             │   │
│  │  ┌─────────────────────────────────────────────────────────────────┐   │   │
│  │  │ ID    │ Pod名称         │ 技能名称    │ 状态    │ 时间         │   │   │
│  │  ├─────────────────────────────────────────────────────────────────┤   │   │
│  │  │ D001  │ my-app-pod-xxx │ CPU飙高诊断 │ ✅ 完成 │ 2分钟前     │   │   │
│  │  │ D002  │ order-svc-pod  │ 内存泄漏    │ ⏳ 运行 │ 进行中      │   │   │
│  │  │ D003  │ user-svc-pod   │ 死锁检测    │ ✅ 完成 │ 1小时前     │   │   │
│  │  └─────────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │  🔔 最新告警                                                             │   │
│  │  ┌─────────────────────────────────────────────────────────────────┐   │   │
│  │  │ ⚠️ CPU使用率超过80% - my-app-pod-xxx                    5分钟前 │   │   │
│  │  │ ⚠️ 内存使用率超过90% - order-svc-pod                   10分钟前 │   │   │
│  │  │ ℹ️ Arthas连接断开 - user-svc-pod                       15分钟前 │   │   │
│  │  └─────────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 1.5 连接中心页面

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  🔗 连接中心                                                 [+ 新建连接]      │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │  🔍 搜索: [________________]  集群: [全部▼]  状态: [全部▼]              │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │  连接列表                                                               │   │
│  │  ┌─────────────────────────────────────────────────────────────────┐   │   │
│  │  │ 状态 │ Pod名称              │ 命名空间    │ Arthas  │ 操作      │   │   │
│  │  ├─────────────────────────────────────────────────────────────────┤   │   │
│  │  │  🟢  │ my-app-pod-xxx      │ production  │ 3.7.0   │ [详情]    │   │   │
│  │  │  🟢  │ order-svc-pod       │ production  │ 3.7.0   │ [详情]    │   │   │
│  │  │  🟡  │ user-svc-pod        │ staging     │ 未连接  │ [连接]    │   │   │
│  │  │  🔴  │ old-service-pod     │ production  │ -       │ [删除]    │   │   │
│  │  └─────────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │  📊 连接详情 (选中 my-app-pod-xxx)                                      │   │
│  │  ┌─────────────────────────────────────────────────────────────────┐   │   │
│  │  │  基本信息                                                       │   │   │
│  │  │  - Pod名称: my-app-pod-7b8d9f4c5-x2j4k                        │   │   │
│  │  │  - 命名空间: production                                         │   │   │
│  │  │  - 集群: prod-cluster                                           │   │   │
│  │  │  - 节点: node-1                                                 │   │   │
│  │  │                                                                 │   │   │
│  │  │  Arthas状态                                                     │   │   │
│  │  │  - 版本: 3.7.0                                                  │   │   │
│  │  │  - PID: 1234                                                    │   │   │
│  │  │  - 连接状态: ✅ 已连接                                           │   │   │
│  │  │  - 最后心跳: 2分钟前                                             │   │   │
│  │  │                                                                 │   │   │
│  │  │  [🧠 诊断] [📊 监控] [🖥️ 终端] [📁 文件] [🔄 断开]             │   │   │
│  │  └─────────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 1.6 任务中心页面

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  📦 任务中心                                                                     │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │  状态筛选: [全部] [运行中(3)] [待处理(2)] [已完成(15)] [失败(1)]        │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │  任务列表                                                               │   │
│  │  ┌─────────────────────────────────────────────────────────────────┐   │   │
│  │  │ ID    │ 类型      │ Pod名称         │ 状态    │ 时间    │ 操作  │   │   │
│  │  ├─────────────────────────────────────────────────────────────────┤   │   │
│  │  │ T001  │ 诊断      │ my-app-pod-xxx │ ✅ 完成 │ 2分钟前 │ [查看]│   │   │
│  │  │ T002  │ 采样      │ order-svc-pod  │ ⏳ 运行 │ 进行中  │ [取消]│   │   │
│  │  │ T003  │ 诊断      │ user-svc-pod   │ ✅ 完成 │ 1小时前 │ [查看]│   │   │
│  │  │ T004  │ 在线修复  │ old-svc-pod    │ ❌ 失败 │ 2小时前 │ [重试]│   │   │
│  │  └─────────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │  📋 任务详情 (选中 T001)                                                │   │
│  │  ┌─────────────────────────────────────────────────────────────────┐   │   │
│  │  │  任务ID: T001                                                   │   │   │
│  │  │  类型: CPU飙高诊断                                               │   │   │
│  │  │  Pod: my-app-pod-7b8d9f4c5-x2j4k                               │   │   │
│  │  │  状态: ✅ 已完成                                                 │   │   │
│  │  │  开始时间: 2026-05-24 07:00:00                                  │   │   │
│  │  │  结束时间: 2026-05-24 07:00:45                                  │   │   │
│  │  │  耗时: 45秒                                                      │   │   │
│  │  │                                                                 │   │   │
│  │  │  [📄 查看报告] [🔄 重新执行] [📋 复制命令]                       │   │   │
│  │  └─────────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 1.7 AI 助手页面

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  🤖 AI 助手                                                                      │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │  📋 当前上下文                                                           │   │
│  │  连接: my-app-pod-xxx (production)  Arthas: 3.7.0  PID: 1234           │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │  💬 对话历史                                                             │   │
│  │  ┌─────────────────────────────────────────────────────────────────┐   │   │
│  │  │  👤 用户: 帮我诊断这个Pod的CPU使用情况                           │   │   │
│  │  │                                                                 │   │   │
│  │  │  🤖 AI: 好的，我来帮你诊断CPU使用情况。让我先执行一些诊断命令。  │   │   │
│  │  │                                                                 │   │   │
│  │  │  🔧 工具调用:                                                   │   │   │
│  │  │  - execute_kubectl("get pod my-app-pod-xxx -o json")            │   │   │
│  │  │  - execute_arthas("dashboard -n 1")                             │   │   │
│  │  │  - execute_arthas("thread -n 5")                                │   │   │
│  │  │                                                                 │   │   │
│  │  │  🤖 AI: 根据诊断结果，我发现：                                   │   │   │
│  │  │  1. Pod状态正常，重启次数为0                                     │   │   │
│  │  │  2. CPU使用率85%，主要消耗在线程pool-1-thread-3                 │   │   │
│  │  │  3. 热点方法: Service.process()                                  │   │   │
│  │  │                                                                 │   │   │
│  │  │  建议使用trace命令进一步分析Service.process()的调用链路。         │   │   │
│  │  └─────────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │  [________________] [发送]  [📎 附件] [🔧 工具]                         │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. 组件详细设计

### 2.1 连接选择器组件

```javascript
// static/js/components/connection-selector.js
class ConnectionSelector {
  constructor(container) {
    this.container = container;
    this.connections = [];
    this.selectedConnection = null;
    this.render();
  }
  
  async loadConnections() {
    const response = await fetch('/api/arthas/connections?status=ready', {
      credentials: 'include'
    });
    const data = await response.json();
    this.connections = data.connections || [];
    this.render();
  }
  
  render() {
    this.container.innerHTML = `
      <div class="connection-selector">
        <div class="selector-header">
          <input type="text" placeholder="🔍 搜索连接..." 
                 class="search-input" oninput="this.filterConnections(this.value)">
        </div>
        <div class="selector-list">
          ${this.connections.map(conn => `
            <div class="connection-item ${conn.id === this.selectedConnection?.id ? 'selected' : ''}"
                 onclick="connectionSelector.select('${conn.id}')">
              <div class="conn-name">${conn.pod_name}</div>
              <div class="conn-namespace">${conn.namespace}</div>
              <div class="conn-status">
                <span class="status-dot ${conn.status}"></span>
                ${conn.status}
              </div>
            </div>
          `).join('')}
        </div>
        <div class="selector-footer">
          <div class="conn-info">
            ${this.selectedConnection ? `
              <div>命名空间: ${this.selectedConnection.namespace}</div>
              <div>Arthas: ${this.selectedConnection.arthas_version || '未连接'}</div>
              <div>PID: ${this.selectedConnection.java_pid || '未知'}</div>
            ` : '请选择连接'}
          </div>
        </div>
      </div>
    `;
  }
  
  select(connectionId) {
    this.selectedConnection = this.connections.find(c => c.id === connectionId);
    this.render();
    // 触发连接变更事件
    store.setState({ currentConnection: this.selectedConnection });
  }
}
```

### 2.2 Skill卡片组件

```javascript
// static/js/components/skill-card.js
class SkillCard {
  constructor(skill) {
    this.skill = skill;
  }
  
  render() {
    const riskColors = {
      low: '#34C759',
      medium: '#FF9500',
      high: '#FF3B30'
    };
    
    const levelIcons = {
      1: '⚡',
      2: '🔍',
      3: '📋',
      4: '🤖'
    };
    
    return `
      <div class="skill-card" onclick="diagnosisCenter.executeSkill('${this.skill.id}')">
        <div class="card-header">
          <span class="card-icon">${levelIcons[this.skill.level] || '📋'}</span>
          <span class="card-level">Level ${this.skill.level}</span>
        </div>
        <div class="card-body">
          <div class="card-title">${this.skill.name}</div>
          <div class="card-description">${this.skill.description}</div>
        </div>
        <div class="card-footer">
          <span class="risk-badge" style="background: ${riskColors[this.skill.risk_level]}">
            ${this.skill.risk_level}
          </span>
          <span class="duration">${this.skill.estimated_duration}s</span>
        </div>
      </div>
    `;
  }
}
```

### 2.3 参数表单组件

```javascript
// static/js/components/param-form.js
class ParamForm {
  constructor(skill, container) {
    this.skill = skill;
    this.container = container;
    this.params = {};
    this.render();
  }
  
  render() {
    const schema = JSON.parse(this.skill.parameters_schema || '[]');
    
    this.container.innerHTML = `
      <div class="param-form">
        <div class="form-header">
          <h3>参数配置</h3>
        </div>
        <div class="form-body">
          ${schema.map(param => `
            <div class="form-group">
              <label class="form-label">
                ${param.label}
                ${param.required ? '<span class="required">*</span>' : ''}
              </label>
              <input type="text" 
                     class="form-input"
                     name="${param.name}"
                     value="${param.default || ''}"
                     placeholder="${param.placeholder || ''}"
                     ${param.required ? 'required' : ''}
                     pattern="${param.pattern || ''}"
                     onchange="paramForm.updateParam('${param.name}', this.value)">
              ${param.description ? `<div class="form-hint">${param.description}</div>` : ''}
            </div>
          `).join('')}
        </div>
        <div class="form-footer">
          <button class="btn btn-primary" onclick="paramForm.submit()">
            开始诊断
          </button>
          <button class="btn btn-secondary" onclick="paramForm.cancel()">
            取消
          </button>
        </div>
      </div>
    `;
  }
  
  updateParam(name, value) {
    this.params[name] = value;
  }
  
  validate() {
    const schema = JSON.parse(this.skill.parameters_schema || '[]');
    for (const param of schema) {
      if (param.required && !this.params[param.name]) {
        alert(`请填写${param.label}`);
        return false;
      }
      if (param.pattern && this.params[param.name]) {
        const regex = new RegExp(param.pattern);
        if (!regex.test(this.params[param.name])) {
          alert(`${param.label}格式不正确`);
          return false;
        }
      }
    }
    return true;
  }
  
  async submit() {
    if (!this.validate()) return;
    
    const connection = store.getState().currentConnection;
    if (!connection) {
      alert('请先选择连接');
      return;
    }
    
    const response = await fetch(`/api/diagnosis/capabilities/${this.skill.id}/execute`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({
        connection_id: connection.id,
        params: this.params
      })
    });
    
    const result = await response.json();
    if (result.ok) {
      // 跳转到执行页面
      window.location.hash = `/diagnosis/${this.skill.id}/execute?run_id=${result.run_id}`;
    } else {
      alert(`执行失败: ${result.error}`);
    }
  }
}
```

### 2.4 执行进度组件

```javascript
// static/js/components/execution-progress.js

// ============================================================
// P0 版本：HTTP 轮询（当前实施）
// ============================================================
class ExecutionProgress {
  constructor(runId, container) {
    this.runId = runId;
    this.container = container;
    this.progress = 0;
    this.steps = [];
    this.pollInterval = null;
    this.startPolling();  // P0: 使用轮询
  }
  
  startPolling() {
    // P0: 每2秒轮询一次执行状态
    this.pollInterval = setInterval(async () => {
      const response = await fetch(`/api/diagnosis/runs/${this.runId}/status`);
      const data = await response.json();
      this.updateFromPolling(data);
    }, 2000);
  }
  
  updateFromPolling(data) {
    this.progress = data.progress || 0;
    this.steps = data.steps || [];
    this.render();
    
    if (data.status === 'success' || data.status === 'failed') {
      this.stopPolling();
    }
  }
  
  stopPolling() {
    if (this.pollInterval) {
      clearInterval(this.pollInterval);
      this.pollInterval = null;
    }
  }
  
  // ... 其他方法保持不变
}

// ============================================================
// P2 版本：WebSocket（后续迭代）
// ============================================================
// class ExecutionProgressWebSocket {
//   constructor(runId, container) {
//     this.runId = runId;
//     this.container = container;
//     this.progress = 0;
//     this.steps = [];
//     this.initWebSocket();  // P2: 使用WebSocket
//   }
//   
//   initWebSocket() {
//     const wsUrl = `ws://${window.location.host}/api/diagnosis/stream/${this.runId}`;
//     this.ws = new WebSocket(wsUrl);
//     // ... WebSocket实现
//   }
// }
        this.onComplete(data);
        break;
    }
    this.updateProgress();
  }
  
  addStep(stepNum, command, status) {
    this.steps[stepNum] = { command, status, output: '', analysis: '' };
    this.render();
  }
  
  updateStepOutput(stepNum, output) {
    if (this.steps[stepNum]) {
      this.steps[stepNum].output = output;
      this.render();
    }
  }
  
  updateStepStatus(stepNum, status) {
    if (this.steps[stepNum]) {
      this.steps[stepNum].status = status;
      this.render();
    }
  }
  
  updateStepAnalysis(stepNum, analysis) {
    if (this.steps[stepNum]) {
      this.steps[stepNum].analysis = analysis;
      this.render();
    }
  }
  
  updateProgress() {
    const completed = this.steps.filter(s => s.status === 'success').length;
    this.progress = (completed / this.steps.length) * 100;
    this.renderProgressBar();
  }
  
  renderProgressBar() {
    const progressBar = this.container.querySelector('.progress-fill');
    if (progressBar) {
      progressBar.style.width = `${this.progress}%`;
    }
  }
  
  render() {
    this.container.innerHTML = `
      <div class="execution-progress">
        <div class="progress-header">
          <div class="progress-bar">
            <div class="progress-fill" style="width: ${this.progress}%"></div>
          </div>
          <div class="progress-text">${Math.round(this.progress)}%</div>
        </div>
        <div class="steps-list">
          ${this.steps.map((step, index) => `
            <div class="step-item ${step.status}">
              <div class="step-header">
                <span class="step-number">${index + 1}</span>
                <span class="step-command">${step.command}</span>
                <span class="step-status">${this.getStatusIcon(step.status)}</span>
              </div>
              ${step.output ? `
                <div class="step-output">
                  <pre>${step.output}</pre>
                </div>
              ` : ''}
              ${step.analysis ? `
                <div class="step-analysis">
                  <div class="analysis-icon">🤖</div>
                  <div class="analysis-text">${step.analysis}</div>
                </div>
              ` : ''}
            </div>
          `).join('')}
        </div>
      </div>
    `;
  }
  
  getStatusIcon(status) {
    const icons = {
      running: '⏳',
      completed: '✅',
      failed: '❌',
      waiting: '⏸️'
    };
    return icons[status] || '❓';
  }
  
  onComplete(data) {
    // 显示完成按钮
    const footer = this.container.querySelector('.progress-footer');
    if (footer) {
      footer.innerHTML = `
        <button class="btn btn-primary" onclick="window.location.hash='/diagnosis/report/${this.runId}'">
          查看报告
        </button>
        <button class="btn btn-secondary" onclick="window.location.hash='/diagnosis'">
          返回诊断中心
        </button>
      `;
    }
  }
}
```

---

## 3. 交互流程设计

### 3.1 完整诊断流程（P0 轮询版本）

```
用户点击"使用"按钮
    │
    ▼
进入参数配置页面
    │
    ▼
填写参数并提交
    │
    ▼
创建执行任务 (POST /api/diagnosis/capabilities/{id}/execute)
    │
    ▼
跳转到执行页面
    │
    ▼
开始轮询 (GET /api/diagnosis/runs/{run_id}/status)  [每2秒]
    │
    ▼
接收轮询响应
    │
    ├── status=running → 更新进度和步骤
    ├── status=success → 显示完成
    └── status=failed → 显示错误
    ├── llm_analysis → 显示AI分析
    └── diagnosis_complete → 显示完成
    │
    ▼
生成诊断报告
    │
    ▼
显示报告页面
```

### 3.2 错误处理流程

```
执行过程中出现错误
    │
    ▼
接收error消息
    │
    ▼
显示错误提示
    │
    ├── 连接断开 → 提示重新连接
    ├── 命令执行失败 → 显示错误详情
    └── AI分析失败 → 显示原始输出
    │
    ▼
提供恢复选项
    │
    ├── 重试当前步骤
    ├── 跳过当前步骤
    └── 终止诊断
```

---

## 4. 状态管理详细

### 4.1 全局状态结构

```javascript
// static/js/core/store.js
const initialState = {
  // 用户信息
  user: null,
  
  // 连接相关
  connections: [],
  currentConnection: null,
  
  // 诊断相关
  skills: [],
  currentSkill: null,
  
  // 执行相关
  currentExecution: null,
  executionHistory: [],
  
  // UI状态
  loading: false,
  error: null,
  
  // AI相关
  aiConfig: null,
  chatMessages: []
};
```

### 4.2 状态更新规则

```javascript
// 状态更新必须通过store.setState
store.setState({
  currentConnection: connection
});

// 订阅状态变化
const unsubscribe = store.subscribe('currentConnection', (newConn) => {
  console.log('连接变更:', newConn);
  // 更新UI
});

// 取消订阅
unsubscribe();
```

---

## 5. API调用详细

### 5.1 诊断能力API（P0 轮询版本）

```javascript
// 获取能力列表（统一使用 /api/diagnosis/capabilities）
GET /api/diagnosis/capabilities?type=arthas_command&category=tool&level=2

// 执行能力
POST /api/diagnosis/capabilities/{capability_id}/execute
{
  "connection_id": "conn_123",
  "params": {
    "class": "com.example.Service",
    "method": "process"
  }
}

// 查询执行状态（轮询接口）
GET /api/diagnosis/runs/{run_id}/status
Response: {
  "run_id": "xxx",
  "status": "running",
  "progress": 0.6,
  "current_step": 2,
  "total_steps": 5
}

// 取消执行
POST /api/diagnosis/runs/{run_id}/cancel
```

### 5.2 WebSocket消息格式（P2 目标态）

```javascript
// 命令开始
{
  "type": "command_start",
  "step": 1,
  "command": "dashboard -n 1"
}

// 命令输出
{
  "type": "command_output",
  "step": 1,
  "output": "ID   NAME   GROUP   Prio..."
}

// 命令完成
{
  "type": "command_complete",
  "step": 1,
  "duration": 2.3
}

// AI分析
{
  "type": "llm_analysis",
  "step": 1,
  "analysis": "CPU使用率正常，线程数正常"
}

// 诊断完成
{
  "type": "diagnosis_complete",
  "run_id": "run_123",
  "summary": "CPU使用率异常，主要消耗在Service.process()方法"
}
```

---

**文档结束**
