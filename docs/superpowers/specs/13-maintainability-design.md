# K8s Arthas 智能诊断平台 — 可维护性设计

> **文档版本**: v1.0
> **创建日期**: 2026-05-24
> **状态**: 设计完成

---

## 目录

1. [编码规范](#1-编码规范)
2. [代码质量](#2-代码质量)
3. [运维支持](#3-运维支持)
4. [文档体系](#4-文档体系)
5. [配置管理](#5-配置管理)
6. [监控告警](#6-监控告警)
7. [部署流程](#7-部署流程)

---

## 1. 编码规范

### 1.1 Python编码规范

#### 1.1.1 命名规范

| 类型 | 规范 | 示例 |
|------|------|------|
| **模块** | 小写+下划线 | `skill_registry.py` |
| **类** | 大驼峰 | `SkillOrchestrator` |
| **函数** | 小写+下划线 | `execute_capability()` |
| **变量** | 小写+下划线 | `connection_id` |
| **常量** | 大写+下划线 | `MAX_CONCURRENT_TASKS` |
| **私有** | 单下划线前缀 | `_validate_params()` |

#### 1.1.2 代码风格

```python
# ✅ 正确示例
class SkillOrchestrator:
    """技能编排器 - 负责执行Skill的DSL步骤"""
    
    MAX_RETRY_COUNT = 3  # 常量大写
    DEFAULT_TIMEOUT = 30  # 默认值
    
    def __init__(self, skill_id: int, connection_id: str):
        """初始化编排器
        
        Args:
            skill_id: Skill ID
            connection_id: 连接ID
        """
        self.skill_id = skill_id  # 小写下划线
        self.connection_id = connection_id
        self._results = []  # 私有变量
    
    async def execute(self) -> ExecutionResult:
        """执行Skill
        
        Returns:
            ExecutionResult: 执行结果
            
        Raises:
            SkillNotFoundError: Skill不存在
            ExecutionError: 执行失败
        """
        pass
```

#### 1.1.3 错误处理

```python
# ✅ 正确的错误处理
class SkillExecutionError(Exception):
    """Skill执行异常"""
    pass

async def execute_skill(skill_id: int) -> ExecutionResult:
    """执行Skill"""
    try:
        skill = await get_skill(skill_id)
        if not skill:
            raise SkillNotFoundError(f"Skill {skill_id} not found")
        
        result = await orchestrator.execute(skill)
        return result
        
    except SkillNotFoundError:
        raise  # 重新抛出业务异常
    except Exception as e:
        logger.error(f"Execute skill failed: {e}", exc_info=True)
        raise SkillExecutionError(f"Execute failed: {e}")
```

### 1.2 JavaScript编码规范

#### 1.2.1 命名规范

| 类型 | 规范 | 示例 |
|------|------|------|
| **变量** | 小驼峰 | `connectionId` |
| **函数** | 小驼峰 | `executeCapability()` |
| **类** | 大驼峰 | `SkillOrchestrator` |
| **常量** | 大写+下划线 | `MAX_RETRY_COUNT` |
| **DOM元素** | 小写+短横线 | `data-tab="diagnosis"` |

#### 1.2.2 代码风格

```javascript
// ✅ 正确示例
class SkillExecutor {
  /**
   * 执行Skill
   * @param {number} skillId - Skill ID
   * @param {Object} params - 参数
   * @returns {Promise<ExecutionResult>} 执行结果
   */
  async execute(skillId, params) {
    const maxRetryCount = 3;  // 常量
    let retryCount = 0;
    
    while (retryCount < maxRetryCount) {
      try {
        const result = await this._doExecute(skillId, params);
        return result;
      } catch (error) {
        retryCount++;
        console.error(`Execute failed (retry ${retryCount}):`, error);
        
        if (retryCount >= maxRetryCount) {
          throw error;
        }
      }
    }
  }
  
  /**
   * 执行内部方法
   * @private
   */
  async _doExecute(skillId, params) {
    // 实现细节
  }
}
```

### 1.3 注释规范

#### 1.3.1 文件头注释

```python
"""
K8s Arthas 智能诊断平台 - Skill编排器

负责执行Skill的DSL步骤，支持条件分支、参数传递、错误处理。

Author: AI Team
Created: 2026-05-24
Version: 1.0.0
"""
```

#### 1.3.2 函数注释

```python
def validate_parameter(name: str, value: str) -> Tuple[bool, str]:
    """校验参数值
    
    根据参数类型和白名单规则校验参数值是否合法。
    
    Args:
        name: 参数名称
        value: 参数值
        
    Returns:
        Tuple[bool, str]: (是否合法, 错误信息)
        
    Example:
        >>> validate_parameter("class", "com.example.Service")
        (True, "")
        >>> validate_parameter("class", "com.example; rm -rf /")
        (False, "参数 class 包含禁止字符")
    """
    pass
```

---

## 2. 代码质量

### 2.1 代码审查清单

#### 2.1.1 功能性审查

| 检查项 | 说明 |
|--------|------|
| 功能完整性 | 是否完整实现了需求 |
| 边界条件 | 是否处理了边界情况 |
| 错误处理 | 是否有完善的错误处理 |
| 输入校验 | 是否校验了所有输入 |

#### 2.1.2 可维护性审查

| 检查项 | 说明 |
|--------|------|
| 代码可读性 | 代码是否易于理解 |
| 函数长度 | 函数是否过长（建议<50行） |
| 类职责 | 类是否职责单一 |
| 重复代码 | 是否有重复代码需要提取 |

#### 2.1.3 性能审查

| 检查项 | 说明 |
|--------|------|
| 数据库查询 | 是否有N+1查询 |
| 缓存使用 | 是否合理使用缓存 |
| 异步处理 | 是否合理使用异步 |
| 资源释放 | 是否正确释放资源 |

### 2.2 单元测试规范

#### 2.2.1 测试覆盖率要求

| 模块类型 | 最低覆盖率 | 目标覆盖率 |
|---------|-----------|-----------|
| **核心业务逻辑** | 80% | 90% |
| **API接口** | 70% | 80% |
| **工具类** | 90% | 95% |
| **前端组件** | 60% | 70% |

#### 2.2.2 测试命名规范

```python
# 测试类命名：Test + 被测试类名
class TestSkillOrchestrator:
    
    # 测试方法命名：test_ + 方法名 + 场景
    def test_execute_skill_success(self):
        """测试执行Skill成功"""
        pass
    
    def test_execute_skill_not_found(self):
        """测试执行Skill不存在"""
        pass
    
    def test_execute_skill_timeout(self):
        """测试执行Skill超时"""
        pass
```

#### 2.2.3 测试示例

```python
import pytest
from unittest.mock import AsyncMock, MagicMock

class TestSkillOrchestrator:
    """Skill编排器测试"""
    
    @pytest.fixture
    def orchestrator(self):
        """创建编排器实例"""
        return SkillOrchestrator(skill_id=1, connection_id="test-conn")
    
    @pytest.mark.asyncio
    async def test_execute_skill_success(self, orchestrator):
        """测试执行Skill成功"""
        # Arrange
        mock_skill = MagicMock()
        mock_skill.dsl = {"steps": [{"type": "arthas_command", "command": "dashboard"}]}
        
        # Act
        with patch("services.skill_registry.get_skill", return_value=mock_skill):
            result = await orchestrator.execute()
        
        # Assert
        assert result.status == "success"
        assert result.duration_ms > 0
    
    @pytest.mark.asyncio
    async def test_execute_skill_not_found(self, orchestrator):
        """测试执行Skill不存在"""
        # Arrange
        with patch("services.skill_registry.get_skill", return_value=None):
            # Act & Assert
            with pytest.raises(SkillNotFoundError):
                await orchestrator.execute()
```

### 2.3 代码静态分析

#### 2.3.1 工具配置

```ini
# pyproject.toml
[tool.black]
line-length = 100
target-version = ['py38']

[tool.isort]
profile = "black"
line_length = 100

[tool.mypy]
python_version = "3.8"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true

[tool.pylint]
max-line-length = 100
disable = ["C0114", "C0115", "C0116"]
```

#### 2.3.2 检查命令

```bash
# 代码格式化
black .

# 导入排序
isort .

# 类型检查
mypy .

# 代码检查
pylint .

# 安全检查
bandit -r .
```

---

## 3. 运维支持

### 3.1 日志规范

#### 3.1.1 日志级别

| 级别 | 用途 | 示例 |
|------|------|------|
| **DEBUG** | 调试信息 | 变量值、SQL语句 |
| **INFO** | 一般信息 | 请求处理、任务完成 |
| **WARNING** | 警告信息 | 降级处理、性能问题 |
| **ERROR** | 错误信息 | 异常发生、操作失败 |
| **CRITICAL** | 严重错误 | 系统崩溃、数据丢失 |

#### 3.1.2 日志格式

```python
import logging

# 日志格式
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    datefmt=DATE_FORMAT
)

# 使用示例
logger = logging.getLogger(__name__)

logger.info("Starting skill execution", extra={
    "skill_id": skill_id,
    "connection_id": connection_id,
    "user_id": user_id
})

logger.error("Skill execution failed", exc_info=True, extra={
    "skill_id": skill_id,
    "error": str(e)
})
```

#### 3.1.3 结构化日志

```python
import json
from datetime import datetime

class StructuredLogger:
    """结构化日志记录器"""
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
    
    def log_event(self, level: str, event: str, **kwargs):
        """记录结构化日志"""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "level": level,
            "event": event,
            **kwargs
        }
        
        getattr(self.logger, level.lower())(json.dumps(log_entry))

# 使用示例
logger = StructuredLogger("skill_executor")

logger.log_event("INFO", "skill_execution_started", 
    skill_id=123,
    connection_id="conn-xxx",
    user_id=456
)
```

### 3.2 监控告警

#### 3.2.1 监控指标

| 指标类型 | 指标名 | 说明 | 告警阈值 |
|---------|--------|------|---------|
| **系统** | CPU使用率 | 服务器CPU使用率 | >80% |
| **系统** | 内存使用率 | 服务器内存使用率 | >90% |
| **系统** | 磁盘使用率 | 磁盘空间使用率 | >85% |
| **应用** | 请求QPS | 每秒请求数 | >1000 |
| **应用** | 响应时间 | 平均响应时间 | >2s |
| **应用** | 错误率 | 请求错误率 | >1% |
| **业务** | 诊断成功率 | 诊断任务成功率 | <90% |
| **业务** | Agent调用成功率 | Agent工具调用成功率 | <95% |

#### 3.2.2 告警规则

```python
# 告警规则配置
ALERT_RULES = {
    "high_cpu": {
        "metric": "cpu_usage_percent",
        "condition": ">",
        "threshold": 80,
        "duration": "5m",
        "severity": "warning",
        "message": "CPU使用率超过80%"
    },
    "high_memory": {
        "metric": "memory_usage_percent",
        "condition": ">",
        "threshold": 90,
        "duration": "5m",
        "severity": "critical",
        "message": "内存使用率超过90%"
    },
    "high_error_rate": {
        "metric": "request_error_rate",
        "condition": ">",
        "threshold": 1,
        "duration": "10m",
        "severity": "critical",
        "message": "请求错误率超过1%"
    }
}
```

#### 3.2.3 健康检查端点

```python
from flask import jsonify

@app.route('/health')
def health_check():
    """健康检查端点"""
    checks = {
        "database": check_database(),
        "redis": check_redis(),
        "agent_sdk": check_agent_sdk()
    }
    
    status = "healthy" if all(checks.values()) else "unhealthy"
    status_code = 200 if status == "healthy" else 503
    
    return jsonify({
        "status": status,
        "checks": checks,
        "timestamp": datetime.now().isoformat()
    }), status_code

@app.route('/ready')
def readiness_check():
    """就绪检查端点"""
    return jsonify({"status": "ready"}), 200
```

### 3.3 配置管理

#### 3.3.1 配置文件结构

```
config/
├── default.py          # 默认配置
├── development.py      # 开发环境配置
├── testing.py          # 测试环境配置
├── production.py       # 生产环境配置
└── config.json         # 运行时配置
```

#### 3.3.2 配置类设计

```python
import os
import json
from dataclasses import dataclass
from typing import Optional

@dataclass
class DatabaseConfig:
    """数据库配置"""
    path: str = "arthas.db"
    pool_size: int = 5
    max_overflow: int = 10
    echo: bool = False

@dataclass
class AgentConfig:
    """Agent配置"""
    preferred_agent: str = "codebuddy"
    fallback_order: list = None
    timeout: int = 30
    max_concurrent: int = 10

@dataclass
class AppConfig:
    """应用配置"""
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 5000
    database: DatabaseConfig = None
    agent: AgentConfig = None

class ConfigManager:
    """配置管理器"""
    
    _instance = None
    _config: Optional[AppConfig] = None
    
    @classmethod
    def get_instance(cls):
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def load_config(self, config_path: str = None):
        """加载配置"""
        if config_path is None:
            config_path = os.getenv("APP_CONFIG", "config/config.json")
        
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                config_data = json.load(f)
            self._config = self._parse_config(config_data)
        else:
            self._config = AppConfig()
    
    def get_config(self) -> AppConfig:
        """获取配置"""
        if self._config is None:
            self.load_config()
        return self._config
```

---

## 4. 文档体系

### 4.1 文档分类

| 文档类型 | 存放位置 | 说明 |
|---------|---------|------|
| **架构文档** | `docs/superpowers/specs/` | 系统架构设计 |
| **实施计划** | `docs/superpowers/plans/` | 项目实施计划 |
| **评审报告** | `docs/superpowers/review/` | 架构评审记录 |
| **API文档** | `docs/api/` | API接口文档 |
| **用户手册** | `docs/user/` | 用户使用手册 |
| **运维手册** | `docs/ops/` | 运维操作手册 |

### 4.2 文档模板

#### 4.2.1 API文档模板

```markdown
# API名称

## 基本信息

| 项目 | 内容 |
|------|------|
| URL | `/api/v1/resource` |
| Method | `POST` |
| 认证 | 需要Bearer Token |

## 请求参数

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| name | string | 是 | 资源名称 |
| type | string | 否 | 资源类型 |

## 请求示例

```json
{
  "name": "test",
  "type": "diagnosis"
}
```

## 响应示例

```json
{
  "ok": true,
  "data": {
    "id": 1,
    "name": "test"
  }
}
```

## 错误码

| 错误码 | 说明 |
|--------|------|
| 400 | 参数错误 |
| 401 | 未认证 |
| 403 | 无权限 |
| 404 | 资源不存在 |
```

### 4.3 文档更新流程

```
代码变更
    │
    ├── 是否影响API
    │       ├── 是 → 更新API文档
    │       └── 否 → 跳过
    │
    ├── 是否影响架构
    │       ├── 是 → 更新架构文档
    │       └── 否 → 跳过
    │
    └── 是否影响用户操作
            ├── 是 → 更新用户手册
            └── 否 → 跳过
```

---

## 5. 版本管理

### 5.1 版本号规范

采用 **语义化版本号** (Semantic Versioning)：

```
MAJOR.MINOR.PATCH
```

| 版本号 | 说明 | 示例 |
|--------|------|------|
| **MAJOR** | 不兼容的API变更 | 2.0.0 |
| **MINOR** | 向后兼容的功能新增 | 1.1.0 |
| **PATCH** | 向后兼容的问题修复 | 1.0.1 |

### 5.2 发布流程

```
代码完成
    │
    ▼
代码审查
    │
    ├── 通过 → 合并到main分支
    └── 不通过 → 返回修改
            │
            ▼
        更新版本号
            │
            ▼
        生成CHANGELOG
            │
            ▼
        打Tag
            │
            ▼
        部署到测试环境
            │
            ▼
        测试通过
            │
            ├── 是 → 部署到生产环境
            └── 否 → 返回修复
```

### 5.3 CHANGELOG格式

```markdown
# Changelog

## [1.1.0] - 2026-05-24

### Added
- 新增Skill Registry模块
- 新增Workflow Engine模块
- 新增Agent Tool Gateway模块

### Changed
- 优化数据模型，删除多余字段
- 重构前端组件结构

### Fixed
- 修复连接状态恢复问题
- 修复多标签页状态同步问题

### Deprecated
- 弃用旧版诊断API

### Removed
- 移除capability_versions表

### Security
- 修复命令注入漏洞
```

---

## 6. 备份与恢复

### 6.1 数据备份策略

| 数据类型 | 备份频率 | 保留时间 | 备份方式 |
|---------|---------|---------|---------|
| **数据库** | 每日 | 30天 | 文件拷贝 |
| **配置文件** | 每次变更 | 永久 | Git版本控制 |
| **日志文件** | 每周 | 90天 | 压缩归档 |
| **用户上传** | 实时 | 永久 | 异地备份 |

### 6.2 备份脚本

```bash
#!/bin/bash
# backup.sh - 数据库备份脚本

BACKUP_DIR="/backup/arthas"
DB_PATH="/data/arthas.db"
DATE=$(date +%Y%m%d_%H%M%S)

# 创建备份目录
mkdir -p $BACKUP_DIR

# 备份数据库
cp $DB_PATH $BACKUP_DIR/arthas_$DATE.db

# 压缩备份
gzip $BACKUP_DIR/arthas_$DATE.db

# 删除30天前的备份
find $BACKUP_DIR -name "arthas_*.db.gz" -mtime +30 -delete

echo "Backup completed: arthas_$DATE.db.gz"
```

### 6.3 恢复流程

```
数据丢失
    │
    ▼
停止服务
    │
    ▼
确定恢复时间点
    │
    ▼
下载备份文件
    │
    ▼
恢复数据库
    │
    ▼
验证数据完整性
    │
    ├── 通过 → 启动服务
    └── 不通过 → 联系管理员
```

---

## 7. 性能优化

### 7.1 数据库优化

#### 7.1.1 索引优化

```sql
-- 核心查询索引
CREATE INDEX idx_task_logs_status ON task_logs(status);
CREATE INDEX idx_task_logs_created_at ON task_logs(created_at);
CREATE INDEX idx_step_logs_run_id ON step_logs(run_id);
CREATE INDEX idx_audit_logs_user_id ON audit_logs(user_id);

-- 复合索引
CREATE INDEX idx_task_logs_user_status ON task_logs(user_id, status);
CREATE INDEX idx_task_logs_capability_status ON task_logs(capability_id, status);
```

#### 7.1.2 查询优化

```python
# ❌ 不好的写法
def get_all_tasks():
    tasks = db.fetch_all("SELECT * FROM task_logs")
    for task in tasks:
        task['steps'] = db.fetch_all(
            "SELECT * FROM step_logs WHERE run_id = ?", 
            (task['id'],)
        )
    return tasks

# ✅ 好的写法
def get_all_tasks():
    tasks = db.fetch_all("""
        SELECT t.*, COUNT(s.id) as step_count
        FROM task_logs t
        LEFT JOIN step_logs s ON t.id = s.run_id
        GROUP BY t.id
        ORDER BY t.created_at DESC
        LIMIT 20
    """)
    return tasks
```

### 7.2 缓存策略

#### 7.2.1 缓存层次

| 缓存层 | 说明 | TTL |
|--------|------|-----|
| **浏览器缓存** | 静态资源缓存 | 1小时 |
| **CDN缓存** | 静态文件分发 | 24小时 |
| **应用缓存** | 热点数据缓存 | 5分钟 |
| **数据库缓存** | 查询结果缓存 | 1分钟 |

#### 7.2.2 缓存实现

```python
from functools import lru_cache
from datetime import datetime, timedelta

class CacheManager:
    """缓存管理器"""
    
    def __init__(self):
        self._cache = {}
        self._timestamps = {}
    
    def get(self, key: str):
        """获取缓存"""
        if key in self._cache:
            timestamp = self._timestamps.get(key)
            if timestamp and datetime.now() - timestamp < timedelta(minutes=5):
                return self._cache[key]
            else:
                del self._cache[key]
                del self._timestamps[key]
        return None
    
    def set(self, key: str, value, ttl: int = 300):
        """设置缓存"""
        self._cache[key] = value
        self._timestamps[key] = datetime.now()
    
    def delete(self, key: str):
        """删除缓存"""
        self._cache.pop(key, None)
        self._timestamps.pop(key, None)

# 使用示例
cache = CacheManager()

def get_skill(skill_id: int):
    """获取Skill（带缓存）"""
    cache_key = f"skill:{skill_id}"
    cached = cache.get(cache_key)
    
    if cached:
        return cached
    
    skill = db.fetch_one("SELECT * FROM skill_registry WHERE id = ?", (skill_id,))
    if skill:
        cache.set(cache_key, skill)
    
    return skill
```

### 7.3 异步处理

#### 7.3.1 异步任务队列

```python
import asyncio
from queue import Queue
from threading import Thread

class AsyncTaskQueue:
    """异步任务队列"""
    
    def __init__(self, max_workers: int = 5):
        self.queue = Queue()
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
            task_func, args, kwargs = self.queue.get()
            try:
                task_func(*args, **kwargs)
            except Exception as e:
                logger.error(f"Async task failed: {e}")
            finally:
                self.queue.task_done()
    
    def submit(self, task_func, *args, **kwargs):
        """提交任务"""
        self.queue.put((task_func, args, kwargs))

# 使用示例
async_queue = AsyncTaskQueue(max_workers=5)
async_queue.start()

# 提交异步任务
async_queue.submit(send_notification, user_id=123, message="任务完成")
```

### 7.4 并发控制

#### 7.4.1 信号量控制

```python
import asyncio
from asyncio import Semaphore

class ConcurrencyLimiter:
    """并发限制器"""
    
    def __init__(self, max_concurrent: int = 10):
        self.semaphore = Semaphore(max_concurrent)
        self.active_count = 0
    
    async def acquire(self):
        """获取信号量"""
        await self.semaphore.acquire()
        self.active_count += 1
    
    def release(self):
        """释放信号量"""
        self.semaphore.release()
        self.active_count -= 1
    
    def get_active_count(self) -> int:
        """获取当前并发数"""
        return self.active_count

# 使用示例
limiter = ConcurrencyLimiter(max_concurrent=10)

async def execute_task(task_id: int):
    """执行任务（带并发限制）"""
    await limiter.acquire()
    try:
        # 执行任务
        result = await do_something(task_id)
        return result
    finally:
        limiter.release()
```

---

**文档结束**
