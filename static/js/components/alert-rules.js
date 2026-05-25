/**
 * 告警规则配置组件 — Phase 6
 *
 * 提供:
 * - loadAlertRules(): 从后端加载规则列表并渲染到 panelBody
 * - renderRuleItem(rule): 渲染单条规则为 HTML
 *
 * 依赖: safeGet, safePut, safeDelete (api.js), esc() (utils.js)
 * 规则编辑模态框在 alerts.html 页面中定义
 */

(function () {
  'use strict';

  /**
   * 指标中文名映射
   */
  const METRIC_LABELS = {
    'cpu.usagePercent': 'CPU 使用率',
    'memory.usagePercent': '内存使用率',
    'jvm.gcPauseMs': 'GC 暂停时间',
    'jvm.threadCount': '线程数',
    'jvm.heapUsagePercent': '堆内存使用率',
    'disk.usePercent': '磁盘使用率',
  };

  /**
   * 严重级别颜色映射（用于 rule-severity 标记）
   */
  const SEVERITY_COLORS = {
    info: '#007AFF',
    warning: '#FFD60A',
    critical: '#FF9500',
    emergency: '#FF3B30',
  };

  /**
   * 渲染单条规则
   *
   * @param {Object} rule - 规则对象
   * @returns {string} HTML 字符串
   */
  function renderRuleItem(rule) {
    const id = rule.id || 0;
    const name = rule.name || '未命名';
    const metric = rule.metric || '';
    const operator = rule.operator || '>';
    const threshold = rule.threshold;
    const duration = rule.duration || 0;
    const severity = rule.severity || 'warning';
    const enabled = !!rule.enabled;
    const description = rule.description || '';

    const metricLabel = METRIC_LABELS[metric] || metric;
    const sevColor = SEVERITY_COLORS[severity] || '#FFD60A';

    const durationText = duration > 0 ? ` 持续 ${duration}s` : '';
    const conditionText = `${metricLabel} ${operator} ${threshold}${durationText}`;

    return `
      <div class="rule-item" data-rule-id="${id}">
        <div class="rule-info">
          <div class="rule-name">
            <span style="color:${sevColor};margin-right:6px">●</span>
            ${esc(name)}
          </div>
          <div class="rule-desc">${esc(description)}</div>
          <div class="rule-metric">${esc(conditionText)}</div>
        </div>
        <div class="rule-actions">
          <div class="rule-toggle ${enabled ? 'on' : ''}"
               onclick="toggleRule(${id}, ${enabled})"
               title="${enabled ? '点击禁用' : '点击启用'}"></div>
          <button class="btn-alert" onclick="editRuleById(${id})" title="编辑">✏️</button>
          <button class="btn-alert" onclick="deleteRule(${id})" title="删除" style="color:var(--a5)">✕</button>
        </div>
      </div>
    `;
  }

  /**
   * 从后端加载并渲染规则列表
   */
  async function loadAlertRules() {
    const body = document.getElementById('panelBody');
    if (!body) return;

    try {
      const data = await safeGet('/api/anomaly/rules');
      const rules = data.rules || [];

      if (rules.length === 0) {
        body.innerHTML = `
          <div class="empty-state">
            <div class="empty-icon">📋</div>
            <div class="empty-text">暂无告警规则</div>
            <button class="btn-alert primary" style="margin-top:12px" onclick="openCreateRuleModal()">
              + 新建规则
            </button>
          </div>
        `;
        return;
      }

      // 在列表顶部添加新建按钮
      const header = `
        <div style="padding:10px 14px;border-bottom:1px solid var(--ln);display:flex;justify-content:flex-end;">
          <button class="btn-alert primary" onclick="openCreateRuleModal()">+ 新建规则</button>
        </div>
      `;

      body.innerHTML = header + rules.map(r => renderRuleItem(r)).join('');
    } catch (e) {
      body.innerHTML = `
        <div class="empty-state">
          <div class="empty-text">加载失败: ${esc(e.message)}</div>
        </div>
      `;
    }
  }

  /**
   * 根据 ID 编辑规则（从全局 fetch 规则数据后打开编辑模态框）
   * @param {number} id
   */
  async function editRuleById(id) {
    try {
      const data = await safeGet('/api/anomaly/rules');
      const rule = (data.rules || []).find(r => r.id === id);
      if (rule && typeof window.openEditRuleModal === 'function') {
        window.openEditRuleModal(rule);
      }
    } catch (e) {
      alert('获取规则详情失败: ' + e.message);
    }
  }

  // 暴露到全局
  if (typeof window !== 'undefined') {
    window.loadAlertRules = loadAlertRules;
    window.renderRuleItem = renderRuleItem;
    window.editRuleById = editRuleById;
  }
})();
