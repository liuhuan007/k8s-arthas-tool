/**
 * 诊断历史记录组件
 * 
 * 功能：
 * 1. 查询 task_logs 表中的诊断记录
 * 2. 支持按能力/时间筛选
 * 3. 查看历史诊断结果
 */
(function() {
  'use strict';

  let _historyData = [];
  let _currentPage = 1;
  const _pageSize = 20;

  /**
   * 初始化历史记录
   */
  window.diagHistoryInit = async function() {
    await loadHistory();
    renderHistory();
  };

  /**
   * 加载历史记录
   */
  async function loadHistory(filters = {}) {
    try {
      // TODO: 实现后端 API /api/tasks/diagnosis/history
      // 暂时使用 task_logs 列表
      const data = await safeGet('/tasks/runs', {
        limit: _pageSize,
        offset: (_currentPage - 1) * _pageSize,
        ...filters
      });

      _historyData = data.runs || [];
    } catch (e) {
      console.error('加载历史记录失败:', e);
    }
  }

  /**
   * 渲染历史记录
   */
  function renderHistory() {
    const container = document.getElementById('diagHistoryContainer');
    if (!container) return;

    if (_historyData.length === 0) {
      container.innerHTML = '<div class="empty-state">暂无历史记录</div>';
      return;
    }

    const rowsHtml = _historyData.map(run => {
      const statusClass = `status-${run.status}`;
      const time = run.started_at || run.created_at || '未知';
      const duration = run.duration_ms ? `${(run.duration_ms / 1000).toFixed(2)}s` : '-';

      return `
        <tr class="history-row" onclick="window.diagViewHistoryDetail('${run.id}')">
          <td>${escapeHtml(run.task_name || '即时诊断')}</td>
          <td><span class="badge ${statusClass}">${getStatusText(run.status)}</span></td>
          <td>${time}</td>
          <td>${duration}</td>
          <td>
            <button class="btn btn-small" onclick="event.stopPropagation(); window.diagViewHistoryDetail('${run.id}')">查看</button>
          </td>
        </tr>
      `;
    }).join('');

    container.innerHTML = `
      <div class="diag-history">
        <table class="history-table">
          <thead>
            <tr>
              <th>诊断任务</th>
              <th>状态</th>
              <th>时间</th>
              <th>耗时</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            ${rowsHtml}
          </tbody>
        </table>
        
        <div class="pagination">
          <button class="btn btn-small" onclick="window.diagHistoryPrevPage()" ${_currentPage === 1 ? 'disabled' : ''}>上一页</button>
          <span class="page-info">第 ${_currentPage} 页</span>
          <button class="btn btn-small" onclick="window.diagHistoryNextPage()">下一页</button>
        </div>
      </div>
    `;
  }

  /**
   * 查看历史详情
   */
  window.diagViewHistoryDetail = async function(runId) {
    try {
      const data = await safeGet(`/tasks/runs/${runId}/logs`);
      const run = data.run;

      if (!run) {
        showError('记录不存在');
        return;
      }

      // 展示结果
      if (run.result_json) {
        try {
          const result = JSON.parse(run.result_json);
          if (window.diagRenderResult) {
            window.diagRenderResult(result, { name: run.task_name || '历史诊断' });
          }
        } catch (e) {
          console.error('解析结果失败:', e);
        }
      }
    } catch (e) {
      showError('加载详情失败: ' + e.message);
    }
  };

  /**
   * 上一页
   */
  window.diagHistoryPrevPage = function() {
    if (_currentPage > 1) {
      _currentPage--;
      loadHistory().then(renderHistory);
    }
  };

  /**
   * 下一页
   */
  window.diagHistoryNextPage = function() {
    _currentPage++;
    loadHistory().then(renderHistory);
  };

  /**
   * 获取状态文本
   */
  function getStatusText(status) {
    const texts = {
      success: '成功',
      failed: '失败',
      running: '执行中',
      partial: '部分成功'
    };
    return texts[status] || status;
  }

  /**
   * HTML 转义
   */
  function escapeHtml(text) {
    if (text === null || text === undefined) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  /**
   * 显示错误
   */
  function showError(msg) {
    if (window.showErrorNotification) {
      window.showErrorNotification(msg);
    } else {
      alert(msg);
    }
  }

})();
