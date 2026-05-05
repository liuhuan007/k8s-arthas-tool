/**
 * 场景方案执行进度组件
 * 
 * 功能：
 * 1. 实时展示场景方案执行进度
 * 2. 步骤状态高亮（执行中/成功/失败）
 * 3. 支持取消执行
 */
(function() {
  'use strict';

  let _progressData = null;

  /**
   * 显示执行进度
   */
  window.diagShowProgress = function(capabilityName, steps) {
    _progressData = {
      capabilityName,
      steps: steps.map((step, idx) => ({
        ...step,
        status: 'pending', // pending | running | success | failed
        output: null
      }))
    };

    renderProgress();
    showProgressModal();
  };

  /**
   * 更新步骤状态
   */
  window.diagUpdateStepStatus = function(stepOrder, status, output) {
    if (!_progressData) return;

    const step = _progressData.steps.find(s => s.step_order === stepOrder);
    if (step) {
      step.status = status;
      step.output = output;
      renderProgress();
    }
  };

  /**
   * 渲染进度
   */
  function renderProgress() {
    if (!_progressData) return;

    const container = document.getElementById('diagProgressContainer');
    if (!container) return;

    const stepsHtml = _progressData.steps.map(step => {
      const statusClass = `step-${step.status}`;
      const icon = getStatusIcon(step.status);
      const outputHtml = step.output ? `<pre class="step-output">${escapeHtml(step.output)}</pre>` : '';

      return `
        <div class="progress-step ${statusClass}">
          <div class="step-header">
            <span class="step-icon">${icon}</span>
            <span class="step-title">${escapeHtml(step.desc || `步骤 ${step.step_order}`)}</span>
          </div>
          <div class="step-command">${escapeHtml(step.command)}</div>
          ${outputHtml}
        </div>
      `;
    }).join('');

    container.innerHTML = `
      <div class="diag-progress">
        <h3>${escapeHtml(_progressData.capabilityName)}</h3>
        <div class="progress-steps">
          ${stepsHtml}
        </div>
      </div>
    `;
  }

  /**
   * 获取状态图标
   */
  function getStatusIcon(status) {
    const icons = {
      pending: '○',
      running: '⟳',
      success: '✓',
      failed: '✗'
    };
    return icons[status] || '○';
  }

  /**
   * 显示进度模态框
   */
  function showProgressModal() {
    const modal = document.getElementById('diagProgressModal');
    if (modal) {
      modal.style.display = 'flex';
    }
  }

  /**
   * 关闭进度
   */
  window.diagCloseProgress = function() {
    const modal = document.getElementById('diagProgressModal');
    if (modal) {
      modal.style.display = 'none';
    }
    _progressData = null;
  };

  /**
   * HTML 转义
   */
  function escapeHtml(text) {
    if (text === null || text === undefined) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

})();
