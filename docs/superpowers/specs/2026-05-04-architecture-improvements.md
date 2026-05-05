# 架构评审改进方案

> 基于第13章模块架构与前端交互设计的架构师评审建议

**评审日期**: 2026-05-04  
**状态**: 已采纳改进

---

## 改进清单

### ✅ 改进 1：统一执行记录模型（高风险）

**问题**：原文档存在 `diagnosis_execution_logs` 和 `task_logs` 双表并存的架构风险。

**改进方案**：

#### 1.1 废弃 diagnosis_execution_logs，统一使用 task_logs

```sql
-- 原有表重命名
ALTER TABLE task_runs RENAME TO task_logs;

-- 扩展字段支持诊断能力
ALTER TABLE task_logs ADD COLUMN capability_id INTEGER REFERENCES diagnosis_capabilities(id);
ALTER TABLE task_logs ADD COLUMN execution_type TEXT;  -- diagnosis | script | pod_exec | node_exec
ALTER TABLE task_logs ADD COLUMN capability_name TEXT;  -- 冗余，防止能力被删除后丢失
ALTER TABLE task_logs ADD COLUMN rendered_command TEXT;  -- 参数替换后的实际命令

-- 索引
CREATE INDEX idx_task_logs_capability_id ON task_logs(capability_id);
CREATE INDEX idx_task_logs_execution_mode ON task_logs(execution_mode);
CREATE INDEX idx_task_logs_execution_type ON task_logs(execution_type);
CREATE INDEX idx_task_logs_cluster_ns_pod ON task_logs(cluster_name, namespace, pod_name);
```

#### 1.2 执行模式统一

| 执行来源 | execution_mode | capability_id | task_id | 说明 |
|---------|----------------|---------------|---------|------|
| 即时诊断 | `immediate` | ✅ 有 | ❌ NULL | 用户直接执行诊断能力 |
| 定时任务 | `scheduled` | 可选 | ✅ 有 | 从 task_definitions 触发 |
| 手动任务 | `manual` | ❌ NULL | ✅ 有 | 通用脚本/Pod/Node 任务 |

#### 1.3 统一查询示例

```sql
-- 查询某用户的所有诊断历史（跨模块）
SELECT 
    tl.id, 
    tl.capability_name,
    tl.execution_mode,
    tl.status,
    tl.duration_ms,
    tl.started_at,
    tl.cluster_name,
    tl.namespace,
    tl.pod_name
FROM task_logs tl
WHERE tl.user_id = ?
ORDER BY tl.started_at DESC
LIMIT 50;
```

---

### ✅ 改进 2：场景方案执行模型明确化（中风险）

**问题**：原文档提到"WebSocket 推送步骤状态"，但当前系统无 WebSocket 基础设施。

**改进方案**：

#### 2.1 采用 HTTP 轮询机制

```python
# backend/diagnosis_executor.py

class ScenarioExecutor:
    """场景方案执行器（异步 + HTTP 轮询）"""
    
    def execute_async(self, capability_id, params, user_id, connection):
        """异步执行场景方案
        
        返回 execution_id，前端通过轮询查询进度
        """
        execution_id = str(uuid4())
        
        # 创建执行记录
        task_log_id = db.insert('task_logs', {
            'id': execution_id,
            'capability_id': capability_id,
            'capability_name': capability.name,
            'execution_mode': 'immediate',
            'execution_type': 'diagnosis',
            'user_id': user_id,
            'status': 'running',
            'cluster_name': connection.cluster_name,
            'namespace': connection.namespace,
            'pod_name': connection.pod_name,
            'params_json': json.dumps(params),
            'started_at': datetime.now(),
        })
        
        # 后台线程执行
        thread = threading.Thread(
            target=self._execute_scenario,
            args=(execution_id, capability_id, params, connection),
            daemon=True
        )
        thread.start()
        
        return {'ok': True, 'execution_id': execution_id}
    
    def _execute_scenario(self, execution_id, capability_id, params, connection):
        """后台执行场景方案"""
        try:
            capability = db.get('diagnosis_capabilities', capability_id)
            steps = db.query(
                'SELECT * FROM diagnosis_scenario_steps WHERE capability_id=? ORDER BY step_order',
                (capability_id,)
            )
            
            previous_outputs = []
            
            for idx, step in enumerate(steps):
                try:
                    # 解析步骤引用（${step1.output}）
                    command = resolve_step_references(step['command'], params, previous_outputs)
                    
                    # 执行命令
                    result = execute_arthas_command(connection, command, step['timeout_ms'])
                    
                    # 记录命令历史
                    db.insert('arthas_command_logs', {
                        'task_log_id': execution_id,
                        'step_order': idx + 1,
                        'command': command,
                        'command_type': extract_command_type(command),
                        'status': 'success',
                        'output_json': json.dumps(result),
                        'duration_ms': result.get('duration_ms'),
                    })
                    
                    previous_outputs.append({'step': idx + 1, 'output': result})
                    
                    # 更新任务状态（前端轮询可见）
                    db.update('task_logs', {
                        'status': 'running',
                        'current_step': idx + 1,
                        'total_steps': len(steps),
                    }, {'id': execution_id})
                    
                except Exception as e:
                    db.insert('arthas_command_logs', {
                        'task_log_id': execution_id,
                        'step_order': idx + 1,
                        'command': step['command'],
                        'status': 'failed',
                        'error_message': str(e),
                    })
                    
                    if step.get('fail_fast', 1):
                        raise  # 立即终止
                    
                    # 否则继续执行
                    
            # 执行完成
            db.update('task_logs', {
                'status': 'success',
                'current_step': len(steps),
                'finished_at': datetime.now(),
            }, {'id': execution_id})
            
        except Exception as e:
            db.update('task_logs', {
                'status': 'failed',
                'error_message': str(e),
                'finished_at': datetime.now(),
            }, {'id': execution_id})
```

#### 2.2 前端轮询实现

```javascript
// static/js/components/diagnosis.js

class DiagnosisExecutor {
  constructor() {
    this.pollingInterval = null;
    this.currentExecutionId = null;
  }
  
  async executeScenario(capabilityId, params) {
    // 1. 发起执行请求
    const resp = await fetch('/api/diagnosis/execute', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        capability_id: capabilityId,
        params: params,
      }),
    });
    
    const data = await resp.json();
    if (!data.ok) throw new Error(data.error);
    
    this.currentExecutionId = data.execution_id;
    
    // 2. 开始轮询进度
    this.startPolling();
    
    // 3. 显示执行面板
    this.showExecutionPanel();
  }
  
  startPolling() {
    this.pollingInterval = setInterval(async () => {
      try {
        const resp = await fetch(`/api/diagnosis/executions/${this.currentExecutionId}/status`);
        const data = await resp.json();
        
        this.updateProgress(data);
        
        // 执行完成，停止轮询
        if (data.status === 'success' || data.status === 'failed') {
          this.stopPolling();
          this.showResult(data);
        }
      } catch (e) {
        console.error('轮询失败:', e);
      }
    }, 2000);  // 每2秒轮询一次
  }
  
  stopPolling() {
    if (this.pollingInterval) {
      clearInterval(this.pollingInterval);
      this.pollingInterval = null;
    }
  }
  
  updateProgress(data) {
    const { current_step, total_steps, status } = data;
    
    // 更新进度条
    const progressEl = document.getElementById('scenario-progress');
    progressEl.innerHTML = `
      <div class="progress-bar">
        <div class="progress-fill" style="width: ${(current_step / total_steps) * 100}%"></div>
      </div>
      <div class="progress-text">Step ${current_step}/${total_steps}</div>
    `;
    
    // 更新步骤状态
    for (let i = 1; i <= total_steps; i++) {
      const stepEl = document.getElementById(`step-${i}`);
      if (i < current_step) {
        stepEl.className = 'step completed';  // ✅ 绿色
      } else if (i === current_step && status === 'running') {
        stepEl.className = 'step running';     // 🔄 旋转
      } else {
        stepEl.className = 'step pending';     // ⏸️ 灰色
      }
    }
  }
  
  async cancelExecution() {
    if (!this.currentExecutionId) return;
    
    await fetch(`/api/diagnosis/executions/${this.currentExecutionId}/cancel`, {
      method: 'POST',
    });
    
    this.stopPolling();
    toast('已取消执行', 'info');
  }
}
```

#### 2.3 API 路由

```python
# api/diagnosis.py

@app.route('/api/diagnosis/execute', methods=['POST'])
@require_login
def execute_diagnosis():
    """执行诊断能力（即时/场景方案）"""
    data = request.json
    capability_id = data.get('capability_id')
    params = data.get('params', {})
    
    capability = db.get('diagnosis_capabilities', capability_id)
    if not capability:
        return jsonify({'ok': False, 'error': '能力不存在'}), 404
    
    # 获取当前连接
    connection = get_current_connection()
    if not connection:
        return jsonify({'ok': False, 'error': '未建立连接'}), 400
    
    executor = ScenarioExecutor()
    result = executor.execute_async(
        capability_id=capability_id,
        params=params,
        user_id=session['user_id'],
        connection=connection
    )
    
    return jsonify(result)


@app.route('/api/diagnosis/executions/<execution_id>/status', methods=['GET'])
@require_login
def get_execution_status(execution_id):
    """查询执行状态（前端轮询）"""
    task_log = db.get('task_logs', execution_id)
    if not task_log:
        return jsonify({'ok': False, 'error': '执行记录不存在'}), 404
    
    # 权限检查
    if task_log['user_id'] != session['user_id'] and not is_admin():
        return jsonify({'ok': False, 'error': '无权限'}), 403
    
    return jsonify({
        'ok': True,
        'status': task_log['status'],
        'current_step': task_log.get('current_step', 0),
        'total_steps': task_log.get('total_steps', 0),
        'result_json': task_log.get('result_json'),
        'error_message': task_log.get('error_message'),
    })


@app.route('/api/diagnosis/executions/<execution_id>/cancel', methods=['POST'])
@require_login
def cancel_execution(execution_id):
    """取消执行"""
    task_log = db.get('task_logs', execution_id)
    if not task_log:
        return jsonify({'ok': False, 'error': '执行记录不存在'}), 404
    
    if task_log['status'] not in ('running', 'pending'):
        return jsonify({'ok': False, 'error': '执行已完成，无法取消'}), 400
    
    db.update('task_logs', {
        'status': 'cancelled',
        'finished_at': datetime.now(),
    }, {'id': execution_id})
    
    return jsonify({'ok': True})
```

---

### ✅ 改进 3：AI 处理器安全边界强化（高风险）

**问题**：原文档使用硬编码白名单，新增能力需修改代码。

**改进方案**：

#### 3.1 数据库驱动的处理器注册表

```python
# backend/handler_registry.py

class HandlerRegistry:
    """诊断处理器注册表（数据库驱动）"""
    
    _cache = {}
    _cache_time = None
    _cache_ttl = 60  # 缓存60秒
    
    @classmethod
    def load_handlers(cls):
        """从数据库加载已注册的处理器"""
        # 检查缓存
        if cls._cache_time and (time.time() - cls._cache_time) < cls._cache_ttl:
            return cls._cache
        
        rows = db.query("""
            SELECT adh.handler, dc.is_enabled
            FROM ai_diagnosis_handlers adh
            JOIN diagnosis_capabilities dc ON adh.capability_id = dc.id
            WHERE dc.type = 'ai_diagnosis'
        """)
        
        cls._cache = {row['handler']: row['is_enabled'] for row in rows}
        cls._cache_time = time.time()
        
        return cls._cache
    
    @classmethod
    def execute(cls, handler_path, **kwargs):
        """安全执行处理器"""
        registry = cls.load_handlers()
        
        # 1. 检查是否注册
        if handler_path not in registry:
            raise SecurityError(f"未注册的处理器: {handler_path}")
        
        # 2. 检查是否启用
        if not registry[handler_path]:
            raise SecurityError(f"处理器已禁用: {handler_path}")
        
        # 3. 模块路径限制（仅允许 performance_diagnose 模块）
        if not handler_path.startswith('performance_diagnose.'):
            raise SecurityError(f"不允许的模块: {handler_path}")
        
        # 4. 动态加载
        module_path, func_name = handler_path.rsplit('.', 1)
        module = __import__(f'api.{module_path}', fromlist=[func_name])
        handler = getattr(module, func_name)
        
        # 5. 执行
        return handler(**kwargs)
    
    @classmethod
    def invalidate_cache(cls):
        """清除缓存（能力更新时调用）"""
        cls._cache = {}
        cls._cache_time = None
```

#### 3.2 AI 诊断执行流程

```python
# api/diagnosis.py

@app.route('/api/diagnosis/execute', methods=['POST'])
@require_login
def execute_diagnosis():
    """执行诊断能力"""
    data = request.json
    capability_id = data.get('capability_id')
    params = data.get('params', {})
    
    capability = db.get('diagnosis_capabilities', capability_id)
    if not capability:
        return jsonify({'ok': False, 'error': '能力不存在'}), 404
    
    connection = get_current_connection()
    
    # 根据能力类型分发执行
    if capability['type'] == 'ai_diagnosis':
        return execute_ai_diagnosis(capability, params, connection)
    elif capability['type'] == 'diagnosis_scenario':
        return execute_scenario(capability, params, connection)
    else:
        return execute_single_command(capability, params, connection)


def execute_ai_diagnosis(capability, params, connection):
    """执行 AI 诊断"""
    # 1. 获取处理器路径
    handler_record = db.query_one(
        'SELECT handler FROM ai_diagnosis_handlers WHERE capability_id = ?',
        (capability['id'],)
    )
    
    if not handler_record:
        return jsonify({'ok': False, 'error': 'AI 诊断未配置处理器'}), 500
    
    handler_path = handler_record['handler']
    
    # 2. 安全执行（通过注册表）
    try:
        diagnosis = HandlerRegistry.execute(
            handler_path,
            connection=connection,
            params=params,
        )
    except SecurityError as e:
        return jsonify({'ok': False, 'error': str(e)}), 403
    except Exception as e:
        return jsonify({'ok': False, 'error': f'执行失败: {str(e)}'}), 500
    
    # 3. 记录执行日志
    task_log_id = db.insert('task_logs', {
        'capability_id': capability['id'],
        'capability_name': capability['name'],
        'execution_mode': 'immediate',
        'execution_type': 'diagnosis',
        'user_id': session['user_id'],
        'status': 'success',
        'cluster_name': connection.cluster_name,
        'namespace': connection.namespace,
        'pod_name': connection.pod_name,
        'params_json': json.dumps(params),
        'result_json': json.dumps(diagnosis),
        'started_at': datetime.now(),
        'finished_at': datetime.now(),
    })
    
    return jsonify({'ok': True, 'diagnosis': diagnosis, 'task_log_id': task_log_id})
```

---

### ✅ 改进 4：前端状态管理机制（中风险）

**问题**：三个模块独立，但存在共享状态（当前连接、执行状态）。

**改进方案**：

```javascript
// static/js/core/diagnosis-context.js

/**
 * 诊断上下文管理器
 * 管理共享状态：当前连接、正在执行的任务
 */
const DiagnosisContext = {
  currentConnection: null,
  activeExecutions: new Map(),  // executionId → {status, capabilityId, startTime}
  listeners: new Set(),
  
  // 初始化
  init() {
    // 监听连接变化
    window.addEventListener('connection:changed', (e) => {
      this.onConnectionChange(e.detail);
    });
  },
  
  // 连接变化处理
  onConnectionChange(newConn) {
    const oldConn = this.currentConnection;
    
    // 连接切换，取消所有正在执行的诊断
    if (newConn?.id !== oldConn?.id) {
      console.log('[DiagnosisContext] 连接切换，取消所有执行');
      
      this.activeExecutions.forEach((exec, id) => {
        if (exec.status === 'running') {
          this.cancelExecution(id);
        }
      });
      this.activeExecutions.clear();
      
      this.notifyListeners('connectionChanged', {old: oldConn, new: newConn});
    }
    
    this.currentConnection = newConn;
  },
  
  // 注册执行任务
  registerExecution(executionId, capabilityId) {
    this.activeExecutions.set(executionId, {
      status: 'running',
      capabilityId,
      startTime: Date.now(),
    });
    this.notifyListeners('executionStarted', {executionId, capabilityId});
  },
  
  // 更新执行状态
  updateExecution(executionId, status) {
    const exec = this.activeExecutions.get(executionId);
    if (exec) {
      exec.status = status;
      this.notifyListeners('executionUpdated', {executionId, status});
      
      // 执行完成，清理
      if (status === 'success' || status === 'failed' || status === 'cancelled') {
        setTimeout(() => {
          this.activeExecutions.delete(executionId);
        }, 5000);  // 5秒后清理
      }
    }
  },
  
  // 取消执行
  async cancelExecution(executionId) {
    try {
      await fetch(`/api/diagnosis/executions/${executionId}/cancel`, {
        method: 'POST',
      });
      this.updateExecution(executionId, 'cancelled');
    } catch (e) {
      console.error('取消执行失败:', e);
    }
  },
  
  // 获取活跃执行数
  getActiveCount() {
    return Array.from(this.activeExecutions.values())
      .filter(e => e.status === 'running').length;
  },
  
  // 监听器
  addListener(fn) {
    this.listeners.add(fn);
  },
  
  removeListener(fn) {
    this.listeners.delete(fn);
  },
  
  notifyListeners(event, data) {
    this.listeners.forEach(fn => fn(event, data));
  }
};

// 导出到全局
window.DiagnosisContext = DiagnosisContext;
```

---

### ✅ 改进 5：场景方案步骤数据传递机制（中风险）

**问题**：原文档提到 `${stepN.field}` 但缺乏具体设计。

**改进方案**：

```python
# backend/step_reference_resolver.py

import re
import json


def resolve_step_references(command_template, params, previous_outputs):
    """解析步骤间的引用
    
    支持的语法：
    1. ${param} - 直接替换参数
    2. ${stepN.field} - 引用第N步的字段
    3. ${stepN} - 引用第N步的完整输出（JSON字符串）
    
    Args:
        command_template: 命令模板，如 "watch ${class} ${method} '${step1.top_threads}'"
        params: 用户输入的参数，如 {"class": "com.example.Service", "method": "doSomething"}
        previous_outputs: 前几步的输出，如 [
            {'step': 1, 'output': {'top_threads': ['thread-1', 'thread-2']}},
        ]
    
    Returns:
        替换后的命令
    """
    
    def replace_ref(match):
        ref = match.group(1)  # 如 "step1.top_threads" 或 "class"
        
        # 1. 检查是否是步骤引用
        if ref.startswith('step'):
            return resolve_step_ref(ref, previous_outputs)
        
        # 2. 普通参数替换
        return str(params.get(ref, match.group(0)))
    
    # 替换所有 ${...} 引用
    return re.sub(r'\$\{([^}]+)\}', replace_ref, command_template)


def resolve_step_ref(ref, previous_outputs):
    """解析步骤引用
    
    Args:
        ref: 引用字符串，如 "step1.top_threads" 或 "step1"
        previous_outputs: 前几步的输出列表
    """
    
    # 解析步骤号和字段名
    if '.' in ref:
        step_part, field = ref.split('.', 1)
    else:
        step_part = ref
        field = None
    
    # 提取步骤号
    step_num = int(step_part.replace('step', ''))
    step_idx = step_num - 1
    
    # 检查步骤是否存在
    if step_idx >= len(previous_outputs):
        raise ValueError(f"步骤 {step_num} 尚未执行")
    
    step_output = previous_outputs[step_idx]['output']
    
    # 无字段名，返回完整输出（JSON字符串）
    if field is None:
        return json.dumps(step_output)
    
    # 有字段名，提取字段
    value = step_output.get(field)
    if value is None:
        raise ValueError(f"步骤 {step_num} 无字段 '{field}'")
    
    # 复杂类型转JSON，简单类型转字符串
    if isinstance(value, (list, dict)):
        return json.dumps(value)
    return str(value)


# 使用示例
if __name__ == '__main__':
    command = "thread -n 5 '${step1.top_threads}'"
    params = {'class': 'com.example.Service'}
    previous_outputs = [
        {'step': 1, 'output': {'top_threads': ['thread-1', 'thread-2']}},
    ]
    
    result = resolve_step_references(command, params, previous_outputs)
    print(result)  # 输出: thread -n 5 '["thread-1", "thread-2"]'
```

---

## 改进后的第13章核心变更

### 13.1 三个模块职责划分（不变）

保持原有设计，职责分离明确。

### 13.2 诊断能力模块（核心变更）

#### 执行模型调整

**原文档**：诊断能力即时执行，无需创建 task_definition

**改进后**：
- 即时诊断仍直接执行，但执行记录统一写入 `task_logs`
- 场景方案采用 **异步执行 + HTTP 轮询**（非 WebSocket）
- AI 诊断通过 **数据库驱动的处理器注册表** 执行（非硬编码白名单）

#### 前端交互优化

**新增**：
1. **执行中断机制**：场景方案执行中提供"取消"按钮
2. **状态管理**：引入 `DiagnosisContext` 管理共享状态
3. **错误处理 UX**：
   - Arthas 连接断开时显示警告横幅
   - 参数校验失败时高亮错误字段
   - 执行失败时显示详细错误信息和重试建议

### 13.3 任务中心模块（微调）

**变更**：
- 执行记录表从 `task_runs` 重命名为 `task_logs`
- 增加 `capability_id` 字段支持关联诊断能力
- 查询逻辑统一，支持跨模块查询

### 13.4 工具箱模块（不变）

保持原有设计。

### 13.5 数据流转关系（重大调整）

**原文档**：
```
诊断能力 → diagnosis_execution_logs → arthas_command_history
任务中心 → task_logs
```

**改进后**：
```
所有执行 → task_logs（统一）
             ↓
      arthas_command_logs（场景方案多步骤）
```

### 13.6 实施优先级（调整）

| 阶段 | 模块 | 优先级 | 工期 | 核心交付 | 关键变更 |
|------|------|--------|------|----------|----------|
| Phase 0-2 | 诊断能力（后端） | P0 | 8 天 | 数据库迁移 + 能力框架 + 执行器 | **统一 task_logs** |
| Phase 3-4 | 诊断能力（前端） | P0 | 7 天 | 能力卡片 + 参数表单 + 场景方案 | **HTTP 轮询 + DiagnosisContext** |
| Phase 5-6 | 任务中心增强 | P1 | 5 天 | 连接健康检查 + 定时清理 | 查询逻辑统一 |
| Phase 7 | 工具箱重构 | P2 | 待定 | 工具包管理 + 脚本模板 | 无 |

---

## 架构决策清单（更新后）

| 决策点 | 原文档方案 | 改进方案 | 状态 |
|--------|-----------|---------|------|
| 执行记录模型 | 双表并存 | **统一为 task_logs** | ✅ 已采纳 |
| 场景方案执行 | WebSocket | **HTTP 轮询**（每2秒） | ✅ 已采纳 |
| AI 处理器安全 | 硬编码白名单 | **数据库驱动注册表** | ✅ 已采纳 |
| 状态管理 | 未定义 | **DiagnosisContext** | ✅ 已采纳 |
| 步骤数据传递 | `${stepN.field}` | **明确解析引擎** | ✅ 已采纳 |
| 执行中断 | 未定义 | **支持取消 + 清理** | ✅ 已采纳 |

---

**文档结束**
