/**
 * execution-history.js — 执行历史列表组件
 *
 * 功能：
 * 1. 查询诊断执行历史记录（分页）
 * 2. 支持按能力名称、状态筛选
 * 3. 查看历史执行详情
 * 4. 支持刷新和分页导航
 */
(function () {
  'use strict';

  // ── 状态 ──────────────────────────────────────────────────────────────
  let _historyData = [];
  let _currentPage = 1;
  const _pageSize = 20;
  let _totalCount = 0;
  let _filterStatus = '';
  let _filterKeyword = '';

  // ════════════════════════════════════════════════════════════════════════
  // 公开 API
  // ════════════════════════════════════════════════════════════════════════

  /**
   * 初始化并加载历史记录
   */
  window.diagHistoryInit = async function () {
    _currentPage = 1;
    await _loadHistory();
    _renderHistory();
  };

  /**
   * 刷新历史记录
   */
  window.diagHistoryRefresh = async function () {
    await _loadHistory();
    _renderHistory();
  };

  /**
   * 筛选历史记录
   */
  window.diagHistoryFilter = function (status) {
    _filterStatus = status;
    _currentPage = 1;
    _loadHistory().then(_renderHistory);
  };

  /**
   * 搜索历史记录
   */
  window.diagHistorySearch = debounce(function (keyword) {
    _filterKeyword = (keyword || '').trim();
    _currentPage = 1;
    _loadHistory().then(_renderHistory);
  }, 300);

  /**
   * 上一页
   */
  window.diagHistoryPrevPage = function () {
    if (_currentPage > 1) {
      _currentPage--;
      _loadHistory().then(_renderHistory);
    }
  };

  /**
   * 下一页
   */
  window.diagHistoryNextPage = function () {
    if (_currentPage * _pageSize < _totalCount) {
      _currentPage++;
      _loadHistory().then(_renderHistory);
    }
  };

  /**
   * 跳到指定页
   */
  window.diagHistoryGoPage = function (page) {
    if (page < 1) page = 1;
    var maxPage = Math.ceil(_totalCount / _pageSize) || 1;
    if (page > maxPage) page = maxPage;
    _currentPage = page;
    _loadHistory().then(_renderHistory);
  };

  /**
   * 查看历史详情
   */
  window.diagViewHistoryDetail = async function (runId) {
    try {
      var data = await safeGet('/tasks/runs/' + runId + '/logs');
      var run = data.run;

      if (!run) {
        _showErr('记录不存在');
        return;
      }

      // 尝试解析 result
      var result = null;
      if (run.result) {
        result = run.result;
      } else if (run.result_json) {
        try { result = JSON.parse(run.result_json); } catch (_) { result = null; }
      }

      _renderHistoryDetail(run, result);
    } catch (e) {
      _showErr('加载详情失败: ' + e.message);
    }
  };

  /**
   * 返回历史列表
   */
  window.diagHistoryBackToList = function () {
    _renderHistory();
  };

  // ════════════════════════════════════════════════════════════════════════
  // 加载数据
  // ════════════════════════════════════════════════════════════════════════

  async function _loadHistory () {
    try {
      var params = {
        limit: _pageSize,
        offset: (_currentPage - 1) * _pageSize,
      };
      if (_filterStatus) params.status = _filterStatus;
      if (_filterKeyword) params.keyword = _filterKeyword;

      var data = await safeGet('/tasks/diagnosis/history', params);
      _historyData = data.history || [];
      _totalCount = data.total || _historyData.length;
    } catch (e) {
      console.error('[executionHistory] 加载历史记录失败:', e);
      _historyData = [];
      _totalCount = 0;
    }
  }

  // ════════════════════════════════════════════════════════════════════════
  // 渲染历史列表
  // ════════════════════════════════════════════════════════════════════════

  function _renderHistory () {
    var container = document.getElementById('dcHistoryContainer');
    if (!container) return;

    if (_historyData.length === 0) {
      container.innerHTML = _renderEmptyState();
      return;
    }

    var totalPages = Math.ceil(_totalCount / _pageSize) || 1;

    var filterBar = '<div style="display:flex;align-items:center;gap:8px;margin-bottom:16px;flex-wrap:wrap">'
      + '<input type="text" class="dc-search-input" style="max-width:240px" placeholder="搜索任务名称..." '
      + 'value="' + _esc(_filterKeyword) + '" '
      + 'oninput="diagHistorySearch(this.value)" />'
      + '<button class="dc-filter-btn ' + (!_filterStatus ? 'active' : '') + '" onclick="diagHistoryFilter(\'\')">全部</button>'
      + '<button class="dc-filter-btn ' + (_filterStatus === 'success' ? 'active' : '') + '" onclick="diagHistoryFilter(\'success\')">✅ 成功</button>'
      + '<button class="dc-filter-btn ' + (_filterStatus === 'failed' ? 'active' : '') + '" onclick="diagHistoryFilter(\'failed\')">❌ 失败</button>'
      + '<button class="dc-filter-btn ' + (_filterStatus === 'running' ? 'active' : '') + '" onclick="diagHistoryFilter(\'running\')">🔄 执行中</button>'
      + '<button class="dc-filter-btn" style="margin-left:auto" onclick="diagHistoryRefresh()">🔄 刷新</button>'
      + '</div>';

    var rowsHtml = _historyData.map(function (run) {
      var statusClass = 'status-' + (run.status || 'unknown');
      var time = run.started_at || run.created_at || '未知';
      var duration = run.duration_ms ? (run.duration_ms / 1000).toFixed(2) + 's' : '-';
      var taskName = run.capability_name || run.task_name || '即时诊断';
      var statusText = _getStatusText(run.status);
      var levelBadge = run.capability_level ? _getLevelBadge(run.capability_level) : '';

      return '<tr class="history-row" onclick="diagViewHistoryDetail(\'' + run.id + '\')">'
        + '<td>' + _esc(taskName) + ' ' + levelBadge + '</td>'
        + '<td><span class="badge ' + statusClass + '">' + statusText + '</span></td>'
        + '<td>' + _esc(time) + '</td>'
        + '<td>' + duration + '</td>'
        + '<td>'
        + '<button class="btn btn-small" onclick="event.stopPropagation();diagViewHistoryDetail(\'' + run.id + '\')">查看</button>'
        + '</td>'
        + '</tr>';
    }).join('');

    container.innerHTML = filterBar
      + '<div class="diag-history">'
      + '<table class="history-table">'
      + '<thead><tr>'
      + '<th>诊断任务</th>'
      + '<th>状态</th>'
      + '<th>时间</th>'
      + '<th>耗时</th>'
      + '<th>操作</th>'
      + '</tr></thead>'
      + '<tbody>' + rowsHtml + '</tbody>'
      + '</table>'
      + '<div class="pagination">'
      + '<button class="btn btn-small" onclick="diagHistoryPrevPage()" ' + (_currentPage <= 1 ? 'disabled' : '') + '>上一页</button>'
      + '<span class="page-info">第 ' + _currentPage + ' / ' + totalPages + ' 页 (共 ' + _totalCount + ' 条)</span>'
      + '<button class="btn btn-small" onclick="diagHistoryNextPage()" ' + (_currentPage >= totalPages ? 'disabled' : '') + '>下一页</button>'
      + '</div>'
      + '</div>';
  }

  function _renderEmptyState () {
    return '<div class="empty-state" style="padding:48px;text-align:center">'
      + '<div style="font-size:48px;margin-bottom:12px">📋</div>'
      + '<div style="font-size:16px;color:var(--tx);margin-bottom:8px">暂无历史记录</div>'
      + '<div style="font-size:12px;color:var(--tx3)">' + (_filterKeyword ? '尝试更换搜索关键字' : '执行诊断后将在此显示记录') + '</div>'
      + '</div>';
  }

  // ════════════════════════════════════════════════════════════════════════
  // 渲染历史详情
  // ════════════════════════════════════════════════════════════════════════

  function _renderHistoryDetail (run, result) {
    var container = document.getElementById('dcHistoryContainer');
    if (!container) return;

    var connectionSnapshot = _parseJson(run.connection_snapshot || run.connection_snapshot_json, {});
    var capabilitySnapshot = _parseJson(run.capability_snapshot || run.capability_snapshot_json, {});
    var params = _parseJson(run.params || run.params_json, {});
    var command = run.rendered_command || capabilitySnapshot.arthas_command || '';

    // 如果有 result，先使用 diagReportShow 展示
    if (result && typeof window.diagReportShow === 'function') {
      window.diagReportShow(result, { name: run.task_name || run.capability_name || '历史诊断' });
    }

    container.innerHTML = '<div class="diag-history-detail">'
      + '<div class="detail-header">'
      + '<button class="btn btn-small" onclick="diagHistoryBackToList()">返回历史</button>'
      + '<h3>' + _esc(run.task_name || run.capability_name || '历史诊断') + '</h3>'
      + '<span class="badge status-' + (run.status || 'unknown') + '">' + _getStatusText(run.status) + '</span>'
      + '</div>'
      + '<div class="detail-grid">'
      + '<section><h4>运行信息</h4><pre>' + _esc(JSON.stringify({
        run_id: run.id,
        execution_id: run.execution_id || run.id,
        started_at: run.started_at,
        finished_at: run.finished_at,
        duration_ms: run.duration_ms,
        error_message: run.error_message || ''
      }, null, 2)) + '</pre></section>'
      + '<section><h4>连接快照</h4><pre>' + _esc(JSON.stringify(connectionSnapshot, null, 2)) + '</pre></section>'
      + '<section><h4>能力快照</h4><pre>' + _esc(JSON.stringify({
        id: capabilitySnapshot.id,
        name: capabilitySnapshot.name || run.capability_name,
        category: capabilitySnapshot.category || run.capability_category,
        level: capabilitySnapshot.level || run.capability_level,
        version: capabilitySnapshot.version || run.capability_version
      }, null, 2)) + '</pre></section>'
      + '<section><h4>参数</h4><pre>' + _esc(JSON.stringify(params, null, 2)) + '</pre></section>'
      + '<section><h4>实际命令</h4><pre>' + _esc(command || '无') + '</pre></section>'
      + '<section><h4>结果</h4><pre>' + _esc(JSON.stringify(result || {}, null, 2)) + '</pre></section>'
      + '</div>'
      + '</div>';
  }

  // ════════════════════════════════════════════════════════════════════════
  // 工具函数
  // ════════════════════════════════════════════════════════════════════════

  function _parseJson (value, fallback) {
    if (!value) return fallback;
    if (typeof value === 'object') return value;
    try { return JSON.parse(value); } catch (_) { return fallback; }
  }

  function _getLevelBadge (level) {
    var badges = {
      1: '<span class="badge" style="font-size:10px;background:rgba(0,122,255,.1);color:var(--a)">⚡快捷</span>',
      2: '<span class="badge" style="font-size:10px;background:rgba(167,139,250,.1);color:#a78bfa">🔍模板</span>',
      3: '<span class="badge" style="font-size:10px;background:rgba(251,191,36,.1);color:#fbbf24">📋场景</span>',
      4: '<span class="badge" style="font-size:10px;background:rgba(52,199,89,.1);color:var(--a3)">🤖AI</span>',
    };
    return badges[level] || '';
  }

  function _getStatusText (status) {
    var texts = {
      success: '成功', completed: '成功', failed: '失败', running: '执行中',
      pending: '等待中', partial: '部分成功', cancelled: '已取消'
    };
    return texts[status] || status || '未知';
  }

  function _esc (text) {
    if (text === null || text === undefined) return '';
    var d = document.createElement('div');
    d.textContent = String(text);
    return d.innerHTML;
  }

  function _showErr (msg) {
    if (typeof dcShowError === 'function') { dcShowError(msg); return; }
    if (typeof toast === 'function') { toast(msg, 'error'); return; }
    alert(msg);
  }

  // 简单 debounce
  function debounce (fn, delay) {
    var timer = null;
    return function () {
      var args = arguments;
      var ctx = this;
      clearTimeout(timer);
      timer = setTimeout(function () { fn.apply(ctx, args); }, delay || 300);
    };
  }

})();
