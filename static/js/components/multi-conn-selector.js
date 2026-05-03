/**
 * 多连接选择器组件
 *
 * 功能:
 * - 当用户需要操作但当前没有选中连接时,弹出模态框展示所有活跃连接
 * - 用户可以选择一个连接作为当前操作上下文
 * - 支持连接卡片展示(集群/命名空间/Pod/运行时/状态)
 * - 只有 1 个活跃连接时自动选中,不弹出
 */

// ═══════════════════════════════════════════════════════════
// 多连接选择器
// ═══════════════════════════════════════════════════════════

const MultiConnSelector = (function() {
  'use strict';

  let _modal = null;
  let _connections = [];
  let _onSelect = null;

  /**
   * 初始化模态框 DOM
   */
  function init() {
    if (_modal) return;

    _modal = document.createElement('div');
    _modal.id = 'multiConnSelectorModal';
    _modal.className = 'mcs-modal';
    _modal.innerHTML = `
      <div class="mcs-backdrop" onclick="MultiConnSelector.close()"></div>
      <div class="mcs-dialog">
        <div class="mcs-header">
          <h3>🔌 选择连接</h3>
          <p>请选择一个活跃连接作为当前操作上下文</p>
          <button class="mcs-close" onclick="MultiConnSelector.close()">✕</button>
        </div>
        <div class="mcs-body" id="mcsConnList">
          <!-- 连接卡片将在这里渲染 -->
        </div>
        <div class="mcs-footer">
          <button class="mcs-btn mcs-btn-cancel" onclick="MultiConnSelector.close()">取消</button>
        </div>
      </div>
    `;

    document.body.appendChild(_modal);
  }

  /**
   * 显示选择器
   * @param {Array} connections - 连接列表
   * @param {Function} onSelect - 选择回调 function(connId)
   */
  function show(connections, onSelect) {
    init();
    _connections = connections || [];
    _onSelect = onSelect;

    if (_connections.length === 0) {
      toast('没有活跃的连接', 'warn');
      return;
    }

    // 只有 1 个活跃连接时,自动选中
    if (_connections.length === 1) {
      const conn = _connections[0];
      toast(`自动选中连接: ${conn.cluster_name || conn.cluster}/${conn.namespace}/${conn.pod_name || conn.pod}`, 'i');
      if (onSelect) onSelect(conn.id);
      return;
    }

    renderConnections();
    _modal.classList.add('show');
  }

  /**
   * 渲染连接卡片列表
   */
  function renderConnections() {
    const list = document.getElementById('mcsConnList');
    if (!list) return;

    if (_connections.length === 0) {
      list.innerHTML = '<div class="mcs-empty">暂无活跃连接</div>';
      return;
    }

    list.innerHTML = _connections.map(conn => {
      const level = inferLevel(conn);
      const levelIcon = level === 'arthas' ? '⚡' : '🔵';
      const levelLabel = level === 'arthas' ? 'Arthas' : 'Pod';
      const runtime = getRuntimeInfo(conn);
      const isActive = conn.id === window._currentConnId;

      return `
        <div class="mcs-card ${isActive ? 'active' : ''}" onclick="MultiConnSelector.select('${esc(conn.id)}')">
          <div class="mcs-card-header">
            <span class="mcs-level-badge ${level}">${levelIcon} ${levelLabel}</span>
            ${isActive ? '<span class="mcs-active-badge">✓ 当前</span>' : ''}
          </div>
          <div class="mcs-card-body">
            <div class="mcs-row">
              <span class="mcs-label">集群</span>
              <span class="mcs-value">${esc(conn.cluster_name || conn.cluster || '—')}</span>
            </div>
            <div class="mcs-row">
              <span class="mcs-label">命名空间</span>
              <span class="mcs-value">${esc(conn.namespace || '—')}</span>
            </div>
            <div class="mcs-row">
              <span class="mcs-label">Pod</span>
              <span class="mcs-value">${esc(conn.pod_name || conn.pod || '—')}</span>
            </div>
            ${runtime ? `
            <div class="mcs-row">
              <span class="mcs-label">运行时</span>
              <span class="mcs-value">${runtime}</span>
            </div>
            ` : ''}
            ${conn.java_pid ? `
            <div class="mcs-row">
              <span class="mcs-label">Java PID</span>
              <span class="mcs-value">${conn.java_pid}</span>
            </div>
            ` : ''}
            ${conn.arthas_version ? `
            <div class="mcs-row">
              <span class="mcs-label">Arthas</span>
              <span class="mcs-value">v${esc(conn.arthas_version)}</span>
            </div>
            ` : ''}
          </div>
        </div>
      `;
    }).join('');
  }

  /**
   * 选择连接
   */
  function select(connId) {
    if (_onSelect) {
      _onSelect(connId);
    }
    close();
  }

  /**
   * 关闭选择器
   */
  function close() {
    if (_modal) {
      _modal.classList.remove('show');
    }
    _connections = [];
    _onSelect = null;
  }

  /**
   * 推断连接层级
   */
  function inferLevel(conn) {
    if (conn.level) return conn.level;
    if (conn.local_port || conn.arthas_version || conn.java_pid) return 'arthas';
    if (conn.runtime_type || conn.runtime) return 'pod';
    return 'pod';
  }

  /**
   * 获取运行时信息
   */
  function getRuntimeInfo(conn) {
    if (conn.runtime && typeof conn.runtime === 'object') {
      const rt = conn.runtime;
      const type = rt.type || rt.runtime_type;
      const ver = rt.version || rt.runtime_version;
      return ver ? `${type} ${ver}` : type;
    }
    if (conn.runtime_type) {
      return conn.runtime_version ? `${conn.runtime_type} ${conn.runtime_version}` : conn.runtime_type;
    }
    return null;
  }

  /**
   * HTML 转义
   */
  function esc(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  // 暴露公共 API
  return {
    init,
    show,
    select,
    close
  };
})();

// 暴露到全局
window.MultiConnSelector = MultiConnSelector;
