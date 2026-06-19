/**
 * ConnectionPool - 连接池渲染和操作
 * 三栏布局中的中间栏，管理连接卡片、搜索、添加
 * 对接真实后端 API
 */

const ConnectionPool = (function() {
  'use strict';

  function init() {
    render();
    ConnectionStore.subscribe(() => render());

    const search = document.getElementById('poolSearch');
    if (search) search.addEventListener('input', e => filterPool(e.target.value));

    const addBtn = document.getElementById('poolAddBtn');
    if (addBtn) addBtn.addEventListener('click', toggleAddPanel);

    const addConfirm = document.getElementById('poolAddConfirm');
    if (addConfirm) addConfirm.addEventListener('click', addNewConnection);

    // 集群选择变化 → 加载命名空间
    const clusterSel = document.getElementById('poolSelCluster');
    if (clusterSel) clusterSel.addEventListener('change', async () => {
      const cluster = clusterSel.value;
      document.getElementById('poolSelNs').innerHTML = '<option value="">加载中...</option>';
      document.getElementById('poolSelPod').innerHTML = '<option value="">选择 Pod...</option>';
      if (!cluster) { document.getElementById('poolSelNs').innerHTML = '<option value="">选择命名空间...</option>'; return; }
      try {
        const r = await fetch(`${API}/clusters/${encodeURIComponent(cluster)}/namespaces`, { credentials: 'include' });
        const d = await r.json();
        const ns = d.namespaces || d || [];
        document.getElementById('poolSelNs').innerHTML = '<option value="">选择命名空间...</option>' +
          ns.map(n => `<option value="${n}">${n}</option>`).join('');
      } catch (e) {
        document.getElementById('poolSelNs').innerHTML = '<option value="">加载失败</option>';
      }
    });

    // 命名空间选择变化 → 加载 Pod
    const nsSel = document.getElementById('poolSelNs');
    if (nsSel) nsSel.addEventListener('change', () => loadPods());

    // 初始加载集群列表
    loadClusters();
  }

  // ── 集群/Pod 加载 ─────────────────────────────────────────────

  async function loadClusters() {
    const sel = document.getElementById('poolSelCluster');
    if (!sel) return;
    sel.innerHTML = '<option value="">加载中...</option>';
    try {
      const r = await fetch(`${API}/clusters`, { credentials: 'include' });
      if (r.status === 401) { toast('请先登录', 'warn'); return; }
      const d = await r.json();
      const clusters = d.clusters || d || [];
      if (clusters.length) {
        sel.innerHTML = '<option value="">选择集群...</option>' +
          clusters.map(c => `<option value="${c.name}">${c.name}</option>`).join('');
      } else {
        sel.innerHTML = '<option value="">暂无集群</option>';
      }
    } catch (e) {
      console.warn('[Pool] loadClusters failed:', e);
      sel.innerHTML = '<option value="">加载失败</option>';
    }
  }

  async function loadPods() {
    const cluster = document.getElementById('poolSelCluster')?.value;
    const ns = document.getElementById('poolSelNs')?.value;
    const podSelect = document.getElementById('poolSelPod');
    const preview = document.getElementById('addConnPreview');
    if (!podSelect || !cluster || !ns) return;
    podSelect.innerHTML = '<option value="">加载中...</option>';
    try {
      const r = await fetch(`${API}/clusters/${encodeURIComponent(cluster)}/pods?namespace=${encodeURIComponent(ns)}`, { credentials: 'include' });
      const d = await r.json();
      if (d.ok && d.pods) {
        podSelect.innerHTML = '<option value="">选择 Pod...</option>' +
          d.pods.map(p => `<option value="${p.name}" data-containers="${(p.containers||[]).join(',')}">[${p.phase}] ${p.name}</option>`).join('');
        // 更新预览
        if (preview) {
          preview.innerHTML = `<div style="font-size:12px;color:var(--tx)">${d.pods.length} 个 Pod 可用</div>` +
            d.pods.map(p => `<div style="padding:4px 0;border-bottom:1px solid var(--ln);display:flex;justify-content:space-between"><span>${p.name}</span><span style="color:${p.phase==='Running'?'var(--a3)':'var(--a5)'}">${p.phase}</span></div>`).join('');
        }
      }
    } catch (e) {
      podSelect.innerHTML = '<option value="">加载失败</option>';
      if (preview) preview.innerHTML = '<div style="color:var(--a5)">Pod 列表加载失败</div>';
    }
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

  // ── 真实 API 操作 ──────────────────────────────────────────────

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
    // 显示工作区区域（可能被隐藏）
    const wsArea = document.getElementById('workspaceArea');
    if (wsArea) wsArea.style.display = 'flex';
    // 隐藏空状态和内容，显示新建连接面板
    document.getElementById('wsEmpty').style.display = 'none';
    document.getElementById('wsContent').style.display = 'none';
    const addView = document.getElementById('addConnView');
    if (addView) addView.style.display = 'flex';
    // 高亮"+ 新连接"按钮
    const btn = document.getElementById('poolAddBtn');
    if (btn) btn.classList.add('pool-add-btn-active');
    // 加载集群列表
    loadClusters();
  }

  function cancelAdd() {
    document.getElementById('addConnView').style.display = 'none';
    const focusId = ConnectionStore.getFocusId();
    if (focusId) {
      document.getElementById('wsContent').style.display = 'flex';
    } else {
      document.getElementById('wsEmpty').style.display = 'flex';
    }
    const btn = document.getElementById('poolAddBtn');
    if (btn) btn.classList.remove('pool-add-btn-active');
  }

  function filterPool(q) {
    document.querySelectorAll('.pool-card').forEach(el => {
      el.style.display = el.textContent.toLowerCase().includes(q.toLowerCase()) ? '' : 'none';
    });
  }

  async function addNewConnection() {
    const cluster = document.getElementById('poolSelCluster')?.value;
    const namespace = document.getElementById('poolSelNs')?.value;
    const podSel = document.getElementById('poolSelPod');
    const pod = podSel?.value;
    const container = podSel?.selectedOptions?.[0]?.dataset?.containers?.split(',')[0] || '';
    if (!cluster || !namespace || !pod) { toast('请选择完整的连接信息', 'warn'); return; }

    const id = `${cluster}/${namespace}/${pod}`;
    if (ConnectionStore.getConnection(id)) { toast('连接已存在', 'warn'); return; }

    // 先添加到池中（connecting 状态）
    ConnectionStore.addConnection({ id, cluster, namespace, pod, container });

    try {
      const r = await fetch(`${API}/pod/connect`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ cluster_name: cluster, namespace, pod_name: pod, container })
      });
      const d = await r.json();
      if (!d.ok) throw new Error(d.error || '连接失败');

      ConnectionStore.updateConnection(id, {
        state: 'connected', level: 'pod', health: 'ok', lastHb: Date.now(),
        runtime: d.runtime, pid: d.runtime?.pid, pod_conn_id: d.connection_id,
      });
      focus(id);
      toast(`Pod 连接成功 (${d.runtime?.runtime_type || 'unknown'})`, 'success');
    } catch (e) {
      ConnectionStore.updateConnection(id, { state: 'disconnected', level: 'disconnected', health: 'off' });
      toast(`连接失败: ${e.message}`, 'error');
    }

    document.getElementById('addConnView').style.display = 'none';
    const btn = document.getElementById('poolAddBtn');
    if (btn) btn.classList.remove('pool-add-btn-active');
  }

  function confirmDelete(id) {
    const c = ConnectionStore.getConnection(id);
    const name = (c?.pod || '').split('-').slice(0, -2).join('-') || id;
    showConfirm('删除连接', `删除 ${name} ？\n\n采样记录保留在「历史」中`, () => {
      // 先断开再删除
      if (c?.state === 'connected' || c?.level === 'arthas') {
        disconnectReal(id).then(() => ConnectionStore.removeConnection(id));
      } else {
        ConnectionStore.removeConnection(id);
      }
      toast('已删除，数据保留', 'success');
    });
  }

  async function reconnect(id) {
    const c = ConnectionStore.getConnection(id);
    if (!c) return;
    ConnectionStore.updateConnection(id, { state: 'connecting', health: 'warn' });
    try {
      const r = await fetch(`${API}/pod/connect`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ cluster_name: c.cluster, namespace: c.namespace, pod_name: c.pod, container: c.container })
      });
      const d = await r.json();
      if (!d.ok) throw new Error(d.error || '重连失败');
      ConnectionStore.updateConnection(id, {
        state: 'connected', level: 'pod', health: 'ok', lastHb: Date.now(),
        runtime: d.runtime, pid: d.runtime?.pid, pod_conn_id: d.connection_id,
      });
      toast('已重连', 'success');
    } catch (e) {
      ConnectionStore.updateConnection(id, { state: 'disconnected', health: 'off' });
      toast(`重连失败: ${e.message}`, 'error');
    }
  }

  async function disconnect(id) {
    const c = ConnectionStore.getConnection(id);
    const name = (c?.pod || '').split('-').slice(0, -2).join('-') || id;
    showConfirm('断开连接', `断开 ${name} ？\n\n采样数据不会被删除`, async () => {
      await disconnectReal(id);
      toast('已断开，数据保留', 'info');
    });
  }

  async function disconnectReal(id) {
    const c = ConnectionStore.getConnection(id);
    if (!c) return;
    try {
      if (c.pod_conn_id) {
        await fetch(`${API}/pod/disconnect`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ connection_id: c.pod_conn_id })
        });
      }
      if (c.level === 'arthas' && c.pod_conn_id) {
        await fetch(`${API}/arthas/disconnect`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ connection_id: c.pod_conn_id })
        });
      }
    } catch (e) {
      console.warn('[Pool] disconnect API error:', e);
    }
    ConnectionStore.updateConnection(id, { state: 'disconnected', level: 'disconnected', arthas: null, health: 'off' });
  }

  async function upgradeArthas(id) {
    const c = ConnectionStore.getConnection(id);
    if (!c) return;
    ConnectionStore.updateConnection(id, { state: 'connecting' });
    toast('启动 Arthas...', 'info');
    try {
      const r = await fetch(`${API}/pod/upgrade-to-arthas`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ connection_id: c.pod_conn_id || c.id })
      });
      const d = await r.json();
      if (!d.ok) throw new Error(d.error || 'Arthas 启动失败');
      ConnectionStore.updateConnection(id, {
        level: 'arthas', state: 'connected', health: 'ok',
        arthas: { port: d.local_port || 8563, version: d.arthas_version || '3.7.1' }
      });
      toast(`Arthas 就绪 (${d.arthas_version || ''})`, 'success');
    } catch (e) {
      ConnectionStore.updateConnection(id, { state: 'connected', level: 'pod' });
      toast(`Arthas 启动失败: ${e.message}`, 'error');
    }
  }

  function stopArthas(id) {
    ConnectionStore.updateConnection(id, { level: 'pod', arthas: null });
    toast('Arthas 已停止', 'info');
  }

  function restart(id) {
    const c = ConnectionStore.getConnection(id);
    const name = (c?.pod || '').split('-').slice(0, -2).join('-') || id;
    showConfirm('重启 Pod', `重启 ${name} ？`, async () => {
      toast('重启中...', 'warn');
      // 先断开
      await disconnectReal(id);
      // 重新连接
      await reconnect(id);
      ConnectionStore.updateConnection(id, { uptime: '0h' });
      toast('已重启', 'success');
    });
  }

  function toggleAutoReconnect(id, val) {
    ConnectionStore.updateConnection(id, { autoReconnect: val });
    toast(val ? '自动重连开启' : '自动重连关闭', 'info');
  }

  // ── 心跳 ──────────────────────────────────────────────────────

  let _heartbeatTimer = null;

  function startHeartbeat() {
    if (_heartbeatTimer) clearInterval(_heartbeatTimer);
    _heartbeatTimer = setInterval(async () => {
      for (const c of ConnectionStore.getConnections()) {
        if (c.state !== 'connected') continue;
        try {
          const r = await fetch(`${API}/pod/connections`, { credentials: 'include' });
          const d = await r.json();
          const alive = d.ok && d.connections?.some(conn => conn.id === c.pod_conn_id);
          ConnectionStore.updateConnection(c.id, {
            health: alive ? 'ok' : 'warn',
            lastHb: alive ? Date.now() : c.lastHb,
            state: alive ? c.state : (c.health === 'warn' ? 'dead' : 'degraded'),
          });
        } catch (e) {
          ConnectionStore.updateConnection(c.id, { health: 'warn', lastHb: c.lastHb });
        }
      }
    }, 15000);
  }

  function stopHeartbeat() {
    if (_heartbeatTimer) { clearInterval(_heartbeatTimer); _heartbeatTimer = null; }
  }

  // ── 确认弹窗 ──────────────────────────────────────────────────
  function showConfirm(title, message, onConfirm) {
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.5);display:flex;align-items:center;justify-content:center;z-index:1000';
    overlay.innerHTML = `<div style="background:var(--bg1);border:1px solid var(--ln);border-radius:8px;padding:20px;max-width:400px;width:90%">
      <div style="font-size:14px;font-weight:600;margin-bottom:8px;color:var(--tx)">${title}</div>
      <div style="font-size:12px;color:var(--tx2);white-space:pre-line;margin-bottom:16px">${message}</div>
      <div style="display:flex;justify-content:flex-end;gap:8px">
        <button class="pool-btn pool-btn-warn" onclick="this.closest('.modal-overlay').remove()">取消</button>
        <button class="pool-btn pool-btn-primary" id="confirmBtn">确认</button>
      </div>
    </div>`;
    document.body.appendChild(overlay);
    overlay.querySelector('#confirmBtn').onclick = () => { overlay.remove(); onConfirm(); };
    overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });
  }

  return {
    init, render, focus, toggleDetail, toggleGroup, toggleAddPanel, filterPool,
    addNewConnection, confirmDelete, reconnect, disconnect, upgradeArthas,
    stopArthas, restart, toggleAutoReconnect, loadPods, loadClusters,
    startHeartbeat, stopHeartbeat
  };
})();

window.ConnectionPool = ConnectionPool;
