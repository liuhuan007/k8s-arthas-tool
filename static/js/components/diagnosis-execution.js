/**
 * 诊断执行上下文 - 全局执行指示器
 * 
 * 功能：
 * 1. 跟踪正在执行的诊断任务
 * 2. 顶部导航栏显示执行中数量
 * 3. 点击可查看执行详情
 */
(function() {
  'use strict';

  // 执行任务缓存
  const _activeExecutions = new Map();

  /**
   * 注册执行任务
   */
  window.registerDiagnosisExecution = function(executionId, capabilityName, startTime) {
    _activeExecutions.set(executionId, {
      id: executionId,
      name: capabilityName,
      startTime: startTime || Date.now(),
      status: 'running'
    });
    updateExecutionIndicator();
  };

  window.replaceDiagnosisExecutionId = function(localId, runId) {
    if (!localId || !runId || localId === runId) return;
    const execution = _activeExecutions.get(localId);
    if (!execution) return;
    _activeExecutions.delete(localId);
    execution.id = runId;
    execution.runId = runId;
    _activeExecutions.set(runId, execution);
    updateExecutionIndicator();
  };

  /**
   * 完成执行任务
   */
  window.completeDiagnosisExecution = function(executionId, status) {
    const execution = _activeExecutions.get(executionId);
    if (execution) {
      execution.status = status;
      execution.endTime = Date.now();
      
      // 3秒后移除
      setTimeout(() => {
        _activeExecutions.delete(executionId);
        updateExecutionIndicator();
      }, 3000);
    }
    updateExecutionIndicator();
  };

  /**
   * 获取活跃执行数
   */
  window.getDiagnosisActiveCount = function() {
    return getExecutionList().filter(e => e.status === 'running').length;
  };

  /**
   * 更新执行指示器
   */
  function updateExecutionIndicator() {
    const container = document.getElementById('executionIndicator');
    if (!container) return;

    const activeCount = getDiagnosisActiveCount();
    
    if (activeCount === 0) {
      container.style.display = 'none';
      return;
    }

    container.style.display = 'flex';
    container.innerHTML = `
      <span class="spinner"></span>
      <span>${activeCount} 个诊断执行中</span>
      <button class="btn-indicator" onclick="showActiveExecutions()">查看</button>
    `;
  }

  /**
   * 显示活跃执行列表
   */
  window.showActiveExecutions = function() {
    const executions = getExecutionList();
    
    const list = executions.map(e => {
      const duration = e.status === 'running' 
        ? `${((Date.now() - e.startTime) / 1000).toFixed(0)}s`
        : `${((e.endTime - e.startTime) / 1000).toFixed(0)}s`;
      
      return `
        <div class="execution-item">
          <div class="execution-name">${escapeHtml(e.name)}</div>
          <div class="execution-meta">
            <span>run_id: ${escapeHtml(e.runId || e.id)}</span>
            <span class="execution-status ${e.status}">${e.status}</span>
            <span>耗时: ${duration}</span>
            ${e.status === 'running' ? `<button class="btn btn-small danger-text" onclick="window.cancelDiagnosisExecution('${escapeAttr(e.runId || e.id)}')">取消</button>` : ''}
          </div>
        </div>
      `;
    }).join('');

    const modal = document.createElement('div');
    modal.className = 'execution-modal-overlay';
    modal.innerHTML = `
      <div class="execution-modal">
        <div class="modal-header">
          <h3>正在执行的诊断任务</h3>
          <button class="btn-close" onclick="this.closest('.execution-modal-overlay').remove()">✕</button>
        </div>
        <div class="modal-body">
          ${list || '<div class="sb-empty">暂无执行中的任务</div>'}
        </div>
      </div>
    `;
    
    document.body.appendChild(modal);
    modal.addEventListener('click', (e) => {
      if (e.target === modal) modal.remove();
    });
  };

  window.cancelDiagnosisExecution = function(runId) {
    if (window.DiagnosisContext) {
      DiagnosisContext.cancelExecution(runId);
    }
    const modal = document.querySelector('.execution-modal-overlay');
    if (modal) modal.remove();
    updateExecutionIndicator();
  };

  function getExecutionList() {
    if (window.DiagnosisContext && DiagnosisContext.activeExecutions) {
      return Array.from(DiagnosisContext.activeExecutions.values()).map(item => ({
        id: item.executionId,
        runId: item.runId || item.executionId,
        name: item.capabilityName,
        startTime: item.startTime,
        endTime: item.endTime,
        status: item.status,
      }));
    }
    return Array.from(_activeExecutions.values());
  }

  /**
   * HTML 转义
   */
  function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  function escapeAttr(text) {
    return escapeHtml(text).replace(/'/g, '&#39;').replace(/"/g, '&quot;');
  }

})();
