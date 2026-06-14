/**
 * task-center.js — 任务中心内容面板（无内部侧边栏）
 * 侧边栏子菜单由主侧边栏提供，此文件只负责渲染内容区
 */
(function () {
  'use strict';

  var _activePanel = 'tasks';
  var _tasks = [];
  var _runs = [];
  var _stats = {};

  // ── 公开入口 ──────────────────────────────────────────────────────────
  window.initTaskCenterV2 = async function () {
    _renderContent();
    await _loadAll();
  };

  window.scSwitchPanel = function (panel) {
    _activePanel = panel;
    // 更新主侧边栏高亮
    document.querySelectorAll('[data-nav-tab]').forEach(function (el) {
      var tab = el.getAttribute('data-nav-tab');
      var isActive = (tab === 'task-center' && panel === 'tasks')
        || (tab === 'task-schedules' && panel === 'schedules')
        || (tab === 'task-runs' && panel === 'runs')
        || (tab === 'task-scripts' && panel === 'scripts');
      el.classList.toggle('on', isActive);
    });
    // 更新内容面板
    document.querySelectorAll('.sc-panel').forEach(function (el) {
      el.classList.toggle('active', el.id === 'sc-panel-' + panel);
    });
    // 渲染
    if (panel === 'tasks') _renderTaskCards();
    if (panel === 'schedules') _renderScheduleList();
    if (panel === 'runs') _renderRunTable();
    if (panel === 'scripts') _renderScriptLibrary();
  };

  // ── 内容渲染（无内部侧边栏） ─────────────────────────────────────────
  function _renderContent() {
    var container = document.getElementById('panel-task-center');
    if (!container) return;

    // 隐藏旧的 hero / tabs / stats
    var opsPage = container.querySelector('.ops-page');
    if (opsPage) { opsPage.style.padding = '0'; opsPage.style.overflow = 'hidden'; }
    var hero = container.querySelector('.ops-hero');
    if (hero) hero.style.display = 'none';
    var tabs = container.querySelector('.task-center-tabs');
    if (tabs) tabs.style.display = 'none';
    var statsDash = container.querySelector('.tc-stats-dashboard');
    if (statsDash) statsDash.style.display = 'none';

    container.innerHTML = ''
      + '<div style="display:flex;flex-direction:column;height:100%;overflow:hidden">'
      // 顶栏
      + '<div class="sc-topbar">'
      + '  <span class="sc-topbar-title" id="sc-topbar-title">📋 任务列表</span>'
      + '  <div class="sc-topbar-stats" id="sc-topbar-stats"></div>'
      + '  <button class="sc-btn-new" onclick="scOpenWizard()">+ 新建任务</button>'
      + '</div>'
      // 内容区
      + '<div class="sc-content">'
      + '  <div class="sc-panel active" id="sc-panel-tasks"></div>'
      + '  <div class="sc-panel" id="sc-panel-schedules"></div>'
      + '  <div class="sc-panel" id="sc-panel-runs"></div>'
      + '  <div class="sc-panel" id="sc-panel-scripts"></div>'
      + '</div>'
      + '</div>';
  }

  // ── 数据加载 ──────────────────────────────────────────────────────────
  async function _loadAll() {
    try {
      var data = await safeGet('/scheduler/tasks', {});
      _tasks = data.tasks || [];
    } catch (e) { console.error('[scheduler] load tasks:', e); }
    try {
      var rData = await safeGet('/scheduler/runs', { limit: 100 });
      _runs = rData.runs || [];
    } catch (e) { console.error('[scheduler] load runs:', e); }
    try {
      _stats = await safeGet('/scheduler/stats', {});
    } catch (e) {}
    _updateStats();
    _renderTaskCards();
  }

  window.scLoadTasks = async function () {
    try {
      var data = await safeGet('/scheduler/tasks', {});
      _tasks = data.tasks || [];
    } catch (e) {}
    try {
      var rData = await safeGet('/scheduler/runs', { limit: 100 });
      _runs = rData.runs || [];
    } catch (e) {}
    _updateStats();
    _renderTaskCards();
  };

  function _updateStats() {
    var el = document.getElementById('sc-topbar-stats');
    if (!el) return;
    el.innerHTML = ''
      + '<span class="sc-stat-badge all">全部 ' + (_stats.total_tasks || _tasks.length) + '</span>'
      + '<span class="sc-stat-badge active">活跃 ' + (_tasks.filter(function (t) { return t.schedule_enabled; }).length) + '</span>'
      + '<span class="sc-stat-badge scheduled">调度中 ' + (_stats.active_schedules || 0) + '</span>';
  }

  // ── 任务列表 ──────────────────────────────────────────────────────────
  function _renderTaskCards() {
    var panel = document.getElementById('sc-panel-tasks');
    if (!panel) return;
    if (_tasks.length === 0) {
      panel.innerHTML = '<div class="sc-empty">'
        + '<div class="sc-empty-icon">📋</div>'
        + '<div class="sc-empty-title">暂无任务</div>'
        + '<div class="sc-empty-desc">创建你的第一个脚本任务，支持 Shell/Python/Binary 运行时，可配置定时调度</div>'
        + '<button class="sc-empty-action" onclick="scOpenWizard()">+ 新建任务</button>'
        + '</div>';
      return;
    }
    panel.innerHTML = _tasks.map(function (t) { return _renderTaskCard(t); }).join('');
  }

  function _renderTaskCard(task) {
    var runtimeTag = '<span class="sc-tag ' + (task.runtime || 'shell') + '">' + (task.runtime || 'shell').toUpperCase() + '</span>';
    var targetTag = '<span class="sc-tag ' + (task.target_type || 'node') + '">' + _targetLabel(task.target_type) + '</span>';
    var schedTag = '';
    if (task.schedule_type && task.schedule_type !== 'none') {
      var schedText = task.schedule_type === 'cron' ? '⏱ ' + (task.cron_expr || '') : '🔁 ' + (task.interval_seconds || 0) + 's';
      schedTag = '<span class="sc-tag schedule">' + schedText + '</span>';
    }
    var lastRun = '';
    if (task.last_run) {
      var cls = task.last_run.status === 'success' ? 'success' : task.last_run.status === 'failed' ? 'failed' : 'pending';
      var label = task.last_run.status === 'success' ? '● 上次成功' : task.last_run.status === 'failed' ? '● 上次失败' : '● ' + task.last_run.status;
      var time = task.last_run.completed_at ? _timeAgo(task.last_run.completed_at) : '';
      lastRun = '<span class="sc-task-last-run ' + cls + '">' + label + ' ' + time + '</span>';
    }
    return '<div class="sc-task-card">'
      + '<div class="sc-task-header">'
      + '  <span class="sc-task-name">' + _esc(task.name) + '</span>'
      + '  ' + runtimeTag + ' ' + targetTag + ' ' + schedTag
      + '  ' + lastRun
      + '</div>'
      + '<div class="sc-task-desc">' + _esc(task.description || '暂无描述') + '</div>'
      + '<div class="sc-task-actions">'
      + '  <button class="sc-btn-sm primary" onclick="scRunTask(\'' + task.id + '\')">▶ 立即执行</button>'
      + '  <button class="sc-btn-sm secondary" onclick="scEditTask(\'' + task.id + '\')">编辑</button>'
      + '  <button class="sc-btn-sm secondary" onclick="scViewRuns(\'' + task.id + '\')">查看记录</button>'
      + '  <button class="sc-btn-sm danger" onclick="scDeleteTask(\'' + task.id + '\')">删除</button>'
      + '</div>'
    + '</div>';
  }

  // ── 调度管理 ──────────────────────────────────────────────────────────
  function _renderScheduleList() {
    var panel = document.getElementById('sc-panel-schedules');
    if (!panel) return;
    var scheduled = _tasks.filter(function (t) { return t.schedule_type && t.schedule_type !== 'none'; });
    if (scheduled.length === 0) {
      panel.innerHTML = '<div class="sc-empty">'
        + '<div class="sc-empty-icon">⏱</div>'
        + '<div class="sc-empty-title">暂无调度任务</div>'
        + '<div class="sc-empty-desc">在任务创建向导的第 3 步配置 Cron 或固定间隔调度</div>'
        + '</div>';
      return;
    }
    var rows = scheduled.map(function (t) {
      var nextRun = t.next_run_at ? new Date(t.next_run_at).toLocaleString('zh-CN') : '-';
      var lastRun = t.last_run_at ? _timeAgo(t.last_run_at) : '-';
      var statusBadge = t.schedule_enabled
        ? '<span class="sc-run-status success">活跃</span>'
        : '<span class="sc-run-status pending">已暂停</span>';
      return '<tr>'
        + '<td>' + _esc(t.name) + '</td>'
        + '<td>' + statusBadge + '</td>'
        + '<td>' + _esc(t.schedule_type === 'cron' ? t.cron_expr : ('每 ' + t.interval_seconds + 's')) + '</td>'
        + '<td>' + nextRun + '</td>'
        + '<td>' + lastRun + '</td>'
        + '<td><button class="sc-btn-sm secondary" onclick="scToggleSchedule(\'' + t.id + '\',' + (t.schedule_enabled ? 'false' : 'true') + ')">' + (t.schedule_enabled ? '暂停' : '恢复') + '</button></td>'
      + '</tr>';
    }).join('');
    panel.innerHTML = '<table class="sc-run-table"><thead><tr>'
      + '<th>任务名称</th><th>状态</th><th>调度规则</th><th>下次执行</th><th>上次执行</th><th>操作</th>'
      + '</tr></thead><tbody>' + rows + '</tbody></table>';
  }

  // ── 执行记录 ──────────────────────────────────────────────────────────
  function _renderRunTable() {
    var panel = document.getElementById('sc-panel-runs');
    if (!panel) return;
    if (_runs.length === 0) {
      panel.innerHTML = '<div class="sc-empty">'
        + '<div class="sc-empty-icon">📊</div>'
        + '<div class="sc-empty-title">暂无执行记录</div>'
        + '<div class="sc-empty-desc">执行任务后，运行记录将在此显示</div>'
        + '</div>';
      return;
    }
    var rows = _runs.map(function (r) {
      var statusCls = r.status || 'pending';
      var duration = (r.started_at && r.completed_at)
        ? ((new Date(r.completed_at) - new Date(r.started_at)) / 1000).toFixed(1) + 's' : '-';
      return '<tr>'
        + '<td>' + _esc(r.task_name || r.task_id) + '</td>'
        + '<td><span class="sc-run-status ' + statusCls + '">' + _statusText(r.status) + '</span></td>'
        + '<td>' + _esc(r.trigger_type || '-') + '</td>'
        + '<td>' + duration + '</td>'
        + '<td>' + (r.exit_code != null ? r.exit_code : '-') + '</td>'
        + '<td>' + _timeAgo(r.created_at) + '</td>'
        + '<td><button class="sc-btn-sm secondary" onclick="scViewRunDetail(\'' + r.id + '\')">查看</button></td>'
      + '</tr>';
    }).join('');
    panel.innerHTML = '<table class="sc-run-table"><thead><tr>'
      + '<th>任务</th><th>状态</th><th>触发</th><th>耗时</th><th>退出码</th><th>时间</th><th>操作</th>'
      + '</tr></thead><tbody>' + rows + '</tbody></table>';
  }

  // ── 脚本库 ──────────────────────────────────────────────────────────
  function _renderScriptLibrary() {
    var panel = document.getElementById('sc-panel-scripts');
    if (!panel) return;
    var scripts = _tasks.filter(function (t) { return t.script_content; });
    if (scripts.length === 0) {
      panel.innerHTML = '<div class="sc-empty">'
        + '<div class="sc-empty-icon">📁</div>'
        + '<div class="sc-empty-title">暂无脚本</div>'
        + '<div class="sc-empty-desc">创建任务时编写脚本，会自动收录到脚本库</div>'
        + '</div>';
      return;
    }
    panel.innerHTML = scripts.map(function (t) {
      var preview = (t.script_content || '').substring(0, 200);
      return '<div class="sc-task-card">'
        + '<div class="sc-task-header">'
        + '  <span class="sc-task-name">' + _esc(t.name) + '</span>'
        + '  <span class="sc-tag ' + (t.runtime || 'shell') + '">' + (t.runtime || 'shell').toUpperCase() + '</span>'
        + '</div>'
        + '<pre style="background:var(--bg);border:1px solid var(--ln);border-radius:6px;padding:10px;font-size:11px;line-height:1.6;color:var(--tx2);max-height:120px;overflow:auto;margin:0 0 8px 0;white-space:pre-wrap">' + _esc(preview) + '</pre>'
        + '<div class="sc-task-actions">'
        + '  <button class="sc-btn-sm primary" onclick="scOpenWizard(_getTaskById(\'' + t.id + '\'))">编辑</button>'
        + '  <button class="sc-btn-sm secondary" onclick="scCopyScript(\'' + t.id + '\')">复制脚本</button>'
        + '</div>'
      + '</div>';
    }).join('');
  }

  // ── 操作函数 ──────────────────────────────────────────────────────────
  window.scRunTask = async function (taskId) {
    try {
      var result = await safePost('/scheduler/tasks/' + taskId + '/run', {});
      if (result && result.ok) {
        if (typeof toast === 'function') toast('任务已触发执行', 'success');
        await scLoadTasks();
      }
    } catch (e) { alert('执行失败: ' + e.message); }
  };

  window.scEditTask = function (taskId) {
    var task = _tasks.find(function (t) { return t.id === taskId; });
    if (task) scOpenWizard(task);
  };

  window.scDeleteTask = async function (taskId) {
    if (!confirm('确定要删除此任务？')) return;
    try {
      await safePost('/scheduler/tasks/' + taskId, {});
      if (typeof toast === 'function') toast('任务已删除', 'success');
      await scLoadTasks();
    } catch (e) { alert('删除失败: ' + e.message); }
  };

  window.scViewRuns = async function (taskId) {
    try {
      var data = await safeGet('/scheduler/tasks/' + taskId + '/runs', { limit: 50 });
      _runs = data.runs || [];
    } catch (e) { _runs = []; }
    scSwitchPanel('runs');
  };

  window.scToggleSchedule = async function (taskId, enabled) {
    try {
      await safePost('/scheduler/tasks/' + taskId + '/schedule', {
        enabled: enabled === 'true' || enabled === true ? 1 : 0,
      });
      await scLoadTasks();
      if (_activePanel === 'schedules') _renderScheduleList();
    } catch (e) { alert('操作失败: ' + e.message); }
  };

  window.scViewRunDetail = async function (runId) {
    try {
      var data = await safeGet('/scheduler/runs/' + runId, {});
      var run = data.run;
      if (!run) return;
      var overlay = document.createElement('div');
      overlay.className = 'sc-run-detail-overlay';
      overlay.onclick = function (e) { if (e.target === overlay) overlay.remove(); };
      overlay.innerHTML = '<div class="sc-run-detail">'
        + '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">'
        + '  <h3 style="font-size:14px;color:var(--tx);margin:0">运行详情</h3>'
        + '  <button class="sc-btn-sm secondary" onclick="this.closest(\'.sc-run-detail-overlay\').remove()">关闭</button>'
        + '</div>'
        + '<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:16px;font-size:12px">'
        + '  <div><span style="color:var(--tx3)">任务:</span> ' + _esc(run.task_name || run.task_id) + '</div>'
        + '  <div><span style="color:var(--tx3)">状态:</span> <span class="sc-run-status ' + run.status + '">' + _statusText(run.status) + '</span></div>'
        + '  <div><span style="color:var(--tx3)">触发:</span> ' + _esc(run.trigger_type) + '</div>'
        + '  <div><span style="color:var(--tx3)">退出码:</span> ' + (run.exit_code != null ? run.exit_code : '-') + '</div>'
        + '</div>'
        + (run.stdout ? '<div style="margin-bottom:12px"><div style="font-size:11px;color:var(--tx3);margin-bottom:4px">STDOUT</div><pre>' + _esc(run.stdout) + '</pre></div>' : '')
        + (run.stderr ? '<div style="margin-bottom:12px"><div style="font-size:11px;color:var(--tx3);margin-bottom:4px">STDERR</div><pre style="border-color:rgba(255,69,58,.2)">' + _esc(run.stderr) + '</pre></div>' : '')
        + (run.error ? '<div style="margin-bottom:12px"><div style="font-size:11px;color:#FF453A;margin-bottom:4px">ERROR</div><pre style="border-color:rgba(255,69,58,.2)">' + _esc(run.error) + '</pre></div>' : '')
        + '</div>';
      document.body.appendChild(overlay);
    } catch (e) { alert('加载失败: ' + e.message); }
  };

  window.scCopyScript = function (taskId) {
    var task = _tasks.find(function (t) { return t.id === taskId; });
    if (task && task.script_content) {
      navigator.clipboard.writeText(task.script_content).then(function () {
        if (typeof toast === 'function') toast('脚本已复制', 'success');
      });
    }
  };

  window._getTaskById = function (id) {
    return _tasks.find(function (t) { return t.id === id; });
  };

  // ── 工具函数 ──────────────────────────────────────────────────────────
  function _esc(s) {
    if (s == null) return '';
    var d = document.createElement('div');
    d.textContent = String(s);
    return d.innerHTML;
  }
  function _targetLabel(type) {
    var m = { node: 'NODE', pod: 'POD', pods: 'PODS', namespace: 'NS' };
    return m[type] || (type || 'NODE').toUpperCase();
  }
  function _statusText(s) {
    var m = { success: '成功', failed: '失败', running: '运行中', pending: '等待中', cancelled: '已取消' };
    return m[s] || s || '未知';
  }
  function _timeAgo(ts) {
    if (!ts) return '';
    var diff = (Date.now() - new Date(ts).getTime()) / 1000;
    if (diff < 60) return '刚刚';
    if (diff < 3600) return Math.floor(diff / 60) + '分钟前';
    if (diff < 86400) return Math.floor(diff / 3600) + '小时前';
    return Math.floor(diff / 86400) + '天前';
  }

})();
