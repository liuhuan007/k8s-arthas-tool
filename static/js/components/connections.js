/**
 * 连接管理组件
 * 处理连接列表、连接切换、连接删除
 *
 * 连接层级 (level):
 *   'pod'    — 仅 Pod 连接（kubectl exec 通道）
 *   'arthas' — Pod + Arthas 连接（深度诊断）
 */

// ── State ─────────────────────────────────────────────────────────────────
// ✅ 使用 ConnectionStore 统一管理连接状态

// ── 获取/设置 ────────────────────────────────────────────────────────────

function getConnections() {
  // ✅ 优先从 ConnectionStore 获取
  if (typeof ConnectionStore !== 'undefined') {
    return ConnectionStore.getConnections();
  }
  return window._connections || [];
}

function setConnections(conns) {
  // ✅ 优先使用 ConnectionStore
  if (typeof ConnectionStore !== 'undefined') {
    ConnectionStore.setState({ connections: conns || [] });
  } else {
    window._connections = conns || [];
  }
  saveConnections();
}

function getCurrentConnId() {
  // ✅ 优先从 ConnectionStore 获取
  if (typeof ConnectionStore !== 'undefined') {
    return ConnectionStore.getCurrentConnId();
  }
  return window._currentConnId || null;
}

function setCurrentConnId(id) {
  // ✅ 优先使用 ConnectionStore
  if (typeof ConnectionStore !== 'undefined') {
    ConnectionStore.setCurrentConnection(id);
  } else {
    window._currentConnId = id;
  }
}

function getCurrentConnection() {
  // ✅ 优先从 ConnectionStore 获取
  if (typeof ConnectionStore !== 'undefined') {
    return ConnectionStore.getCurrentConnection();
  }
  return (window._connections || []).find(c => c.id === (window._currentConnId || null)) || null;
}

// ── level 辅助函数 ──────────────────────────────────────────────────────

/**
 * 推断连接层级
 * 优先使用显式 level 字段，否则根据元数据推断
 */
function inferConnLevel(conn) {
  if (!conn) return 'pod';
  if (conn.level) return conn.level;
  // 有 Arthas 元数据 → arthas
  if (conn.local_port || conn.arthas_version || conn.java_pid) return 'arthas';
  // 有 runtime 信息但无 Arthas → pod
  if (conn.runtime_type || conn.runtime) return 'pod';
  // 兼容旧数据：有 status=connected 的一般是旧 Arthas 连接
  if (conn.status === 'connected') return 'arthas';
  return 'pod';
}

/**
 * 获取连接的运行时信息
 */
function getConnRuntime(conn) {
  if (conn.runtime && typeof conn.runtime === 'object') {
    // 后端 RuntimeInfo.__dict__ 字段为 runtime_type/version，前端统一为 type/version
    const rt = conn.runtime;
    return { type: rt.type || rt.runtime_type, version: rt.version || rt.runtime_version || '' };
  }
  // 兼容旧字段
  if (conn.runtime_type) return { type: conn.runtime_type, version: conn.runtime_version || '' };
  return null;
}

/**
 * 获取运行时图标
 */
function getRuntimeIcon(type) {
  const icons = { java: '☕', node: '🟢', python: '🐍', go: '🔵', dotnet: '🟣', unknown: '❓' };
  return icons[type] || '❓';
}

/**
 * 判断连接是否可升级到 Arthas
 * 条件：level=pod 且运行时为 Java
 */
function canUpgradeConnection(conn) {
  if (!conn) return false;
  const level = inferConnLevel(conn);
  if (level === 'arthas') return false;
  const rt = getConnRuntime(conn);
  return rt && rt.type === 'java';
}

// ── 本地存储 ─────────────────────────────────────────────────────────────

function saveConnections() {
  localStorage.setItem('arthas_connections', JSON.stringify(window._connections || []));
  // 保存当前选中的连接 ID
  if (window._currentConnId) {
    localStorage.setItem('arthas_current_conn_id', window._currentConnId);
  } else {
    localStorage.removeItem('arthas_current_conn_id');
  }
}

function loadConnections() {
  try {
    const stored = localStorage.getItem('arthas_connections');
    if (stored) {
      window._connections = JSON.parse(stored);
      // 确保 id 和 level 字段
      window._connections = window._connections.map(c => ({
        ...c,
        id: c.id || `${c.cluster || c.cluster_name}/${c.namespace}/${c.pod || c.pod_name}`,
        level: inferConnLevel(c),
      }));
    } else {
      window._connections = [];
    }
    
    // 加载当前选中的连接 ID
    const currentStored = localStorage.getItem('arthas_current_conn_id');
    if (currentStored) {
      window._currentConnId = currentStored;
    }
  } catch (e) {
    console.error('加载连接失败:', e);
    window._connections = [];
  }
}

// ── 渲染 ─────────────────────────────────────────────────────────────────

/**
 * ✅ renderConnList() 已在 app-ui.js 中重新定义
 * 此处的版本已被覆盖,保留仅为向后兼容
 * 实际渲染使用 app-ui.js 中的版本,从 ConnectionStore 获取数据
 */

// 原 renderConnList 实现已移至 app-ui.js
// 如需查看实现,请搜索 app-ui.js 中的 renderConnList() 函数

// ── 操作 ─────────────────────────────────────────────────────────────────

function addConnection(conn) {
  const exists = (window._connections || []).find(c => c.id === conn.id);
  if (!exists) {
    // 确保 level 字段
    conn.level = inferConnLevel(conn);
    conn.status = conn.status || 'connected';
    window._connections.push(conn);
    saveConnections();
  } else {
    // 更新现有连接的状态信息
    exists.status = conn.status || 'connected';
    // 更新 level
    if (conn.level) exists.level = conn.level;
    // 更新运行时信息
    if (conn.runtime) exists.runtime = conn.runtime;
    if (conn.runtime_type) exists.runtime_type = conn.runtime_type;
    // 更新 Arthas 信息
    if (conn.local_port) exists.local_port = conn.local_port;
    if (conn.java_pid) exists.java_pid = conn.java_pid;
    if (conn.arthas_version) exists.arthas_version = conn.arthas_version;
    if (conn.arthas_address) exists.arthas_address = conn.arthas_address;
    saveConnections();
  }
}

function removeConnection(connId) {
  window._connections = (window._connections || []).filter(c => c.id !== connId);
  if (window._currentConnId === connId) {
    window._currentConnId = null;
  }
  saveConnections();
}

/**
 * 从连接列表中触发升级到 Arthas
 */
async function upgradeConnectionFromList(connId) {
  const conn = (window._connections || []).find(c => c.id === connId);
  if (!conn) {
    toast('连接不存在', 'warn');
    return false;
  }

  try {
    if (typeof window.upgradeConnectionById === 'function') {
      await window.upgradeConnectionById(connId, { source: 'legacy-connection-list' });
      return true;
    }

    await switchConnection(connId);
    if (typeof upgradeToArthas === 'function') {
      return upgradeToArthas();
    }
    throw new Error('Arthas 升级入口不可用');
  } catch (e) {
    console.error('[connections] upgradeConnectionFromList error:', e);
    if (typeof window.upgradeConnectionById !== 'function') {
      toast(`启动 Arthas 失败: ${e.message}`, 'error');
    }
    return false;
  }
}

async function deleteConnection(connId) {
  const confirmed = await confirmModal({
    title: '删除连接',
    message: '确定删除此连接？此操作不可撤销。',
    confirmText: '删除',
    cancelText: '取消',
    type: 'danger',
  });
  if (!confirmed) return;

  // 如果删除的是当前连接，先断开
  if (window._currentConnId === connId) {
    await stopPoll();
    window._currentConnId = null;
  }

  try {
    const apiBase = window.API || '/api';
    const resp = await fetch(`${apiBase}/connections/${encodeURIComponent(connId)}`, {
      method: 'DELETE',
      credentials: 'include',
    });
    let data = {};
    try { data = await resp.json(); } catch (_) {}
    if (!resp.ok || (data.code && data.code >= 400) || data.ok === false) {
      throw new Error(data.message || data.error || `HTTP ${resp.status}`);
    }
  } catch (e) {
    toast(`删除失败: ${e.message}`, 'error');
    return;
  }

  removeConnection(connId);
  renderConnList();
}

// 导出
if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    getConnections,
    setConnections,
    getCurrentConnId,
    setCurrentConnId,
    getCurrentConnection,
    inferConnLevel,
    getConnRuntime,
    canUpgradeConnection,
    saveConnections,
    loadConnections,
    // ✅ renderConnList 已移至 app-ui.js
    addConnection,
    removeConnection,
    deleteConnection,
    upgradeConnectionFromList,
    confirmModal,
    hasActiveDiagnosis,
  };
}

// ── 批量操作 ─────────────────────────────────────────────────────────────

/**
 * 在连接记录表格上方添加批量操作栏
 */
function renderConnectionBatchActions() {
  const container = document.getElementById('connList');
  if (!container) return;
  if (container.querySelector('.conn-batch-bar')) return;

  const batchBar = document.createElement('div');
  batchBar.className = 'conn-batch-bar';
  batchBar.innerHTML = `
    <div class="conn-batch-left">
      <label class="conn-batch-select-all">
        <input type="checkbox" id="connSelectAll" onchange="toggleAllConnections(this.checked)">
        全选
      </label>
      <span id="connSelectedCount" style="font-size:12px;color:var(--tx2)">已选 0 个</span>
    </div>
    <div class="conn-batch-actions">
      <button class="btn btn-g btn-sm" onclick="batchDistributeFromConnections()">📦 批量分发工具</button>
    </div>
  `;
  container.insertBefore(batchBar, container.firstChild);
}

window.toggleAllConnections = function(checked) {
  const checkboxes = document.querySelectorAll('.conn-checkbox');
  checkboxes.forEach(cb => { cb.checked = checked; });
  updateSelectedCount();
};

window.updateSelectedCount = function() {
  const checked = document.querySelectorAll('.conn-checkbox:checked').length;
  const el = document.getElementById('connSelectedCount');
  if (el) el.textContent = `已选 ${checked} 个`;
};

window.batchDistributeFromConnections = function() {
  const checked = document.querySelectorAll('.conn-checkbox:checked');
  if (checked.length === 0) { toast('请先选择连接', 'warn'); return; }
  navigateTo('toolchain-center');
  setTimeout(() => { if (typeof toolboxOpenBatchDistribute === 'function') toolboxOpenBatchDistribute(); }, 300);
};

// 全局暴露（供 HTML onclick 调用）
window.upgradeConnectionFromList = upgradeConnectionFromList;
window.inferConnLevel = inferConnLevel;
window.getConnRuntime = getConnRuntime;
window.canUpgradeConnection = canUpgradeConnection;
window.confirmModal = confirmModal;
window.hasActiveDiagnosis = hasActiveDiagnosis;
window.renderConnectionBatchActions = renderConnectionBatchActions;

// ═══════════════════════════════════════════════════════════════════════════════
// Phase 5: 自定义确认对话框 (不用原生 alert/confirm)
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * 自定义确认对话框
 * @param {object} options
 * @param {string} options.title - 对话框标题
 * @param {string} options.message - 确认消息内容
 * @param {string} [options.confirmText='确认'] - 确认按钮文字
 * @param {string} [options.cancelText='取消'] - 取消按钮文字
 * @param {string} [options.type='default'] - 类型: default/danger/warning/info
 * @param {string} [options.detail] - 可选的详细说明文本
 * @returns {Promise<boolean>} 用户是否确认
 */
function confirmModal({ title = '确认', message = '', confirmText = '确认', cancelText = '取消', type = 'default', detail = '' } = {}) {
  return new Promise((resolve) => {
    // 如果已有 modal，先移除
    const existing = document.getElementById('conn-confirm-modal');
    if (existing) existing.remove();

    const typeColors = {
      default: '#4a90d9',
      danger: '#e74c3c',
      warning: '#f39c12',
      info: '#3498db',
    };
    const btnColor = typeColors[type] || typeColors.default;
    const iconMap = {
      default: '❓',
      danger: '⚠️',
      warning: '⚡',
      info: 'ℹ️',
    };
    const icon = iconMap[type] || iconMap.default;

    const modal = document.createElement('div');
    modal.id = 'conn-confirm-modal';
    modal.style.cssText = `
      position: fixed; top: 0; left: 0; width: 100%; height: 100%;
      background: rgba(0,0,0,0.5); z-index: 10001;
      display: flex; align-items: center; justify-content: center;
      animation: fadeIn 0.15s ease;
    `;
    modal.innerHTML = `
      <div style="
        background: #2a2a3e; border-radius: 12px; padding: 28px 32px;
        max-width: 420px; width: 90%; box-shadow: 0 20px 60px rgba(0,0,0,0.5);
        border: 1px solid rgba(255,255,255,0.1);
        animation: slideUp 0.2s ease;
      ">
        <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 16px;">
          <span style="font-size: 24px;">${icon}</span>
          <h3 style="margin: 0; color: #e8e8f0; font-size: 18px; font-weight: 600;">${escHtml(title)}</h3>
        </div>
        <p style="margin: 0 0 8px; color: #c0c0d0; font-size: 14px; line-height: 1.6;">${escHtml(message)}</p>
        ${detail ? `<p style="margin: 0 0 20px; color: #888; font-size: 12px; line-height: 1.5;">${escHtml(detail)}</p>` : '<div style="margin-bottom: 20px;"></div>'}
        <div style="display: flex; justify-content: flex-end; gap: 10px;">
          <button id="confirm-cancel-btn" style="
            padding: 8px 20px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.15);
            background: transparent; color: #c0c0d0; cursor: pointer; font-size: 14px;
            transition: background 0.2s;
          " onmouseover="this.style.background='rgba(255,255,255,0.05)'"
             onmouseout="this.style.background='transparent'">${escHtml(cancelText)}</button>
          <button id="confirm-ok-btn" style="
            padding: 8px 20px; border-radius: 6px; border: none;
            background: ${btnColor}; color: #fff; cursor: pointer; font-size: 14px; font-weight: 500;
            transition: opacity 0.2s;
          " onmouseover="this.style.opacity='0.85'"
             onmouseout="this.style.opacity='1'">${escHtml(confirmText)}</button>
        </div>
      </div>
    `;

    // 简单 HTML 转义
    function escHtml(s) {
      return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    const close = (result) => {
      modal.style.opacity = '0';
      modal.style.transition = 'opacity 0.15s';
      setTimeout(() => modal.remove(), 150);
      resolve(result);
    };

    modal.querySelector('#confirm-cancel-btn').onclick = () => close(false);
    modal.querySelector('#confirm-ok-btn').onclick = () => close(true);
    modal.onclick = (e) => { if (e.target === modal) close(false); };

    // ESC 键关闭
    const onKeydown = (e) => {
      if (e.key === 'Escape') {
        document.removeEventListener('keydown', onKeydown);
        close(false);
      }
    };
    document.addEventListener('keydown', onKeydown);

    document.body.appendChild(modal);
    modal.querySelector('#confirm-ok-btn').focus();
  });
}

// ═══════════════════════════════════════════════════════════════════════════════
// Phase 5: 连接切换确认 (在切换前检查是否有活跃诊断任务)
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * 检查是否有活跃的诊断任务
 * @returns {boolean}
 */
function hasActiveDiagnosis() {
  // 检查连接状态栏或诊断状态
  if (typeof ConnectionStore !== 'undefined') {
    const state = ConnectionStore.getConnectionState();
    // 如果处于 Arthas 就绪状态，可能有活跃任务
    if (state === 'arthas_ready') {
      // 检查是否有执行中的诊断
      const connState = window._connState;
      if (connState === 'running' || connState === 'executing') {
        return true;
      }
    }
  }
  // 检查全局状态
  if (window._activeDiagnosis || window._diagnosisRunning) {
    return true;
  }
  return false;
}

/**
 * Phase 5: 包装原始 switchConnection，添加切换确认对话框
 * 在 DOMContentLoaded 后（app-ui.js 已加载）绑定到 window
 */
document.addEventListener('DOMContentLoaded', () => {
  // 延迟绑定，确保 app-ui.js 中的 switchConnection 已注册
  setTimeout(() => {
    const _originalSwitchConnection = window.switchConnection;
    if (typeof _originalSwitchConnection !== 'function') return;

    window.switchConnection = async function(connId) {
      // 如果切换到当前连接，直接执行
      const currentId = (typeof ConnectionStore !== 'undefined')
        ? ConnectionStore.getCurrentConnId()
        : window._currentConnId;
      if (connId === currentId) {
        return _originalSwitchConnection(connId);
      }

      // 检查是否有活跃的诊断任务
      const isActive = hasActiveDiagnosis();
      const targetConn = (window._connections || []).find(c => c.id === connId);
      const targetLabel = targetConn
        ? `${targetConn.cluster_name || ''} / ${targetConn.namespace || ''} / ${targetConn.pod_name || ''}`
        : connId;

      let detail = '';
      if (isActive) {
        detail = '当前有活跃的诊断任务正在进行中，切换连接可能导致任务中断。';
      }

      const confirmed = await confirmModal({
        title: '切换连接',
        message: `确定要切换到连接 "${targetLabel}" 吗？`,
        confirmText: '切换',
        cancelText: '取消',
        type: isActive ? 'warning' : 'default',
        detail,
      });

      if (confirmed) {
        return _originalSwitchConnection(connId);
      }
    };

    // 确保全局引用也更新
    window.switchConnection = window.switchConnection;
  }, 100);
});
