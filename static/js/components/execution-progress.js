/**
 * execution-progress.js — 执行进度组件
 *
 * 功能：
 * 1. 展示单次诊断执行的实时进度（状态轮询）
 * 2. 支持多步骤场景方案的逐步进度
 * 3. 支持取消执行
 * 4. 完成后回调（成功/失败/取消）
 */
(function () {
  'use strict';

  // ── 状态 ──────────────────────────────────────────────────────────────
  let _pollTimer = null;
  let _currentRunId = null;
  let _pollAttempts = 0;
  const _MAX_POLL_ATTEMPTS = 150;
  const _POLL_INTERVAL = 2000;
  let _onComplete = null;

  // ════════════════════════════════════════════════════════════════════════
  // 公开 API
  // ════════════════════════════════════════════════════════════════════════

  /**
   * 启动进度追踪
   * @param {string} runId - 执行 ID
   * @param {string} capabilityName - 能力名称
   * @param {Function} onComplete - 完成回调 (result: {status, data, error})
   */
  window.execProgressStart = function (runId, capabilityName, onComplete) {
    _currentRunId = runId;
    _onComplete = onComplete || null;
    _pollAttempts = 0;

    _renderInitial(capabilityName);
    _showModal();
    _startPolling();
  };

  /**
   * 取消当前执行
   */
  window.execProgressCancel = async function () {
    if (!_currentRunId) return;

    try {
      await safePost('/tasks/diagnosis/runs/' + _currentRunId + '/cancel', {}, 10000);
      _stopPolling();
      _renderCancelled();
      _notifyComplete('cancelled', null);
    } catch (e) {
      if (typeof dcShowError === 'function') {
        dcShowError('取消失败: ' + e.message);
      }
    }
  };

  /**
   * 关闭进度弹窗
   */
  window.execProgressClose = function () {
    _stopPolling();
    _hideModal();
    _currentRunId = null;
  };

  /**
   * 更新步骤状态（供场景方案组件调用）
   * @param {number} stepOrder
   * @param {string} status - pending | running | success | failed
   * @param {string} output
   */
  window.execProgressUpdateStep = function (stepOrder, status, output) {
    _updateStepUI(stepOrder, status, output);
  };

  // ════════════════════════════════════════════════════════════════════════
  // 轮询
  // ════════════════════════════════════════════════════════════════════════

  function _startPolling () {
    _stopPolling();
    _pollTimer = setInterval(_pollOnce, _POLL_INTERVAL);
    _pollOnce(); // 立即查一次
  }

  function _stopPolling () {
    if (_pollTimer) {
      clearInterval(_pollTimer);
      _pollTimer = null;
    }
  }

  async function _pollOnce () {
    if (!_currentRunId) return;
    _pollAttempts++;

    if (_pollAttempts > _MAX_POLL_ATTEMPTS) {
      _stopPolling();
      _renderTimeout();
      _notifyComplete('timeout', null);
      return;
    }

    try {
      const data = await safeGet('/tasks/diagnosis/runs/' + _currentRunId, {}, 8000);
      if (!data || !data.ok) return;

      const run = data.run;
      if (!run) return;

      const status = run.status;

      if (status === 'running' || status === 'pending') {
        _renderRunning(run);
      } else {
        _stopPolling();
        if (status === 'success' || status === 'completed') {
          _renderCompleted(run);
          _notifyComplete('completed', run);
        } else if (status === 'failed') {
          _renderFailed(run);
          _notifyComplete('failed', run);
        } else if (status === 'cancelled') {
          _renderCancelled();
          _notifyComplete('cancelled', run);
        } else if (status === 'partial') {
          _renderPartial(run);
          _notifyComplete('partial', run);
        }
      }
    } catch (e) {
      // 网络错误不中断轮询，继续尝试
      console.warn('[execProgress] 轮询出错:', e.message);
    }
  }

  // ════════════════════════════════════════════════════════════════════════
  // 渲染
  // ════════════════════════════════════════════════════════════════════════

  function _renderInitial (capName) {
    var container = document.getElementById('diagProgressContainer');
    if (!container) return;

    container.innerHTML = '<div class="diag-progress">'
      + '<h3>' + _esc(capName || '诊断执行') + '</h3>'
      + '<div class="exec-progress-body" id="execProgressBody">'
      + '<div style="display:flex;align-items:center;gap:12px;padding:24px 0">'
      + '<div class="spinner" style="width:24px;height:24px;border:3px solid rgba(0,122,255,.2);border-top-color:var(--a);border-radius:50%;animation:spin 1s linear infinite"></div>'
      + '<span style="color:var(--tx2)">正在执行，请稍候...</span>'
      + '</div>'
      + '</div>'
      + '<div style="display:flex;justify-content:flex-end;gap:8px;margin-top:16px;padding-top:12px;border-top:1px solid var(--ln)">'
      + '<button class="btn btn-secondary" onclick="execProgressClose()">关闭</button>'
      + '<button class="btn btn-primary" style="background:var(--a5)" onclick="execProgressCancel()">取消执行</button>'
      + '</div>'
      + '</div>';
  }

  function _renderRunning (run) {
    var body = document.getElementById('execProgressBody');
    if (!body) return;

    var duration = '';
    if (run.started_at) {
      var elapsed = ((Date.now() - new Date(run.started_at).getTime()) / 1000).toFixed(0);
      duration = elapsed + 's';
    } else if (run.duration_ms) {
      duration = (run.duration_ms / 1000).toFixed(1) + 's';
    }

    var stepsHtml = '';
    if (run.steps && Array.isArray(run.steps)) {
      stepsHtml = '<div style="margin-top:16px">'
        + run.steps.map(function (step, idx) {
          var s = step.status || 'pending';
          var icon = s === 'running' ? '⟳' : s === 'success' ? '✓' : s === 'failed' ? '✗' : '○';
          return '<div class="progress-step step-' + s + '" style="margin-bottom:8px;padding:8px 12px">'
            + '<span style="font-size:14px;margin-right:8px">' + icon + '</span>'
            + '<span style="font-size:12px">' + _esc(step.desc || ('步骤 ' + (idx + 1))) + '</span>'
            + (step.output ? '<pre style="margin-top:6px;font-size:10px;color:var(--tx3);max-height:80px;overflow:auto">' + _esc(step.output) + '</pre>' : '')
            + '</div>';
        }).join('')
        + '</div>';
    }

    body.innerHTML = '<div style="display:flex;align-items:center;gap:12px;margin-bottom:12px">'
      + '<div class="spinner" style="width:20px;height:20px;border:3px solid rgba(0,122,255,.2);border-top-color:var(--a);border-radius:50%;animation:spin 1s linear infinite"></div>'
      + '<span style="font-size:13px;color:var(--tx)">执行中...</span>'
      + (duration ? '<span style="font-size:11px;color:var(--tx3);margin-left:auto">已耗时 ' + duration + '</span>' : '')
      + '</div>'
      + (run.error_message ? '<div style="padding:8px 12px;background:rgba(255,59,48,.06);border:1px solid rgba(255,59,48,.2);border-radius:6px;font-size:11px;color:var(--a5);margin-bottom:8px">' + _esc(run.error_message) + '</div>' : '')
      + stepsHtml;
  }

  function _renderCompleted (run) {
    var body = document.getElementById('execProgressBody');
    if (!body) return;

    var duration = run.duration_ms ? (run.duration_ms / 1000).toFixed(2) + 's' : '-';

    body.innerHTML = '<div style="display:flex;align-items:center;gap:12px;padding:16px 0">'
      + '<span style="font-size:24px">✅</span>'
      + '<div>'
      + '<div style="font-size:14px;font-weight:600;color:var(--a3)">执行完成</div>'
      + '<div style="font-size:12px;color:var(--tx3)">耗时: ' + duration + '</div>'
      + '</div>'
      + '</div>';
  }

  function _renderPartial (run) {
    var body = document.getElementById('execProgressBody');
    if (!body) return;

    var duration = run.duration_ms ? (run.duration_ms / 1000).toFixed(2) + 's' : '-';

    body.innerHTML = '<div style="display:flex;align-items:center;gap:12px;padding:16px 0">'
      + '<span style="font-size:24px">⚠️</span>'
      + '<div>'
      + '<div style="font-size:14px;font-weight:600;color:var(--a6)">部分完成</div>'
      + '<div style="font-size:12px;color:var(--tx3)">耗时: ' + duration + '</div>'
      + (run.error_message ? '<div style="font-size:11px;color:var(--a5);margin-top:4px">' + _esc(run.error_message) + '</div>' : '')
      + '</div>'
      + '</div>';
  }

  function _renderFailed (run) {
    var body = document.getElementById('execProgressBody');
    if (!body) return;

    body.innerHTML = '<div style="display:flex;align-items:center;gap:12px;padding:16px 0">'
      + '<span style="font-size:24px">❌</span>'
      + '<div>'
      + '<div style="font-size:14px;font-weight:600;color:var(--a5)">执行失败</div>'
      + '<div style="font-size:12px;color:var(--a5);margin-top:4px">' + _esc(run.error_message || '未知错误') + '</div>'
      + '</div>'
      + '</div>';
  }

  function _renderCancelled () {
    var body = document.getElementById('execProgressBody');
    if (!body) return;

    body.innerHTML = '<div style="display:flex;align-items:center;gap:12px;padding:16px 0">'
      + '<span style="font-size:24px">🚫</span>'
      + '<div>'
      + '<div style="font-size:14px;font-weight:600;color:var(--tx2)">已取消</div>'
      + '<div style="font-size:12px;color:var(--tx3)">执行已被用户取消</div>'
      + '</div>'
      + '</div>';
  }

  function _renderTimeout () {
    var body = document.getElementById('execProgressBody');
    if (!body) return;

    body.innerHTML = '<div style="display:flex;align-items:center;gap:12px;padding:16px 0">'
      + '<span style="font-size:24px">⏱️</span>'
      + '<div>'
      + '<div style="font-size:14px;font-weight:600;color:var(--a6)">轮询超时</div>'
      + '<div style="font-size:12px;color:var(--tx3)">请在执行历史中查看结果</div>'
      + '</div>'
      + '</div>';
  }

  function _updateStepUI (stepOrder, status, output) {
    // 场景方案步骤更新的 UI 入口（可由外部调用）
    var body = document.getElementById('execProgressBody');
    if (!body) return;

    var stepEl = body.querySelector('[data-step-order="' + stepOrder + '"]');
    if (!stepEl) return;

    stepEl.className = 'progress-step step-' + status;
    var iconEl = stepEl.querySelector('.step-icon');
    if (iconEl) {
      var icons = { pending: '○', running: '⟳', success: '✓', failed: '✗' };
      iconEl.textContent = icons[status] || '○';
    }
    if (output) {
      var outputEl = stepEl.querySelector('.step-output');
      if (outputEl) outputEl.textContent = output;
    }
  }

  // ════════════════════════════════════════════════════════════════════════
  // 模态框
  // ════════════════════════════════════════════════════════════════════════

  function _showModal () {
    var modal = document.getElementById('diagProgressModal');
    if (modal) modal.style.display = 'flex';
  }

  function _hideModal () {
    var modal = document.getElementById('diagProgressModal');
    if (modal) modal.style.display = 'none';
  }

  // ════════════════════════════════════════════════════════════════════════
  // 回调
  // ════════════════════════════════════════════════════════════════════════

  function _notifyComplete (status, runData) {
    if (typeof _onComplete === 'function') {
      try {
        _onComplete({ status: status, data: runData });
      } catch (e) {
        console.error('[execProgress] onComplete 回调异常:', e);
      }
    }
  }

  // ════════════════════════════════════════════════════════════════════════
  // 工具
  // ════════════════════════════════════════════════════════════════════════

  function _esc (text) {
    if (text === null || text === undefined) return '';
    var d = document.createElement('div');
    d.textContent = String(text);
    return d.innerHTML;
  }

})();
