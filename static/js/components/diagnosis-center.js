/**
 * diagnosis-center.js - 诊断中心主组件（侧边栏导航版）
 *
 * 职责：
 * 1. 加载并展示能力卡片列表（按 level 分配到 3 个内容区）
 * 2. 搜索 & 分类筛选（快捷诊断区）
 * 3. 内容区切换（由侧边栏 navigateToDiagnosis 控制）
 * 4. 协调 parameter-form / execution-progress / agent-chat
 */
(function () {
  'use strict';

  // ── 状态 ──────────────────────────────────────────────────────────────
  var _allCapabilities = [];
  var _activeSection = 'quick';
  var _searchText = '';
  var _activeCategory = '';

  // L1+L2 都归入 quick，L3→scenario，L4→ai
  var LEVEL_SECTION_MAP = { 1: 'quick', 2: 'quick', 3: 'scenario', 4: 'ai' };

  // ── 公开入口 ──────────────────────────────────────────────────────────
  window.dcInit = async function () {
    dcShowLoading('加载诊断能力...');
    try {
      await _loadCapabilities();
      _renderCurrentSectionCards();
    } catch (e) {
      console.error('[dcInit] 初始化失败:', e);
      dcShowError('加载失败: ' + e.message);
    } finally {
      dcHideLoading();
    }
  };

  // ── 内容区切换（由侧边栏调用）──────────────────────────────────────
  window.dcSwitchSection = function (section) {
    _activeSection = section;
    document.querySelectorAll('.dc-panel').forEach(function (el) {
      el.classList.remove('active');
    });
    var panel = document.getElementById('dc-panel-' + section);
    if (panel) panel.classList.add('active');

    if (section === 'history') {
      dcLoadHistory();
    } else {
      _renderCurrentSectionCards();
      if (section === 'ai' && typeof dcAgentInit === 'function') {
        dcAgentInit();
      }
    }
  };

  // ── 分类筛选（快捷诊断区）──────────────────────────────────────────
  window.dcFilterCategory = function (btn, category) {
    _activeCategory = category;
    document.querySelectorAll('#dc-panel-quick .dc-filter-btn').forEach(function (el) {
      el.classList.remove('active');
    });
    if (btn) btn.classList.add('active');
    _renderCurrentSectionCards();
  };

  // ── 搜索 ──────────────────────────────────────────────────────────────
  window.dcOnSearch = debounce(function (text) {
    _searchText = (text || '').toLowerCase().trim();
    _renderCurrentSectionCards();
  }, 250);

  // ── 返回主站 ──────────────────────────────────────────────────────────
  window.dcBackToMain = function () {
    if (typeof switchTab === 'function') {
      switchTab('connections');
    } else {
      window.location.href = '/';
    }
  };

  // ── 错误/加载提示 ────────────────────────────────────────────────────
  window.dcShowError = function (msg) {
    if (typeof toast === 'function') { toast(msg, 'error'); return; }
    if (typeof showErrorNotification === 'function') { showErrorNotification(msg); return; }
    alert(msg);
  };
  window.dcShowSuccess = function (msg) {
    if (typeof toast === 'function') { toast(msg, 'success'); return; }
    if (typeof showSuccessNotification === 'function') { showSuccessNotification(msg); return; }
    alert(msg);
  };
  window.dcShowLoading = function (text) {
    var overlay = document.getElementById('diagLoadingOverlay');
    var label = document.getElementById('dcLoadingText');
    if (overlay) overlay.style.display = 'flex';
    if (label) label.textContent = text || '加载中...';
  };
  window.dcHideLoading = function () {
    var overlay = document.getElementById('diagLoadingOverlay');
    if (overlay) overlay.style.display = 'none';
  };

  // ── 私有：加载能力 ────────────────────────────────────────────────────
  async function _loadCapabilities() {
    var data = await safeGet('/tasks/capabilities', {});
    _allCapabilities = data.capabilities || [];
  }

  // ── 渲染当前内容区的能力卡片 ─────────────────────────────────────────
  function _renderCurrentSectionCards() {
    var grid = document.getElementById('dcCapabilityGrid-' + _activeSection);
    if (!grid) return;

    var filtered = _allCapabilities.filter(function (cap) {
      var capSection = LEVEL_SECTION_MAP[cap.level] || 'quick';

      if (_activeSection === 'quick') {
        if (cap.level !== 1 && cap.level !== 2) return false;
      } else {
        if (capSection !== _activeSection) return false;
      }

      if (cap.status === 'disabled') return false;

      if (_activeSection === 'quick' && _activeCategory) {
        if ((cap.category || '') !== _activeCategory) return false;
      }

      if (_searchText) {
        var haystack = ((cap.name || '') + ' ' + (cap.description || '') + ' ' + (cap.category || '')).toLowerCase();
        if (haystack.indexOf(_searchText) < 0) return false;
      }
      return true;
    });

    if (filtered.length === 0) {
      grid.innerHTML = _renderEmptyState();
      return;
    }
    grid.innerHTML = '<div class="capability-grid">' +
      filtered.map(function (cap) { return _renderCard(cap); }).join('') +
      '</div>';
  }

  function _renderCard(cap) {
    var hasParams = cap.parameters_schema && cap.parameters_schema !== '{}' && cap.parameters_schema !== '[]';
    var riskBadge = _getRiskBadge(cap.risk_level);
    var categoryLabel = _getCategoryLabel(cap.category);
    var duration = cap.estimated_duration || 10;
    var isDisabled = cap.status === 'disabled';

    return '<div class="capability-card' + (isDisabled ? ' is-disabled' : '') + '" data-cap-id="' + cap.id + '">' +
      '<div class="capability-header">' +
        '<h4 class="capability-name">' + _esc(cap.name) + '</h4>' +
        '<div class="capability-badges">' + riskBadge +
          '<span class="badge badge-category">' + categoryLabel + '</span>' +
          (isDisabled ? '<span class="badge badge-medium">已禁用</span>' : '') +
        '</div>' +
      '</div>' +
      '<p class="capability-desc">' + _esc(cap.description || '') + '</p>' +
      '<div class="capability-meta">' +
        '<span class="meta-item">⏱ 预计 ' + duration + 's</span>' +
      '</div>' +
      '<div class="capability-actions">' +
        (hasParams
          ? '<button class="btn btn-config" onclick="dcOpenForm(' + cap.id + ')">配置参数</button>'
          : '<button class="btn btn-primary" onclick="dcExecute(' + cap.id + ')">执行诊断</button>') +
      '</div>' +
    '</div>';
  }

  function _renderEmptyState() {
    var msg = _searchText ? '尝试更换搜索关键字' : '当前分类暂无诊断能力';
    return '<div style="padding:48px;text-align:center">' +
      '<div style="font-size:48px;margin-bottom:12px">📋</div>' +
      '<div style="font-size:16px;color:var(--tx);margin-bottom:8px">暂无匹配的诊断能力</div>' +
      '<div style="font-size:12px;color:var(--tx3)">' + msg + '</div>' +
    '</div>';
  }

  // ── 能力执行 ──────────────────────────────────────────────────────────
  window.dcOpenForm = function (capId) {
    var cap = _allCapabilities.find(function (c) { return c.id === capId; });
    if (!cap) { dcShowError('能力不存在'); return; }
    var hasParams = cap.parameters_schema && cap.parameters_schema !== '{}' && cap.parameters_schema !== '[]';
    if (!hasParams) { dcExecute(capId); return; }
    if (typeof window.diagShowParameterForm === 'function') {
      window.diagShowParameterForm(capId);
    } else {
      dcExecute(capId);
    }
  };

  window.dcExecute = async function (capId) {
    var cap = _allCapabilities.find(function (c) { return c.id === capId; });
    if (!cap) { dcShowError('能力不存在'); return; }
    if (cap.risk_level === 'high') {
      if (!confirm('此操作为高风险，是否继续？\n\n能力：' + cap.name + '\n描述：' + (cap.description || ''))) return;
    }
    var connId = _getCurrentConnectionId();
    if (!connId) { dcShowError('请先在连接中心建立 Pod 连接'); return; }

    if (typeof window.diagExecuteCap === 'function') {
      await window.diagExecuteCap(capId);
    } else {
      dcShowLoading('正在执行: ' + cap.name + '...');
      try {
        var result = await safePost('/tasks/diagnosis/execute', {
          capability_id: capId,
          connection_id: connId,
          params: {}
        }, 120000);
        dcHideLoading();
        if (result.ok) {
          dcShowSuccess('诊断完成');
        }
        else { dcShowError(result.error || '诊断失败'); }
      } catch (e) {
        dcHideLoading();
        dcShowError('执行失败: ' + e.message);
      }
    }
  };

  function _getCurrentConnectionId() {
    if (window.ConnectionStore && typeof ConnectionStore.getCurrentConnectionId === 'function') {
      return ConnectionStore.getCurrentConnectionId();
    }
    if (window._currentConnId) return window._currentConnId;
    return null;
  }

  // ── 执行历史（含运行中筛选）─────────────────────────────────────────
  window.dcLoadHistory = async function (statusFilter) {
    var container = document.getElementById('dcHistoryContainer');
    if (!container) return;

    if (typeof window.diagHistoryInit === 'function') {
      var historyWrap = document.getElementById('dcHistoryContent');
      if (!historyWrap) {
        historyWrap = document.createElement('div');
        historyWrap.id = 'dcHistoryContent';
        container.appendChild(historyWrap);
      }
      await window.diagHistoryInit();
      return;
    }

    dcShowLoading('加载历史记录...');
    try {
      var params = { limit: 30, offset: 0 };
      if (statusFilter) params.status = statusFilter;
      var data = await safeGet('/tasks/diagnosis/history', params);
      var history = data.history || [];

      // 渲染筛选按钮 + 历史表格
      var filterBar = '<div class="dc-filter-bar" style="margin-bottom:16px">'
        + '<button class="dc-filter-btn ' + (!statusFilter ? 'active' : '') + '" onclick="dcLoadHistory()">全部</button>'
        + '<button class="dc-filter-btn ' + (statusFilter === 'running' ? 'active' : '') + '" onclick="dcLoadHistory(\'running\')">🔄 执行中</button>'
        + '<button class="dc-filter-btn ' + (statusFilter === 'success' ? 'active' : '') + '" onclick="dcLoadHistory(\'success\')">✅ 成功</button>'
        + '<button class="dc-filter-btn ' + (statusFilter === 'failed' ? 'active' : '') + '" onclick="dcLoadHistory(\'failed\')">❌ 失败</button>'
        + '</div>';

      if (history.length === 0) {
        container.innerHTML = filterBar + '<div class="empty-state">暂无历史记录</div>';
      } else {
        container.innerHTML = filterBar + _renderHistoryTable(history);
      }
    } catch (e) {
      container.innerHTML = '<div class="empty-state">加载失败: ' + _esc(e.message) + '</div>';
    } finally {
      dcHideLoading();
    }
  };

  function _renderHistoryTable(rows) {
    var rowsHtml = rows.map(function (run) {
      var statusClass = 'status-' + run.status;
      var time = run.started_at || run.created_at || '未知';
      var duration = run.duration_ms ? (run.duration_ms / 1000).toFixed(2) + 's' : '-';
      var taskName = run.capability_name || '即时诊断';
      var statusText = _getStatusText(run.status);
      return '<tr class="history-row" onclick="dcViewHistoryDetail(\'' + run.id + '\')">' +
        '<td>' + _esc(taskName) + '</td>' +
        '<td><span class="badge ' + statusClass + '">' + statusText + '</span></td>' +
        '<td>' + _esc(time) + '</td>' +
        '<td>' + duration + '</td>' +
        '<td><button class="btn btn-small" onclick="event.stopPropagation();dcViewHistoryDetail(\'' + run.id + '\')">查看</button></td>' +
      '</tr>';
    }).join('');

    return '<div class="diag-history"><table class="history-table"><thead><tr>' +
      '<th>诊断任务</th><th>状态</th><th>时间</th><th>耗时</th><th>操作</th>' +
    '</tr></thead><tbody>' + rowsHtml + '</tbody></table></div>';
  }

  window.dcViewHistoryDetail = async function (runId) {
    if (typeof window.diagViewHistoryDetail === 'function') {
      await window.diagViewHistoryDetail(runId);
      return;
    }
    dcShowLoading('加载详情...');
    try {
      var data = await safeGet('/tasks/runs/' + runId + '/logs');
      dcHideLoading();
      var run = data.run;
      if (!run) { dcShowError('记录不存在'); return; }

      var result = null;
      try { result = run.result_json ? JSON.parse(run.result_json) : null; } catch (_) {}

      var container = document.getElementById('dcResultContainer-history');
      if (!container) container = document.getElementById('dcResultContainer-quick');
      if (container) {
        container.classList.add('visible');
        container.innerHTML = '<div class="diag-history-detail" style="margin-top:16px">' +
          '<div class="detail-header">' +
          '<button class="btn btn-small" onclick="this.closest(\'.dc-result-container\').classList.remove(\'visible\')">关闭</button>' +
          '<h3>' + _esc(run.task_name || run.capability_name || '诊断详情') + '</h3>' +
          '<span class="badge status-' + run.status + '">' + _getStatusText(run.status) + '</span>' +
          '</div>' +
          '<pre style="max-height:400px;overflow:auto;background:var(--bg2);padding:12px;border-radius:6px;font-size:12px;color:var(--tx2)">' +
          _esc(JSON.stringify(result || run, null, 2)) +
          '</pre></div>';
      }
    } catch (e) {
      dcHideLoading();
      dcShowError('加载详情失败: ' + e.message);
    }
  };

  // ── 工具函数 ──────────────────────────────────────────────────────────
  function _getRiskBadge(riskLevel) {
    var config = {
      low: { cls: 'badge-low', text: '低风险' },
      medium: { cls: 'badge-medium', text: '中风险' },
      high: { cls: 'badge-high', text: '高风险' }
    };
    var c = config[riskLevel] || config.low;
    return '<span class="badge ' + c.cls + '">' + c.text + '</span>';
  }

  function _getCategoryLabel(category) {
    var labels = { quick: '快速', tool: '工具', scenario: '场景', ai: 'AI', pod_monitor: 'Pod' };
    return labels[category] || category || '';
  }

  function _getStatusText(status) {
    var texts = { success: '成功', completed: '成功', failed: '失败', running: '执行中', pending: '等待中', partial: '部分成功', cancelled: '已取消' };
    return texts[status] || status || '未知';
  }

  function _esc(text) {
    if (text === null || text === undefined) return '';
    var d = document.createElement('div');
    d.textContent = String(text);
    return d.innerHTML;
  }

  // ── 页面加载初始化 ────────────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', function () {
    if (typeof window.debounce === 'undefined') {
      window.debounce = function (fn, delay) {
        var timer = null;
        return function () {
          var args = arguments;
          var ctx = this;
          clearTimeout(timer);
          timer = setTimeout(function () { fn.apply(ctx, args); }, delay || 300);
        };
      };
    }
    if (typeof dcInit === 'function') dcInit();
  });

})();
