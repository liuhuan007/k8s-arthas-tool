/**
 * 性能分析组件
 * 处理 async-profiler、JFR、线程/堆 Dump 等任务
 */

// ── State ─────────────────────────────────────────────────────────────────
// _pfTaskId, _pfPollTimer, _pfStart, _pfDur, _pfLL, _pfTasksByConn 在 app-ui.js 中声明

// 设置采样任务
function pfSetTask(connId, task) {
  if (!window._pfTasksByConn) window._pfTasksByConn = {};
  window._pfTasksByConn[connId] = task;
}

// 获取采样任务
function pfGetTask(connId) {
  return _pfTasksByConn[connId] || null;
}

// 获取当前任务的采样状态
function getPfState() {
  return {
    taskId: _pfTaskId,
    pollTimer: _pfPollTimer,
    start: _pfStart,
    duration: _pfDur,
    lastLines: _pfLL,
    pollingForConn: null
  };
}

// 设置采样模式
function pfSetMode(mode) {
  // 更新 UI 模式选择
  const el = document.querySelector(`.pf-mode-${mode}`);
  if (el) {
    document.querySelectorAll('.pf-mode-btn').forEach(b => b.classList.remove('active'));
    el.classList.add('active');
  }
}

// 设置采样持续时间
function pfSetDur(s) {
  _pfDur = s;
  document.getElementById('pfDurSlider').value = s;
  document.getElementById('pfDurVal').textContent = s + 's';
}

// 开始采样任务
async function startProfilerTask(connId, mode, duration) {
  const conn = getCurrentConnection();
  if (!conn) {
    toast('请先选择连接', 'error');
    return;
  }
  
  try {
    const resp = await safePost('/api/profile/start', {
      connection_id: connId,
      type: mode,
      duration: duration
    });
    
    _pfTaskId = resp.task_id;
    _pfStart = Date.now();
    _pfDur = duration;
    _pfLL = 0;
    
    pfSetTask(connId, {
      taskId: resp.task_id,
      startTime: _pfStart,
      duration,
      status: 'running',
      logLines: []
    });
    
    // 启动轮询
    pollProfilerStatus(connId);
    toast(`采样任务已启动 (${mode})`, 'success');
  } catch (e) {
    toast('启动采样失败: ' + e.message, 'error');
  }
}

// 轮询采样状态
async function pollProfilerStatus(connId) {
  if (!_pfTaskId) return;
  
  try {
    const resp = await safePost('/api/profile/status', {
      task_id: _pfTaskId
    });
    
    const task = pfGetTask(connId);
    if (task) {
      task.status = resp.status;
      task.logLines = resp.logs || [];
      task.progress = resp.progress;
    }
    
    // 更新 UI
    renderProfilerStatus(resp);
    
    if (resp.status === 'completed' || resp.status === 'failed') {
      _pfPollTimer = null;
      _pfTaskId = null;
    } else {
      _pfPollTimer = setTimeout(() => pollProfilerStatus(connId), 2000);
    }
  } catch (e) {
    console.error('轮询采样状态失败:', e);
  }
}

// 渲染采样状态
function renderProfilerStatus(resp) {
  const el = document.getElementById('pfStatus');
  if (!el) return;
  
  el.innerHTML = `
    <div class="pf-status">
      <span class="pf-status-label">状态:</span>
      <span class="pf-status-value pf-status-${resp.status}">${resp.status}</span>
      <span class="pf-progress">${resp.progress || 0}%</span>
    </div>`;
}

// 停止采样
async function stopProfilerTask() {
  if (!_pfTaskId) return;
  
  try {
    await safePost('/api/profile/stop', { task_id: _pfTaskId });
    _pfTaskId = null;
    if (_pfPollTimer) {
      clearTimeout(_pfPollTimer);
      _pfPollTimer = null;
    }
    toast('采样任务已停止', 'info');
  } catch (e) {
    toast('停止采样失败: ' + e.message, 'error');
  }
}

// 导出
if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    pfSetTask,
    pfGetTask,
    getPfState,
    pfSetMode,
    pfSetDur,
    startProfilerTask,
    pollProfilerStatus,
    stopProfilerTask,
    renderProfilerStatus
  };
}