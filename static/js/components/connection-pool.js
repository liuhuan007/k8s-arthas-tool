/**
 * ConnectionPool - 连接池渲染和操作
 * 三栏布局中的中间栏，管理连接卡片、搜索、添加
 */

const ConnectionPool = (function() {
  'use strict';

  function init() {
    render();
    ConnectionStore.subscribe(() => render());

    // 搜索
    const search = document.getElementById('poolSearch');
    if (search) search.addEventListener('input', e => filterPool(e.target.value));

    // 添加按钮
    const addBtn = document.getElementById('poolAddBtn');
    if (addBtn) addBtn.addEventListener('click', toggleAddPanel);

    // 添加确认
    const addConfirm = document.getElementById('poolAddConfirm');
    if (addConfirm) addConfirm.addEventListener('click', addNewConnection);

    // namespace 选择
    const nsSelect = document.getElementById('poolSelNs');
    if (nsSelect) nsSelect.addEventListener('change', () => loadPods());

    // 初始加载 Pod 列表
    loadPods();
  }

  // ── 渲染 ──────────────────────────────────────────────────────

  function render() {
    const el = document.getElementById('poolList');
    if (!el) return;
    const conns = ConnectionStore.getConnections();
    document.getElementById('poolCount').textContent = `(${conns.length})`;

    if (!conns.length) {
      el.innerHTML = `<div class="pool-empty">
        <div class="pool-empty-icon">🔌</div>
        <div class="pool-empty-title">暂无连接</div>
        <div class="pool-empty-desc">点击上方"+ 新连接"开始</div>
      </div>`;
      return;
    }

    const active = conns.filter(c => c.state !== 'disconnected' && c.state !== 'dead')
      .sort((a, b) => (b.lastUsed || 0) - (a.lastUsed || 0));
    const inactive = conns.filter(c => c.state === 'disconnected' || c.state === 'dead')
      .sort((a, b) => (b.lastUsed || 0) - (a.lastUsed || 0));

    let html = '';
    if (active.length) {
      html += `<div class="pool-group-title" onclick="ConnectionPool.toggleGroup(this)">活跃连接 <span class="pool-group-count">${active.length}</span></div>`;
      html += `<div class="pool-group-items">${active.map(renderCard).join('')}</div>`;
    }
    if (inactive.length) {
      html += `<div class="pool-group-title" onclick="ConnectionPool.toggleGroup(this)">已断开 <span class="pool-group-count">${inactive.length}</span></div>`;
      html += `<div class="pool-group-items pool-group-collapsed">${inactive.map(renderCard).join('')}</div>`;
    }
    el.innerHTML = html;
  }

  function renderCard(c) {
    const isFocus = c.id === ConnectionStore.getFocusId();
    const dotCls = getDotClass(c);
    const shortName = (c.pod || '').split('-').slice(0, -2).join('-') || c.pod;
    const expanded = window._poolExpandedId === c.id;

    return `<div class="pool-card${isFocus ? ' pool-card-focus' : ''}"
                 onclick="ConnectionPool.focus('${c.id}')" tabindex="0"
                 role="button" aria-label="${shortName}">
      <div class="pool-card-actions">
        <button class="pool-card-action" title="展开详情"
                onclick="event.stopPropagation();ConnectionPool.toggleDetail('${c.id}')" tabindex="-1">⋯</button>
        <button class="pool-card-action pool-card-action-del" title="删除"
                onclick="event.stopPropagation();ConnectionPool.confirmDelete('${c.id}')" tabindex="-1">✕</button>
      </div>
      <div class="pool-card-header">
        <div class="pool-card-dot ${dotCls}"></div>
        <div class="pool-card-name">${shortName}</div>
        <span class="pool-card-badge ${dotCls}">${getBadgeText(c)}</span>
      </div>
      <div class="pool-card-meta">
        <span>${c.cluster || '?'}/${c.namespace || '?'}</span>
        <span>${c.runtime?.type || '?'}</span>
      </div>
      <div class="pool-card-detail${expanded ? ' show' : ''}">
        <div class="pool-card-detail-inner">
          <div class="pool-card-row"><span class="pool-card-k">Pod</span><span class="pool-card-v">${c.pod || '?'}</span></div>
          <div class="pool-card-row"><span class="pool-card-k">运行时</span><span class="pool-card-v">${c.runtime?.type || '?'} ${c.runtime?.version || ''}</span></div>
          <div class="pool-card-row"><span class="pool-card-k">PID</span><span class="pool-card-v">${c.pid || '?'}</span></div>
          ${c.level === 'arthas' ? `<div class="pool-card-row"><span class="pool-card-k">Arthas</span><span class="pool-card-v">v${c.arthas?.version || '?'} :${c.arthas?.port || '?'}</span></div>` : ''}
          <div class="pool-card-health pool-card-health-${c.health}">${getHealthText(c)}</div>
          <label class="pool-card-reconnect"><input type="checkbox" ${c.autoReconnect ? 'checked' : ''}
            onclick="event.stopPropagation();ConnectionPool.toggleAutoReconnect('${c.id}', this.checked)"> 自动重连</label>
          <div class="pool-card-buttons">${renderButtons(c)}</div>
        </div>
      </div>
    </div>`;
  }

  function renderButtons(c) {
    let html = '';
    if (c.state === 'disconnected' || c.state === 'dead') {
      html += `<button class="pool-btn pool-btn-success" onclick="event.stopPropagation();ConnectionPool.reconnect('${c.id}')">⚡ 重连</button>`;
    }
    if (c.state === 'connected' && c.level !== 'arthas') {
      html += `<button class="pool-btn pool-btn-primary" onclick="event.stopPropagation();ConnectionPool.upgradeArthas('${c.id}')">🚀 Arthas</button>`;
    }
    if (c.level === 'arthas') {
      html += `<button class="pool-btn pool-btn-danger" onclick="event.stopPropagation();ConnectionPool.stopArthas('${c.id}')">⏹ Arthas</button>`;
    }
    if (c.state !== 'disconnected' && c.state !== 'dead') {
      html += `<button class="pool-btn pool-btn-danger" onclick="event.stopPropagation();ConnectionPool.disconnect('${c.id}')">🔌 断开</button>`;
    }
    if (c.state !== 'dead') {
      html += `<button class="pool-btn pool-btn-warn" onclick="event.stopPropagation();ConnectionPool.restart('${c.id}')">🔄 重启</button>`;
    }
    return html;
  }

  // ── 辅助函数 ──────────────────────────────────────────────────

  function getDotClass(c) {
    if (c.state === 'connecting') return 'connecting';
    if (c.state === 'dead') return 'dead';
    if (c.state === 'disconnected') return 'off';
    if (c.health === 'warn') return 'degraded';
    if (c.health === 'err') return 'dead';
    return c.level === 'arthas' ? 'arthas' : 'pod';
  }

  function getBadgeText(c) {
    const map = { arthas: 'Arthas', pod: 'Pod', degraded: '⚠ 弱', dead: '✕ 失效', off: '未连', connecting: '...' };
    if (c.state === 'connecting') return '连接中';
    if (c.state === 'disconnected') return '未连';
    if (c.state === 'dead') return '✕ 失效';
    if (c.health === 'warn') return '⚠ 弱';
    return map[c.level] || c.state;
  }

  function getHealthText(c) {
    const map = { ok: '✅ 健康', warn: '⚠ 响应缓慢', err: '✕ 失效' };
    const timeAgo = c.lastHb ? Math.round((Date.now() - c.lastHb) / 1000) + 's前' : '';
    return `${map[c.health] || '未知'}${timeAgo ? ' · ' + timeAgo : ''}`;
  }

  // ── 操作 ──────────────────────────────────────────────────────

  function focus(id) {
    ConnectionStore.setFocus(id);
    if (typeof ConnectionWorkspace !== 'undefined') ConnectionWorkspace.render();
  }

  function toggleDetail(id) {
    window._poolExpandedId = window._poolExpandedId === id ? null : id;
    render();
  }

  function toggleGroup(el) {
    el.nextElementSibling?.classList.toggle('pool-group-collapsed');
  }

  function toggleAddPanel() {
    document.getElementById('poolAddPanel')?.classList.toggle('show');
  }

  function filterPool(q) {
    document.querySelectorAll('.pool-card').forEach(el => {
      el.style.display = el.textContent.toLowerCase().includes(q.toLowerCase()) ? '' : 'none';
    });
  }

  function loadPods() {
    const ns = document.getElementById('poolSelNs')?.value;
    const podSelect = document.getElementById('poolSelPod');
    if (!podSelect || !ns) return;
    // TODO: 从后端 API 加载 Pod 列表
    // fetch(`/api/clusters/${cluster}/pods?namespace=${ns}`)
    podSelect.innerHTML = '<option value="">选择 Pod...</option>';
  }

  function addNewConnection() {
    const cluster = document.getElementById('poolSelCluster')?.value;
    const namespace = document.getElementById('poolSelNs')?.value;
    const pod = document.getElementById('poolSelPod')?.value;
    if (!cluster || !namespace || !pod) { toast('请选择完整的连接信息', 'warn'); return; }

    const id = `${cluster}/${namespace}/${pod}`;
    if (ConnectionStore.getConnection(id)) { toast('连接已存在', 'warn'); return; }

    ConnectionStore.addConnection({
      id, cluster, namespace, pod,
      runtime: { type: 'java', version: '17.0.2' },
      pid: Math.floor(Math.random() * 90000 + 10000),
      uptime: '0h',
      state: 'connecting',
    });

    toast('连接中...', 'info');
    // TODO: 调用后端 API 建立连接
    setTimeout(() => {
      ConnectionStore.updateConnection(id, {
        state: 'connected', level: 'pod', health: 'ok', lastHb: Date.now()
      });
      focus(id);
      toast('已连接', 'success');
    }, 800);

    document.getElementById('poolAddPanel')?.classList.remove('show');
  }

  function confirmDelete(id) {
    const c = ConnectionStore.getConnection(id);
    const name = (c?.pod || '').split('-').slice(0, -2).join('-') || id;
    showConfirm('删除连接', `删除 ${name} ？\n\n采样记录保留在「历史」中`, () => {
      ConnectionStore.removeConnection(id);
      toast('已删除，数据保留', 'success');
    });
  }

  function reconnect(id) {
    ConnectionStore.updateConnection(id, { state: 'connecting', health: 'warn' });
    toast('重连中...', 'info');
    setTimeout(() => {
      ConnectionStore.updateConnection(id, { state: 'connected', level: 'pod', health: 'ok', lastHb: Date.now(), arthas: null });
      toast('已重连', 'success');
    }, 1200);
  }

  function disconnect(id) {
    const c = ConnectionStore.getConnection(id);
    const name = (c?.pod || '').split('-').slice(0, -2).join('-') || id;
    showConfirm('断开连接', `断开 ${name} ？\n\n采样数据不会被删除`, () => {
      ConnectionStore.updateConnection(id, { state: 'disconnected', level: 'disconnected', arthas: null, health: 'off' });
      toast('已断开，数据保留', 'info');
    });
  }

  function upgradeArthas(id) {
    ConnectionStore.updateConnection(id, { state: 'connecting' });
    toast('启动 Arthas...', 'info');
    setTimeout(() => {
      ConnectionStore.updateConnection(id, {
        level: 'arthas', state: 'connected', health: 'ok',
        arthas: { port: 8563, version: '3.7.1' }
      });
      toast('Arthas 就绪', 'success');
    }, 1000);
  }

  function stopArthas(id) {
    ConnectionStore.updateConnection(id, { level: 'pod', arthas: null });
    toast('Arthas 已停止', 'info');
  }

  function restart(id) {
    const c = ConnectionStore.getConnection(id);
    const name = (c?.pod || '').split('-').slice(0, -2).join('-') || id;
    showConfirm('重启 Pod', `重启 ${name} ？`, () => {
      toast('重启中...', 'warn');
      ConnectionStore.updateConnection(id, { state: 'connecting', health: 'warn', arthas: null, level: 'pod' });
      setTimeout(() => {
        ConnectionStore.updateConnection(id, { state: 'connected', health: 'ok', lastHb: Date.now(), uptime: '0h' });
        toast('已重启', 'success');
      }, 2000);
    });
  }

  function toggleAutoReconnect(id, val) {
    ConnectionStore.updateConnection(id, { autoReconnect: val });
    toast(val ? '自动重连开启' : '自动重连关闭', 'info');
  }

  return {
    init, render, focus, toggleDetail, toggleGroup, toggleAddPanel, filterPool,
    addNewConnection, confirmDelete, reconnect, disconnect, upgradeArthas,
    stopArthas, restart, toggleAutoReconnect
  };
})();

window.ConnectionPool = ConnectionPool;
