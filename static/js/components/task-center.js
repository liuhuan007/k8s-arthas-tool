/**
 * 任务中心组件 - 重构版
 * 
 * 功能：
 * 1. 任务定义管理（创建/编辑/删除）
 * 2. 执行历史查询（即时诊断/定时任务）
 * 3. 定时调度管理（Cron/间隔/一次性）
 */
(function() {
  'use strict';
  console.log('[TaskCenter] loaded version 20260514b');

  /**
   * 初始化任务中心
   */
  window.initTaskCenterV2 = async function() {
    await Promise.all([
      loadTaskDefinitions(),
      loadTaskLogs(),
      loadTaskSchedules(),
      loadTaskStats()
    ]);
  };

  /**
   * 加载任务统计
   */
  async function loadTaskStats() {
    try {
      const data = await safeGet('/tasks/overview');
      const stats = data.stats || data;

      // 更新统计卡片
      const total = (stats.running || 0) + (stats.pending || 0) + (stats.success || 0) + (stats.failed || 0) + (stats.cancelled || 0);
      document.getElementById('tcStatTotal').textContent = total;
      document.getElementById('tcStatRunning').textContent = stats.running || 0;
      document.getElementById('tcStatPending').textContent = stats.pending || 0;
      document.getElementById('tcStatSuccess').textContent = stats.success || 0;
      document.getElementById('tcStatFailed').textContent = stats.failed || 0;

      // 计算成功率
      const successRate = total > 0 ? Math.round(((stats.success || 0) / total) * 100) : 0;
      document.getElementById('tcStatSuccessRate').textContent = `${successRate}%`;
    } catch (e) {
      console.error('加载任务统计失败:', e);
    }
  }

  /**
   * 按状态筛选任务
   */
  window.filterByStatus = function(status) {
    // 切换到执行历史 Tab
    switchTCTab('logs');

    // 筛选日志列表
    const logItems = document.querySelectorAll('.task-log-item');
    logItems.forEach(item => {
      if (status === 'all') {
        item.style.display = '';
      } else {
        const itemStatus = item.dataset.status;
        item.style.display = itemStatus === status ? '' : 'none';
      }
    });

    // 更新 Tab 高亮
    document.querySelectorAll('.tc-stat-card').forEach(card => {
      card.classList.remove('active');
    });
    event.currentTarget.classList.add('active');
  };
  
  /**
   * 切换 Tab
   */
  window.switchTCTab = function(tabName) {
    // 更新按钮状态
    document.querySelectorAll('.tc-tab').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.tcTab === tabName);
    });
    
    // 更新面板显示
    document.querySelectorAll('.tc-panel').forEach(panel => {
      panel.style.display = 'none';
    });
    document.getElementById(`tcPanel-${tabName}`).style.display = 'block';
  };
  
  /**
   * 打开创建任务模态框
   */
  window.openCreateTaskModal = function() {
    console.log('[TaskCenter] openCreateTaskModal called');
    const modal = document.createElement('div');
    modal.className = 'capability-modal-overlay';
    modal.style.cssText = 'position:fixed;inset:0;z-index:12000;display:flex;align-items:center;justify-content:center;padding:24px;background:rgba(5,8,14,.72);backdrop-filter:blur(8px)';
    modal.innerHTML = `
      <div class="capability-modal" style="width:min(720px,96vw);max-height:86vh;overflow:hidden;border:1px solid var(--border-color,var(--ln,#2a3a52));border-radius:12px;background:var(--bg-card,var(--bg1,#101827));box-shadow:0 24px 80px rgba(0,0,0,.48);display:flex;flex-direction:column">
        <div class="modal-header">
          <h3>创建任务</h3>
          <button class="btn-close" onclick="this.closest('.capability-modal-overlay').remove()">✕</button>
        </div>
        <div class="modal-body" style="padding:20px;overflow:auto;max-height:calc(86vh - 80px)">
          <div class="form-group">
            <label class="form-label">任务名称 <span class="required">*</span></label>
            <input id="newTaskName" class="form-input" placeholder="例如：CPU 巡检">
          </div>
          <div class="form-group">
            <label class="form-label">执行位置</label>
            <select id="newTaskExecMode" class="form-input" onchange="document.getElementById('newTaskPodTarget').style.display=this.value==='pod'?'block':'none'">
              <option value="node">服务端本机</option>
              <option value="pod">Pod 内执行</option>
            </select>
          </div>
          <div class="form-group">
            <label class="form-label">脚本运行时</label>
            <select id="newTaskRuntime" class="form-input">
              <option value="python">Python</option>
              <option value="shell">Shell</option>
            </select>
          </div>
          <div class="form-group">
            <label class="form-label">超时时间(秒)</label>
            <input id="newTaskTimeout" class="form-input" type="number" min="1" max="600" value="60">
          </div>
          <div id="newTaskPodTarget" style="display:none">
            <div class="form-group"><label class="form-label">集群名称</label><input id="newTaskCluster" class="form-input" placeholder="cluster name"></div>
            <div class="form-group"><label class="form-label">命名空间</label><input id="newTaskNamespace" class="form-input" placeholder="default"></div>
            <div class="form-group"><label class="form-label">Pod 名称</label><input id="newTaskPod" class="form-input" placeholder="pod name"></div>
            <div class="form-group"><label class="form-label">容器名</label><input id="newTaskContainer" class="form-input" placeholder="可选"></div>
          </div>
          <div class="form-group">
            <label class="form-label">脚本内容 <span class="required">*</span></label>
            <textarea id="newTaskScript" class="form-input" rows="8" placeholder="print('hello')"></textarea>
          </div>
        </div>
        <div class="modal-footer" style="padding:16px 20px;border-top:1px solid var(--border-color);display:flex;justify-content:flex-end;gap:8px">
          <button class="btn btn-g" onclick="this.closest('.capability-modal-overlay').remove()">取消</button>
          <button class="btn btn-p" onclick="submitCreateTaskV2()">创建</button>
        </div>
      </div>
    `;
    document.body.appendChild(modal);
    modal.addEventListener('click', (e) => {
      if (e.target === modal) modal.remove();
    });
  };
  
  /**
   * 提交创建任务
   */
  window.submitCreateTaskV2 = async function() {
    const name = document.getElementById('newTaskName').value.trim();
    if (!name) {
      alert('请输入任务名称');
      return;
    }
    const scriptBody = document.getElementById('newTaskScript').value.trim();
    if (!scriptBody) {
      alert('请输入脚本内容');
      return;
    }
    
    try {
      const executionMode = document.getElementById('newTaskExecMode').value;
      const target = executionMode === 'pod' ? {
        cluster_name: document.getElementById('newTaskCluster').value.trim(),
        namespace: document.getElementById('newTaskNamespace').value.trim(),
        pod_name: document.getElementById('newTaskPod').value.trim(),
        container: document.getElementById('newTaskContainer').value.trim(),
      } : {};
      if (executionMode === 'pod' && (!target.cluster_name || !target.namespace || !target.pod_name)) {
        alert('Pod 内执行需要填写集群、命名空间和 Pod 名称');
        return;
      }
      await safePost('/tasks/definitions', {
        name: name,
        execution_mode: executionMode,
        runtime: document.getElementById('newTaskRuntime').value,
        timeout_seconds: Number(document.getElementById('newTaskTimeout').value || 60),
        script_body: scriptBody,
        target,
      });
      
      toast('任务创建成功', 'ok');
      document.querySelector('.capability-modal-overlay')?.remove();
      await loadTaskDefinitions();
      await loadTaskLogs();
      if (typeof switchTCTab === 'function') switchTCTab('definitions');
    } catch (e) {
      toast(`创建失败：${e.message}`, 'err');
    }
  };

  /**
   * 加载任务定义
   */
  async function loadTaskDefinitions() {
    try {
      const data = await safeGet('/tasks/definitions');
      renderTaskDefinitions(data.tasks || data.definitions || []);
    } catch (e) {
      console.error('加载任务定义失败:', e);
    }
  }

  /**
   * 渲染任务定义列表
   */
  function renderTaskDefinitions(definitions) {
    const container = document.getElementById('taskDefList');
    if (!container) return;

    if (definitions.length === 0) {
      container.innerHTML = `
        <div class="tc-empty-state">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" opacity=".25">
            <rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18"/><path d="M9 21V9"/>
          </svg>
          <div class="tc-empty-title">暂无任务定义</div>
          <div class="tc-empty-sub">点击「新建任务」创建第一个任务</div>
        </div>
      `;
      return;
    }

    container.innerHTML = definitions.map(def => {
      const modeConfig = {
        immediate: { text: '即时诊断', icon: '⚡', cls: 'tc-mode-immediate' },
        manual: { text: '手动任务', icon: '▶️', cls: 'tc-mode-manual' },
        scheduled: { text: '定时任务', icon: '⏰', cls: 'tc-mode-scheduled' }
      };
      const mode = modeConfig[def.execution_mode] || { text: def.execution_mode, icon: '📋', cls: '' };

      const runtimeIcon = def.runtime === 'python' ? '🐍' : '📜';
      const execCount = def.execution_count || 0;
      const lastExec = def.last_executed_at ? formatTimeAgo(def.last_executed_at) : '从未执行';

      return `
        <div class="tc-task-card" data-id="${def.id}">
          <div class="tc-task-header">
            <div class="tc-task-title-row">
              <span class="tc-task-icon">${mode.icon}</span>
              <span class="tc-task-name">${escapeHtml(def.name)}</span>
              <span class="tc-mode-badge ${mode.cls}">${mode.text}</span>
            </div>
            <div class="tc-task-actions">
              <button class="tc-btn tc-btn-primary" onclick="executeTaskDefinition(${def.id})" title="执行任务">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                执行
              </button>
              <button class="tc-btn tc-btn-ghost" onclick="editTaskDefinition(${def.id})" title="编辑任务">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
              </button>
              <button class="tc-btn tc-btn-ghost tc-btn-danger" onclick="deleteTaskDefinition(${def.id})" title="删除任务">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
              </button>
            </div>
          </div>
          <div class="tc-task-meta">
            <span class="tc-meta-item" title="运行时">
              ${runtimeIcon} ${def.runtime || 'shell'}
            </span>
            <span class="tc-meta-item" title="超时时间">
              ⏱️ ${def.timeout_seconds || 60}s
            </span>
            <span class="tc-meta-item" title="执行次数">
              📊 执行 ${execCount} 次
            </span>
            <span class="tc-meta-item" title="最后执行">
              🕐 ${lastExec}
            </span>
          </div>
          ${def.description ? `<div class="tc-task-desc">${escapeHtml(def.description)}</div>` : ''}
        </div>
      `;
    }).join('');
  }

  /**
   * 格式化时间为 "多久前"
   */
  function formatTimeAgo(dateStr) {
    if (!dateStr) return '未知';
    const date = new Date(dateStr);
    const now = new Date();
    const diff = Math.floor((now - date) / 1000);

    if (diff < 60) return '刚刚';
    if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`;
    if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`;
    if (diff < 604800) return `${Math.floor(diff / 86400)} 天前`;
    return date.toLocaleDateString('zh-CN');
  }

  /**
   * 加载执行历史
   */
  async function loadTaskLogs() {
    try {
      const data = await safeGet('/tasks/runs', { limit: 20 });
      renderTaskLogs(data.runs || []);
    } catch (e) {
      console.error('加载执行历史失败:', e);
    }
  }

  /**
   * 渲染执行历史
   */
  function renderTaskLogs(logs) {
    const container = document.getElementById('taskLogList');
    if (!container) return;

    if (logs.length === 0) {
      container.innerHTML = `
        <div class="tc-empty-state">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" opacity=".25">
            <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
          </svg>
          <div class="tc-empty-title">暂无执行记录</div>
          <div class="tc-empty-sub">执行任务后，记录将显示在这里</div>
        </div>
      `;
      return;
    }

    container.innerHTML = logs.map(log => {
      const statusConfig = {
        success: { text: '成功', cls: 'tc-status-success', icon: '✓' },
        failed: { text: '失败', cls: 'tc-status-failed', icon: '✕' },
        running: { text: '执行中', cls: 'tc-status-running', icon: '⟳' },
        pending: { text: '待处理', cls: 'tc-status-pending', icon: '⏳' },
        cancelled: { text: '已取消', cls: 'tc-status-cancelled', icon: '⊘' },
        partial: { text: '部分成功', cls: 'tc-status-partial', icon: '⚠' }
      };
      const status = statusConfig[log.status] || { text: log.status, cls: '', icon: '?' };

      const duration = log.duration_ms ? (log.duration_ms >= 1000 ? `${(log.duration_ms / 1000).toFixed(1)}s` : `${log.duration_ms}ms`) : '-';
      const timeAgo = formatTimeAgo(log.started_at);

      return `
        <div class="tc-log-item" data-status="${log.status}" onclick="viewTaskLogDetail(${log.id})">
          <div class="tc-log-status ${status.cls}">
            <span class="tc-status-icon">${status.icon}</span>
          </div>
          <div class="tc-log-content">
            <div class="tc-log-title">${escapeHtml(log.task_name || log.capability_name || '即时诊断')}</div>
            <div class="tc-log-meta">
              <span class="tc-log-time" title="${log.started_at}">${timeAgo}</span>
              <span class="tc-log-duration">耗时 ${duration}</span>
              ${log.execution_mode ? `<span class="tc-log-mode">${log.execution_mode}</span>` : ''}
            </div>
          </div>
          <div class="tc-log-actions">
            <span class="tc-status-badge ${status.cls}">${status.text}</span>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="tc-log-arrow">
              <polyline points="9 18 15 12 9 6"/>
            </svg>
          </div>
        </div>
      `;
    }).join('');
  }

  /**
   * 加载定时调度
   */
  async function loadTaskSchedules() {
    try {
      const data = await safeGet('/tasks/schedules');
      renderTaskSchedules(data.schedules || []);
    } catch (e) {
      console.error('加载定时调度失败:', e);
    }
  }

  /**
   * 渲染定时调度列表
   */
  function renderTaskSchedules(schedules) {
    const container = document.getElementById('taskScheduleList');
    if (!container) return;

    if (schedules.length === 0) {
      container.innerHTML = `
        <div class="tc-empty-state">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" opacity=".25">
            <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
          </svg>
          <div class="tc-empty-title">暂无定时任务</div>
          <div class="tc-empty-sub">创建定时调度以开始使用</div>
        </div>
      `;
      return;
    }

    container.innerHTML = schedules.map(s => {
      const isActive = s.status === 'active';
      const scheduleType = s.schedule_type === 'cron' ? 'Cron' : '间隔';
      const scheduleValue = s.schedule_type === 'cron' ? s.cron_expression : `${s.interval_seconds}s`;
      const nextRun = s.next_run_at ? formatTimeAgo(s.next_run_at) : '-';
      const execCount = s.execution_count || 0;

      return `
        <div class="tc-schedule-item ${isActive ? 'tc-schedule-active' : 'tc-schedule-paused'}">
          <div class="tc-schedule-header">
            <div class="tc-schedule-title-row">
              <span class="tc-schedule-icon">${isActive ? '🟢' : '⏸️'}</span>
              <span class="tc-schedule-name">${escapeHtml(s.name)}</span>
              <span class="tc-schedule-status ${isActive ? 'tc-active' : 'tc-paused'}">${isActive ? '运行中' : '已暂停'}</span>
            </div>
            <div class="tc-schedule-actions">
              <button class="tc-btn tc-btn-ghost" onclick="toggleSchedule(${s.id}, '${isActive ? 'paused' : 'active'}')" title="${isActive ? '暂停' : '恢复'}">
                ${isActive ? '⏸️' : '▶️'}
              </button>
              <button class="tc-btn tc-btn-ghost tc-btn-danger" onclick="deleteSchedule(${s.id})" title="删除">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
              </button>
            </div>
          </div>
          <div class="tc-schedule-meta">
            <span class="tc-meta-item" title="调度类型">
              📅 ${scheduleType}: ${scheduleValue}
            </span>
            <span class="tc-meta-item" title="执行次数">
              📊 已执行 ${execCount} 次
            </span>
            <span class="tc-meta-item" title="下次执行">
              ⏰ 下次：${nextRun}
            </span>
          </div>
        </div>
      `;
    }).join('');
  }

  /**
   * 执行任务定义
   */
  window.executeTaskDefinition = async function(defId) {
    try {
      toast('开始执行任务...', 'info');
      const result = await safePost(`/tasks/definitions/${defId}/run`, {}, 650000);
      const runId = result.run?.id || result.run?.run_id;
      const status = result.run?.status || 'unknown';
      toast(status === 'success' ? '任务执行成功' : '任务执行完成，请查看日志', status === 'success' ? 'ok' : 'warn');
      loadTaskLogs();
      if (runId) setTimeout(() => window.viewTaskLogDetail(runId), 80);
    } catch (e) {
      toast(`执行失败：${e.message}`, 'err');
    }
  };

  /**
   * 查看执行详情
   */
  window.viewTaskLogDetail = async function(logId) {
    try {
      const data = await safeGet(`/tasks/runs/${logId}/logs`);
      const log = data.run;

      const result = log.result || (log.result_json ? JSON.parse(log.result_json) : null);
      const stdout = log.stdout || result?.stdout || '';
      const stderr = log.stderr || result?.stderr || '';
      const errorMsg = log.error_message || result?.error || '';

      const statusConfig = {
        success: { text: '成功', cls: 'tc-detail-success', icon: '✓' },
        failed: { text: '失败', cls: 'tc-detail-failed', icon: '✕' },
        running: { text: '执行中', cls: 'tc-detail-running', icon: '⟳' },
        pending: { text: '待处理', cls: 'tc-detail-pending', icon: '⏳' },
        cancelled: { text: '已取消', cls: 'tc-detail-cancelled', icon: '⊘' }
      };
      const status = statusConfig[log.status] || { text: log.status, cls: '', icon: '?' };
      const duration = log.duration_ms ? (log.duration_ms >= 1000 ? `${(log.duration_ms / 1000).toFixed(2)}s` : `${log.duration_ms}ms`) : '-';

      // 创建详情模态框
      const modal = document.createElement('div');
      modal.className = 'tc-modal-overlay';
      modal.innerHTML = `
        <div class="tc-modal">
          <div class="tc-modal-header">
            <div class="tc-modal-title-row">
              <span class="tc-modal-icon ${status.cls}">${status.icon}</span>
              <div>
                <h3 class="tc-modal-title">${escapeHtml(log.task_name || log.capability_name || '执行详情')}</h3>
                <span class="tc-modal-subtitle">ID: ${log.id}</span>
              </div>
            </div>
            <button class="tc-modal-close" onclick="this.closest('.tc-modal-overlay').remove()">&times;</button>
          </div>

          <div class="tc-modal-body">
            <!-- 状态卡片 -->
            <div class="tc-detail-status-card ${status.cls}">
              <div class="tc-detail-stat">
                <span class="tc-detail-stat-label">状态</span>
                <span class="tc-detail-stat-value">${status.text}</span>
              </div>
              <div class="tc-detail-stat">
                <span class="tc-detail-stat-label">耗时</span>
                <span class="tc-detail-stat-value">${duration}</span>
              </div>
              <div class="tc-detail-stat">
                <span class="tc-detail-stat-label">开始时间</span>
                <span class="tc-detail-stat-value">${log.started_at || '-'}</span>
              </div>
              <div class="tc-detail-stat">
                <span class="tc-detail-stat-label">执行模式</span>
                <span class="tc-detail-stat-value">${log.execution_mode || '-'}</span>
              </div>
            </div>

            <!-- 基本信息 -->
            <div class="tc-detail-section">
              <h4 class="tc-detail-section-title">基本信息</h4>
              <div class="tc-detail-grid">
                <div class="tc-detail-item">
                  <span class="tc-detail-label">能力名称</span>
                  <span class="tc-detail-value">${escapeHtml(log.capability_name || '-')}</span>
                </div>
                <div class="tc-detail-item">
                  <span class="tc-detail-label">能力版本</span>
                  <span class="tc-detail-value">${log.capability_version || '-'}</span>
                </div>
                <div class="tc-detail-item">
                  <span class="tc-detail-label">执行类型</span>
                  <span class="tc-detail-value">${log.execution_type || '-'}</span>
                </div>
                <div class="tc-detail-item">
                  <span class="tc-detail-label">退出码</span>
                  <span class="tc-detail-value">${log.exit_code ?? '-'}</span>
                </div>
              </div>
            </div>

            ${errorMsg ? `
            <!-- 错误信息 -->
            <div class="tc-detail-section">
              <h4 class="tc-detail-section-title tc-text-danger">错误信息</h4>
              <div class="tc-detail-error">${escapeHtml(errorMsg)}</div>
            </div>
            ` : ''}

            ${stdout ? `
            <!-- 标准输出 -->
            <div class="tc-detail-section">
              <h4 class="tc-detail-section-title">标准输出</h4>
              <pre class="tc-detail-output tc-detail-stdout">${escapeHtml(stdout)}</pre>
            </div>
            ` : ''}

            ${stderr ? `
            <!-- 标准错误 -->
            <div class="tc-detail-section">
              <h4 class="tc-detail-section-title tc-text-warning">标准错误</h4>
              <pre class="tc-detail-output tc-detail-stderr">${escapeHtml(stderr)}</pre>
            </div>
            ` : ''}

            ${log.rendered_command ? `
            <!-- 执行命令 -->
            <div class="tc-detail-section">
              <h4 class="tc-detail-section-title">执行命令</h4>
              <pre class="tc-detail-output tc-detail-command">${escapeHtml(log.rendered_command)}</pre>
            </div>
            ` : ''}
          </div>

          <div class="tc-modal-footer">
            ${log.status === 'running' ? `<button class="tc-btn tc-btn-danger" onclick="cancelTaskRun(${log.id})">取消执行</button>` : ''}
            ${log.status === 'failed' ? `<button class="tc-btn tc-btn-primary" onclick="retryTaskRun(${log.id})">重试</button>` : ''}
            <button class="tc-btn" onclick="this.closest('.tc-modal-overlay').remove()">关闭</button>
          </div>
        </div>
      `;

      document.body.appendChild(modal);
      modal.addEventListener('click', (e) => {
        if (e.target === modal) modal.remove();
      });
    } catch (e) {
      toast(`加载详情失败：${e.message}`, 'err');
    }
  };

  /**
   * 取消任务执行
   */
  window.cancelTaskRun = async function(runId) {
    if (!confirm('确认取消此任务执行？')) return;
    try {
      await safePost(`/tasks/runs/${runId}/cancel`);
      toast('任务已取消', 'ok');
      document.querySelector('.tc-modal-overlay')?.remove();
      loadTaskLogs();
    } catch (e) {
      toast(`取消失败：${e.message}`, 'err');
    }
  };

  /**
   * 重试任务执行
   */
  window.retryTaskRun = async function(runId) {
    if (!confirm('确认重试此任务？')) return;
    try {
      toast('正在重试任务...', 'info');
      document.querySelector('.tc-modal-overlay')?.remove();
      loadTaskLogs();
    } catch (e) {
      toast(`重试失败：${e.message}`, 'err');
    }
  };

  /**
   * 切换调度状态
   */
  window.toggleSchedule = async function(scheduleId, status) {
    try {
      await safePut(`/tasks/schedules/${scheduleId}`, { status });
      toast(status === 'active' ? '调度已恢复' : '调度已暂停', 'ok');
      loadTaskSchedules();
    } catch (e) {
      toast(`操作失败：${e.message}`, 'err');
    }
  };

  /**
   * 删除调度
   */
  window.deleteSchedule = async function(scheduleId) {
    if (!confirm('确认删除此定时任务？')) return;
    try {
      await safeDelete(`/tasks/schedules/${scheduleId}`);
      toast('定时任务已删除', 'ok');
      loadTaskSchedules();
    } catch (e) {
      toast(`删除失败：${e.message}`, 'err');
    }
  };

  /**
   * HTML 转义
   */
  function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

})();
