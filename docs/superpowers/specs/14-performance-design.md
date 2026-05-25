# K8s Arthas 智能诊断平台 — 性能设计

> **文档版本**: v1.0
> **创建日期**: 2026-05-24
> **状态**: 设计完成

---

## 目录

1. [性能SLA定义](#1-性能sla定义)
2. [性能指标](#2-性能指标)
3. [性能优化策略](#3-性能优化策略)
4. [容量规划](#4-容量规划)
5. [性能测试策略](#5-性能测试策略)
6. [性能监控](#6-性能监控)

---

## 1. 性能SLA定义

### 1.1 服务等级协议

| SLA指标 | 目标值 | 说明 |
|---------|--------|------|
| **可用性** | 99.9% | 月度可用时间 |
| **响应时间** | <2s | 95%请求响应时间 |
| **吞吐量** | >1000 QPS | 峰值请求处理能力 |
| **错误率** | <1% | 请求错误率 |
| **恢复时间** | <5min | 故障恢复时间 |

### 1.2 接口响应时间要求

| 接口类型 | P50 | P95 | P99 | 超时时间 |
|---------|-----|-----|-----|---------|
| **查询接口** | <100ms | <500ms | <1s | 5s |
| **写入接口** | <200ms | <1s | <2s | 10s |
| **诊断执行** | <5s | <30s | <60s | 120s |
| **Agent调用** | <2s | <10s | <30s | 60s |
| **文件上传** | <1s | <5s | <10s | 30s |

### 1.3 并发要求

| 场景 | 并发数 | 说明 |
|------|--------|------|
| **同时在线用户** | 50 | 正常工作时间 |
| **并发诊断任务** | 10 | 同时执行的诊断 |
| **并发Agent调用** | 5 | 同时进行的Agent会话 |
| **数据库连接** | 20 | 连接池大小 |

---

## 2. 性能指标

### 2.1 系统指标

| 指标 | 说明 | 采集方式 |
|------|------|---------|
| **CPU使用率** | 服务器CPU使用率 | node_exporter |
| **内存使用率** | 服务器内存使用率 | node_exporter |
| **磁盘IO** | 磁盘读写速率 | node_exporter |
| **网络IO** | 网络流量 | node_exporter |
| **系统负载** | 系统负载平均值 | uptime |

### 2.2 应用指标

| 指标 | 说明 | 采集方式 |
|------|------|---------|
| **请求QPS** | 每秒请求数 | Prometheus |
| **响应时间** | 请求响应时间 | Prometheus |
| **错误率** | 请求错误率 | Prometheus |
| **活跃连接数** | 当前活跃连接数 | 自定义 |
| **任务队列长度** | 待处理任务数 | 自定义 |

### 2.3 业务指标

| 指标 | 说明 | 采集方式 |
|------|------|---------|
| **诊断成功率** | 诊断任务成功率 | 数据库统计 |
| **诊断耗时** | 诊断任务平均耗时 | 数据库统计 |
| **Agent调用成功率** | Agent工具调用成功率 | 数据库统计 |
| **Skill执行成功率** | Skill执行成功率 | 数据库统计 |
| **连接建立成功率** | 连接建立成功率 | 数据库统计 |

---

## 3. 性能优化策略

### 3.1 数据库优化

#### 3.1.1 SQLite优化配置

```python
# 启用WAL模式
db.execute("PRAGMA journal_mode=WAL")
db.execute("PRAGMA synchronous=NORMAL")
db.execute("PRAGMA cache_size=10000")  # 10MB缓存
db.execute("PRAGMA temp_store=MEMORY")
db.execute("PRAGMA mmap_size=268435456")  # 256MB mmap
```

#### 3.1.2 查询优化

```python
# 1. 使用索引
CREATE INDEX idx_task_logs_status ON task_logs(status);
CREATE INDEX idx_task_logs_created_at ON task_logs(created_at);

# 2. 避免SELECT *
SELECT id, name, status FROM task_logs WHERE status = 'running'

# 3. 分页查询
SELECT * FROM task_logs 
ORDER BY created_at DESC 
LIMIT 20 OFFSET 0;

# 4. 批量插入
db.executemany(
    "INSERT INTO step_logs (run_id, step_number, command) VALUES (?, ?, ?)",
    [(run_id, i, cmd) for i, cmd in enumerate(commands)]
)
```

#### 3.1.3 连接池管理

```python
import sqlite3
from contextlib import contextmanager

class DatabasePool:
    """数据库连接池"""
    
    def __init__(self, db_path: str, pool_size: int = 10):
        self.db_path = db_path
        self.pool_size = pool_size
        self.pool = []
        self.lock = threading.Lock()
    
    def get_connection(self):
        """获取连接"""
        with self.lock:
            if self.pool:
                return self.pool.pop()
            return sqlite3.connect(self.db_path)
    
    def return_connection(self, conn):
        """归还连接"""
        with self.lock:
            if len(self.pool) < self.pool_size:
                self.pool.append(conn)
            else:
                conn.close()
    
    @contextmanager
    def connection(self):
        """上下文管理器"""
        conn = self.get_connection()
        try:
            yield conn
        finally:
            self.return_connection(conn)
```

### 3.2 缓存优化

#### 3.2.1 多级缓存架构

```
请求
    │
    ▼
L1: 浏览器缓存（静态资源）
    │
    ├── 命中 → 返回
    └── 未命中 ↓
L2: CDN缓存（静态文件）
    │
    ├── 命中 → 返回
    └── 未命中 ↓
L3: 应用缓存（热点数据）
    │
    ├── 命中 → 返回
    └── 未命中 ↓
L4: 数据库缓存（查询结果）
    │
    ├── 命中 → 返回
    └── 未命中 ↓
L5: 数据库
```

#### 3.2.2 缓存策略

| 数据类型 | 缓存位置 | TTL | 更新策略 |
|---------|---------|-----|---------|
| **静态资源** | 浏览器/CDN | 1小时 | 版本号更新 |
| **配置数据** | 应用内存 | 5分钟 | 定时刷新 |
| **Skill定义** | 应用内存 | 5分钟 | 变更时刷新 |
| **用户信息** | 应用内存 | 1分钟 | 变更时刷新 |
| **诊断结果** | 不缓存 | - | - |

#### 3.2.3 缓存实现

```python
from functools import lru_cache
from datetime import datetime, timedelta

class TTLCache:
    """带TTL的缓存"""
    
    def __init__(self, default_ttl: int = 300):
        self.cache = {}
        self.timestamps = {}
        self.default_ttl = default_ttl
    
    def get(self, key: str):
        """获取缓存"""
        if key not in self.cache:
            return None
        
        timestamp = self.timestamps.get(key)
        if timestamp and datetime.now() - timestamp < timedelta(seconds=self.default_ttl):
            return self.cache[key]
        
        # 缓存过期
        del self.cache[key]
        del self.timestamps[key]
        return None
    
    def set(self, key: str, value, ttl: int = None):
        """设置缓存"""
        self.cache[key] = value
        self.timestamps[key] = datetime.now()
    
    def invalidate(self, key: str):
        """使缓存失效"""
        self.cache.pop(key, None)
        self.timestamps.pop(key, None)
    
    def clear(self):
        """清空缓存"""
        self.cache.clear()
        self.timestamps.clear()

# 全局缓存实例
cache = TTLCache(default_ttl=300)

@lru_cache(maxsize=128)
def get_skill(skill_id: int):
    """获取Skill（带LRU缓存）"""
    return db.fetch_one("SELECT * FROM skill_registry WHERE id = ?", (skill_id,))
```

### 3.3 异步处理

#### 3.3.1 异步任务架构

```
请求 → Flask → 任务队列 → 工作线程 → 结果存储
                │
                ├── 立即返回任务ID
                │
                └── 前端轮询查询状态
```

#### 3.3.2 异步任务实现

```python
import asyncio
from queue import Queue
from threading import Thread
from typing import Callable, Any

class AsyncTaskManager:
    """异步任务管理器"""
    
    def __init__(self, max_workers: int = 5):
        self.task_queue = Queue()
        self.results = {}
        self.workers = []
        self.max_workers = max_workers
    
    def start(self):
        """启动工作线程"""
        for i in range(self.max_workers):
            worker = Thread(target=self._worker, daemon=True)
            worker.start()
            self.workers.append(worker)
    
    def _worker(self):
        """工作线程"""
        while True:
            task_id, task_func, args, kwargs = self.task_queue.get()
            try:
                result = task_func(*args, **kwargs)
                self.results[task_id] = {
                    "status": "completed",
                    "result": result
                }
            except Exception as e:
                self.results[task_id] = {
                    "status": "failed",
                    "error": str(e)
                }
            finally:
                self.task_queue.task_done()
    
    def submit(self, task_id: str, task_func: Callable, *args, **kwargs):
        """提交任务"""
        self.results[task_id] = {"status": "pending"}
        self.task_queue.put((task_id, task_func, args, kwargs))
    
    def get_result(self, task_id: str) -> dict:
        """获取任务结果"""
        return self.results.get(task_id, {"status": "not_found"})

# 全局任务管理器
task_manager = AsyncTaskManager(max_workers=5)
task_manager.start()

def execute_diagnosis_async(skill_id: int, connection_id: str) -> str:
    """异步执行诊断"""
    import uuid
    task_id = str(uuid.uuid4())
    
    task_manager.submit(
        task_id,
        execute_diagnosis,
        skill_id=skill_id,
        connection_id=connection_id
    )
    
    return task_id
```

### 3.4 并发控制

#### 3.4.1 信号量控制

```python
import asyncio
from asyncio import Semaphore

class ConcurrencyLimiter:
    """并发限制器"""
    
    def __init__(self, max_concurrent: int = 10):
        self.semaphore = Semaphore(max_concurrent)
        self.active_count = 0
        self.wait_count = 0
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        self.wait_count += 1
        await self.semaphore.acquire()
        self.wait_count -= 1
        self.active_count += 1
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        self.active_count -= 1
        self.semaphore.release()
    
    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            "active": self.active_count,
            "waiting": self.wait_count
        }

# 使用示例
diagnosis_limiter = ConcurrencyLimiter(max_concurrent=10)

async def execute_diagnosis_with_limit(skill_id: int, connection_id: str):
    """执行诊断（带并发限制）"""
    async with diagnosis_limiter:
        return await execute_diagnosis(skill_id, connection_id)
```

#### 3.4.2 速率限制

```python
import time
from collections import defaultdict

class RateLimiter:
    """速率限制器"""
    
    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = defaultdict(list)
    
    def is_allowed(self, key: str) -> bool:
        """检查是否允许请求"""
        now = time.time()
        window_start = now - self.window_seconds
        
        # 清理过期请求
        self.requests[key] = [
            req_time for req_time in self.requests[key]
            if req_time > window_start
        ]
        
        # 检查是否超过限制
        if len(self.requests[key]) >= self.max_requests:
            return False
        
        # 记录请求
        self.requests[key].append(now)
        return True

# 使用示例
rate_limiter = RateLimiter(max_requests=100, window_seconds=60)

@app.before_request
def check_rate_limit():
    """检查速率限制"""
    user_id = get_current_user_id()
    if not rate_limiter.is_allowed(f"user:{user_id}"):
        return jsonify({"error": "Rate limit exceeded"}), 429
```

---

## 4. 容量规划

### 4.1 资源需求评估

| 资源 | 最小配置 | 推荐配置 | 说明 |
|------|---------|---------|------|
| **CPU** | 2核 | 4核 | Flask应用 |
| **内存** | 2GB | 4GB | 应用+缓存 |
| **磁盘** | 20GB | 50GB | 数据库+日志 |
| **网络** | 100Mbps | 1Gbps | API通信 |

### 4.2 并发能力评估

| 场景 | 最小配置 | 推荐配置 | 说明 |
|------|---------|---------|------|
| **并发用户** | 20 | 50 | 同时在线 |
| **并发任务** | 5 | 10 | 同时执行 |
| **数据库连接** | 10 | 20 | 连接池 |
| **缓存大小** | 100MB | 500MB | 内存缓存 |

### 4.3 扩展策略

#### 4.3.1 垂直扩展

| 瓶颈 | 扩展方案 | 效果 |
|------|---------|------|
| **CPU不足** | 增加CPU核心数 | 提高并发处理能力 |
| **内存不足** | 增加内存 | 提高缓存容量 |
| **磁盘IO** | 使用SSD | 提高读写速度 |

#### 4.3.2 水平扩展

| 瓶颈 | 扩展方案 | 效果 |
|------|---------|------|
| **应用瓶颈** | 多实例部署 | 提高吞吐量 |
| **数据库瓶颈** | 读写分离 | 提高查询性能 |
| **缓存瓶颈** | 分布式缓存 | 提高缓存容量 |

---

## 5. 性能测试策略

### 5.1 测试类型

| 测试类型 | 目标 | 工具 |
|---------|------|------|
| **基准测试** | 建立性能基线 | pytest-benchmark |
| **负载测试** | 验证并发能力 | Locust |
| **压力测试** | 找到系统极限 | JMeter |
| **稳定性测试** | 验证长时间运行 | Locust |
| **容量测试** | 验证扩展能力 | JMeter |

### 5.2 测试场景

#### 5.2.1 基准测试场景

```python
import pytest
from benchmark import benchmark

@pytest.mark.benchmark
def test_get_skill_benchmark(benchmark):
    """获取Skill基准测试"""
    def get_skill():
        return db.fetch_one("SELECT * FROM skill_registry WHERE id = 1")
    
    benchmark(get_skill)

@pytest.mark.benchmark
def test_execute_diagnosis_benchmark(benchmark):
    """执行诊断基准测试"""
    async def execute():
        return await execute_diagnosis(skill_id=1, connection_id="test")
    
    benchmark(execute)
```

#### 5.2.2 负载测试场景

```python
from locust import HttpUser, task, between

class DiagnosisUser(HttpUser):
    """诊断用户负载测试"""
    
    wait_time = between(1, 3)
    
    @task(3)
    def get_capabilities(self):
        """获取能力列表"""
        self.client.get("/api/diagnosis/capabilities")
    
    @task(2)
    def execute_diagnosis(self):
        """执行诊断"""
        self.client.post("/api/diagnosis/capabilities/1/execute", json={
            "connection_id": "test-conn",
            "params": {}
        })
    
    @task(1)
    def get_diagnosis_status(self):
        """查询诊断状态"""
        self.client.get("/api/diagnosis/runs/test-run-id/status")
```

### 5.3 性能基准

| 场景 | 指标 | 目标值 | 说明 |
|------|------|--------|------|
| **查询接口** | QPS | >1000 | 单实例 |
| **写入接口** | QPS | >500 | 单实例 |
| **诊断执行** | 并发 | >10 | 同时执行 |
| **响应时间** | P95 | <1s | 95%请求 |
| **错误率** | - | <1% | 请求错误率 |

---

## 6. 性能监控

### 6.1 监控架构

```
应用
    │
    ├── Prometheus Exporter
    │       │
    │       ▼
    │   Prometheus
    │       │
    │       ▼
    │   Grafana
    │
    └── 日志采集
            │
            ▼
        ELK Stack
```

### 6.2 监控指标

#### 6.2.1 系统监控

| 指标 | 告警阈值 | 说明 |
|------|---------|------|
| CPU使用率 | >80% | 服务器CPU |
| 内存使用率 | >90% | 服务器内存 |
| 磁盘使用率 | >85% | 磁盘空间 |
| 系统负载 | >CPU核心数*2 | 系统负载 |

#### 6.2.2 应用监控

| 指标 | 告警阈值 | 说明 |
|------|---------|------|
| 请求QPS | >1000 | 每秒请求数 |
| 响应时间 | >2s | 平均响应时间 |
| 错误率 | >1% | 请求错误率 |
| 活跃连接 | >50 | 当前活跃连接 |

#### 6.2.3 业务监控

| 指标 | 告警阈值 | 说明 |
|------|---------|------|
| 诊断成功率 | <90% | 诊断任务成功率 |
| Agent调用成功率 | <95% | Agent工具调用成功率 |
| 连接建立成功率 | <95% | 连接建立成功率 |

### 6.3 告警配置

```yaml
# prometheus/alerts.yml
groups:
  - name: arthas-alerts
    rules:
      - alert: HighCPUUsage
        expr: cpu_usage_percent > 80
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High CPU usage"
          description: "CPU usage is above 80% for 5 minutes"
      
      - alert: HighMemoryUsage
        expr: memory_usage_percent > 90
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High memory usage"
          description: "Memory usage is above 90% for 5 minutes"
      
      - alert: HighErrorRate
        expr: request_error_rate > 1
        for: 10m
        labels:
          severity: critical
        annotations:
          summary: "High error rate"
          description: "Error rate is above 1% for 10 minutes"
```

### 6.4 性能报告

#### 6.4.1 日报模板

```markdown
# 性能日报 - 2026-05-24

## 概览

| 指标 | 值 | 趋势 |
|------|-----|------|
| 平均QPS | 850 | ↑ |
| 平均响应时间 | 450ms | ↓ |
| 错误率 | 0.3% | → |
| 可用性 | 99.95% | → |

## 峰值时段

- 10:00-11:00: QPS达到1200
- 14:00-15:00: QPS达到1100

## 问题记录

- 10:15: 数据库连接池耗尽，已扩容

## 优化建议

1. 优化诊断执行的数据库查询
2. 增加Skill缓存TTL
```

---

**文档结束**
