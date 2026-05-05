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

  /**
   * 初始化任务中心
   */
  window.initTaskCenterV2 = async function() {
    await Promise.all([
      loadTaskDefinitions(),
      loadTaskLogs(),
      loadTaskSchedules()
    ]);
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
    modal.innerHTML = `
      <div class="capability-modal">
        <div class="modal-header">
          <h3>创建任务</h3>
          <button class="btn-close" onclick="this.closest('.capability-modal-overlay').remove()">✕</button>
        </div>
        <div class="modal-body" style="padding:20px">
          <div class="form-group">
            <label class="form-label">任务名称 <span class="required">*</span></label>
            <input id="newTaskName" class="form-input" placeholder="例如：CPU 巡检">
          </div>
          <div class="form-group">
            <label class="form-label">任务类型</label>
            <select id="newTaskType" class="form-input">
              <option value="script">脚本任务</option>
              <option value="pod_command">Pod 命令</option>
              <option value="diagnosis">诊断能力</option>
            </select>
          </div>
          <div class="form-group">
            <label class="form-label">执行模式</label>
            <select id="newTaskExecMode" class="form-input">
              <option value="manual">手动执行</option>
              <option value="scheduled">定时执行</option>
            </select>
          </div>
          <div class="form-group">
            <label class="form-label">描述</label>
            <textarea id="newTaskDesc" class="form-input" rows="3" placeholder="任务说明"></textarea>
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
    
    try {
      await safePost('/tasks/definitions', {
        name: name,
        execution_mode: document.getElementById('newTaskExecMode').value,
        description: document.getElementById('newTaskDesc').value
      });
      
      toast('任务创建成功', 'ok');
      document.querySelector('.capability-modal-overlay')?.remove();
      loadTaskDefinitions();
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
      renderTaskDefinitions(data.definitions || []);
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
      container.innerHTML = '<div class="sb-empty">暂无任务定义<br>创建任务以开始使用</div>';
      return;
    }

    container.innerHTML = definitions.map(def => {
      const modeText = {
        immediate: '即时诊断',
        manual: '手动任务',
        scheduled: '定时任务'
      }[def.execution_mode] || def.execution_mode;

      return `
        <div class="task-def-item">
          <div class="task-def-main">
            <div>
              <div class="task-item-name">${escapeHtml(def.name)}</div>
              <div class="task-item-meta">模式：${modeText} · 执行：${def.execution_count || 0} 次</div>
            </div>
            <div class="task-item-actions">
              <button class="btn btn-p" onclick="executeTaskDefinition(${def.id})">执行</button>
              <button class="btn btn-g" onclick="editTaskDefinition(${def.id})">编辑</button>
              <button class="btn btn-g danger-text" onclick="deleteTaskDefinition(${def.id})">删除</button>
            </div>
          </div>
        </div>
      `;
    }).join('');
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
      container.innerHTML = '<div class="sb-empty">暂无执行记录</div>';
      return;
    }

    container.innerHTML = logs.map(log => {
      const statusClass = log.status === 'success' ? 'running' : 'stopped';
      const statusText = {
        success: '成功',
        failed: '失败',
        running: '执行中',
        partial: '部分成功'
      }[log.status] || log.status;

      const duration = log.duration_ms ? `${(log.duration_ms / 1000).toFixed(2)}s` : '-';

      return `
        <div class="task-log-item">
          <div class="task-log-main">
            <div>
              <div class="task-item-name">${escapeHtml(log.task_name || '即时诊断')}</div>
              <div class="task-item-meta">状态：${statusText} · 耗时：${duration} · 时间：${log.started_at || '-'}</div>
            </div>
            <div class="task-item-actions">
              <span class="task-status ${statusClass}">${statusText}</span>
              <button class="btn btn-g" onclick="viewTaskLogDetail(${log.id})">查看详情</button>
            </div>
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
      container.innerHTML = '<div class="sb-empty">暂无定时任务<br>创建定时调度以开始使用</div>';
      return;
    }

    container.innerHTML = schedules.map(s => {
      const statusClass = s.status === 'active' ? 'running' : 'stopped';
      const statusText = s.status === 'active' ? '运行中' : '已暂停';
      const scheduleText = s.schedule_type === 'cron' 
        ? `Cron: ${s.cron_expression}` 
        : `间隔: ${s.interval_seconds}s`;

      return `
        <div class="task-schedule-item">
          <div class="task-schedule-main">
            <div>
              <div class="task-item-name">${escapeHtml(s.name)}</div>
              <div class="task-item-meta">类型：${scheduleText} · 已执行：${s.execution_count || 0} 次 · 下次：${s.next_run_at || '-'}</div>
            </div>
            <div class="task-item-actions">
              <span class="task-status ${statusClass}">${statusText}</span>
              <button class="btn btn-g" onclick="toggleSchedule(${s.id}, '${s.status === 'active' ? 'paused' : 'active'}')">
                ${s.status === 'active' ? '暂停' : '恢复'}
              </button>
              <button class="btn btn-g danger-text" onclick="deleteSchedule(${s.id})">删除</button>
            </div>
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
      await safePost(`/tasks/definitions/${defId}/execute`, {});
      toast('任务已提交执行', 'ok');
      loadTaskLogs();
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
      
      if (log.result_json) {
        const result = JSON.parse(log.result_json);
        alert(`执行结果：\n\n${JSON.stringify(result, null, 2)}`);
      } else {
        alert('暂无执行结果');
      }
    } catch (e) {
      toast(`加载详情失败：${e.message}`, 'err');
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
