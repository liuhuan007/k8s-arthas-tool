# 第13章架构评审补充报告

> 聚焦原文档缺失的关键架构设计维度

**评审日期**: 2026-05-04  
**评审范围**: 第13章模块架构与前端交互设计  
**评审视角**: 架构师（系统性/扩展性/可靠性/权衡决策）

---

## 一、原文档重大缺失（架构风险）

### ❌ 缺失 1：执行层并发控制模型

**问题**：
```
原文档 13.5 数据流转关系：
诊断能力 → ArthasCommandExecutor → task_logs
```

**缺失关键设计**：
- 多用户同时执行诊断能力时,线程池大小如何配置?
- 单个 Pod 同时被多个用户诊断,Arthas 是否支持并发命令?
- 场景方案执行中,某步骤超时如何影响线程池?

**架构师建议**：

```python
# backend/diagnosis_executor.py

class DiagnosisExecutorPool:
    """诊断执行器线程池（并发控制）"""
    
    def __init__(self):
        # 全局线程池（限制并发执行数）
        self.global_pool = ThreadPoolExecutor(
            max_workers=10,  # 最多10个并发诊断
            thread_name_prefix='diagnosis-'
        )
        
        # Pod 级别锁（防止同一 Pod 被并发诊断）
        self.pod_locks = defaultdict(threading.Lock)
    
    def execute(self, connection, capability, params, user_id):
        """提交诊断任务（带并发控制）"""
        
        # 1. 检查全局并发数
        if self.global_pool._work_queue.qsize() >= 10:
            raise ConcurrencyError('系统繁忙,请稍后重试')
        
        # 2. 获取 Pod 级别锁
        pod_key = f"{connection.cluster_name}/{connection.namespace}/{connection.pod_name}"
        pod_lock = self.pod_locks[pod_key]
        
        if not pod_lock.acquire(blocking=False):
            raise ConcurrencyError(f'Pod {pod_key} 正在被诊断,请稍后')
        
        try:
            # 3. 提交到线程池
            future = self.global_pool.submit(
                self._execute_with_lock,
                connection, capability, params, user_id, pod_lock
            )
            return {'ok': True, 'future': future}
        except Exception as e:
            pod_lock.release()
            raise
    
    def _execute_with_lock(self, connection, capability, params, user_id, pod_lock):
        """带锁的执行逻辑"""
        try:
            return self._do_execute(connection, capability, params, user_id)
        finally:
            pod_lock.release()  # 执行完成释放锁
```

**关键设计决策**：
| 决策点 | 方案 | 理由 |
|--------|------|------|
| 全局并发数 | 10 | Arthas HTTP API 单 Pod 并发能力有限 |
| Pod 级别锁 | 互斥锁 | 防止多用户同时操作同一 Pod 导致命令冲突 |
| 超时控制 | 单步骤 60s | 防止慢命令阻塞线程池 |

---

### ❌ 缺失 2：连接生命周期管理

**问题**：
原文档假设"连接已建立",但未定义:
- 诊断执行过程中连接断开如何处理?
- 场景方案执行到第2步时连接失效,前一步结果是否回滚?
- 连接重建后,正在执行的诊断是否自动重试?

**架构师建议**：

```python
class ConnectionAwareExecutor:
    """连接感知执行器"""
    
    def execute_with_connection_guard(self, connection, capability, params):
        """带连接保护的战斗执行"""
        
        execution_id = str(uuid4())
        
        # 1. 注册连接监听器
        def on_connection_lost():
            """连接断开回调"""
            db.update('task_logs', {
                'status': 'failed',
                'error_message': 'Arthas 连接已断开',
                'finished_at': datetime.now(),
            }, {'id': execution_id})
            
            # 如果是场景方案,清理已执行的命令
            if capability['type'] == 'diagnosis_scenario':
                self._rollback_scenario_steps(execution_id)
        
        ConnectionManager.register_listener(connection.id, on_connection_lost)
        
        try:
            # 2. 执行诊断
            result = self._execute(connection, capability, params)
            
            return result
        finally:
            # 3. 移除监听器
            ConnectionManager.unregister_listener(connection.id, on_connection_lost)
```

**前端交互设计**：

```javascript
// 连接断开时的用户体验
class DiagnosisExecutor {
  async execute(capabilityId, params) {
    try {
      const result = await api.executeDiagnosis(capabilityId, params);
      return result;
    } catch (e) {
      if (e.message.includes('连接已断开')) {
        // 显示友好提示 + 自动重连引导
        this.showConnectionLostDialog({
          title: 'Arthas 连接已断开',
          message: '诊断执行过程中连接中断,请重新建立连接后重试',
          action: '重新连接',
          onAction: () => switchTab('connections')
        });
      }
      throw e;
    }
  }
}
```

---

### ❌ 缺失 3：能力版本管理与向后兼容

**问题**：
原文档未定义:
- 管理员修改了 Trace 诊断能力的参数,历史执行记录如何追溯?
- 场景方案新增步骤后,正在执行的旧版本如何处理?
- AI 诊断处理器重构后,旧的 `handler` 路径是否失效?

**架构师建议**：

```sql
-- 增加版本号字段
ALTER TABLE diagnosis_capabilities ADD COLUMN version INTEGER DEFAULT 1;

-- 执行记录关联版本号
ALTER TABLE task_logs ADD COLUMN capability_version INTEGER;

-- 版本历史表
CREATE TABLE capability_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    capability_id INTEGER NOT NULL,
    version INTEGER NOT NULL,
    parameters_schema TEXT,
    extension_snapshot TEXT,  -- 扩展表数据快照
    changed_by INTEGER,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (capability_id) REFERENCES diagnosis_capabilities(id),
    UNIQUE(capability_id, version)
);
```

**版本管理流程**：

```python
class CapabilityVersionManager:
    """能力版本管理器"""
    
    def update_capability(self, capability_id, new_data):
        """更新能力（自动创建版本快照）"""
        
        # 1. 获取当前版本
        current = db.get('diagnosis_capabilities', capability_id)
        current_version = current['version']
        
        # 2. 创建版本快照
        db.insert('capability_versions', {
            'capability_id': capability_id,
            'version': current_version,
            'parameters_schema': current['parameters_schema'],
            'extension_snapshot': self._capture_extension_snapshot(capability_id),
            'changed_by': session['user_id'],
        })
        
        # 3. 更新能力（版本号 +1）
        db.update('diagnosis_capabilities', {
            **new_data,
            'version': current_version + 1,
        }, {'id': capability_id})
    
    def _capture_extension_snapshot(self, capability_id):
        """捕获扩展表数据快照"""
        capability = db.get('diagnosis_capabilities', capability_id)
        
        snapshot = {}
        if capability['type'] == 'arthas_command':
            snapshot['arthas_command'] = db.query_one(
                'SELECT arthas_command FROM arthas_command_templates WHERE capability_id = ?',
                (capability_id,)
            )
        elif capability['type'] == 'diagnosis_scenario':
            snapshot['steps'] = db.query(
                'SELECT * FROM diagnosis_scenario_steps WHERE capability_id =? ORDER BY step_order',
                (capability_id,)
            )
        elif capability['type'] == 'ai_diagnosis':
            snapshot['handler'] = db.query_one(
                'SELECT handler FROM ai_diagnosis_handlers WHERE capability_id = ?',
                (capability_id,)
            )
        
        return json.dumps(snapshot)
```

---

### ❌ 缺失 4：权限模型与数据隔离

**问题**：
原文档未定义:
- 用户 A 创建的诊断能力,用户 B 能否执行?
- 普通用户能否查看其他用户的执行历史?
- 管理员能否限制某些高危能力仅特定用户组可用?

**架构师建议**：

```sql
-- 能力可见性控制
ALTER TABLE diagnosis_capabilities ADD COLUMN visibility TEXT DEFAULT 'public';
-- public: 所有用户可见
-- private: 仅创建者可见
-- group: 特定用户组可见

-- 用户组关联表
CREATE TABLE capability_user_groups (
    capability_id INTEGER NOT NULL,
    group_id INTEGER NOT NULL,
    PRIMARY KEY (capability_id, group_id),
    FOREIGN KEY (capability_id) REFERENCES diagnosis_capabilities(id),
    FOREIGN KEY (group_id) REFERENCES user_groups(id)
);

-- 执行记录权限（已有 user_id,需增加索引）
CREATE INDEX idx_task_logs_user_id ON task_logs(user_id);
```

**权限检查逻辑**：

```python
def check_capability_permission(capability_id, user_id):
    """检查用户是否有权限执行诊断能力"""
    
    capability = db.get('diagnosis_capabilities', capability_id)
    
    # 1. 管理员无限制
    if is_admin(user_id):
        return True
    
    # 2. 公开能力
    if capability['visibility'] == 'public':
        return True
    
    # 3. 私有能力
    if capability['visibility'] == 'private':
        return capability['created_by'] == user_id
    
    # 4. 用户组能力
    if capability['visibility'] == 'group':
        user_groups = db.query(
            'SELECT group_id FROM user_group_members WHERE user_id = ?',
            (user_id,)
        )
        group_ids = [g['group_id'] for g in user_groups]
        
        allowed_groups = db.query(
            'SELECT group_id FROM capability_user_groups WHERE capability_id = ?',
            (capability_id,)
        )
        allowed_group_ids = [g['group_id'] for g in allowed_groups]
        
        return any(gid in allowed_group_ids for gid in group_ids)
    
    return False
```

---

### ❌ 缺失 5：诊断结果渲染规范

**问题**：
原文档提到"显示结果",但未定义:
- Trace 命令输出如何结构化展示?（火焰图?表格?）
- Profiler 报告如何嵌入前端?（iframe? 下载链接?）
- AI 诊断报告如何呈现?（Markdown? 结构化 JSON?）

**架构师建议**：

```python
# 诊断结果统一格式
class DiagnosisResult:
    """诊断结果封装"""
    
    def __init__(self, capability_type, raw_output):
        self.capability_type = capability_type
        self.raw_output = raw_output
        self.render_mode = self._detect_render_mode()
        self.structured_data = self._parse_output()
    
    def _detect_render_mode(self):
        """检测渲染模式"""
        if self.capability_type == 'arthas_command':
            if 'profiler' in self.raw_output:
                return 'file_link'  # Profiler 报告 → 文件链接
            elif 'trace' in self.raw_output:
                return 'table'  # Trace 输出 → 表格
            else:
                return 'text'  # 其他 → 原始文本
        elif self.capability_type == 'ai_diagnosis':
            return 'markdown'  # AI 报告 → Markdown 渲染
        elif self.capability_type == 'diagnosis_scenario':
            return 'multi_step'  # 场景方案 → 多步骤展示
    
    def _parse_output(self):
        """解析输出为结构化数据"""
        if self.render_mode == 'table':
            return self._parse_trace_output()
        elif self.render_mode == 'file_link':
            return self._extract_file_links()
        elif self.render_mode == 'markdown':
            return self.raw_output  # AI 报告直接返回
```

**前端渲染组件**：

```javascript
// static/js/components/diagnosis-result-renderer.js

class DiagnosisResultRenderer {
  static render(result) {
    switch (result.render_mode) {
      case 'table':
        return this.renderTraceTable(result.structured_data);
      case 'file_link':
        return this.renderFileLinks(result.structured_data);
      case 'markdown':
        return this.renderMarkdown(result.structured_data);
      case 'multi_step':
        return this.renderMultiStep(result.structured_data);
      case 'text':
      default:
        return this.renderPlainText(result.raw_output);
    }
  }
  
  static renderTraceTable(data) {
    // Trace 输出 → 表格
    return `
      <table class="trace-table">
        <thead>
          <tr>
            <th>线程</th>
            <th>方法</th>
            <th>耗时(ms)</th>
            <th>调用次数</th>
          </tr>
        </thead>
        <tbody>
          ${data.rows.map(row => `
            <tr>
              <td>${row.thread}</td>
              <td>${row.method}</td>
              <td class="duration">${row.duration}</td>
              <td>${row.count}</td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    `;
  }
  
  static renderFileLinks(data) {
    // Profiler 报告 → 文件链接
    return `
      <div class="file-links">
        <h4>诊断报告</h4>
        ${data.files.map(file => `
          <a href="/api/files/${file.id}/download" class="file-link">
            <i class="icon-file"></i>
            ${file.name} (${file.size})
          </a>
        `).join('')}
      </div>
    `;
  }
  
  static renderMarkdown(text) {
    // AI 报告 → Markdown 渲染
    return `
      <div class="markdown-body">
        ${marked.parse(text)}
      </div>
    `;
  }
}
```

---

## 二、交互设计深度评审

### 优点 ✅
1. **分层卡片设计**：L1-L4 视觉区分明确,符合用户心智模型
2. **参数表单动态化**：减少前端开发量,提升扩展性

### 严重缺陷 ❌

#### 缺陷 1：缺少"执行中"状态的全局指示器

**问题**：
- 用户执行场景方案后切换到其他 Tab,如何知道诊断还在执行?
- 多个诊断同时执行时,如何快速定位?

**架构师建议**：

```javascript
// 全局执行指示器（顶部导航栏）
class ExecutionIndicator {
  static render() {
    const activeCount = DiagnosisContext.getActiveCount();
    
    if (activeCount === 0) return '';
    
    return `
      <div class="execution-indicator" onclick="showActiveExecutions()">
        <span class="spinner"></span>
        ${activeCount} 个诊断执行中
      </div>
    `;
  }
}

// 添加到导航栏
document.querySelector('.nav-bar').insertAdjacentHTML('beforeend', ExecutionIndicator.render());
```

#### 缺陷 2：场景方案步骤预览过于简单

**问题**：
- 原文档仅显示 "Step1: trace → Step2: watch",未展示参数
- 用户无法确认参数替换后的实际命令

**架构师建议**：

```
步骤预览面板（执行前）：
┌─────────────────────────────────────────────┐
│ 场景方案：接口响应慢诊断                      │
├─────────────────────────────────────────────┤
│ Step 1/3: Trace 方法调用                     │
│   命令: trace com.example.OrderService      │
│         createOrder -n 10 '#cost > .5'       │
│   超时: 30s                                  │
│   失败策略: 停止执行                          │
├─────────────────────────────────────────────┤
│ Step 2/3: Watch 方法参数                     │
│   命令: watch com.example.OrderService      │
│         createOrder '{params, returnObj}'    │
│   超时: 20s                                  │
│   失败策略: 继续执行                          │
├─────────────────────────────────────────────┤
│ Step 3/3: Profiler CPU 分析                  │
│   命令: profiler start --event cpu           │
│         --duration 30                        │
│   超时: 60s                                  │
│   失败策略: 停止执行                          │
├─────────────────────────────────────────────┤
│ [取消] [确认执行]                            │
└─────────────────────────────────────────────┘
```

#### 缺陷 3：诊断历史缺乏对比分析

**问题**：
- 用户执行了 3 次 Trace,如何对比结果变化?
- 某接口响应时间从 100ms 飙升到 500ms,如何快速定位?

**架构师建议**：

```javascript
// 诊断历史对比功能
class DiagnosisHistoryComparator {
  async compare(executionIds) {
    // 获取多次执行结果
    const executions = await Promise.all(
      executionIds.map(id => api.getExecutionDetail(id))
    );
    
    // 提取关键指标
    const metrics = executions.map(exec => ({
      id: exec.id,
      timestamp: exec.started_at,
      avg_duration: this.extractAvgDuration(exec.result_json),
      max_duration: this.extractMaxDuration(exec.result_json),
      slow_methods: this.extractSlowMethods(exec.result_json),
    }));
    
    // 渲染对比表格
    this.renderComparisonTable(metrics);
  }
  
  renderComparisonTable(metrics) {
    return `
      <table class="comparison-table">
        <thead>
          <tr>
            <th>指标</th>
            ${metrics.map(m => `<th>${formatTime(m.timestamp)}</th>`).join('')}
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>平均耗时</td>
            ${metrics.map(m => `<td>${m.avg_duration}ms</td>`).join('')}
          </tr>
          <tr>
            <td>最大耗时</td>
            ${metrics.map(m => `<td class="${this.isAnomaly(m.max_duration) ? 'anomaly' : ''}">${m.max_duration}ms</td>`).join('')}
          </tr>
        </tbody>
      </table>
    `;
  }
}
```

---

## 三、架构决策清单（补充）

| 决策点 | 原文档方案 | 补充建议 | 影响等级 |
|--------|-----------|---------|---------|
| 并发控制 | 未定义 | **线程池 + Pod 级别锁** | 高 |
| 连接生命周期 | 假设连接稳定 | **连接监听器 + 自动清理** | 高 |
| 能力版本管理 | 未定义 | **版本号 + 快照表** | 中 |
| 权限模型 | 未定义 | **visibility + 用户组** | 高 |
| 结果渲染规范 | 未定义 | **render_mode 枚举** | 中 |
| 全局执行指示器 | 未定义 | **顶部导航栏状态** | 中 |
| 步骤预览 | 简单展示 | **完整命令预览面板** | 低 |
| 历史对比 | 未定义 | **多执行对比表格** | 低 |

---

## 四、总结

### 原文档核心问题

1. **执行层缺乏并发控制**：多用户/多 Pod 场景下可能崩溃
2. **连接生命周期未管理**：连接断开后无清理机制
3. **能力版本管理缺失**：历史执行无法追溯
4. **权限模型未定义**：数据隔离和安全边界不清
5. **结果渲染规范空白**：前端展示缺乏统一标准

### 必须补充的关键设计

| 优先级 | 设计 | 原因 |
|--------|------|------|
| P0 | 并发控制模型 | 防止系统过载 |
| P0 | 连接生命周期管理 | 防止资源泄漏 |
| P0 | 权限模型 | 数据安全 |
| P1 | 能力版本管理 | 历史追溯 |
| P1 | 结果渲染规范 | 用户体验一致性 |
| P2 | 全局执行指示器 | 可观测性 |

---

**文档结束**
