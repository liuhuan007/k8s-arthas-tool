/**
 * 诊断结果展示组件
 * 
 * 功能：
 * 1. 展示单步诊断结果
 * 2. 展示场景方案多步骤结果
 * 3. 支持结果下载
 * 4. 支持结果格式化展示
 */
(function() {
  'use strict';

  /**
   * 渲染诊断结果
   */
  window.diagRenderResult = function(result, capability) {
    const container = document.getElementById('diagResultContainer');
    if (!container) {
      console.warn('diagResultContainer 容器不存在');
      return;
    }

    container.style.display = 'block';

    // 判断是否为场景方案
    if (result.steps && Array.isArray(result.steps)) {
      renderScenarioResult(result, capability, container);
    } else {
      renderSingleResult(result, capability, container);
    }

    // 滚动到结果区域
    container.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  /**
   * 渲染单步结果
   */
  function renderSingleResult(result, capability, container) {
    const status = result.status || 'unknown';
    const duration = result.duration_ms ? `${(result.duration_ms / 1000).toFixed(2)}s` : '未知';
    
    let outputHtml = '';
    
    if (result.result) {
      const state = result.result.state || 'unknown';
      const message = result.result.message || '';
      const body = result.result.body;

      outputHtml = `
        <div class="result-section">
          <h4>执行结果</h4>
          <div class="result-state ${state.toLowerCase()}">状态: ${state}</div>
          ${message ? `<div class="result-message">${escapeHtml(message)}</div>` : ''}
          ${body ? `<pre class="result-output">${formatOutput(body)}</pre>` : ''}
        </div>
      `;
    }

    container.innerHTML = `
      <div class="diag-result">
        <div class="result-header">
          <h3>${escapeHtml(capability?.name || '诊断结果')}</h3>
          <div class="result-meta">
            <span class="meta-item status-${status}">${getStatusText(status)}</span>
            <span class="meta-item">耗时: ${duration}</span>
          </div>
        </div>
        
        ${outputHtml}
        
        <div class="result-actions">
          <button class="btn btn-secondary" onclick="window.diagDownloadResult()">下载结果</button>
          <button class="btn btn-primary" onclick="window.diagCloseResult()">关闭</button>
        </div>
      </div>
    `;
  }

  /**
   * 渲染场景方案结果
   */
  function renderScenarioResult(result, capability, container) {
    const status = result.status || 'unknown';
    const duration = result.duration_ms ? `${(result.duration_ms / 1000).toFixed(2)}s` : '未知';
    const steps = result.steps || [];

    const stepsHtml = steps.map((step, idx) => {
      const stepStatus = step.success ? 'success' : 'failed';
      const icon = step.success ? '✓' : '✗';
      
      let stepOutput = '';
      if (step.result) {
        const message = step.result.message || '';
        const body = step.result.body;
        stepOutput = `
          <div class="step-output">
            ${message ? `<div class="result-message">${escapeHtml(message)}</div>` : ''}
            ${body ? `<pre class="result-output">${formatOutput(body)}</pre>` : ''}
          </div>
        `;
      }

      return `
        <div class="step-item step-${stepStatus}">
          <div class="step-header">
            <span class="step-icon">${icon}</span>
            <span class="step-title">步骤 ${step.step_order}: ${escapeHtml(step.desc || '')}</span>
            <span class="step-command">${escapeHtml(step.command)}</span>
          </div>
          ${stepOutput}
        </div>
      `;
    }).join('');

    container.innerHTML = `
      <div class="diag-result scenario-result">
        <div class="result-header">
          <h3>${escapeHtml(capability?.name || '场景方案结果')}</h3>
          <div class="result-meta">
            <span class="meta-item status-${status}">${getStatusText(status)}</span>
            <span class="meta-item">进度: ${result.completed_steps}/${result.total_steps}</span>
            <span class="meta-item">耗时: ${duration}</span>
          </div>
        </div>
        
        <div class="steps-container">
          ${stepsHtml}
        </div>
        
        <div class="result-actions">
          <button class="btn btn-secondary" onclick="window.diagDownloadResult()">下载结果</button>
          <button class="btn btn-primary" onclick="window.diagCloseResult()">关闭</button>
        </div>
      </div>
    `;
  }

  /**
   * 格式化输出
   */
  function formatOutput(body) {
    if (typeof body === 'string') {
      return escapeHtml(body);
    }
    if (typeof body === 'object') {
      return escapeHtml(JSON.stringify(body, null, 2));
    }
    return escapeHtml(String(body));
  }

  /**
   * 获取状态文本
   */
  function getStatusText(status) {
    const texts = {
      success: '成功',
      failed: '失败',
      partial: '部分成功',
      running: '执行中',
      unknown: '未知'
    };
    return texts[status] || status;
  }

  /**
   * 下载结果
   */
  window.diagDownloadResult = function() {
    const container = document.getElementById('diagResultContainer');
    if (!container) return;

    const text = container.innerText;
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `diagnosis-result-${Date.now()}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  /**
   * 关闭结果
   */
  window.diagCloseResult = function() {
    const container = document.getElementById('diagResultContainer');
    if (container) {
      container.style.display = 'none';
    }
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
