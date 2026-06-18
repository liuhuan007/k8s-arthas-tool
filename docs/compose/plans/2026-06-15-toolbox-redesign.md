# 工具箱（Toolbox）重设计 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use compose:subagent (recommended) or compose:execute to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the toolbox feature with capability-aware single/batch tool distribution to Pods, reorganized sidebar navigation, and card-based UI for binary tools, script tools, and quick actions.

**Architecture:** Extend existing `api/task_center.py` with new tables (`script_tools`, `quick_actions`, `tool_distributions`) and API endpoints. Rewrite `static/js/components/toolbox.js` for card-based layout with inline single distribute + batch distribute modal. Update `index.html` sidebar navigation to group tools by capability level.

**Tech Stack:** Python/Flask (backend), SQLite (database), vanilla JS (frontend), existing WebSocket for real-time progress.

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `index.html` | Modify | Sidebar navigation restructuring |
| `api/task_center.py` | Modify | New API endpoints: script_tools CRUD, quick_actions CRUD, batch distribute, capability detection |
| `models/db.py` | Modify | New table migrations: `script_tools`, `quick_actions`, `tool_distributions` |
| `static/js/components/toolbox.js` | Rewrite | Card-based toolbox UI, single distribute form, batch distribute modal |
| `static/css/app.css` | Modify | New styles for toolbox cards, batch modal, capability badges |
| `tests/test_toolbox.py` | Create | Unit tests for new API endpoints |

---

### Task 1: Sidebar Navigation Restructuring

**Covers:** [S2]

**Files:**
- Modify: `index.html:166-286` (sidebar section)

- [ ] **Step 1: Read current sidebar structure**

Read `index.html` lines 166-286 to understand the current sidebar groups.

- [ ] **Step 2: Restructure sidebar groups**

Replace the sidebar `<div class="side-nav">` content with the new structure. The key changes:

1. Rename "工具中心" group to "实时操作"
2. Split into two sub-groups: "Pod 基础" and "JVM 诊断"
3. Move "控制面板" from outside to under "诊断" group
4. Make "工具箱" a top-level group (not nested under anything)
5. Remove "脚本库" from task center (scripts live in toolbox now)

New sidebar structure:

```html
<!-- 连接管理 (unchanged) -->
<div class="side-nav-group side-nav-group-expanded" data-side-group="connection">
  <!-- existing content -->
</div>

<!-- 诊断 -->
<div class="side-nav-group side-nav-group-expanded" data-side-group="diagnosis">
  <button class="side-nav-title" type="button" onclick="toggleSideNavGroup(this)">
    <span>诊断</span><span class="side-nav-arrow">▾</span>
  </button>
  <div class="side-nav-items" style="display:block;">
    <button class="side-nav-item" data-nav-tab="diagnosis-quick" onclick="navigateToDiagnosis('quick')">
      <span>⚡</span><span>快捷诊断</span>
    </button>
    <button class="side-nav-item" data-nav-tab="diagnosis-scenario" onclick="navigateToDiagnosis('scenario')">
      <span>📋</span><span>场景方案</span>
    </button>
    <button class="side-nav-item" data-nav-tab="diagnosis-ai" onclick="navigateToDiagnosis('ai')">
      <span>🤖</span><span>AI 诊断</span>
    </button>
    <button class="side-nav-item" data-nav-tab="diagnosis-history" onclick="navigateToDiagnosis('history')">
      <span>📊</span><span>历史记录</span>
    </button>
    <button class="side-nav-item" data-nav-tab="dashboard" onclick="navigateTo('dashboard')">
      <span>📈</span><span>控制面板</span>
    </button>
  </div>
</div>

<!-- 实时操作 -->
<div class="side-nav-group" data-side-group="live-tools">
  <button class="side-nav-title" type="button" onclick="toggleSideNavGroup(this)">
    <span>实时操作</span><span class="side-nav-arrow">▾</span>
  </button>
  <div class="side-nav-items">
    <div class="side-nav-subgroup">
      <div class="side-nav-subgroup-label">Pod 基础</div>
      <button class="side-nav-item" data-nav-tab="terminal" onclick="navigateTo('terminal')">
        <span>🖥️</span><span>终端</span>
      </button>
      <button class="side-nav-item" data-nav-tab="filebrowser" onclick="navigateTo('filebrowser')">
        <span>📂</span><span>文件下载</span>
      </button>
      <button class="side-nav-item" data-nav-tab="monitor" onclick="navigateTo('monitor')">
        <span>📊</span><span>Pod 监控</span>
      </button>
    </div>
    <div class="side-nav-subgroup">
      <div class="side-nav-subgroup-label">JVM 诊断</div>
      <button class="side-nav-item" data-nav-tab="profiler" onclick="navigateTo('profiler')">
        <span>🔥</span><span>采样工具</span>
      </button>
      <button class="side-nav-item" data-nav-tab="hotfix" onclick="navigateTo('hotfix')">
        <span>🔧</span><span>在线修复</span>
      </button>
      <button class="side-nav-item" data-nav-tab="thread-diagnosis" onclick="navigateTo('thread-diagnosis')">
        <span>🧵</span><span>线程诊断</span>
      </button>
    </div>
  </div>
</div>

<!-- 工具箱 (独立组) -->
<div class="side-nav-group" data-side-group="toolbox">
  <button class="side-nav-title" type="button" onclick="toggleSideNavGroup(this)">
    <span>工具箱</span><span class="side-nav-arrow">▾</span>
  </button>
  <div class="side-nav-items">
    <button class="side-nav-item" data-nav-tab="toolchain-center" onclick="navigateTo('toolchain-center')">
      <span>🧰</span><span>工具管理</span>
    </button>
  </div>
</div>

<!-- 任务中心 (remove 脚本库 tab) -->
<div class="side-nav-group" data-side-group="task">
  <button class="side-nav-title" type="button" onclick="toggleSideNavGroup(this)">
    <span>任务中心</span><span class="side-nav-arrow">▾</span>
  </button>
  <div class="side-nav-items">
    <button class="side-nav-item" data-nav-tab="task-center" onclick="navigateToTaskCenter('tasks')">
      <span>📋</span><span>任务列表</span>
    </button>
    <button class="side-nav-item" data-nav-tab="task-schedules" onclick="navigateToTaskCenter('schedules')">
      <span>⏱</span><span>调度管理</span>
    </button>
    <button class="side-nav-item" data-nav-tab="task-runs" onclick="navigateToTaskCenter('runs')">
      <span>📊</span><span>执行记录</span>
    </button>
  </div>
</div>

<!-- 系统管理 (unchanged) -->
<!-- 外部系统 (unchanged) -->
```

- [ ] **Step 3: Add CSS for subgroup labels**

Add to `static/css/app.css`:

```css
.side-nav-subgroup-label {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--tx3);
  padding: 8px 16px 4px;
  opacity: 0.7;
}

.side-nav-subgroup + .side-nav-subgroup {
  border-top: 1px solid var(--ln);
  margin-top: 4px;
  padding-top: 4px;
}
```

- [ ] **Step 4: Commit**

```bash
git add index.html static/css/app.css
git commit -m "refactor: restructure sidebar navigation by capability level"
```

---

### Task 2: Database Migrations

**Covers:** [S4]

**Files:**
- Modify: `models/db.py:500-531` (add new table migrations)

- [ ] **Step 1: Add script_tools table migration**

In `models/db.py`, find the `_init_schema` method and add after the existing `tool_packages` table creation:

```python
# script_tools 表（脚本工具）
cursor.execute("""
    CREATE TABLE IF NOT EXISTS script_tools (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        runtime TEXT NOT NULL DEFAULT 'python',
        script_body TEXT NOT NULL,
        risk_level TEXT DEFAULT 'low',
        parameters_schema TEXT,
        capability_id INTEGER,
        description TEXT,
        created_by INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (capability_id) REFERENCES diagnosis_capabilities(id) ON DELETE SET NULL,
        FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
    )
""")
cursor.execute("CREATE INDEX IF NOT EXISTS idx_script_tools_runtime ON script_tools(runtime)")
log.info("Schema initialized: script_tools table created")
```

- [ ] **Step 2: Add quick_actions table migration**

```python
# quick_actions 表（快捷操作）
cursor.execute("""
    CREATE TABLE IF NOT EXISTS quick_actions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        category TEXT,
        command_template TEXT NOT NULL,
        parameters_schema TEXT,
        risk_level TEXT DEFAULT 'low',
        description TEXT,
        arthas_doc_url TEXT,
        created_by INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
    )
""")
cursor.execute("CREATE INDEX IF NOT EXISTS idx_quick_actions_category ON quick_actions(category)")
log.info("Schema initialized: quick_actions table created")
```

- [ ] **Step 3: Add tool_distributions table migration**

```python
# tool_distributions 表（分发记录）
cursor.execute("""
    CREATE TABLE IF NOT EXISTS tool_distributions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tool_type TEXT NOT NULL,
        tool_id INTEGER NOT NULL,
        tool_name TEXT,
        target_cluster TEXT,
        target_namespace TEXT,
        target_pod TEXT,
        target_container TEXT,
        install_path TEXT,
        status TEXT DEFAULT 'pending',
        error_message TEXT,
        duration_ms INTEGER,
        distributed_by INTEGER,
        distributed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (distributed_by) REFERENCES users(id) ON DELETE SET NULL
    )
""")
cursor.execute("CREATE INDEX IF NOT EXISTS idx_tool_dist_type ON tool_distributions(tool_type, tool_id)")
cursor.execute("CREATE INDEX IF NOT EXISTS idx_tool_dist_pod ON tool_distributions(target_cluster, target_namespace, target_pod)")
cursor.execute("CREATE INDEX IF NOT EXISTS idx_tool_dist_status ON tool_distributions(status)")
log.info("Schema initialized: tool_distributions table created")
```

- [ ] **Step 4: Commit**

```bash
git add models/db.py
git commit -m "feat: add script_tools, quick_actions, tool_distributions tables"
```

---

### Task 3: Backend API — Script Tools CRUD

**Covers:** [S3, S8]

**Files:**
- Modify: `api/task_center.py` (add new routes after existing tool-packages routes)

- [ ] **Step 1: Add script tools list/create endpoints**

Add after the existing tool-packages routes in `api/task_center.py`:

```python
# ═══════════════════════════════════════════════════════════════════════════════
# 脚本工具 API
# ═══════════════════════════════════════════════════════════════════════════════

@task_bp.route('/script-tools', methods=['GET'])
@login_required
def list_script_tools():
    """查询脚本工具列表"""
    runtime_filter = request.args.get('runtime')
    where_clauses = []
    params = []
    if runtime_filter:
        where_clauses.append('runtime = ?')
        params.append(runtime_filter)
    where_sql = ' AND '.join(where_clauses) if where_clauses else '1=1'
    rows = db.fetch_all(
        f'SELECT * FROM script_tools WHERE {where_sql} ORDER BY id DESC',
        tuple(params)
    )
    return jsonify({'tools': [dict(r) for r in rows]})


@task_bp.route('/script-tools', methods=['POST'])
@login_required
def create_script_tool():
    """创建脚本工具"""
    data = request.get_json(force=True)
    name = data.get('name', '').strip()
    script_body = data.get('script_body', '').strip()
    if not name or not script_body:
        return _error('名称和脚本内容不能为空')
    tool_id = db.insert('script_tools', {
        'name': name,
        'runtime': data.get('runtime', 'python'),
        'script_body': script_body,
        'risk_level': data.get('risk_level', 'low'),
        'parameters_schema': data.get('parameters_schema'),
        'capability_id': data.get('capability_id'),
        'description': data.get('description', ''),
        'created_by': current_user.id if hasattr(current_user, 'id') else None,
    })
    row = db.fetch_one('SELECT * FROM script_tools WHERE id = ?', (tool_id,))
    return jsonify({'ok': True, 'tool': dict(row)}), 201


@task_bp.route('/script-tools/<int:tool_id>', methods=['PUT'])
@login_required
def update_script_tool(tool_id: int):
    """更新脚本工具"""
    row = db.fetch_one('SELECT * FROM script_tools WHERE id = ?', (tool_id,))
    if not row:
        return _error('脚本工具不存在', 404)
    data = request.get_json(force=True)
    updates = {}
    for key in ('name', 'runtime', 'script_body', 'risk_level', 'parameters_schema', 'capability_id', 'description'):
        if key in data:
            updates[key] = data[key]
    if updates:
        updates['updated_at'] = _now_text()
        db.update('script_tools', updates, 'id = ?', (tool_id,))
    row = db.fetch_one('SELECT * FROM script_tools WHERE id = ?', (tool_id,))
    return jsonify({'ok': True, 'tool': dict(row)})


@task_bp.route('/script-tools/<int:tool_id>', methods=['DELETE'])
@login_required
def delete_script_tool(tool_id: int):
    """删除脚本工具"""
    row = db.fetch_one('SELECT * FROM script_tools WHERE id = ?', (tool_id,))
    if not row:
        return _error('脚本工具不存在', 404)
    db.execute('DELETE FROM script_tools WHERE id = ?', (tool_id,))
    return jsonify({'ok': True})
```

- [ ] **Step 2: Commit**

```bash
git add api/task_center.py
git commit -m "feat: add script tools CRUD API endpoints"
```

---

### Task 4: Backend API — Quick Actions CRUD

**Covers:** [S3, S8]

**Files:**
- Modify: `api/task_center.py` (add new routes after script tools routes)

- [ ] **Step 1: Add quick actions list/create endpoints**

```python
# ═══════════════════════════════════════════════════════════════════════════════
# 快捷操作 API
# ═══════════════════════════════════════════════════════════════════════════════

@task_bp.route('/quick-actions', methods=['GET'])
@login_required
def list_quick_actions():
    """查询快捷操作列表"""
    category_filter = request.args.get('category')
    where_clauses = []
    params = []
    if category_filter:
        where_clauses.append('category = ?')
        params.append(category_filter)
    where_sql = ' AND '.join(where_clauses) if where_clauses else '1=1'
    rows = db.fetch_all(
        f'SELECT * FROM quick_actions WHERE {where_sql} ORDER BY category, id',
        tuple(params)
    )
    return jsonify({'actions': [dict(r) for r in rows]})


@task_bp.route('/quick-actions', methods=['POST'])
@login_required
def create_quick_action():
    """创建快捷操作"""
    data = request.get_json(force=True)
    name = data.get('name', '').strip()
    command_template = data.get('command_template', '').strip()
    if not name or not command_template:
        return _error('名称和命令模板不能为空')
    action_id = db.insert('quick_actions', {
        'name': name,
        'category': data.get('category'),
        'command_template': command_template,
        'risk_level': data.get('risk_level', 'low'),
        'parameters_schema': data.get('parameters_schema'),
        'description': data.get('description', ''),
        'arthas_doc_url': data.get('arthas_doc_url'),
        'created_by': current_user.id if hasattr(current_user, 'id') else None,
    })
    row = db.fetch_one('SELECT * FROM quick_actions WHERE id = ?', (action_id,))
    return jsonify({'ok': True, 'action': dict(row)}), 201


@task_bp.route('/quick-actions/<int:action_id>', methods=['PUT'])
@login_required
def update_quick_action(action_id: int):
    """更新快捷操作"""
    row = db.fetch_one('SELECT * FROM quick_actions WHERE id = ?', (action_id,))
    if not row:
        return _error('快捷操作不存在', 404)
    data = request.get_json(force=True)
    updates = {}
    for key in ('name', 'category', 'command_template', 'risk_level', 'parameters_schema', 'description', 'arthas_doc_url'):
        if key in data:
            updates[key] = data[key]
    if updates:
        updates['updated_at'] = _now_text()
        db.update('quick_actions', updates, 'id = ?', (action_id,))
    row = db.fetch_one('SELECT * FROM quick_actions WHERE id = ?', (action_id,))
    return jsonify({'ok': True, 'action': dict(row)})


@task_bp.route('/quick-actions/<int:action_id>', methods=['DELETE'])
@login_required
def delete_quick_action(action_id: int):
    """删除快捷操作"""
    row = db.fetch_one('SELECT * FROM quick_actions WHERE id = ?', (action_id,))
    if not row:
        return _error('快捷操作不存在', 404)
    db.execute('DELETE FROM quick_actions WHERE id = ?', (action_id,))
    return jsonify({'ok': True})
```

- [ ] **Step 2: Commit**

```bash
git add api/task_center.py
git commit -m "feat: add quick actions CRUD API endpoints"
```

---

### Task 5: Backend API — Pod Capability Detection

**Covers:** [S7, S8]

**Files:**
- Modify: `api/task_center.py` (add new route)

- [ ] **Step 1: Add capability detection endpoint**

```python
# ═══════════════════════════════════════════════════════════════════════════════
# Pod 能力检测 API
# ═══════════════════════════════════════════════════════════════════════════════

@task_bp.route('/detect-capability', methods=['POST'])
@login_required
def detect_pod_capability():
    """检测 Pod 能力（Java/Go/Python，Arthas 状态）"""
    data = request.get_json(force=True)
    cluster = data.get('cluster')
    namespace = data.get('namespace', 'default')
    pod = data.get('pod')
    container = data.get('container', '')
    if not cluster or not pod:
        return _error('cluster 和 pod 不能为空')

    result = {
        'has_java': False,
        'java_version': None,
        'has_arthas': False,
        'arthas_version': None,
        'has_exec': True,
        'capability_level': 'unknown',
    }

    try:
        # 检测 Java 版本
        cmd_parts = ['kubectl', 'exec', '-n', namespace, pod]
        if container:
            cmd_parts.extend(['-c', container])
        cmd_parts.extend(['--', 'java', '-version'])

        proc = subprocess.run(cmd_parts, capture_output=True, text=True, timeout=10)
        if proc.returncode == 0:
            result['has_java'] = True
            # 从 stderr 解析 Java 版本 (java -version 输出到 stderr)
            version_match = re.search(r'"(\d+\.\d+\.\d+)', proc.stderr or proc.stdout)
            if version_match:
                result['java_version'] = version_match.group(1)

            # 检测 Arthas
            arthas_paths = ['/app/arthas/arthas-boot.jar', '/opt/arthas/arthas-boot.jar',
                           '/arthas/arthas-boot.jar', '/home/admin/arthas-boot.jar']
            for arthas_path in arthas_paths:
                check_cmd = cmd_parts[:-3] + ['--', 'ls', '-la', arthas_path]
                check_proc = subprocess.run(check_cmd, capture_output=True, text=True, timeout=5)
                if check_proc.returncode == 0 and 'arthas-boot.jar' in (check_proc.stdout or ''):
                    result['has_arthas'] = True
                    break
        elif 'exec' in (proc.stderr or '').lower() or 'forbidden' in (proc.stderr or '').lower():
            result['has_exec'] = False
    except subprocess.TimeoutExpired:
        result['has_exec'] = False
    except Exception as e:
        log.warning(f"能力检测失败: {e}")

    # 确定能力级别
    if result['has_java'] and result['has_arthas']:
        result['capability_level'] = 'pod+arthas'
    elif result['has_java']:
        result['capability_level'] = 'pod-only'
    elif result['has_exec']:
        result['capability_level'] = 'non-java'
    else:
        result['capability_level'] = 'no-exec'

    return jsonify(result)
```

- [ ] **Step 2: Commit**

```bash
git add api/task_center.py
git commit -m "feat: add Pod capability detection API endpoint"
```

---

### Task 6: Backend API — Batch Distribution

**Covers:** [S6, S7, S8]

**Files:**
- Modify: `api/task_center.py` (add new routes, extend existing distribute endpoint)

- [ ] **Step 1: Add batch distribute endpoint**

```python
# ═══════════════════════════════════════════════════════════════════════════════
# 批量分发 API
# ═══════════════════════════════════════════════════════════════════════════════

@task_bp.route('/batch-distribute', methods=['POST'])
@login_required
def batch_distribute():
    """批量分发工具到多个 Pod"""
    data = request.get_json(force=True)
    tool_ids = data.get('tool_ids', [])
    tool_type = data.get('tool_type', 'binary')
    targets = data.get('targets', [])
    install_path = data.get('install_path', '/tmp/arthas/arthas-boot.jar')

    if not tool_ids or not targets:
        return _error('请选择工具和目标 Pod')

    batch_id = f"batch-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    results = []

    for tool_id in tool_ids:
        tool_row = db.fetch_one('SELECT * FROM tool_packages WHERE id = ?', (tool_id,))
        if not tool_row:
            continue
        tool_name = tool_row.get('name', f'tool-{tool_id}')

        for target in targets:
            cluster = target.get('cluster', '')
            namespace = target.get('namespace', 'default')
            pod = target.get('pod', '')
            container = target.get('container', '')

            dist_id = db.insert('tool_distributions', {
                'tool_type': tool_type,
                'tool_id': tool_id,
                'tool_name': tool_name,
                'target_cluster': cluster,
                'target_namespace': namespace,
                'target_pod': pod,
                'target_container': container,
                'install_path': install_path,
                'status': 'pending',
                'distributed_by': current_user.id if hasattr(current_user, 'id') else None,
            })

            # 执行分发（复用现有 distribute 逻辑）
            try:
                start_time = time.time()
                _do_distribute(tool_row, cluster, namespace, pod, container, install_path)
                duration_ms = int((time.time() - start_time) * 1000)
                db.update('tool_distributions', {
                    'status': 'success',
                    'duration_ms': duration_ms,
                }, 'id = ?', (dist_id,))
                results.append({
                    'tool': tool_name,
                    'pod': pod,
                    'status': 'success',
                    'duration_ms': duration_ms,
                })
            except Exception as e:
                db.update('tool_distributions', {
                    'status': 'failed',
                    'error_message': str(e),
                }, 'id = ?', (dist_id,))
                results.append({
                    'tool': tool_name,
                    'pod': pod,
                    'status': 'failed',
                    'error': str(e),
                })

    success_count = sum(1 for r in results if r['status'] == 'success')
    failed_count = sum(1 for r in results if r['status'] == 'failed')

    return jsonify({
        'batch_id': batch_id,
        'total': len(results),
        'results': results,
        'summary': {
            'success': success_count,
            'failed': failed_count,
            'skipped': 0,
        }
    })


def _do_distribute(tool_row, cluster, namespace, pod, container, install_path):
    """执行单次分发（从现有 distribute 逻辑提取）"""
    file_path = tool_row.get('file_path', '')
    if not file_path or not os.path.exists(file_path):
        raise ValueError(f"工具文件不存在: {file_path}")

    # 构建 kubectl cp 命令
    cmd_parts = ['kubectl', 'cp', '-n', namespace]
    if container:
        cmd_parts.extend(['-c', container])
    target = f"{cluster}/{pod}:{install_path}" if cluster else f"{pod}:{install_path}"
    cmd_parts.extend([file_path, target])

    proc = subprocess.run(cmd_parts, capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        raise RuntimeError(f"kubectl cp 失败: {proc.stderr}")
```

- [ ] **Step 2: Add distribution history endpoint (extend existing)**

The existing `/tool-packages/distributions` endpoint already handles this. Verify it returns the new `tool_distributions` table data. If needed, update the query to union both tables.

- [ ] **Step 3: Commit**

```bash
git add api/task_center.py
git commit -m "feat: add batch distribution API with capability-aware logic"
```

---

### Task 7: Frontend — Toolbox Card Layout Rewrite

**Covers:** [S3, S5]

**Files:**
- Rewrite: `static/js/components/toolbox.js`

- [ ] **Step 1: Rewrite toolbox.js with card-based layout**

Replace the entire content of `static/js/components/toolbox.js` with:

```javascript
/**
 * 工具箱组件 - 卡片布局 + 分发功能
 * 三类工具：二进制工具、脚本工具、快捷操作
 */
(function() {
  'use strict';

  /**
   * 渲染工具箱整体布局
   */
  window.renderToolbox = async function() {
    await Promise.all([
      loadBinaryTools(),
      loadScriptTools(),
      loadQuickActions()
    ]);
    initToolboxRealtimeRefresh();
  };

  // ═══════════════════════════════════════════════════════════════
  // 二进制工具
  // ═══════════════════════════════════════════════════════════════

  async function loadBinaryTools() {
    try {
      const data = await safeGet('/tasks/tool-packages');
      renderBinaryToolCards(data.packages || []);
    } catch (e) {
      console.error('加载二进制工具失败:', e);
    }
  }

  function renderBinaryToolCards(packages) {
    const container = document.getElementById('toolboxBinaryTools');
    if (!container) return;
    if (packages.length === 0) {
      container.innerHTML = '<div class="sb-empty">暂无二进制工具<br>点击"上传工具"添加</div>';
      return;
    }
    container.innerHTML = packages.map(p => {
      const sha = p.sha256 ? `${p.sha256.slice(0, 12)}...` : '未校验';
      const statusClass = p.status === 'active' ? 'running' : 'stopped';
      const statusText = p.status === 'active' ? '可用' : '停用';
      return `
        <div class="toolbox-card toolbox-card-binary" data-id="${p.id}">
          <div class="toolbox-card-header">
            <span class="toolbox-card-icon">📦</span>
            <span class="toolbox-card-name">${esc(p.name)}</span>
            ${p.is_builtin ? '<span class="badge badge-low">内置</span>' : ''}
            <span class="badge ${statusClass}">${statusText}</span>
          </div>
          <div class="toolbox-card-meta">
            类型：${esc(p.tool_type)} · 版本：${esc(p.version || '-')} · SHA：${sha}
          </div>
          <div class="toolbox-card-path">${esc(p.install_path || '-')}</div>
          <div class="toolbox-card-actions">
            <button class="btn btn-g btn-sm" onclick="toolboxVerify(${p.id})">校验</button>
            <button class="btn btn-p btn-sm" onclick="toolboxSingleDistribute(${p.id}, 'binary', '${esc(p.install_path || '')}')">分发→</button>
            ${!p.is_builtin ? `<button class="btn btn-g btn-sm danger-text" onclick="toolboxDeleteBinary(${p.id})">删除</button>` : ''}
          </div>
          <div class="toolbox-distribute-form" id="distForm-binary-${p.id}" style="display:none"></div>
        </div>
      `;
    }).join('');
  }

  // ═══════════════════════════════════════════════════════════════
  // 脚本工具
  // ═══════════════════════════════════════════════════════════════

  async function loadScriptTools() {
    try {
      const data = await safeGet('/tasks/script-tools');
      renderScriptToolCards(data.tools || []);
    } catch (e) {
      console.error('加载脚本工具失败:', e);
    }
  }

  function renderScriptToolCards(tools) {
    const container = document.getElementById('toolboxScriptTools');
    if (!container) return;
    if (tools.length === 0) {
      container.innerHTML = '<div class="sb-empty">暂无脚本工具<br>点击"+ 新建"添加</div>';
      return;
    }
    container.innerHTML = tools.map(t => {
      const runtimeIcon = { python: '🐍', shell: '⚙️', node: '🟢' }[t.runtime] || '📄';
      return `
        <div class="toolbox-card toolbox-card-script" data-id="${t.id}">
          <div class="toolbox-card-header">
            <span class="toolbox-card-icon">${runtimeIcon}</span>
            <span class="toolbox-card-name">${esc(t.name)}</span>
            <span class="badge badge-${t.risk_level || 'low'}">${riskText(t.risk_level)}</span>
          </div>
          <div class="toolbox-card-meta">
            运行时：${esc(t.runtime)}${t.capability_id ? ' · 关联诊断能力' : ''}
          </div>
          <div class="toolbox-card-actions">
            <button class="btn btn-g btn-sm" onclick="toolboxEditScript(${t.id})">编辑</button>
            <button class="btn btn-p btn-sm" onclick="toolboxExecuteScript(${t.id})">执行→</button>
            <button class="btn btn-g btn-sm danger-text" onclick="toolboxDeleteScript(${t.id})">删除</button>
          </div>
        </div>
      `;
    }).join('');
  }

  // ═══════════════════════════════════════════════════════════════
  // 快捷操作
  // ═══════════════════════════════════════════════════════════════

  async function loadQuickActions() {
    try {
      const data = await safeGet('/tasks/quick-actions');
      renderQuickActionCards(data.actions || []);
    } catch (e) {
      console.error('加载快捷操作失败:', e);
    }
  }

  function renderQuickActionCards(actions) {
    const container = document.getElementById('toolboxQuickActions');
    if (!container) return;
    if (actions.length === 0) {
      container.innerHTML = '<div class="sb-empty">暂无快捷操作<br>点击"+ 新建"添加</div>';
      return;
    }
    container.innerHTML = actions.map(a => `
      <div class="toolbox-card toolbox-card-quick" data-id="${a.id}">
        <div class="toolbox-card-header">
          <span class="toolbox-card-icon">⚡</span>
          <span class="toolbox-card-name">${esc(a.name)}</span>
          <span class="badge badge-${a.risk_level || 'low'}">${riskText(a.risk_level)}</span>
        </div>
        <div class="toolbox-card-meta">${esc(a.category || '通用')}</div>
        <div class="toolbox-card-command"><code>${esc(a.command_template)}</code></div>
        <div class="toolbox-card-actions">
          <button class="btn btn-p btn-sm" onclick="toolboxExecuteQuick(${a.id})">执行→</button>
          ${a.arthas_doc_url ? `<a href="${esc(a.arthas_doc_url)}" target="_blank" class="btn btn-g btn-sm">文档</a>` : ''}
        </div>
      </div>
    `).join('');
  }

  // ═══════════════════════════════════════════════════════════════
  // 单个分发
  // ═══════════════════════════════════════════════════════════════

  window.toolboxSingleDistribute = function(toolId, toolType, defaultPath) {
    const formId = `distForm-${toolType}-${toolId}`;
    const form = document.getElementById(formId);
    if (!form) return;

    if (form.style.display !== 'none') {
      form.style.display = 'none';
      return;
    }

    // 获取当前连接信息
    const conn = window.getCurrentConnection ? window.getCurrentConnection() : {};

    form.innerHTML = `
      <div class="dist-form-inner">
        <div class="dist-form-title">分发到 Pod</div>
        <div class="dist-form-row">
          <label>集群</label>
          <input id="dist-cluster-${toolId}" class="inp" value="${esc(conn.cluster || '')}">
        </div>
        <div class="dist-form-row">
          <label>Namespace</label>
          <input id="dist-ns-${toolId}" class="inp" value="${esc(conn.namespace || 'default')}">
        </div>
        <div class="dist-form-row">
          <label>Pod</label>
          <input id="dist-pod-${toolId}" class="inp" value="${esc(conn.pod || '')}">
        </div>
        <div class="dist-form-row">
          <label>容器</label>
          <input id="dist-ctr-${toolId}" class="inp" placeholder="可选">
        </div>
        <div class="dist-form-row">
          <label>安装路径</label>
          <input id="dist-path-${toolId}" class="inp" value="${esc(defaultPath || '/tmp/arthas/arthas-boot.jar')}">
        </div>
        <div class="dist-form-actions">
          <button class="btn btn-p btn-sm" onclick="toolboxConfirmDistribute(${toolId}, '${toolType}')">确认分发</button>
          <button class="btn btn-g btn-sm" onclick="document.getElementById('${formId}').style.display='none'">取消</button>
        </div>
        <div id="dist-progress-${toolId}" style="display:none;margin-top:8px"></div>
      </div>
    `;
    form.style.display = 'block';
  };

  window.toolboxConfirmDistribute = async function(toolId, toolType) {
    const cluster = document.getElementById(`dist-cluster-${toolId}`)?.value || '';
    const ns = document.getElementById(`dist-ns-${toolId}`)?.value || 'default';
    const pod = document.getElementById(`dist-pod-${toolId}`)?.value || '';
    const ctr = document.getElementById(`dist-ctr-${toolId}`)?.value || '';
    const path = document.getElementById(`dist-path-${toolId}`)?.value || '/tmp/arthas/arthas-boot.jar';

    if (!pod) { toast('请输入 Pod 名称', 'warn'); return; }

    const progressEl = document.getElementById(`dist-progress-${toolId}`);
    if (progressEl) {
      progressEl.style.display = 'block';
      progressEl.innerHTML = '<span class="spinner"></span> 分发中...';
    }

    try {
      const result = await safePost('/tasks/distribute', {
        tool_id: toolId,
        cluster, namespace: ns, pod, container: ctr, install_path: path
      });
      if (progressEl) {
        progressEl.innerHTML = `<span style="color:var(--green)">✅ 分发成功</span>`;
      }
      toast('分发成功', 'ok');
    } catch (e) {
      if (progressEl) {
        progressEl.innerHTML = `<span style="color:var(--red)">❌ ${esc(e.message)}</span>`;
      }
      toast(`分发失败：${e.message}`, 'err');
    }
  };

  // ═══════════════════════════════════════════════════════════════
  // 批量分发浮层
  // ═══════════════════════════════════════════════════════════════

  window.toolboxOpenBatchDistribute = function() {
    const modal = document.createElement('div');
    modal.className = 'capability-modal-overlay';
    modal.id = 'batchDistModal';
    modal.innerHTML = `
      <div class="capability-modal" style="max-width:700px">
        <div class="modal-header">
          <h3>批量分发工具</h3>
          <button class="btn-close" onclick="this.closest('.capability-modal-overlay').remove()">✕</button>
        </div>
        <div class="modal-body" style="padding:20px">
          <div id="batchStep1">
            <h4 style="margin-bottom:12px">Step 1: 选择工具包</h4>
            <div id="batchToolList" class="batch-tool-list">加载中...</div>
          </div>
          <div id="batchStep2" style="display:none;margin-top:20px">
            <h4 style="margin-bottom:12px">Step 2: 选择目标 Pod</h4>
            <div class="batch-filter-bar">
              <button class="btn btn-g btn-sm" onclick="batchFilterPods('all')">全部</button>
              <button class="btn btn-g btn-sm" onclick="batchFilterPods('java')">仅 Java Pod</button>
              <button class="btn btn-g btn-sm" onclick="batchFilterPods('connected')">仅已连接</button>
            </div>
            <div id="batchPodList" class="batch-pod-list">加载中...</div>
          </div>
          <div id="batchStep3" style="display:none;margin-top:20px">
            <h4 style="margin-bottom:12px">Step 3: 确认分发</h4>
            <div id="batchSummary"></div>
            <div id="batchProgress" style="margin-top:12px"></div>
          </div>
        </div>
        <div class="modal-footer" style="padding:16px 20px;border-top:1px solid var(--border-color);display:flex;justify-content:flex-end;gap:8px">
          <button class="btn btn-g" onclick="this.closest('.capability-modal-overlay').remove()">取消</button>
          <button class="btn btn-p" id="batchNextBtn" onclick="batchNextStep()">下一步</button>
        </div>
      </div>
    `;
    document.body.appendChild(modal);
    modal.addEventListener('click', (e) => { if (e.target === modal) modal.remove(); });

    // 加载工具列表
    loadBatchToolList();
  };

  let _batchState = { step: 1, selectedTools: [], selectedPods: [] };

  async function loadBatchToolList() {
    try {
      const data = await safeGet('/tasks/tool-packages');
      const packages = data.packages || [];
      const container = document.getElementById('batchToolList');
      if (!container) return;
      container.innerHTML = packages.map(p => `
        <label class="batch-item">
          <input type="checkbox" value="${p.id}" data-name="${esc(p.name)}" data-path="${esc(p.install_path || '')}" onchange="batchUpdateTools()">
          <span>${esc(p.name)}</span>
          <span class="batch-item-meta">${esc(p.tool_type)} · ${esc(p.version || '-')}</span>
        </label>
      `).join('');
    } catch (e) {
      console.error('加载工具列表失败:', e);
    }
  }

  window.batchUpdateTools = function() {
    const checkboxes = document.querySelectorAll('#batchToolList input[type=checkbox]:checked');
    _batchState.selectedTools = Array.from(checkboxes).map(cb => ({
      id: parseInt(cb.value),
      name: cb.dataset.name,
      install_path: cb.dataset.path,
    }));
  };

  window.batchNextStep = function() {
    if (_batchState.step === 1) {
      if (_batchState.selectedTools.length === 0) { toast('请选择至少一个工具', 'warn'); return; }
      _batchState.step = 2;
      document.getElementById('batchStep1').style.display = 'none';
      document.getElementById('batchStep2').style.display = 'block';
      loadBatchPodList();
    } else if (_batchState.step === 2) {
      if (_batchState.selectedPods.length === 0) { toast('请选择至少一个 Pod', 'warn'); return; }
      _batchState.step = 3;
      document.getElementById('batchStep2').style.display = 'none';
      document.getElementById('batchStep3').style.display = 'block';
      renderBatchSummary();
      document.getElementById('batchNextBtn').textContent = '确认分发';
      document.getElementById('batchNextBtn').onclick = batchExecute;
    }
  };

  async function loadBatchPodList() {
    // 从连接记录加载 Pod 列表
    try {
      const data = await safeGet('/clusters');
      const clusters = data.clusters || [];
      const container = document.getElementById('batchPodList');
      if (!container) return;

      // 简化：显示当前集群的 Pod
      let html = '';
      for (const c of clusters) {
        try {
          const podsData = await safeGet(`/clusters/${c.name}/pods`);
          const pods = podsData.pods || [];
          for (const pod of pods) {
            html += `
              <label class="batch-item">
                <input type="checkbox" value="${esc(c.name)}:${esc(pod.namespace)}:${esc(pod.name)}"
                       onchange="batchUpdatePods()">
                <span>${esc(pod.name)}</span>
                <span class="batch-item-meta">${esc(c.name)}/${esc(pod.namespace)} · ${esc(pod.status)}</span>
              </label>
            `;
          }
        } catch (e) { /* skip cluster */ }
      }
      container.innerHTML = html || '<div class="sb-empty">无可用 Pod</div>';
    } catch (e) {
      console.error('加载 Pod 列表失败:', e);
    }
  }

  window.batchUpdatePods = function() {
    const checkboxes = document.querySelectorAll('#batchPodList input[type=checkbox]:checked');
    _batchState.selectedPods = Array.from(checkboxes).map(cb => {
      const [cluster, namespace, pod] = cb.value.split(':');
      return { cluster, namespace, pod };
    });
  };

  function renderBatchSummary() {
    const el = document.getElementById('batchSummary');
    if (!el) return;
    const total = _batchState.selectedTools.length * _batchState.selectedPods.length;
    el.innerHTML = `
      <p>将 <strong>${_batchState.selectedTools.length}</strong> 个工具分发到
      <strong>${_batchState.selectedPods.length}</strong> 个 Pod
      (共 <strong>${total}</strong> 次分发操作)</p>
    `;
  }

  window.batchExecute = async function() {
    const btn = document.getElementById('batchNextBtn');
    if (btn) btn.disabled = true;
    const progressEl = document.getElementById('batchProgress');
    if (progressEl) progressEl.innerHTML = '<span class="spinner"></span> 分发中...';

    try {
      const result = await safePost('/tasks/batch-distribute', {
        tool_ids: _batchState.selectedTools.map(t => t.id),
        tool_type: 'binary',
        targets: _batchState.selectedPods,
        install_path: _batchState.selectedTools[0]?.install_path || '/tmp/arthas/arthas-boot.jar',
      });

      if (progressEl) {
        const summary = result.summary || {};
        progressEl.innerHTML = `
          <div class="batch-result">
            <p>✅ 成功: ${summary.success || 0} | ❌ 失败: ${summary.failed || 0}</p>
            ${(result.results || []).map(r => `
              <div class="batch-result-item ${r.status}">
                ${r.status === 'success' ? '✅' : '❌'} ${esc(r.tool)} → ${esc(r.pod)}
                ${r.error ? `<span class="batch-error">${esc(r.error)}</span>` : ''}
                ${r.duration_ms ? `<span class="batch-duration">${r.duration_ms}ms</span>` : ''}
              </div>
            `).join('')}
          </div>
        `;
      }
      toast('批量分发完成', 'ok');
    } catch (e) {
      if (progressEl) progressEl.innerHTML = `<span style="color:var(--red)">❌ ${esc(e.message)}</span>`;
      toast(`批量分发失败：${e.message}`, 'err');
    } finally {
      if (btn) btn.disabled = false;
    }
  };

  // ═══════════════════════════════════════════════════════════════
  // 工具操作
  // ═══════════════════════════════════════════════════════════════

  window.toolboxVerify = async function(id) {
    try {
      await safePost(`/tasks/tool-packages/${id}/verify`);
      toast('校验完成', 'ok');
      loadBinaryTools();
    } catch (e) {
      toast(`校验失败：${e.message}`, 'err');
    }
  };

  window.toolboxDeleteBinary = async function(id) {
    if (!confirm('确认删除此工具包？')) return;
    try {
      await safeDelete(`/tasks/tool-packages/${id}`);
      toast('已删除', 'ok');
      loadBinaryTools();
    } catch (e) {
      toast(`删除失败：${e.message}`, 'err');
    }
  };

  window.toolboxDeleteScript = async function(id) {
    if (!confirm('确认删除此脚本工具？')) return;
    try {
      await safeDelete(`/tasks/script-tools/${id}`);
      toast('已删除', 'ok');
      loadScriptTools();
    } catch (e) {
      toast(`删除失败：${e.message}`, 'err');
    }
  };

  // ═══════════════════════════════════════════════════════════════
  // 工具函数
  // ═══════════════════════════════════════════════════════════════

  function esc(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  function riskText(level) {
    return { low: '低风险', medium: '中风险', high: '高风险' }[level] || '低风险';
  }

  // ═══════════════════════════════════════════════════════════════
  // 实时刷新
  // ═══════════════════════════════════════════════════════════════

  let _refreshInterval = null;

  function initToolboxRealtimeRefresh() {
    if (_refreshInterval) clearInterval(_refreshInterval);
    _refreshInterval = setInterval(() => {
      const panel = document.getElementById('panel-toolchain-center');
      if (panel && panel.style.display !== 'none') {
        loadBinaryTools();
      }
    }, 30000);
  }

  window.addEventListener('beforeunload', () => {
    if (_refreshInterval) clearInterval(_refreshInterval);
  });

})();
```

- [ ] **Step 2: Commit**

```bash
git add static/js/components/toolbox.js
git commit -m "feat: rewrite toolbox with card-based layout and batch distribute"
```

---

### Task 8: Frontend — Toolbox Panel HTML Update

**Covers:** [S3, S5]

**Files:**
- Modify: `index.html:717-881` (panel-toolchain-center section)

- [ ] **Step 1: Replace toolbox panel HTML**

Replace the `panel-toolchain-center` div content with the new card-based layout:

```html
<div class="panel" id="panel-toolchain-center">
  <div class="ops-page toolchain-page">
    <div class="ops-hero">
      <div>
        <div class="ops-kicker">Toolbox</div>
        <h2>诊断工具箱</h2>
        <p>管理二进制工具、脚本工具和快捷操作，支持单个和批量分发到 Pod</p>
      </div>
      <div class="toolchain-hero-actions">
        <button class="btn btn-g" onclick="renderToolbox()">刷新</button>
        <button class="btn btn-p" onclick="toolboxOpenBatchDistribute()">📦 批量分发</button>
      </div>
    </div>

    <div class="task-summary toolchain-summary" id="toolchainSummary">
      <div class="task-stat"><span>二进制工具</span><b id="statBinary">-</b></div>
      <div class="task-stat"><span>脚本工具</span><b id="statScript">-</b></div>
      <div class="task-stat"><span>快捷操作</span><b id="statQuick">-</b></div>
      <div class="task-stat"><span>分发次数</span><b id="statDist">-</b></div>
    </div>

    <!-- 二进制工具卡片组 -->
    <section class="toolbox-section">
      <div class="toolbox-section-header">
        <h3>📦 二进制工具</h3>
        <button class="btn btn-p btn-sm" onclick="toolboxUploadBinary()">上传工具</button>
      </div>
      <div id="toolboxBinaryTools" class="toolbox-card-grid">
        <div class="sb-empty">加载中...</div>
      </div>
    </section>

    <!-- 脚本工具卡片组 -->
    <section class="toolbox-section">
      <div class="toolbox-section-header">
        <h3>🐍 脚本工具</h3>
        <button class="btn btn-p btn-sm" onclick="toolboxCreateScript()">+ 新建</button>
      </div>
      <div id="toolboxScriptTools" class="toolbox-card-grid">
        <div class="sb-empty">加载中...</div>
      </div>
    </section>

    <!-- 快捷操作卡片组 -->
    <section class="toolbox-section">
      <div class="toolbox-section-header">
        <h3>⚡ 快捷操作</h3>
        <button class="btn btn-p btn-sm" onclick="toolboxCreateQuick()">+ 新建</button>
      </div>
      <div id="toolboxQuickActions" class="toolbox-card-grid">
        <div class="sb-empty">加载中...</div>
      </div>
    </section>
  </div>
</div>
```

- [ ] **Step 2: Commit**

```bash
git add index.html
git commit -m "feat: update toolbox panel with card-based sections"
```

---

### Task 9: Frontend — Toolbox CSS Styles

**Covers:** [S5]

**Files:**
- Modify: `static/css/app.css` (add new styles)

- [ ] **Step 1: Add toolbox card styles**

Add at the end of `static/css/app.css`:

```css
/* ═══════════════════════════════════════════════════════════════ */
/* 工具箱卡片布局                                                  */
/* ═══════════════════════════════════════════════════════════════ */

.toolbox-section {
  margin-top: 24px;
}

.toolbox-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.toolbox-section-header h3 {
  font-size: 15px;
  font-weight: 600;
  color: var(--tx);
}

.toolbox-card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 12px;
}

.toolbox-card {
  background: var(--bg1);
  border: 1px solid var(--ln);
  border-radius: 8px;
  padding: 16px;
  transition: border-color 0.2s;
}

.toolbox-card:hover {
  border-color: var(--accent);
}

.toolbox-card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.toolbox-card-icon {
  font-size: 18px;
}

.toolbox-card-name {
  font-weight: 600;
  font-size: 14px;
  color: var(--tx);
}

.toolbox-card-meta {
  font-size: 12px;
  color: var(--tx2);
  margin-bottom: 4px;
}

.toolbox-card-path {
  font-size: 11px;
  color: var(--tx3);
  font-family: monospace;
  margin-bottom: 8px;
  word-break: break-all;
}

.toolbox-card-command {
  font-size: 12px;
  margin-bottom: 8px;
}

.toolbox-card-command code {
  background: var(--bg);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 12px;
}

.toolbox-card-actions {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

/* 分发表单 */
.toolbox-distribute-form {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--ln);
}

.dist-form-inner {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.dist-form-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--tx);
  margin-bottom: 4px;
}

.dist-form-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.dist-form-row label {
  font-size: 12px;
  color: var(--tx2);
  min-width: 60px;
}

.dist-form-row .inp {
  flex: 1;
  font-size: 12px;
}

.dist-form-actions {
  display: flex;
  gap: 6px;
  margin-top: 4px;
}

/* 批量分发 */
.batch-tool-list,
.batch-pod-list {
  max-height: 240px;
  overflow-y: auto;
  border: 1px solid var(--ln);
  border-radius: 6px;
  padding: 8px;
}

.batch-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
}

.batch-item:hover {
  background: var(--bg2);
}

.batch-item input[type=checkbox] {
  margin: 0;
}

.batch-item-meta {
  font-size: 11px;
  color: var(--tx3);
  margin-left: auto;
}

.batch-filter-bar {
  display: flex;
  gap: 6px;
  margin-bottom: 8px;
}

.batch-result-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  font-size: 13px;
}

.batch-result-item.success {
  color: var(--green);
}

.batch-result-item.failed {
  color: var(--red);
}

.batch-error {
  font-size: 11px;
  color: var(--red);
}

.batch-duration {
  font-size: 11px;
  color: var(--tx3);
  margin-left: auto;
}
```

- [ ] **Step 2: Commit**

```bash
git add static/css/app.css
git commit -m "feat: add toolbox card layout and batch distribute styles"
```

---

### Task 10: Connection Center Batch Distribution Entry

**Covers:** [S6]

**Files:**
- Modify: `static/js/components/connections.js` (add batch action button)

- [ ] **Step 1: Add batch distribute button to connection list**

In `connections.js`, find the connection list rendering function and add a batch action bar above the table:

```javascript
// 在连接记录表格上方添加批量操作栏
function renderConnectionBatchActions() {
  const container = document.getElementById('connection-list-container');
  if (!container) return;

  // 检查是否已有批量操作栏
  if (container.querySelector('.conn-batch-bar')) return;

  const batchBar = document.createElement('div');
  batchBar.className = 'conn-batch-bar';
  batchBar.innerHTML = `
    <div class="conn-batch-left">
      <label class="conn-batch-select-all">
        <input type="checkbox" id="connSelectAll" onchange="toggleAllConnections(this.checked)">
        全选
      </label>
      <span id="connSelectedCount" style="font-size:12px;color:var(--tx2)">已选 0 个</span>
    </div>
    <div class="conn-batch-actions">
      <button class="btn btn-g btn-sm" onclick="batchDistributeFromConnections()">📦 批量分发工具</button>
    </div>
  `;
  container.insertBefore(batchBar, container.firstChild);
}

window.toggleAllConnections = function(checked) {
  const checkboxes = document.querySelectorAll('.conn-checkbox');
  checkboxes.forEach(cb => { cb.checked = checked; });
  updateSelectedCount();
};

window.updateSelectedCount = function() {
  const checked = document.querySelectorAll('.conn-checkbox:checked').length;
  const el = document.getElementById('connSelectedCount');
  if (el) el.textContent = `已选 ${checked} 个`;
};

window.batchDistributeFromConnections = function() {
  const checked = document.querySelectorAll('.conn-checkbox:checked');
  if (checked.length === 0) { toast('请先选择连接', 'warn'); return; }
  // 跳转到工具箱的批量分发
  navigateTo('toolchain-center');
  setTimeout(() => toolboxOpenBatchDistribute(), 300);
};
```

- [ ] **Step 2: Add checkbox to each connection row**

In the connection row rendering, add a checkbox:

```html
<td><input type="checkbox" class="conn-checkbox" onchange="updateSelectedCount()"></td>
```

- [ ] **Step 3: Add CSS for batch bar**

```css
.conn-batch-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  background: var(--bg1);
  border-bottom: 1px solid var(--ln);
  font-size: 13px;
}

.conn-batch-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.conn-batch-select-all {
  display: flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
}
```

- [ ] **Step 4: Commit**

```bash
git add static/js/components/connections.js static/css/app.css
git commit -m "feat: add batch distribution entry to connection center"
```

---

### Task 11: Tests

**Covers:** [S8]

**Files:**
- Create: `tests/test_toolbox.py`

- [ ] **Step 1: Write tests for new API endpoints**

```python
"""Tests for toolbox API endpoints."""
import json
import pytest
from unittest.mock import patch, MagicMock


class TestScriptToolsAPI:
    """Test script tools CRUD endpoints."""

    def test_list_script_tools_empty(self, client):
        """GET /tasks/script-tools returns empty list initially."""
        resp = client.get('/api/tasks/script-tools')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'tools' in data

    def test_create_script_tool(self, client):
        """POST /tasks/script-tools creates a new script tool."""
        resp = client.post('/api/tasks/script-tools', json={
            'name': 'CPU Analysis',
            'runtime': 'python',
            'script_body': 'print("hello")',
            'risk_level': 'low',
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['ok'] is True
        assert data['tool']['name'] == 'CPU Analysis'

    def test_create_script_tool_validation(self, client):
        """POST /tasks/script-tools rejects empty name."""
        resp = client.post('/api/tasks/script-tools', json={
            'name': '',
            'script_body': 'print("hello")',
        })
        assert resp.status_code == 400

    def test_delete_script_tool(self, client):
        """DELETE /tasks/script-tools/:id removes the tool."""
        # Create first
        resp = client.post('/api/tasks/script-tools', json={
            'name': 'To Delete',
            'script_body': 'x = 1',
        })
        tool_id = resp.get_json()['tool']['id']

        # Delete
        resp = client.delete(f'/api/tasks/script-tools/{tool_id}')
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True


class TestQuickActionsAPI:
    """Test quick actions CRUD endpoints."""

    def test_create_quick_action(self, client):
        """POST /tasks/quick-actions creates a new quick action."""
        resp = client.post('/api/tasks/quick-actions', json={
            'name': 'jad 反编译',
            'category': 'jvm',
            'command_template': 'jad {class_name}',
            'risk_level': 'low',
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['ok'] is True
        assert data['action']['name'] == 'jad 反编译'

    def test_list_quick_actions(self, client):
        """GET /tasks/quick-actions returns list."""
        resp = client.get('/api/tasks/quick-actions')
        assert resp.status_code == 200
        assert 'actions' in resp.get_json()


class TestBatchDistribute:
    """Test batch distribution endpoint."""

    def test_batch_distribute_validation(self, client):
        """POST /tasks/batch-distribute rejects empty targets."""
        resp = client.post('/api/tasks/batch-distribute', json={
            'tool_ids': [],
            'targets': [],
        })
        assert resp.status_code == 400
```

- [ ] **Step 2: Run tests**

```bash
cd E:\tmp\k8s-arthas-tool
python -m pytest tests/test_toolbox.py -v
```

Expected: All tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/test_toolbox.py
git commit -m "test: add unit tests for toolbox API endpoints"
```

---

### Task 12: Integration Verification

**Covers:** [S1-S9]

**Files:**
- None (verification only)

- [ ] **Step 1: Run full test suite**

```bash
python -m pytest tests/ -v
```

Expected: All existing tests pass, new tests pass.

- [ ] **Step 2: Start server and verify UI**

```bash
python server.py
```

Open browser, navigate to:
1. Sidebar: verify new menu structure (连接管理 → 诊断 → 实时操作 → 工具箱 → 任务中心 → 系统管理)
2. 工具箱: verify three card sections (二进制工具、脚本工具、快捷操作)
3. 批量分发: click "批量分发" button, verify Step 1-3 wizard
4. 单个分发: click "分发→" on a binary tool card, verify inline form
5. 连接中心: verify batch action bar with checkboxes

- [ ] **Step 3: Commit final state**

```bash
git add -A
git commit -m "feat: toolbox redesign complete - card layout, batch distribute, capability-aware"
```
