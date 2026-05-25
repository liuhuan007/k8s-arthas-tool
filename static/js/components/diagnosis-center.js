/**
 * diagnosis-center.js — 诊断中心主组件（编排层）
 *
 * 职责：
 * 1. 加载并展示能力卡片列表（委托 diagnosis.js 的 diagCapInit）
 * 2. 搜索 & 分级筛选
 * 3. Tab 切换（诊断能力 / 执行历史 / AI Agent）
 * 4. 协调 parameter-form / execution-progress / execution-history / agent-chat
 * 5. 全局执行数量指示器
 */
(function () {
  'use strict';

  // ── 状态 ──────────────────────────────────────────────────────────────
  let _allCapabilities = [];      // 全量能力列表（含从后端获取的原始数据）
  let _filteredCapabilities = []; // 筛选后的列表
  let _currentLevel = 'all';     // 当前层级筛选
  let _searchText = '';           // 当前搜索关键字
  let _activePollTimer = null;    // 执行数量轮询定时器

  // ── 公开入口 ──────────────────────────────────────────────────────────
  window.dcInit = async function () {
    dcShowLoading('加载诊断能力...');
    try {
      await _loadCapabilities();
      _renderCards();
      _startActiveCountPoll();
    } catch (e) {
      console.error('[dcInit] 初始化失败:', e);
      dcShowError('加载失败: ' + e.message);
    } finally {
      dcHideLoading();
    }
  };

  // ── Tab 切换 ──────────────────────────────────────────────────────────
  window.dcSwitchTab = function (tabName) {
    // 更新 tab 高亮
    document.querySelectorAll('.dc-tab[data-tab]').forEach(el => {
      el.classList.toggle('active', el.dataset.tab === tabName);
    });
    // 切换 panel
    document.querySelectorAll('.dc-panel').forEach(el => {
      el.classList.remove('active');
    });
    const panel = document.getElementById('dc-panel-' + tabName);
    if (panel) panel.classList.add('active');

    // 按需初始化
    if (tabName === 'history') {
      dcLoadHistory();
    }
  };

  // ── 搜索 ──────────────────────────────────────────────────────────────
  window.dcOnSearch = debounce(function (text) {
    _searchText = (text || '').toLowerCase().trim();
    _filterAndRender();
  }, 250);

  // ── 层级筛选 ──────────────────────────────────────────────────────────
  window.dcFilterByLevel = function (level, btnEl) {
    _currentLevel = level;
    // 按钮高亮
    document.querySelectorAll('.dc-filter-btn').forEach(b => b.classList.remove('active'));
    if (btnEl) btnEl.classList.add('active');
    _filterAndRender();
  };

  // ── 返回主站 ──────────────────────────────────────────────────────────
  window.dcBackToMain = function () {
    window.location.href = '/';
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
    const overlay = document.getElementById('diagLoadingOverlay');
    const label = document.getElementById('dcLoadingText');
    if (overlay) { overlay.style.display = 'flex'; }
    if (label) { label.textContent = text || '加载中...'; }
  };

  window.dcHideLoading = function () {
    const overlay = document.getElementById('diagLoadingOverlay');
    if (overlay) { overlay.style.display = 'none'; }
  };

  // ── 私有方法 ──────────────────────────────────────────────────────────

  /**
   * 从后端加载能力目录
   */
  async function _loadCapabilities () {
    const params = {};
    const data = await safeGet('/tasks/capabilities', params);
    _allCapabilities = data.capabilities || [];
    _filteredCapabilities = _allCapabilities.slice();
  }

  /**
   * 根据当前筛选条件过滤并重新渲染
   */
  function _filterAndRender () {
    _filteredCapabilities = _allCapabilities.filter(cap => {
      // 层级筛选
      if (_currentLevel !== 'all') {
        const level = String(cap.level || 1);
        if (level !== String(_currentLevel)) return false;
      }
      // 搜索筛选
      if (_searchText) {
        const haystack = ((cap.name || '') + ' ' + (cap.description || '') + ' ' + (cap.category || '')).toLowerCase();
        if (!haystack.includes(_searchText)) return false;
      }
      return true;
    });
    _renderCards();
  }

  /**
   * 渲染能力卡片到网格容器
   */
  function _renderCards () {
    const container = document.getElementById('dcCapabilityGrid');
    if (!container) return;

    if (_filteredCapabilities.length === 0) {
      container.innerHTML = _renderEmptyState();
      return;
    }

    // 按层级分组
    const grouped = {};
    _filteredCapabilities.forEach(cap => {
      const level = cap.level || 1;
      if (!grouped[level]) grouped[level] = [];
      grouped[level].push(cap);
    });

    const levelTitles = { 1: 'L1 - 快速工具', 2: 'L2 - 诊断工具', 3: 'L3 - 场景方案', 4: 'L4 - AI 诊断' };

    container.innerHTML = Object.keys(grouped).sort((a, b) => a - b).map(level => `
      <div class="capability-level-group">
        <h3 class="level-title">${levelTitles[level] || 'L' + level}</h3>
        <div class="capability-grid">
          ${grouped[level].map(cap => _renderCard(cap)).join('')}
        </div>
      </div>
    `).join('');

    // 更新 tab 上的计数
    const countEl = document.getElementById('dcActiveCountText');
    if (countEl) {
      countEl.textContent = _filteredCapabilities.length + ' 项能力';
      document.getElementById('dcActiveCount').style.display = _filteredCapabilities.length > 0 ? '' : 'none';
    }
  }

  /**
   * 渲染单个能力卡片
   */
  function _renderCard (cap) {
    const hasParams = cap.parameters_schema && cap.parameters_schema !== '{}' && cap.parameters_schema !== '[]';
    const riskBadge = _getRiskBadge(cap.risk_level);
    const categoryLabel = _getCategoryLabel(cap.category);
    const duration = cap.estimated_duration || 10;
    const isDisabled = cap.status === 'disabled';

    return `
      <div class="capability-card ${isDisabled ? 'is-disabled' : ''}" data-cap-id="${cap.id}">
        <div class="capability-header">
          <h4 class="capability-name">${_esc(cap.name)}</h4>
          <div class="capability-badges">
            ${riskBadge}
            <span class="badge badge-category">${categoryLabel}</span>
            ${isDisabled ? '<span class="badge badge-medium">已禁用</span>' : ''}
          </div>
        </div>
        <p class="capability-desc">${_esc(cap.description || '')}</p>
        <div class="capability-meta">
          <span class="meta-item">⏱ 预计 ${duration}s</span>
          ${cap.related_capabilities ? '<span class="meta-item">🔗 关联 ' + JSON.parse(cap.related_capabilities || '[]').length + ' 个</span>' : ''}
        </div>
        <div class="capability-actions">
          ${hasParams
            ? `<button class="btn btn-config" onclick="dcOpenForm(${cap.id})" ${isDisabled ? 'disabled' : ''}>配置参数</button>`
            : `<button class="btn btn-primary" onclick="dcExecute(${cap.id})" ${isDisabled ? 'disabled' : ''}>执行诊断</button>`
          }
        </div>
      </div>
    `;
  }

  function _renderEmptyState () {
    return `
      <div class="sb-empty" style="padding:48px;text-align:center">
        <div style="font-size:48px;margin-bottom:12px">📋</div>
        <div style="font-size:16px;color:var(--tx);margin-bottom:8px">暂无匹配的诊断能力</div>
        <div style="font-size:12px;color:var(--tx3)">${_searchText ? '尝试更换搜索关键字' : '管理员可在后台配置诊断能力'}</div>
      </div>
    `;
  }

  // ── 能力执行 ──────────────────────────────────────────────────────────

  /**
   * 打开参数表单（无参数能力直接执行）
   */
  window.dcOpenForm = function (capId) {
    const cap = _allCapabilities.find(c => c.id === capId) || _filteredCapabilities.find(c => c.id === capId);
    if (!cap) { dcShowError('能力不存在'); return; }

    const hasParams = cap.parameters_schema && cap.parameters_schema !== '{}' && cap.parameters_schema !== '[]';
    if (!hasParams) {
      dcExecute(capId);
      return;
    }

    // 委托 diagnosis.js 的参数表单
    if (typeof window.diagShowParameterForm === 'function') {
      window.diagShowParameterForm(capId);
    } else {
      // 降级：直接执行
      dcExecute(capId);
    }
  };

  /**
   * 执行诊断（无参数）
   */
  window.dcExecute = async function (capId) {
    const cap = _allCapabilities.find(c => c.id === capId);
    if (!cap) { dcShowError('能力不存在'); return; }

    // 高危确认
    if (cap.risk_level === 'high') {
      if (!confirm('此操作为高风险，是否继续？\n\n能力：' + cap.name + '\n描述：' + (cap.description || ''))) return;
    }

    // 检查连接
    const connId = _getCurrentConnectionId();
    if (!connId) {
      dcShowError('请先在连接中心建立 Pod 连接');
      return;
    }

    // 委托 diagnosis.js 的执行能力
    if (typeof window.diagExecuteCap === 'function') {
      await window.diagExecuteCap(capId);
    } else {
      dcShowLoading('正在执行: ' + cap.name + '...');
      try {
        const result = await safePost('/tasks/diagnosis/execute', {
          capability_id: capId,
          connection_id: connId,
          params: {},
        }, 120000);
        dcHideLoading();
        if (result.ok) {
          dcShowSuccess('诊断完成');
        } else {
          dcShowError(result.error || '诊断失败');
        }
      } catch (e) {
        dcHideLoading();
        dcShowError('执行失败: ' + e.message);
      }
    }
  };

  /**
   * 获取当前连接 ID
   */
  function _getCurrentConnectionId () {
    if (window.ConnectionStore && typeof ConnectionStore.getCurrentConnectionId === 'function') {
      return ConnectionStore.getCurrentConnectionId();
    }
    if (window._currentConnId) return window._currentConnId;
    return null;
  }

  // ── 执行历史 ──────────────────────────────────────────────────────────

  window.dcLoadHistory = async function () {
    const container = document.getElementById('dcHistoryContainer');
    if (!container) return;

    // 委托 execution-history 组件
    if (typeof window.diagHistoryInit === 'function') {
      // 渲染到 history 面板
      // 首先把 execution-history 的容器移入 history 面板
      let historyWrap = document.getElementById('dcHistoryContent');
      if (!historyWrap) {
        historyWrap = document.createElement('div');
        historyWrap.id = 'dcHistoryContent';
        container.appendChild(historyWrap);
      }
      await window.diagHistoryInit();
      return;
    }

    // 降级：直接加载
    dcShowLoading('加载历史记录...');
    try {
      const data = await safeGet('/tasks/diagnosis/history', { limit: 30, offset: 0 });
      const history = data.history || [];
      if (history.length === 0) {
        container.innerHTML = '<div class="empty-state">暂无历史记录</div>';
      } else {
        container.innerHTML = _renderHistoryTable(history);
      }
    } catch (e) {
      container.innerHTML = '<div class="empty-state">加载失败: ' + _esc(e.message) + '</div>';
    } finally {
      dcHideLoading();
    }
  };

  function _renderHistoryTable (rows) {
    const rowsHtml = rows.map(run => {
      const statusClass = 'status-' + run.status;
      const time = run.started_at || run.created_at || '未知';
      const duration = run.duration_ms ? (run.duration_ms / 1000).toFixed(2) + 's' : '-';
      const taskName = run.capability_name || '即时诊断';
      const statusText = _getStatusText(run.status);

      return `
        <tr class="history-row" onclick="dcViewHistoryDetail('${run.id}')">
          <td>${_esc(taskName)}</td>
          <td><span class="badge ${statusClass}">${statusText}</span></td>
          <td>${_esc(time)}</td>
          <td>${duration}</td>
          <td>
            <button class="btn btn-small" onclick="event.stopPropagation();dcViewHistoryDetail('${run.id}')">查看</button>
          </td>
        </tr>
      `;
    }).join('');

    return `
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
          <tbody>${rowsHtml}</tbody>
        </table>
      </div>
    `;
  }

  window.dcViewHistoryDetail = async function (runId) {
    if (typeof window.diagViewHistoryDetail === 'function') {
      await window.diagViewHistoryDetail(runId);
      return;
    }
    // 降级
    dcShowLoading('加载详情...');
    try {
      const data = await safeGet('/tasks/runs/' + runId + '/logs');
      dcHideLoading();
      const run = data.run;
      if (!run) { dcShowError('记录不存在'); return; }

      let result = null;
      try { result = run.result_json ? JSON.parse(run.result_json) : null; } catch (_) {}

      const container = document.getElementById('dcResultContainer');
      if (container) {
        container.classList.add('visible');
        container.innerHTML = '<div class="diag-history-detail" style="margin-top:16px">'
          + '<div class="detail-header">'
          + '<button class="btn btn-small" onclick="document.getElementById(\'dcResultContainer\').classList.remove(\'visible\')">关闭</button>'
          + '<h3>' + _esc(run.task_name || run.capability_name || '诊断详情') + '</h3>'
          + '<span class="badge status-' + run.status + '">' + _getStatusText(run.status) + '</span>'
          + '</div>'
          + '<pre style="max-height:400px;overflow:auto;background:var(--bg2);padding:12px;border-radius:6px;font-size:12px;color:var(--tx2)">' + _esc(JSON.stringify(result || run, null, 2)) + '</pre>'
          + '</div>';
      }
    } catch (e) {
      dcHideLoading();
      dcShowError('加载详情失败: ' + e.message);
    }
  };

  // ── 执行中数量轮询 ───────────────────────────────────────────────────

  function _startActiveCountPoll () {
    if (_activePollTimer) clearInterval(_activePollTimer);
    _activePollTimer = setInterval(() => {
      const activeCount = (typeof DiagnosisContext !== 'undefined') ? DiagnosisContext.getActiveCount() : 0;
      const el = document.getElementById('dcActiveCount');
      if (activeCount > 0) {
        el.style.display = '';
        document.getElementById('dcActiveCountText').textContent = activeCount + ' 个执行中';
      } else {
        el.style.display = 'none';
      }
    }, 3000);
  }

  // ── 工具函数 ──────────────────────────────────────────────────────────

  function _getRiskBadge (riskLevel) {
    const config = { low: { cls: 'badge-low', text: '低风险' }, medium: { cls: 'badge-medium', text: '中风险' }, high: { cls: 'badge-high', text: '高风险' } };
    const c = config[riskLevel] || config.low;
    return '<span class="badge ' + c.cls + '">' + c.text + '</span>';
  }

  function _getCategoryLabel (category) {
    const labels = { quick: '快速', tool: '工具', scenario: '场景', ai: 'AI', pod_monitor: 'Pod' };
    return labels[category] || category || '';
  }

  function _getStatusText (status) {
    const texts = { success: '成功', completed: '成功', failed: '失败', running: '执行中', pending: '等待中', partial: '部分成功', cancelled: '已取消' };
    return texts[status] || status || '未知';
  }

  function _esc (text) {
    if (text === null || text === undefined) return '';
    const d = document.createElement('div');
    d.textContent = String(text);
    return d.innerHTML;
  }

  // ── 页面加载初始化 ────────────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', function () {
    // 暴露 debounce 给搜索框使用
    if (typeof window.debounce === 'undefined') {
      window.debounce = function (fn, delay) {
        let timer = null;
        return function () {
          const args = arguments;
          const ctx = this;
          clearTimeout(timer);
          timer = setTimeout(function () { fn.apply(ctx, args); }, delay || 300);
        };
      };
    }
    // 启动诊断中心
    if (typeof dcInit === 'function') dcInit();
  });

})();
