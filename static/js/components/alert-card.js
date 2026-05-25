/**
 * 告警卡片组件 — Phase 6
 *
 * 提供:
 * - renderAlertCard(event): 渲染单条异常事件为 HTML 卡片
 * - severityBadge(severity): 根据严重级别返回 badge HTML
 * - severityLabel(severity): 严重级别中文标签
 *
 * 依赖: esc(), fmtTs() (utils.js)
 */

(function () {
  'use strict';

  /**
   * 严重级别标签映射
   */
  const SEVERITY_LABELS = {
    info: 'Info',
    warning: 'Warning',
    critical: 'Critical',
    emergency: 'Emergency',
  };

  /**
   * 严重级别 Badge 颜色
   */
  const SEVERITY_BADGE = {
    info: 'badge-blue',
    warning: 'badge-yellow',
    critical: 'badge-orange',
    emergency: 'badge-red',
  };

  /**
   * 返回严重级别 badge HTML
   * @param {string} severity
   * @returns {string} HTML 字符串
   */
  function severityBadge(severity) {
    const cls = SEVERITY_BADGE[severity] || 'badge-blue';
    const label = SEVERITY_LABELS[severity] || severity;
    return `<span class="badge ${cls}">${esc(label)}</span>`;
  }

  /**
   * 返回严重级别中文标签
   * @param {string} severity
   * @returns {string}
   */
  function severityLabel(severity) {
    return SEVERITY_LABELS[severity] || severity;
  }

  /**
   * 渲染单条异常事件为 HTML 卡片
   *
   * @param {Object} evt - 异常事件对象
   * @param {number} evt.id - 事件 ID
   * @param {string} evt.cluster - 集群
   * @param {string} evt.namespace - 命名空间
   * @param {string} evt.pod - Pod 名
   * @param {string} evt.rule_name - 触发规则名
   * @param {string} evt.severity - 严重级别
   * @param {string} evt.message - 事件消息
   * @param {string} evt.created_at - 创建时间
   * @returns {string} HTML 字符串
   */
  function renderAlertCard(evt) {
    const severity = evt.severity || 'info';
    const cluster = evt.cluster || '';
    const namespace = evt.namespace || '';
    const pod = evt.pod || '';
    const ruleName = evt.rule_name || '';
    const message = evt.message || '';
    const createdAt = evt.created_at || '';
    const eventId = evt.id || 0;

    // 构建位置标签
    const locationParts = [cluster, namespace, pod].filter(Boolean);
    const location = locationParts.join(' / ');

    return `
      <div class="event-item" data-event-id="${eventId}">
        <div class="event-severity-dot ${esc(severity)}"></div>
        <div class="event-info">
          <div class="event-title">
            ${severityBadge(severity)}
            <span style="margin-left:6px">${esc(ruleName)}</span>
          </div>
          <div class="event-message">${esc(message)}</div>
          <div class="event-meta">
            ${location ? `<span>📍 ${esc(location)}</span>` : ''}
            <span>🕐 ${fmtTs(createdAt)}</span>
          </div>
        </div>
        <div class="event-actions">
          <button title="删除" onclick="deleteEvent(${eventId})">✕</button>
        </div>
      </div>
    `;
  }

  // 暴露到全局
  if (typeof window !== 'undefined') {
    window.renderAlertCard = renderAlertCard;
    window.severityBadge = severityBadge;
    window.severityLabel = severityLabel;
  }
})();
