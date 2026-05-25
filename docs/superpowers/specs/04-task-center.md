# K8s Arthas 智能诊断平台 — 任务中心设计


**文档版本**: v1.0
**创建日期**: 2026-05-23
**状态**: 设计完成

---

## 目录

1. [设计目标](#1-设计目标)
2. [执行模式](#2-执行模式)
3. [任务状态机](#3-任务状态机)
4. [任务数据模型](#4-任务数据模型)
5. [任务队列管理](#5-任务队列管理)
6. [定时任务调度](#6-定时任务调度)
7. [场景方案步骤数据传递](#7-场景方案步骤数据传递)
8. [任务中心API](#8-任务中心api)
9. [任务中心界面](#9-任务中心界面)
10. [任务监控详情](#10-任务监控详情)
11. [任务历史查询](#11-任务历史查询)
12. [报告管理](#12-报告管理)

---

## 1. 设计目标

- 即时诊断直接执行，基于 `diagnosis_capability` 创建 run，不创建 task_definition
- 定时任务保留 task_definitions，基于 task_definition 创建 scheduled run
- **统一日志表**：所有执行日志统一使用 `task_logs`，通过 `execution_mode` 区分
- **术语统一**：task_logs 记录 `capability_id`，不记录 `skill_id`

任务中心是管理所有诊断任务的核心模块，提供：
- **任务创建**：基于 diagnosis_capability 创建诊断 run
- **任务队列**：管理并发任务执行
- **任务监控**：实时查看任务状态和进度
- **任务历史**：查看历史任务和结果
- **报告管理**：生成、存储、导出诊断报告

---

## 2. 执行模式

**即时诊断**：
```
diagnosis_capabilities → task_logs (execution_mode='immediate') → arthas_command_logs
```

**定时任务**：
```
task_definitions → task_logs (execution_mode='scheduled') → arthas_command_logs
```

**通用任务**：
```
task_definitions → task_logs (execution_mode='manual'|'scheduled')
```

---

## 3. 任务状态机

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Pending   │───▶│  Running    │───▶│   Success   │
└─────────────┘    └─────────────┘    └─────────────┘
                         │                   │
                         │                   │
                         ▼                   ▼
                   ┌─────────────┐    ┌─────────────┐
                   │   Failed    │    │  Cancelled  │
                   └─────────────┘    └─────────────┘
```

> **状态命名统一**：数据库和API统一使用 `pending / running / success / failed / cancelled`，前端显示时映射为"已完成"。

---

## 4. 任务数据模型

```python
class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"  # 统一使用 success
    FAILED = "failed"
    CANCELLED = "cancelled"

class DiagnosisRun:
    """诊断运行记录（run级）"""
    id: str
    capability_id: int  # 关联 diagnosis_capabilities.id
    user_id: int
    connection_id: str
    connection_snapshot_json: str  # 执行时的连接快照
    capability_snapshot_json: str  # 执行时的能力快照
    params_json: dict
    status: TaskStatus
    progress: float  # 0.0 - 1.0
    result_json: Optional[dict]  # 最终结果
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]

class StepLog:
    """步骤级日志"""
    id: str
    run_id: str  # 关联 task_logs.id
    step_number: int
    step_name: str
    step_type: str  # arthas_command/llm_analysis/get_pod_status
    command: str
    output: str
    status: TaskStatus
    duration_ms: int
    llm_analysis: Optional[str]
    created_at: datetime
```

> **术语统一**：
> - `task_logs` = run级日志，记录 `capability_id`，不记录 `skill_id`
> - `step_logs` = step级日志，记录每个步骤的命令和输出
> - 如果需要追溯源 Skill，通过 `task_logs.capability_snapshot_json.source_skill_id`
    error: Optional[str]
```

---

## 5. 任务队列管理

```python
class TaskQueue:
    """任务队列管理"""
    def __init__(self, max_concurrent: int = 5):
        self.max_concurrent = max_concurrent
        self.running_tasks = {}
        self.pending_tasks = []
    
    async def submit_task(self, task: DiagnosisTask):
        """提交任务"""
        if len(self.running_tasks) < self.max_concurrent:
            await self._start_task(task)
        else:
            self.pending_tasks.append(task)
    
    async def _start_task(self, task: DiagnosisTask):
        """启动任务"""
        self.running_tasks[task.id] = task
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now()
        
        # 执行任务
        try:
            result = await self._execute_task(task)
            task.result = result
            task.status = TaskStatus.COMPLETED
        except Exception as e:
            task.error = str(e)
            task.status = TaskStatus.FAILED
        finally:
            task.completed_at = datetime.now()
            del self.running_tasks[task.id]
            await self._process_queue()
    
    async def _process_queue(self):
        """处理队列中的下一个任务"""
        if self.pending_tasks and len(self.running_tasks) < self.max_concurrent:
            next_task = self.pending_tasks.pop(0)
            await self._start_task(next_task)
```

---

## 6. 定时任务调度

定时任务不支持 Arthas 连接模式（依赖 port-forward，用户断开后进程退出），只支持 `node` 和 `pod` 模式。

**适合定时的任务**：定时 thread dump、定时 JVM 指标采集、定时健康检查脚本。

**Cron 表达式支持**：标准 5 位 Cron 格式，支持固定间隔和一次性任务。

---

## 7. 场景方案步骤数据传递

```python
def resolve_step_references(command_template, params, previous_outputs):
    """解析步骤间引用
    
    支持语法：
    1. ${param} - 直接替换参数
    2. ${stepN.field} - 引用第N步的字段
    3. ${stepN} - 引用第N步的完整输出（JSON字符串）
    """
```

---

## 8. 任务中心API

```
POST   /api/tasks                 # 创建任务
GET    /api/tasks                 # 获取任务列表
GET    /api/tasks/{task_id}       # 获取任务详情
DELETE /api/tasks/{task_id}       # 取消任务
POST   /api/tasks/{task_id}/retry # 重试任务
GET    /api/tasks/{task_id}/stream # WebSocket实时推送
GET    /api/tasks/history         # 获取任务历史
GET    /api/tasks/statistics      # 获取任务统计
```

---

## 9. 任务中心界面

```
┌─────────────────────────────────────────────────────────┐
│  任务中心                                    [+ 新建任务] │
├─────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │   运行中     │  │   待处理     │  │   已完成     │  │
│  │     (3)      │  │     (2)      │  │    (15)      │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
├─────────────────────────────────────────────────────────┤
│  任务列表                                               │
│  ┌─────────────────────────────────────────────────┐   │
│  │ ID    │ 技能名称     │ 状态    │ 进度   │ 操作  │   │
│  ├─────────────────────────────────────────────────┤   │
│  │ T001  │ CPU飙高诊断  │ 运行中  │ 60%   │ [详情]│   │
│  │ T002  │ 内存泄漏诊断 │ 待处理  │ 0%    │ [详情]│   │
│  │ T003  │ 死锁检测     │ 已完成  │ 100%  │ [详情]│   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

---

## 10. 任务监控详情

```
┌─────────────────────────────────────────────────────────┐
│  任务 T001 - CPU飙高诊断                     [暂停] [取消]│
├─────────────────────────────────────────────────────────┤
│  基本信息                                               │
│  ┌─────────────────────────────────────────────────┐   │
│  │ 技能: CPU飙高诊断                                │   │
│  │ Pod: my-app-pod-7b8d9f4c5-x2j4k                 │   │
│  │ 命名空间: production                             │   │
│  │ 创建时间: 2026-05-23 00:05:32                    │   │
│  │ 开始时间: 2026-05-23 00:05:35                    │   │
│  │ 预计完成: 2026-05-23 00:06:05                    │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  执行进度                                               │
│  ┌─────────────────────────────────────────────────┐   │
│  │ 总体进度: ████████████░░░░░░░░░░░░░░░░░░░░ 60%  │   │
│  │                                                 │   │
│  │ 步骤1: dashboard -n 1           ✅ 完成 (2.3s)  │   │
│  │ 步骤2: thread -n 5              ✅ 完成 (1.8s)  │   │
│  │ 步骤3: thread -b                ⏳ 执行中       │   │
│  │ 步骤4: stack com.example.Service ⏳ 等待中       │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  实时输出                                               │
│  ┌─────────────────────────────────────────────────┐   │
│  │ > thread -b                                     │   │
│  │                                                 │   │
│  │ "pool-1-thread-3" Id=23 RUNNABLE                │   │
│  │   at com.example.Service.process(Service.java:42)│   │
│  │   at com.example.Controller.handle(Controller:15)│   │
│  │                                                 │   │
│  │ 大模型分析: 未发现死锁，线程状态正常             │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

---

## 11. 任务历史查询

```
┌─────────────────────────────────────────────────────────┐
│  任务历史                                    [筛选] [导出] │
├─────────────────────────────────────────────────────────┤
│  筛选条件:                                              │
│  ┌─────────────────────────────────────────────────┐   │
│  │ 时间范围: [2026-05-01] 至 [2026-05-23]          │   │
│  │ 技能类型: [全部▼]                               │   │
│  │ 任务状态: [全部▼]                               │   │
│  │ Pod名称:  [全部▼]                               │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  历史记录                                               │
│  ┌─────────────────────────────────────────────────┐   │
│  │ ID    │ 技能名称     │ 状态    │ 完成时间 │ 操作│   │
│  ├─────────────────────────────────────────────────┤   │
│  │ T003  │ 死锁检测     │ 已完成  │ 00:04:15 │ [查看]│  │
│  │ T004  │ 内存泄漏诊断 │ 已完成  │ 00:03:22 │ [查看]│  │
│  │ T005  │ CPU飙高诊断  │ 失败    │ 00:02:10 │ [重试]│  │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  分页: < 1 2 3 4 5 ... 15 >                             │
└─────────────────────────────────────────────────────────┘
```

---

## 12. 报告管理

```
┌─────────────────────────────────────────────────────────┐
│  诊断报告管理                                [+ 生成报告] │
├─────────────────────────────────────────────────────────┤
│  报告列表                                               │
│  ┌─────────────────────────────────────────────────┐   │
│  │ ID    │ 技能名称     │ 严重程度 │ 生成时间 │ 操作│   │
│  ├─────────────────────────────────────────────────┤   │
│  │ R001  │ CPU飙高诊断  │ 中等     │ 00:06:10 │ [查看]│  │
│  │ R002  │ 内存泄漏诊断 │ 高       │ 00:05:22 │ [查看]│  │
│  │ R003  │ 死锁检测     │ 低       │ 00:04:15 │ [查看]│  │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  报告详情                                               │
│  ┌─────────────────────────────────────────────────┐   │
│  │ 报告ID: R001                                    │   │
│  │ 技能: CPU飙高诊断                                │   │
│  │ 严重程度: 中等                                   │   │
│  │ 生成时间: 2026-05-23 00:06:10                    │   │
│  │                                                 │   │
│  │ 摘要: CPU使用率异常，主要消耗在                  │   │
│  │       com.example.Service.process方法            │   │
│  │                                                 │   │
│  │ [查看完整报告] [导出PDF] [分享链接]              │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```