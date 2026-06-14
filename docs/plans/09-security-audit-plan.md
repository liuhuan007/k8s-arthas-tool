# 安全审计实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 实现安全审计，包括认证授权、审计日志、安全防护、敏感数据保护等。

**Architecture:** 安全审计作为系统基础层，为所有业务模块提供安全保障。采用多层次安全策略，包括认证、授权、审计、加密、脱敏等。

**Tech Stack:** Python, Flask, bcrypt, Flask-Login, 审计日志

---

## 1. 目标

实现安全审计，包括认证授权、审计日志、安全防护、敏感数据保护等。

## 2. 架构

安全审计作为系统基础层，为所有业务模块提供安全保障。采用多层次安全策略，包括认证、授权、审计、加密、脱敏等。

## 3. 安全策略

### 3.1 认证策略

| 策略 | 说明 | 实现 |
|------|------|------|
| 用户名密码 | 基础认证 | bcrypt 哈希 |
| Session 管理 | 会话管理 | Flask-Login |
| 超时控制 | 会话超时 | 30分钟无操作 |
| 并发控制 | 多设备登录 | 单设备登录 |

### 3.2 授权策略

| 策略 | 说明 | 实现 |
|------|------|------|
| RBAC | 基于角色的访问控制 | admin/user 角色 |
| 资源授权 | 集群级别授权 | user_clusters 表 |
| 操作授权 | API 级别授权 | @admin_required 装饰器 |
| 数据隔离 | 用户数据隔离 | user_id 过滤 |

### 3.3 审计策略

| 策略 | 说明 | 实现 |
|------|------|------|
| 操作审计 | 记录所有操作 | audit_logs 表 |
| 资源审计 | 记录资源变更 | resource_id 字段 |
| 安全审计 | 记录安全事件 | risk_level 字段 |
| 保留策略 | 审计日志保留 | 90天自动清理 |

## 4. 安全防护

### 4.1 输入校验

```python
# 参数白名单正则表达式
PARAM_PATTERNS = {
    'class': r'^[A-Za-z_$][\w.$]*$',      # Java类名
    'method': r'^[\w*]+$',                  # 方法名（支持通配符*）
    'namespace': r'^[a-z0-9-]+$',           # K8s命名空间
    'pod_name': r'^[a-z0-9]([-a-z0-9]*[a-z0-9])?$',  # Pod名称
    'container': r'^[a-z0-9]([-a-z0-9]*[a-z0-9])?$',  # 容器名
    'default': r'^[a-zA-Z0-9_./-]+$'       # 默认：只允许字母、数字、下划线、点、斜杠、横杠
}
```

### 4.2 命令注入防护

```python
def validate_parameter(name: str, value: str) -> Tuple[bool, str]:
    """校验参数值"""
    pattern = PARAM_PATTERNS.get(name, PARAM_PATTERNS['default'])
    if not re.match(pattern, value):
        return False, f"参数 {name} 包含非法字符"
    return True, ""
```

### 4.3 敏感数据脱敏

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

### 4.4 危险命令识别

```python
DANGEROUS_COMMANDS = [
    'redefine',  # 热更新
    'ognl',      # OGNL表达式
    'ognl '@java.lang.Runtime@getRuntime().exec(...)'',  # 命令执行
]

def is_dangerous_command(command: str) -> bool:
    """识别危险命令"""
    return any(cmd in command for cmd in DANGEROUS_COMMANDS)
```

## 5. 审计日志

### 5.1 审计日志表

```sql
CREATE TABLE audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    action TEXT NOT NULL,
    resource_type TEXT,
    resource_id TEXT,
    execution_mode TEXT,
    risk_level TEXT,
    details TEXT,
    ip_address TEXT,
    user_agent TEXT,
    duration_ms INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
```

### 5.2 审计日志记录

```python
def log_audit(action: str, resource_type: str = None, resource_id: str = None,
              details: str = None, risk_level: str = 'low'):
    """记录审计日志"""
    user_id = get_current_user_id()
    ip_address = request.remote_addr
    user_agent = request.user_agent.string
    
    db.execute(
        """INSERT INTO audit_logs 
           (user_id, action, resource_type, resource_id, risk_level, details, ip_address, user_agent)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (user_id, action, resource_type, resource_id, risk_level, details, ip_address, user_agent)
    )
    db.commit()
```

### 5.3 审计日志查询

```python
def query_audit_logs(user_id: int = None, action: str = None,
                     resource_type: str = None, start_date: str = None,
                     end_date: str = None, page: int = 1, per_page: int = 20):
    """查询审计日志"""
    query = "SELECT * FROM audit_logs WHERE 1=1"
    params = []
    
    if user_id:
        query += " AND user_id = ?"
        params.append(user_id)
    if action:
        query += " AND action = ?"
        params.append(action)
    if resource_type:
        query += " AND resource_type = ?"
        params.append(resource_type)
    if start_date:
        query += " AND created_at >= ?"
        params.append(start_date)
    if end_date:
        query += " AND created_at <= ?"
        params.append(end_date)
    
    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([per_page, (page - 1) * per_page])
    
    return db.execute(query, params).fetchall()
```

## 6. 敏感命令确认机制

### 6.1 命令风险等级

| 风险等级 | 说明 | 确认要求 |
|---------|------|---------|
| low | 低风险命令 | 无需确认 |
| medium | 中风险命令 | 二次确认 |
| high | 高风险命令 | 强制确认 + 审计 |

### 6.2 确认流程

```
用户执行命令 → 风险评估 → 低风险直接执行
                      ↓
                中风险弹窗确认 → 确认执行
                      ↓
                高风险强制确认 + 审计日志 → 确认执行
```

## 7. 任务分解

### 任务 1：实现认证授权

**文件：**
- 修改：`services/auth_service.py`
- 修改：`services/authorization_service.py`
- 修改：`models/user.py`

**步骤：**
1. 实现用户名密码认证
2. 实现 Session 管理
3. 实现 RBAC 授权
4. 实现资源授权
5. 实现数据隔离
6. 编写单元测试

### 任务 2：实现审计日志

**文件：**
- 修改：`services/audit_service.py`
- 修改：`models/db.py`

**步骤：**
1. 创建审计日志表
2. 实现审计日志记录
3. 实现审计日志查询
4. 实现审计日志清理
5. 编写单元测试

### 任务 3：实现输入校验

**文件：**
- 创建：`services/validator.py`
- 修改：`api/task_center.py`

**步骤：**
1. 定义参数白名单
2. 实现参数校验函数
3. 集成到 API 接口
4. 编写单元测试

### 任务 4：实现命令注入防护

**文件：**
- 创建：`services/command_validator.py`
- 修改：`api/arthas.py`

**步骤：**
1. 识别危险命令
2. 实现命令校验
3. 集成到 Arthas 执行
4. 编写单元测试

### 任务 5：实现敏感数据脱敏

**文件：**
- 创建：`services/data_masker.py`
- 修改：`api/audit.py`

**步骤：**
1. 识别敏感字段
2. 实现脱敏函数
3. 集成到审计日志
4. 编写单元测试

### 任务 6：实现危险命令确认

**文件：**
- 创建：`api/confirmation.py`
- 修改：`static/js/components/confirmation.js`

**步骤：**
1. 定义命令风险等级
2. 实现确认 API
3. 实现前端确认弹窗
4. 编写单元测试

### 任务 7：实现安全审计

**文件：**
- 修改：`api/audit.py`
- 修改：`static/js/components/audit-logs.js`

**步骤：**
1. 实现审计日志查询 API
2. 实现审计日志前端展示
3. 实现审计日志导出
4. 编写单元测试

### 任务 8：实现加密存储

**文件：**
- 创建：`services/encryption.py`
- 修改：`services/auth_service.py`

**步骤：**
1. 实现密码加密
2. 实现敏感数据加密
3. 实现密钥管理
4. 编写单元测试

## 8. 验收标准

- [ ] 认证授权实现完成
- [ ] 审计日志实现完成
- [ ] 输入校验实现完成
- [ ] 命令注入防护实现完成
- [ ] 敏感数据脱敏实现完成
- [ ] 危险命令确认实现完成
- [ ] 安全审计实现完成
- [ ] 加密存储实现完成
- [ ] 单元测试覆盖率 > 80%
- [ ] 安全测试通过

## 9. 风险与缓解措施

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 认证绕过 | 高 | 多因素认证 |
| 权限提升 | 高 | 最小权限原则 |
| 审计日志篡改 | 高 | 只追加不可修改 |
| 敏感数据泄露 | 高 | 加密存储 + 脱敏 |

## 10. 后续演进

### P1 阶段

- 实现多因素认证
- 实现 OAuth2 集成
- 实现 API 限流

### P2 阶段

- 实现零信任架构
- 实现安全态势感知
- 实现自动化安全测试
