/**
 * ConnectionPool - 连接池渲染和操作
 * 三栏布局中的中间栏，管理连接卡片、搜索、添加
 * 对接真实后端 API
 */

const ConnectionPool = (function() {
  'use strict';
  let addViewOpen = false;

  function init() {
    render();
    ConnectionStore.subscribe(() => render());

    const addBtn = document.getElementById('poolAddBtn');
    if (addBtn) addBtn.addEventListener('click', showAddView);

    const search = document.getElementById('poolSearch');
    if (search) {
      hardenSearchInput(search);
      search.addEventListener('input', e => filterPool(e.target.value));
    }

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

    // Pod 选择变化 → 更新预览
    const podSel = document.getElementById('poolSelPod');
    if (podSel) podSel.addEventListener('change', () => updatePodPreview());

    // 初始加载集群列表
    loadClusters();
  }

  // ── 集群/Pod 加载 ─────────────────────────────────────────────

  function hardenSearchInput(input) {
    if (!input || input.dataset.noAutofillReady) return;
    input.dataset.noAutofillReady = '1';
    input.setAttribute('autocomplete', 'off');
    input.setAttribute('autocorrect', 'off');
    input.setAttribute('autocapitalize', 'off');
    input.setAttribute('spellcheck', 'false');
    input.setAttribute('data-lpignore', 'true');
    input.setAttribute('data-form-type', 'other');
    input.removeAttribute('name');
    const clearIfUnexpected = () => {
      const v = (input.value || '').trim().toLowerCase();
      if (v === 'admin' || v === 'administrator' || v.includes('@')) {
        input.value = '';
      }
    };
    input.readOnly = true;
    let ready = false;
    const enable = () => { if (!ready) { ready = true; input.readOnly = false; } };
    const guard = setInterval(() => { clearIfUnexpected(); if (ready) clearInterval(guard); }, 200);
    setTimeout(() => { enable(); }, 3000);
    input.addEventListener('focus', enable, { once: true });
    input.addEventListener('mousedown', enable, { once: true });
  }

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
    if (preview) preview.innerHTML = '<div style="color:var(--tx3)">加载中...</div>';
    try {
      const r = await fetch(`${API}/clusters/${encodeURIComponent(cluster)}/pods?namespace=${encodeURIComponent(ns)}`, { credentials: 'include' });
      const d = await r.json();
      if (d.pods) {
        podSelect.innerHTML = '<option value="">选择 Pod...</option>' +
          d.pods.map(p => `<option value="${p.name}" data-containers="${(p.containers||[]).join(',')}">[${p.phase}] ${p.name}</option>`).join('');
        if (preview) preview.innerHTML = `<div style="font-size:12px;color:var(--tx3)">共 ${d.pods.length} 个 Pod，请从左侧选择</div>`;
      }
    } catch (e) {
      podSelect.innerHTML = '<option value="">加载失败</option>';
      if (preview) preview.innerHTML = '<div style="color:var(--a5)">Pod 列表加载失败</div>';
    }
  }

  function updatePodPreview() {
    const podSel = document.getElementById('poolSelPod');
    const preview = document.getElementById('addConnPreview');
    const cluster = document.getElementById('poolSelCluster')?.value;
    const ns = document.getElementById('poolSelNs')?.value;
    if (!podSel || !preview) return;

    const pod = podSel.value;
    if (!pod) {
      preview.innerHTML = '<div style="font-size:12px;color:var(--tx3)">选择 Pod 后显示预览</div>';
      return;
    }

    const opt = podSel.selectedOptions[0];
    const containers = opt?.dataset?.containers?.split(',').filter(Boolean) || [];
    const phase = opt?.textContent?.match(/\[(\w+)\]/)?.[1] || 'Unknown';

    preview.innerHTML = `
      <div style="margin-bottom:10px">
        <div style="font-size:10px;color:var(--tx3);margin-bottom:2px;text-transform:uppercase">连接目标</div>
        <div style="font-size:12px;color:var(--tx);font-weight:500">${cluster}/${ns}/${pod}</div>
      </div>
      <div style="margin-bottom:10px">
        <div style="font-size:10px;color:var(--tx3);margin-bottom:2px;text-transform:uppercase">状态</div>
        <div style="font-size:12px;color:${phase==='Running'?'var(--a3)':'var(--a5)'}">${phase}</div>
      </div>
      ${containers.length ? `
      <div style="margin-bottom:10px">
        <div style="font-size:10px;color:var(--tx3);margin-bottom:2px;text-transform:uppercase">容器</div>
        <div style="font-size:12px;color:var(--tx)">${containers.join(', ')}</div>
      </div>` : ''}
      <div style="padding:8px;background:var(--bg2);border-radius:4px;font-size:11px;color:var(--tx3);margin-top:8px">
        点击"连接"按钮建立 Pod 连接
      </div>
    `;
  }

  // ── 渲染 ──────────────────────────────────────────────────────

  function firstValue(...values) {
    for (const value of values) {
      if (value !== undefined && value !== null && value !== '') return value;
    }
    return '';
  }

  function textValue(value, fallback = '—') {
    return value === undefined || value === null || value === '' ? fallback : String(value);
  }

  function escapeHtml(value) {
    return textValue(value, '').replace(/[&<>"]/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch]));
  }

  function escapeJsArg(value) {
    return textValue(value, '').replace(/\\/g, '\\\\').replace(/'/g, "\\'");
  }

  function normalizeState(state, status) {
    const raw = textValue(firstValue(state, status), '').toLowerCase();
    if (['connecting', 'pending', 'starting', 'arthas_upgrading'].includes(raw)) return 'connecting';
    if (['connected', 'ready', 'running', 'ok', 'healthy', 'arthas', 'pod_connected', 'arthas_ready', 'degraded'].includes(raw)) return 'connected';
    if (['dead', 'failed', 'error', 'err', 'invalid'].includes(raw)) return 'dead';
    return 'disconnected';
  }

  function normalizeHealth(health, state, rawState) {
    const raw = textValue(health, '').toLowerCase();
    if (['ok', 'healthy', 'success'].includes(raw)) return 'ok';
    if (['warn', 'warning', 'slow', 'degraded'].includes(raw)) return 'warn';
    if (['err', 'error', 'dead', 'failed'].includes(raw)) return 'err';
    if (textValue(rawState, '').toLowerCase() === 'degraded') return 'warn';
    return state === 'connected' ? 'ok' : state === 'connecting' ? 'warn' : 'off';
  }

  function normalizeConnection(conn) {
    const c = conn || {};
    const idParts = typeof c.id === 'string' ? c.id.split('/') : [];
    const runtimeObj = c.runtime && typeof c.runtime === 'object' ? c.runtime : {};
    const arthasObj = c.arthas && typeof c.arthas === 'object' ? c.arthas : {};
    const cluster = firstValue(c.cluster, c.cluster_name, c.clusterName, idParts.length >= 3 ? idParts[0] : '');
    const namespace = firstValue(c.namespace, c.ns, c.namespace_name, idParts.length >= 3 ? idParts[1] : '');
    const pod = firstValue(c.pod, c.pod_name, c.podName, idParts.length >= 3 ? idParts.slice(2).join('/') : '');
    const container = firstValue(c.container, c.container_name, c.containerName);
    const runtimeType = firstValue(runtimeObj.type, runtimeObj.runtime_type, c.runtime_type, typeof c.runtime === 'string' ? c.runtime : '');
    const runtimeVersion = firstValue(runtimeObj.version, runtimeObj.runtime_version, c.runtime_version);
    const pid = firstValue(c.pid, c.java_pid, runtimeObj.pid, runtimeObj.java_pid);
    const arthasVersion = firstValue(arthasObj.version, arthasObj.arthas_version, c.arthas_version);
    const arthasPort = firstValue(arthasObj.port, arthasObj.local_port, c.local_port, c.arthas_port);
    const rawState = firstValue(c.state, c.status);
    const state = normalizeState(c.state, c.status);
    let level = firstValue(c.level, c.connection_level);
    if (!level || level === 'connected' || (level === 'disconnected' && state !== 'disconnected')) {
      level = arthasVersion || arthasPort ? 'arthas' : (state === 'connected' || state === 'connecting' ? 'pod' : 'disconnected');
    }
    if (textValue(rawState, '').toLowerCase() === 'arthas_ready') level = 'arthas';
    const health = normalizeHealth(c.health, state, rawState);
    const id = firstValue(c.id, [cluster, namespace, pod].filter(Boolean).join('/'));
    const displayPod = textValue(pod, textValue(id));
    const compactPod = displayPod === '—' ? displayPod : (displayPod.split('-').slice(0, -2).join('-') || displayPod);

    return {
      raw: c,
      id,
      cluster: textValue(cluster),
      namespace: textValue(namespace),
      pod: textValue(pod),
      container: textValue(container, ''),
      shortName: compactPod,
      runtimeType: textValue(runtimeType),
      runtimeVersion: textValue(runtimeVersion, ''),
      runtimeLabel: [runtimeType, runtimeVersion].filter(Boolean).join(' ') || '—',
      pid: textValue(pid),
      state,
      level,
      health,
      arthasVersion: textValue(arthasVersion, ''),
      arthasPort: textValue(arthasPort, ''),
      autoReconnect: !!c.autoReconnect,
      lastHb: firstValue(c.lastHb, c.last_hb, c.last_heartbeat),
      lastUsed: firstValue(c.lastUsed, c.last_used, c.updated_at, 0),
      podConnId: firstValue(c.pod_conn_id, c.podConnId, c.connection_id),
    };
  }

  function render() {
    const el = document.getElementById('poolList');
    if (!el) return;
    const conns = ConnectionStore.getConnections();
    document.getElementById('poolCount').textContent = `(${conns.length})`;

    if (!conns.length) {
      el.innerHTML = `<div class="pool-empty">
        <div class="pool-empty-icon">🔌</div>
        <div class="pool-empty-title">暂无连接</div>
        <div class="pool-empty-desc">点击右侧"+ 新连接"开始</div>
      </div>`;
      return;
    }

    const rows = conns.map(normalizeConnection);
    const active = rows.filter(c => c.state !== 'disconnected' && c.state !== 'dead')
      .sort((a, b) => (b.lastUsed || 0) - (a.lastUsed || 0));
    const inactive = rows.filter(c => c.state === 'disconnected' || c.state === 'dead')
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
    const expanded = window._poolExpandedId === c.id;
    const idArg = escapeJsArg(c.id);
    const safeName = escapeHtml(c.shortName);
    const safePod = escapeHtml(c.pod);
    const arthasLabel = c.arthasVersion || c.arthasPort ? `${c.arthasVersion ? `v${escapeHtml(c.arthasVersion)}` : 'v—'}${c.arthasPort ? ` :${escapeHtml(c.arthasPort)}` : ''}` : '—';

    return `<div class="pool-card${isFocus ? ' pool-card-focus' : ''}" onclick="ConnectionPool.focus('${idArg}')" tabindex="0" role="button" aria-label="${safePod}">
      <div class="pool-card-actions">
        <button class="pool-card-action" title="详情" onclick="event.stopPropagation();ConnectionPool.toggleDetail('${idArg}')" tabindex="-1">⋯</button>
        <button class="pool-card-action pool-card-action-del" title="删除" onclick="event.stopPropagation();ConnectionPool.confirmDelete('${idArg}')" tabindex="-1">✕</button>
      </div>
      <div class="pool-card-header">
        <div class="pool-card-dot ${dotCls}"></div>
        <div class="pool-card-name">${safeName}</div>
        <span class="pool-card-badge ${dotCls}">${getBadgeText(c)}</span>
      </div>
      <div class="pool-card-pod" title="${safePod}">${safePod}</div>
      ${c.state === 'disconnected' || c.state === 'dead' ? `<button class="pool-card-reconnect-btn" onclick="event.stopPropagation();ConnectionPool.reconnect('${idArg}')">⚡ 重连</button>` : ''}
      ${c.state === 'connected' && c.level !== 'arthas' ? `<button class="pool-card-upgrade-btn" onclick="event.stopPropagation();ConnectionPool.upgradeArthas('${idArg}')">🚀 启动 Arthas</button>` : ''}
      <div class="pool-card-meta">
        <span>${escapeHtml(c.cluster)}/${escapeHtml(c.namespace)}</span>
        <span>${escapeHtml(c.runtimeType)}</span>
      </div>
      <div class="pool-card-detail${expanded ? ' show' : ''}">
        <div class="pool-card-detail-inner">
          <div class="pool-card-row"><span class="pool-card-k">Pod</span><span class="pool-card-v">${escapeHtml(c.pod)}</span></div>
          <div class="pool-card-row"><span class="pool-card-k">运行时</span><span class="pool-card-v">${escapeHtml(c.runtimeLabel)}</span></div>
          <div class="pool-card-row"><span class="pool-card-k">PID</span><span class="pool-card-v">${escapeHtml(c.pid)}</span></div>
          ${c.level === 'arthas' ? `<div class="pool-card-row"><span class="pool-card-k">Arthas</span><span class="pool-card-v">${arthasLabel}</span></div>` : ''}
          <div class="pool-card-health pool-card-health-${c.health}">${getHealthText(c)}</div>
          <label class="pool-card-reconnect"><input type="checkbox" ${c.autoReconnect ? 'checked' : ''}
            onclick="event.stopPropagation();ConnectionPool.toggleAutoReconnect('${idArg}', this.checked)"> 自动重连</label>
          <div class="pool-card-buttons">${renderButtons(c)}</div>
        </div>
      </div>
    </div>`;
  }

  function renderButtons(c) {
    let html = '';
    const idArg = escapeJsArg(c.id);
    if (c.state === 'disconnected' || c.state === 'dead') {
      html += `<button class="pool-btn pool-btn-success" onclick="event.stopPropagation();ConnectionPool.reconnect('${idArg}')">⚡ 重连</button>`;
    }
    if (c.state === 'connected' && c.level !== 'arthas') {
      html += `<button class="pool-btn pool-btn-primary" onclick="event.stopPropagation();ConnectionPool.upgradeArthas('${idArg}')">🚀 Arthas</button>`;
    }
    if (c.level === 'arthas') {
      html += `<button class="pool-btn pool-btn-warn" onclick="event.stopPropagation();ConnectionPool.stopArthas('${idArg}')">⏹ Arthas</button>`;
    }
    if (c.state !== 'disconnected' && c.state !== 'dead') {
      html += `<button class="pool-btn pool-btn-danger" onclick="event.stopPropagation();ConnectionPool.disconnect('${idArg}')">🔌 断开</button>`;
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
    if (c.state === 'connecting') return '连接中';
    if (c.state === 'disconnected') return '未连';
    if (c.state === 'dead') return '✕ 失效';
    if (c.health === 'warn') return '⚠ 不稳';
    return c.level === 'arthas' ? 'Arthas' : 'Pod';
  }

  function getHealthText(c) {
    const map = { ok: '✅ 健康', warn: '⚠ 连接不稳定', err: '✕ 失效', off: '未连接' };
    const timeAgo = c.lastHb ? Math.round((Date.now() - c.lastHb) / 1000) + 's前' : '';
    return `${map[c.health] || '未知'}${timeAgo ? ' · ' + timeAgo : ''}`;
  }

  // ── 视图切换 ──────────────────────────────────────────────────

  function showAddView() {
    addViewOpen = true;
    const empty = document.getElementById('wsEmpty');
    const content = document.getElementById('wsContent');
    const addView = document.getElementById('addConnView');
    if (empty) empty.style.display = 'none';
    if (content) content.style.display = 'none';
    if (addView) {
      addView.style.display = 'flex';
      addView.scrollIntoView({ block: 'nearest' });
    }
    if (window.ConnectionWorkspace && typeof ConnectionWorkspace.restoreLegacyPanel === 'function') {
      ConnectionWorkspace.restoreLegacyPanel();
    }
    loadClusters();
  }

  function hideAddView() {
    addViewOpen = false;
    const addView = document.getElementById('addConnView');
    if (addView) addView.style.display = 'none';
    const focusId = ConnectionStore.getFocusId();
    if (focusId) {
      document.getElementById('wsContent').style.display = 'flex';
      if (typeof ConnectionWorkspace !== 'undefined' && typeof ConnectionWorkspace.render === 'function') {
        ConnectionWorkspace.render();
      }
    } else {
      document.getElementById('wsEmpty').style.display = 'flex';
    }
  }

  // ── 操作 ──────────────────────────────────────────────────────

  function focus(id) {
    if (addViewOpen) hideAddView();
    ConnectionStore.setFocus(id);
    if (typeof ConnectionWorkspace !== 'undefined') ConnectionWorkspace.render();
  }

  function isAddViewOpen() {
    return addViewOpen;
  }

  function toggleDetail(id) {
    window._poolExpandedId = window._poolExpandedId === id ? null : id;
    render();
  }

  function toggleGroup(el) {
    el.nextElementSibling?.classList.toggle('pool-group-collapsed');
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
    const existing = ConnectionStore.getConnection(id);
    if (existing) {
      const vm = normalizeConnection(existing);
      if (vm.state === 'disconnected' || vm.state === 'dead') {
        toast('连接已存在，正在尝试重连...', 'info');
        await reconnect(id);
        return;
      }
      focus(id);
      hideAddView();
      toast('连接已存在，已切换到该连接', 'info');
      return;
    }

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

      const realId = d.connection_id || id;
      const pid = d.runtime?.processes?.[0]?.pid || d.runtime?.pid || d.runtime?.java_pid;
      const connectionData = {
        id: realId, cluster, cluster_name: cluster, namespace, pod, pod_name: pod, container, container_name: container,
        state: 'connected', status: 'pod_connected', level: 'pod', health: 'ok', lastHb: Date.now(),
        runtime: d.runtime, pid: pid, pod_conn_id: realId, connection_id: realId,
      };
      if (realId !== id) {
        ConnectionStore.removeConnection(id);
        ConnectionStore.addConnection(connectionData);
      } else {
        ConnectionStore.updateConnection(id, connectionData);
      }
      focus(realId);
      hideAddView();
      toast(`Pod 连接成功 (${d.runtime?.runtime_type || 'unknown'})`, 'success');
    } catch (e) {
      ConnectionStore.updateConnection(id, { state: 'disconnected', level: 'disconnected', health: 'off' });
      toast(`连接失败: ${e.message}`, 'error');
    }
  }

  function confirmDelete(id) {
    const c = ConnectionStore.getConnection(id);
    const vm = normalizeConnection(c);
    const name = vm.shortName || id;
    showConfirm('删除连接', `删除 ${name} ？\n\n采样记录保留在「历史」中`, () => {
      if (vm.state === 'connected' || vm.level === 'arthas') {
        disconnectReal(id).then(() => ConnectionStore.removeConnection(id));
      } else {
        ConnectionStore.removeConnection(id);
      }
      toast('已删除，数据保留', 'success');
    });
  }

  function confirmDeletePersistent(id) {
    const c = ConnectionStore.getConnection(id);
    const vm = normalizeConnection(c);
    const name = vm.shortName || id;
    showConfirm('删除连接', `删除 ${name}？\n\n该操作会从连接池永久移除，刷新后不会恢复。`, async () => {
      try {
        await deletePersistedConnection(id);
        ConnectionStore.removeConnection(id);
        toast('已删除', 'success');
      } catch (e) {
        toast(`删除失败: ${e.message}`, 'error');
      }
    });
  }

  async function deletePersistedConnection(id) {
    const r = await fetch(`${API}/connections/${encodeURIComponent(id)}`, {
      method: 'DELETE',
      credentials: 'include',
    });
    let d = {};
    try { d = await r.json(); } catch (_) {}
    if (!r.ok || (d.code && d.code >= 400) || d.ok === false) {
      throw new Error(d.message || d.error || `HTTP ${r.status}`);
    }
  }

  async function reconnect(id) {
    const c = ConnectionStore.getConnection(id);
    if (!c) return;
    const vm = normalizeConnection(c);
    try {
      if (typeof window.reconnectConnectionById !== 'function') {
        throw new Error('共享重连入口不可用');
      }
      const result = await window.reconnectConnectionById(id, { source: 'connection-pool' });
      focus(result?.connectionId || id);
      hideAddView();
      if (result && result.partial) return result;
      return result;
    } catch (e) {
      ConnectionStore.updateConnection(id, { state: 'disconnected', level: 'disconnected', health: 'off' });
      if (typeof showPodError === 'function') {
        showPodError(e.message, {
          details: `${vm.cluster}/${vm.namespace}/${vm.pod}`,
        });
      }
      toast(`重连失败: ${e.message}`, 'error');
    }
  }

  async function disconnect(id) {
    const c = ConnectionStore.getConnection(id);
    const vm = normalizeConnection(c);
    const name = vm.shortName || id;
    showConfirm('断开连接', `断开 ${name} ？\n\n采样数据不会被删除`, async () => {
      await disconnectReal(id);
      toast('已断开，数据保留', 'info');
    });
  }

  async function disconnectReal(id) {
    const c = ConnectionStore.getConnection(id);
    if (!c) return;
    const vm = normalizeConnection(c);
    try {
      if (vm.podConnId) {
        await fetch(`${API}/pod/disconnect`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ connection_id: vm.podConnId })
        });
      }
      if (vm.level === 'arthas' && vm.podConnId) {
        await fetch(`${API}/arthas/disconnect`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ connection_id: vm.podConnId })
        });
      }
    } catch (e) {
      console.warn('[Pool] disconnect API error:', e);
    }
    ConnectionStore.updateConnection(id, { state: 'disconnected', level: 'disconnected', arthas: null, health: 'off' });
  }

  async function upgradeArthas(id) {
    const c = ConnectionStore.getConnection(id);
    const vm = normalizeConnection(c);
    try {
      if (typeof window.upgradeConnectionById !== 'function') {
        throw new Error('共享 Arthas 升级入口不可用');
      }
      ConnectionStore.updateConnection(id, { state: 'connecting', health: 'warn' });
      toast('正在启动 Arthas 诊断环境...', 'info');
      const result = await window.upgradeConnectionById(id, { source: 'connection-pool' });
      focus(result?.connectionId || id);
      return result;
    } catch (e) {
      console.error('[Pool] upgradeArthas error:', e);
      ConnectionStore.updateConnection(id, { state: 'connected', level: 'pod', health: 'ok' });
      if (typeof showArthasError === 'function') {
        showArthasError(e.message, { details: `${vm.cluster}/${vm.namespace}/${vm.pod}` });
      } else {
        toast(`启动 Arthas 失败: ${e.message}`, 'error');
      }
      return { ok: false, error: e.message };
    }
  }

  function stopArthas(id) {
    ConnectionStore.updateConnection(id, { level: 'pod', arthas: null });
    toast('Arthas 已停止', 'info');
  }

  function toggleAutoReconnect(id, val) {
    ConnectionStore.updateConnection(id, { autoReconnect: val });
    toast(val ? '自动重连开启' : '自动重连关闭', 'info');
  }

  // ── 确认弹窗 ──────────────────────────────────────────────────
  function showConfirm(title, message, onConfirm) {
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.6);display:flex;align-items:center;justify-content:center;z-index:100;backdrop-filter:blur(4px)';
    overlay.innerHTML = `<div style="background:var(--bg1);border:1px solid var(--ln);border-radius:12px;padding:20px;max-width:400px;width:90%;animation:modalIn .2s var(--ease)">
      <div style="font-size:15px;font-weight:600;margin-bottom:12px;font-family:var(--sans)">${title}</div>
      <div style="font-size:12px;color:var(--tx2);white-space:pre-line;margin-bottom:16px;line-height:1.5">${message}</div>
      <div style="display:flex;gap:8px;justify-content:flex-end">
        <button style="padding:6px 16px;border-radius:4px;font-size:12px;border:1px solid var(--ln);background:var(--bg2);color:var(--tx2);cursor:pointer;font-weight:600" onclick="this.closest('.modal-overlay').remove()">取消</button>
        <button style="padding:6px 16px;border-radius:4px;font-size:12px;border:none;background:var(--a5);color:#fff;cursor:pointer;font-weight:600" id="confirmBtn">确认</button>
      </div>
    </div>`;
    document.body.appendChild(overlay);
    overlay.querySelector('#confirmBtn').onclick = () => { overlay.remove(); onConfirm(); };
    overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });
  }

  return {
    init, render, focus, toggleDetail, toggleGroup, filterPool,
    addNewConnection, confirmDelete: confirmDeletePersistent, reconnect, disconnect, upgradeArthas,
    stopArthas, toggleAutoReconnect, loadPods, loadClusters,
    showAddView, hideAddView, cancelAdd: hideAddView, hardenSearchInput, isAddViewOpen,
  };
})();

window.ConnectionPool = ConnectionPool;
