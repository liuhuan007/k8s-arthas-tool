# K8s Arthas 智能诊断平台 - 编码规范

## 概述

本文档定义了 K8s Arthas 智能诊断平台的编码规范，确保代码质量、可维护性和团队协作效率。

---

## Python 编码规范

### 命名规范

| 类型 | 规范 | 示例 |
|------|------|------|
| **模块** | 小写+下划线 | `skill_registry.py` |
| **类** | 大驼峰 | `SkillOrchestrator` |
| **函数** | 小写+下划线 | `execute_capability()` |
| **变量** | 小写+下划线 | `connection_id` |
| **常量** | 大写+下划线 | `MAX_CONCURRENT_TASKS` |
| **私有** | 单下划线前缀 | `_validate_params()` |

### 代码风格

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

### 错误处理

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

### 类型注解

```python
from typing import Optional, List, Dict, Any
from datetime import datetime

def get_skill(skill_id: int) -> Optional[Dict[str, Any]]:
    """获取Skill"""
    pass

def list_skills(
    status: Optional[str] = None,
    category: Optional[str] = None
) -> List[Dict[str, Any]]:
    """列出Skills"""
    pass
```

### 文档字符串

```python
def validate_parameter(name: str, value: str) -> tuple[bool, str]:
    """校验参数值

    根据参数类型和白名单规则校验参数值是否合法。

    Args:
        name: 参数名称
        value: 参数值

    Returns:
        tuple[bool, str]: (是否合法, 错误信息)

    Example:
        >>> validate_parameter("class", "com.example.Service")
        (True, "")
        >>> validate_parameter("class", "com.example; rm -rf /")
        (False, "参数 class 包含禁止字符")
    """
    pass
```

---

## JavaScript 编码规范

### 命名规范

| 类型 | 规范 | 示例 |
|------|------|------|
| **变量** | 小驼峰 | `connectionId` |
| **函数** | 小驼峰 | `executeCapability()` |
| **类** | 大驼峰 | `SkillOrchestrator` |
| **常量** | 大写+下划线 | `MAX_RETRY_COUNT` |
| **DOM元素** | 小写+短横线 | `data-tab="diagnosis"` |

### 代码风格

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

### 错误处理

```javascript
// ✅ 正确的错误处理
async function executeSkill(skillId) {
  try {
    const skill = await getSkill(skillId);
    if (!skill) {
      throw new Error(`Skill ${skillId} not found`);
    }

    const result = await orchestrator.execute(skill);
    return result;
  } catch (error) {
    console.error('Execute skill failed:', error);
    throw error;
  }
}
```

---

## 文件组织

### 目录结构

```
k8s-arthas-tool/
├── api/                    # API 路由
├── backend/                # 后端核心逻辑
│   ├── config.py          # 配置
│   └── core/              # 核心模块
├── models/                 # 数据模型
├── services/               # 业务服务
├── static/                 # 前端静态文件
├── tests/                  # 测试
└── docs/                   # 文档
```

### 文件命名

- **Python**: 小写+下划线 (`skill_registry.py`)
- **JavaScript**: 小驼峰 (`app-ui.js`)
- **CSS**: 小写+短横线 (`app.css`)
- **HTML**: 小写+短横线 (`connection-detail.html`)

---

## 代码审查清单

### 功能性审查

- [ ] 功能完整性：是否完整实现了需求
- [ ] 边界条件：是否处理了边界情况
- [ ] 错误处理：是否有完善的错误处理
- [ ] 输入校验：是否校验了所有输入

### 非功能性审查

- [ ] 性能：是否有性能问题
- [ ] 安全性：是否有安全漏洞
- [ ] 可维护性：代码是否易于维护
- [ ] 可测试性：代码是否易于测试

### 文档审查

- [ ] 文档字符串：是否有完整的文档字符串
- [ ] 注释：复杂逻辑是否有注释
- [ ] README：是否有使用说明

---

## 提交规范

### Commit Message 格式

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Type 类型

- **feat**: 新功能
- **fix**: 修复 Bug
- **docs**: 文档更新
- **style**: 代码格式（不影响功能）
- **refactor**: 重构
- **test**: 测试相关
- **chore**: 构建/工具相关

### 示例

```
feat(skill): 添加 Skill Registry 服务

- 实现 Skill 导入、校验、发布功能
- 添加 14 个内置 Skill 预制数据
- 添加单元测试

Closes #123
```

---

## 测试规范

### 单元测试

```python
import pytest
from services.skill_registry import SkillRegistry

class TestSkillRegistry:
    """SkillRegistry 单元测试"""

    def test_import_skill_success(self):
        """测试导入 Skill 成功"""
        registry = SkillRegistry(":memory:")

        skill_data = {
            "name": "test-skill",
            "version": "1.0.0",
            "category": "quick",
            "level": 1,
            "description": "测试Skill"
        }

        skill_id = registry.import_skill(skill_data)
        assert skill_id > 0

    def test_import_skill_missing_field(self):
        """测试导入 Skill 缺少必填字段"""
        registry = SkillRegistry(":memory:")

        skill_data = {
            "name": "test-skill",
            # 缺少 version
            "category": "quick",
            "level": 1
        }

        with pytest.raises(ValueError, match="Missing required field: version"):
            registry.import_skill(skill_data)
```

### 测试覆盖率

- 核心模块：> 80%
- 工具函数：> 90%
- API 接口：> 70%

---

## Git 工作流

### 分支命名

- **feature/**: 新功能 (`feature/skill-registry`)
- **fix/**: 修复 Bug (`fix/connection-timeout`)
- **docs/**: 文档更新 (`docs/api-reference`)
- **refactor/**: 重构 (`refactor/workflow-engine`)

### Pull Request 规范

1. 标题清晰描述变更内容
2. 包含变更说明和测试结果
3. 至少一人审查通过
4. CI 检查通过

---

## 性能优化

### 数据库查询

```python
# ✅ 使用索引
CREATE INDEX idx_task_logs_status ON task_logs(status);

# ✅ 避免 SELECT *
SELECT id, name, status FROM task_logs WHERE status = 'running'

# ✅ 分页查询
SELECT * FROM task_logs
ORDER BY created_at DESC
LIMIT 20 OFFSET 0;
```

### 缓存策略

| 数据类型 | 缓存位置 | TTL | 更新策略 |
|---------|---------|-----|---------|
| **静态资源** | 浏览器/CDN | 1小时 | 版本号更新 |
| **配置数据** | 应用内存 | 5分钟 | 定时刷新 |
| **Skill定义** | 应用内存 | 5分钟 | 变更时刷新 |

---

## 安全规范

### 输入校验

```python
import re

# 参数白名单正则表达式
PARAM_PATTERNS = {
    'class': r'^[A-Za-z_$][\w.$]*$',      # Java类名
    'method': r'^[\w*]+$',                  # 方法名
    'namespace': r'^[a-z0-9-]+$',           # K8s命名空间
    'pod_name': r'^[a-z0-9]([-a-z0-9]*[a-z0-9])?$',  # Pod名称
}
```

### 敏感数据处理

```python
SENSITIVE_FIELDS = ['password', 'token', 'secret', 'key']

def mask_sensitive_data(data: dict) -> dict:
    """脱敏敏感数据"""
    masked = {}
    for key, value in data.items():
        if any(field in key.lower() for field in SENSITIVE_FIELDS):
            masked[key] = '***'
        else:
            masked[key] = value
    return masked
```

---

## 版本管理

### 语义化版本

- **MAJOR**: 不兼容的 API 变更
- **MINOR**: 向后兼容的功能性新增
- **PATCH**: 向后兼容的问题修复

### 示例

- `1.0.0`: 初始版本
- `1.1.0`: 添加 Skill Registry
- `1.1.1`: 修复 Skill 校验 Bug

---

**文档版本**: v1.0
**最后更新**: 2026-05-24
