/**
 * ConnectionWorkspace - per-connection 工作区
 * 根据焦点连接的层级动态生成 Tab 栏和内容
 */

const ConnectionWorkspace = (function() {
  'use strict';

  let mountedLegacyPanel = null;
  const legacyPanelAnchors = {};
  let monitorSnapshotTimer = null;
  let monitorSnapshotKey = '';
  let monitorSnapshotAt = 0;

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
    if (['connected', 'ready', 'running', 'ok', 'healthy', 'pod_connected', 'arthas_ready', 'degraded'].includes(raw)) return 'connected';
    if (['dead', 'failed', 'error', 'err', 'invalid'].includes(raw)) return 'dead';
    return 'disconnected';
  }

  function normalizeConnection(conn) {
    const c = conn || {};
    const idParts = typeof c.id === 'string' ? c.id.split('/') : [];
    const runtimeObj = c.runtime && typeof c.runtime === 'object' ? c.runtime : {};
    const arthasObj = c.arthas && typeof c.arthas === 'object' ? c.arthas : {};
    const cluster = firstValue(c.cluster, c.cluster_name, c.clusterName, idParts.length >= 3 ? idParts[0] : '');
    const namespace = firstValue(c.namespace, c.ns, c.namespace_name, idParts.length >= 3 ? idParts[1] : '', 'default');
    const pod = firstValue(c.pod, c.pod_name, c.podName, idParts.length >= 3 ? idParts.slice(2).join('/') : '');
    const container = firstValue(c.container, c.container_name, c.containerName);
    const runtimeType = firstValue(runtimeObj.type, runtimeObj.runtime_type, c.runtime_type, typeof c.runtime === 'string' ? c.runtime : '');
    const runtimeVersion = firstValue(runtimeObj.version, runtimeObj.runtime_version, c.runtime_version);
    const pid = firstValue(c.pid, c.java_pid, runtimeObj.pid, runtimeObj.java_pid, arthasObj.pid, arthasObj.java_pid);
    const arthasVersion = firstValue(arthasObj.version, arthasObj.arthas_version, c.arthas_version);
    const arthasPort = firstValue(arthasObj.port, arthasObj.local_port, c.local_port, c.arthas_port);
    const state = normalizeState(c.state, c.status);
    let level = firstValue(c.level, c.connection_level);
    const rawState = textValue(firstValue(c.state, c.status), '').toLowerCase();
    if (!level || level === 'connected' || (level === 'disconnected' && state !== 'disconnected')) {
      level = arthasVersion || arthasPort || rawState === 'arthas_ready' ? 'arthas' : (state === 'connected' || state === 'connecting' ? 'pod' : 'disconnected');
    }
    const id = firstValue(c.id, [cluster, namespace, pod].filter(Boolean).join('/'));
    const podLabel = textValue(pod, textValue(id));
    return {
      raw: c,
      id,
      cluster: textValue(cluster),
      namespace: textValue(namespace),
      pod: textValue(pod),
      container: textValue(container, ''),
      shortName: podLabel === '—' ? podLabel : (podLabel.split('-').slice(0, -2).join('-') || podLabel),
      runtimeType: textValue(runtimeType),
      runtimeVersion: textValue(runtimeVersion, ''),
      runtimeLabel: [runtimeType, runtimeVersion].filter(Boolean).join(' ') || '—',
      pid: textValue(pid),
      arthasVersion: textValue(arthasVersion, ''),
      arthasPort: textValue(arthasPort, ''),
      state,
      level,
      podConnId: firstValue(c.pod_conn_id, c.podConnId, c.connection_id),
      runtimeRaw: c.runtime || null,
    };
  }

  function syncLegacyTarget(c, vm) {
    if (!vm || !vm.id) return;
    const workspaceConn = c || {};
    const workspaceVm = vm;
    const hasPodRuntime = !!(workspaceVm.runtimeRaw || workspaceVm.podConnId || workspaceConn.runtime || workspaceConn.runtime_type);
    const podUsable = workspaceVm.state === 'connected' || (workspaceVm.state === 'connecting' && (workspaceVm.level === 'pod' || hasPodRuntime));
    const connState = workspaceVm.level === 'arthas' ? 'arthas_ready' : (podUsable ? 'pod_connected' : 'disconnected');
    window._connState = connState;
    if (typeof ConnectionStore !== 'undefined' && ConnectionStore.getState && ConnectionStore.setState) {
      const st = ConnectionStore.getState();
      if (st.connState !== connState || st.currentConnId !== vm.id) {
        ConnectionStore.setState({ currentConnId: vm.id, connState, runtimeInfo: vm.runtimeRaw });
      }
    } else if (window._currentConnId !== vm.id) {
      window._currentConnId = vm.id;
    }
    if (typeof syncPodTargetFromConnection === 'function') {
      syncPodTargetFromConnection({
        ...c,
        cluster_name: vm.cluster === '—' ? '' : vm.cluster,
        namespace: vm.namespace === '—' ? 'default' : vm.namespace,
        pod_name: vm.pod === '—' ? '' : vm.pod,
        container_name: vm.container,
        java_pid: vm.pid === '—' ? '' : vm.pid,
      });
    }
  }

  function restoreLegacyPanel() {
    if (!mountedLegacyPanel) return;
    const panel = mountedLegacyPanel;
    const anchor = legacyPanelAnchors[panel.id];
    panel.classList.remove('ws-mounted-panel', 'on');
    panel.style.display = 'none';
    if (anchor && anchor.parentNode) anchor.parentNode.insertBefore(panel, anchor.nextSibling);
    mountedLegacyPanel = null;
  }

  function mountLegacyPanel(container, panelId, onMount) {
    restoreLegacyPanel();
    const panel = document.getElementById(panelId);
    if (!container || !panel) return false;
    if (!legacyPanelAnchors[panelId] && panel.parentNode) {
      legacyPanelAnchors[panelId] = document.createComment('workspace legacy anchor: ' + panelId);
      panel.parentNode.insertBefore(legacyPanelAnchors[panelId], panel);
    }
    container.innerHTML = '';
    container.appendChild(panel);
    panel.classList.add('ws-mounted-panel', 'on');
    panel.style.display = 'flex';
    mountedLegacyPanel = panel;
    if (typeof onMount === 'function') onMount(panel);
    return true;
  }

  function markLegacyTabActive(tabName) {
    const allTabs = ['connections','console','profiler','hotfix','monitor','filebrowser','terminal','ai','model-config','mcp-center','task-center','toolchain-center','external-system','history','diag','diagnosis-cap','skill-management','user-management','audit-logs','alerts'];
    allTabs.forEach(name => {
      const tab = document.getElementById('tab-' + name);
      if (tab) tab.classList.toggle('on', name === tabName);
    });
  }

  function init() {
    ConnectionStore.subscribe(() => render());
    render();
  }

  function render() {
    if (window.ConnectionPool && typeof ConnectionPool.isAddViewOpen === 'function' && ConnectionPool.isAddViewOpen()) {
      if (typeof window.clearWorkspaceHistoryHost === 'function') window.clearWorkspaceHistoryHost();
      const emptyEl = document.getElementById('wsEmpty');
      const contentEl = document.getElementById('wsContent');
      if (emptyEl) emptyEl.style.display = 'none';
      if (contentEl) contentEl.style.display = 'none';
      return;
    }
    const focusId = ConnectionStore.getFocusId();
    const emptyEl = document.getElementById('wsEmpty');
    const contentEl = document.getElementById('wsContent');
    if (!focusId) {
      if (typeof window.clearWorkspaceHistoryHost === 'function') window.clearWorkspaceHistoryHost();
      if (emptyEl) emptyEl.style.display = 'flex';
      if (contentEl) contentEl.style.display = 'none';
      return;
    }
    if (emptyEl) emptyEl.style.display = 'none';
    if (contentEl) contentEl.style.display = 'flex';

    const conn = ConnectionStore.getFocusConnection();
    if (!conn) {
      if (typeof window.clearWorkspaceHistoryHost === 'function') window.clearWorkspaceHistoryHost();
      return;
    }

    const vm = normalizeConnection(conn);
    const resolvedTab = resolveWorkspaceTab(conn, vm);
    const rawTab = conn.tab || 'monitor';
    const next = resolvedTab === rawTab ? conn : { ...conn, tab: resolvedTab };
    syncLegacyTarget(next, vm);
    if (resolvedTab !== rawTab && next?.id) {
      ConnectionStore.updateConnection(next.id, { tab: resolvedTab });
    }
    renderHead(next, vm);
    renderTabs(next, vm, resolvedTab);
    renderBody(next, vm, resolvedTab);
  }

  // ── 头部 ──────────────────────────────────────────────────────

  function renderHead(c, vm) {
    const dotColor = vm.level === 'arthas' ? 'var(--a3)' : vm.state === 'connected' ? 'var(--a)' : 'var(--a6)';
    const dot = document.getElementById('wsDot');
    if (dot) dot.style.background = dotColor;

    const podEl = document.getElementById('wsPod');
    if (podEl) {
      podEl.textContent = vm.pod;
      podEl.title = vm.pod;
    }

    const nsEl = document.getElementById('wsNs');
    if (nsEl) nsEl.textContent = `${vm.shortName} · ${vm.cluster} / ${vm.namespace}`;

    const rtEl = document.getElementById('wsRt');
    if (rtEl) rtEl.textContent = [vm.runtimeLabel !== '—' ? vm.runtimeLabel : '', vm.pid !== '—' ? 'PID:' + vm.pid : ''].filter(Boolean).join(' · ');

    let actions = '';
    const idArg = escapeJsArg(vm.id);
    if (vm.state === 'disconnected' || vm.state === 'dead') {
      actions += `<button class="ws-btn" onclick="ConnectionPool.reconnect('${idArg}')">⚡ 重连</button>`;
    }
    if (vm.level !== 'arthas' && vm.state === 'connected') {
      actions += `<button class="ws-btn" onclick="ConnectionPool.upgradeArthas('${idArg}')">🚀 Arthas</button>`;
    }
    if (vm.level === 'arthas') {
      actions += `<button class="ws-btn" onclick="ConnectionPool.stopArthas('${idArg}')">⏹ Arthas</button>`;
    }
    if (vm.state !== 'disconnected' && vm.state !== 'dead') {
      actions += `<button class="ws-btn ws-btn-danger" onclick="ConnectionPool.disconnect('${idArg}')">断开</button>`;
    }
    const abEl = document.getElementById('wsActions');
    if (abEl) abEl.innerHTML = actions;
  }

  // ── Tab 栏 ────────────────────────────────────────────────────

  function getWorkspaceTabs(vm) {
    const tabs = [{ id: 'monitor', icon: '📊', label: '监控' }];

    if (vm.level === 'arthas' && vm.state === 'connected') {
      tabs.push(
        { id: 'sampling', icon: '🔥', label: '采样' },
        { id: 'console', icon: '⚡', label: 'Arthas' },
        { id: 'hotfix', icon: '🔧', label: '热修复' },
        { id: 'diag', icon: '🔬', label: '诊断' },
      );
    }

    if (vm.state === 'connected') {
      tabs.push(
        { id: 'terminal', icon: '🖥️', label: '终端' },
        { id: 'files', icon: '📂', label: '文件' },
      );
    }

    tabs.push({ id: 'history', icon: '📋', label: '历史' });
    return tabs;
  }

  function resolveWorkspaceTab(c, vm, requestedTab) {
    // 兼容 app-ui 里的单参数调用，避免重连编排阶段 vm 尚未显式传入时直接读空对象。
    const workspaceConn = c || {};
    const workspaceVm = vm || normalizeConnection(workspaceConn);
    const tab = requestedTab || workspaceConn.tab || 'monitor';
    const arthasOnlyTabs = ['sampling', 'console', 'hotfix', 'diag'];
    if (arthasOnlyTabs.includes(tab) && !(workspaceVm.level === 'arthas' && workspaceVm.state === 'connected')) return 'monitor';
    if (['terminal', 'files'].includes(tab) && workspaceVm.state !== 'connected') return 'monitor';
    const availableTabs = getWorkspaceTabs(workspaceVm).map(item => item.id);
    return availableTabs.includes(tab) ? tab : 'monitor';
  }

  function renderTabs(c, vm, resolvedTab) {
    const tabs = getWorkspaceTabs(vm);
    const activeTab = resolvedTab || resolveWorkspaceTab(c, vm);

    const el = document.getElementById('wsTabs');
    if (el) {
      el.innerHTML = tabs.map(t =>
        `<div class="ws-tab${t.id === activeTab ? ' active' : ''}"
              onclick="ConnectionWorkspace.switchTab('${t.id}')"
              role="tab" aria-selected="${t.id === activeTab}">${t.icon} ${t.label}</div>`
      ).join('');
    }
  }

  function switchTab(tabId) {
    const conn = ConnectionStore.getFocusConnection();
    if (conn) {
      const currentVm = normalizeConnection(conn);
      const currentTab = resolveWorkspaceTab(conn, currentVm);
      if (tabId === 'history' && typeof window.rememberWorkspaceHistoryReturn === 'function') {
        window.rememberWorkspaceHistoryReturn(currentTab);
      }
      const next = { ...conn, tab: tabId };
      const vm = normalizeConnection(next);
      const resolvedTab = resolveWorkspaceTab(next, vm, tabId);
      ConnectionStore.updateConnection(conn.id, { tab: resolvedTab });
      next.tab = resolvedTab;
      syncLegacyTarget(next, vm);
      renderTabs(next, vm, resolvedTab);
      renderBody(next, vm, resolvedTab);
    }
  }

  // ── 内容渲染 ──────────────────────────────────────────────────

  function renderBody(c, vm, resolvedTab) {
    const el = document.getElementById('wsBody');
    if (!el) return;
    const activeTab = resolvedTab || resolveWorkspaceTab(c, vm);
    if (activeTab !== 'history' && typeof window.clearWorkspaceHistoryHost === 'function') {
      window.clearWorkspaceHistoryHost();
    }

    switch (activeTab) {
      case 'monitor': renderMonitor(el, c, vm); break;
      case 'sampling': renderLegacyFeature(el, 'panel-profiler', 'profiler'); break;
      case 'console': renderLegacyFeature(el, 'panel-console', 'console', () => {
        if (typeof window.hardenCommandSearchAutofill === 'function') {
          window.hardenCommandSearchAutofill();
          setTimeout(window.hardenCommandSearchAutofill, 250);
        }
      }); break;
      case 'terminal': renderLegacyFeature(el, 'panel-terminal', 'terminal'); break;
      case 'files': renderLegacyFeature(el, 'panel-filebrowser', 'filebrowser'); break;
      case 'history': renderWorkspaceHistory(el); break;
      case 'hotfix': renderLegacyFeature(el, 'panel-hotfix', 'hotfix'); break;
      case 'diag': renderLegacyFeature(el, 'panel-diag', 'diag'); break;
      default: renderMonitor(el, c, vm);
    }
  }

  function renderWorkspaceHistory(el) {
    if (!el) return;
    if (typeof window.clearWorkspaceHistoryHost === 'function') window.clearWorkspaceHistoryHost();
    markLegacyTabActive('history');
    if (typeof updateWorkspaceHead === 'function') updateWorkspaceHead('history');
    if (typeof updateConnectionBarVisibility === 'function') updateConnectionBarVisibility('history');
    if (typeof loadAdminFrameIfNeeded === 'function') loadAdminFrameIfNeeded('history');
    el.innerHTML = `
      <div class="ws-history-shell" data-history-host="workspace" style="flex:1;overflow:hidden;display:flex;flex-direction:column;min-height:0">
        <div style="display:flex;align-items:center;padding:0 14px;height:40px;border-bottom:1px solid var(--ln);flex-shrink:0;background:var(--bg1);gap:8px">
          <button class="ib" onclick="historyGoBack()" title="返回" style="display:flex;align-items:center;gap:4px;font-size:12px">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M19 12H5"/><polyline points="12 19 5 12 12 5"/></svg>
            <span>返回</span>
          </button>
          <span style="font-size:13px;font-weight:600;color:var(--tx)">历史记录</span>
          <div style="flex:1"></div>
          <label data-history-role="filter-label" style="display:none;align-items:center;gap:5px;font-size:11px;color:var(--tx2);cursor:pointer;white-space:nowrap;user-select:none">
            <input type="checkbox" data-history-role="filter-checkbox" onchange="toggleHistoryConnFilter()" style="accent-color:var(--a);cursor:pointer">
            <span>仅当前连接</span>
            <span data-history-role="filter-pod" style="color:var(--a);font-family:var(--mono);font-size:10px"></span>
          </label>
          <button class="ib" style="font-size:11px;display:flex;align-items:center;gap:3px" onclick="loadHistory()">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
            刷新
          </button>
        </div>
        <div style="display:flex;gap:0;border-bottom:1px solid var(--ln);flex-shrink:0;background:var(--bg2)">
          <div class="pm-st on" data-history-role="tab-profiler" onclick="switchHistTab('profiler')" style="font-size:11px">
            采样任务 <span data-history-role="count-profiler" style="background:var(--bg3);border-radius:10px;padding:1px 6px;font-size:10px">0</span>
          </div>
          <div class="pm-st" data-history-role="tab-files" onclick="switchHistTab('files')" style="font-size:11px">
            下载文件 <span data-history-role="count-files" style="background:var(--bg3);border-radius:10px;padding:1px 6px;font-size:10px">0</span>
          </div>
        </div>
        <div style="flex:1;overflow:hidden;display:flex;flex-direction:column;min-height:0">
          <div data-history-role="panel-profiler" style="flex:1;min-height:0;overflow:visible"></div>
          <div data-history-role="panel-files" style="height:100%;overflow-y:auto;padding:14px;display:none">
            <div style="color:var(--tx3);text-align:center;padding:40px">暂无下载记录</div>
          </div>
        </div>
      </div>`;
    const host = el.querySelector('[data-history-host="workspace"]');
    if (host && typeof window.setWorkspaceHistoryHost === 'function') {
      window.setWorkspaceHistoryHost(host);
    }
    if (typeof switchHistTab === 'function') switchHistTab('profiler');
    if (typeof loadHistory === 'function') loadHistory();
  }

  function renderLegacyFeature(el, panelId, tabName, afterMount) {
    const mounted = mountLegacyPanel(el, panelId, () => {
      markLegacyTabActive(tabName);
      if (typeof updateWorkspaceHead === 'function') updateWorkspaceHead(tabName);
      if (typeof updateConnectionBarVisibility === 'function') updateConnectionBarVisibility(tabName);
      if (typeof loadAdminFrameIfNeeded === 'function') loadAdminFrameIfNeeded(tabName);
      if (typeof afterMount === 'function') afterMount();
    });
    if (!mounted) {
      el.innerHTML = `<div style="padding:16px;color:var(--tx3)">该能力面板暂不可用：${escapeHtml(tabName)}</div>`;
    }
  }

  function renderMonitor(el, c, vm) {
    renderLegacyFeature(el, 'panel-monitor', 'monitor', () => {
      el.querySelectorAll('.ws-upgrade-guide').forEach(node => node.remove());
      if (vm && vm.state === 'connected' && vm.level !== 'arthas') {
        const guide = document.createElement('div');
        guide.className = 'ws-upgrade-guide';
        guide.innerHTML = `<div><strong>🚀 启动 Arthas</strong><span>当前是 Pod 连接，终端 / 文件 / 监控可用；需要 JVM 诊断、采样、热修复时请启动 Arthas。</span></div><button class="ws-btn ws-btn-primary" onclick="ConnectionPool.upgradeArthas('${escapeJsArg(vm.id)}')">🚀 启动 Arthas</button>`;
        el.insertBefore(guide, el.firstChild);
      }
      const currentTab = c.pmTab || 'ov';
      if (typeof window.switchPm === 'function') window.switchPm(currentTab);
      scheduleMonitorSnapshot(vm);
    });
  }

  function scheduleMonitorSnapshot(vm) {
    if (typeof loadSnap !== 'function' || !vm || vm.state !== 'connected') return;
    const key = `${vm.id}:${vm.podConnId || ''}`;
    const now = Date.now();
    if (monitorSnapshotKey === key && now - monitorSnapshotAt < 30000) return;
    monitorSnapshotKey = key;
    monitorSnapshotAt = now;
    if (monitorSnapshotTimer) clearTimeout(monitorSnapshotTimer);
    monitorSnapshotTimer = setTimeout(() => {
      const focusId = ConnectionStore.getFocusId();
      const focusConn = ConnectionStore.getFocusConnection();
      if (focusId !== vm.id || (focusConn && resolveWorkspaceTab(focusConn, normalizeConnection(focusConn)) !== 'monitor')) return;
      loadSnap(true);
    }, 80);
  }

  function renderPmBody(el, c) {
    const body = el.querySelector('#pmBody') || document.getElementById('pmBody');
    if (!body) return;
    const t = c.pmTab || 'ov';

    // 先显示骨架屏
    if (t === 'ov' || t === 'pr' || t === 'nw' || t === 'dk') {
      body.innerHTML = '<div class="skeleton" style="height:200px;margin:16px"></div>';
    }

    // 从后端获取真实数据
    const connId = c.pod_conn_id || c.id;
    if (!connId) { body.innerHTML = '<div style="padding:16px;color:var(--tx3)">请先建立连接</div>'; return; }

    if (t === 'ov') {
      fetchMonitorSnapshot(connId).then(d => {
        const cpu = d.cpu_percent ?? 0;
        const mem = d.memory_used_mb ?? 0;
        const memMax = d.memory_limit_mb ?? 4096;
        const th = d.threads ?? 0;
        const gc = d.gc_count ?? 0;
        const rx = d.network_rx_kb ?? 0;
        const tx = d.network_tx_kb ?? 0;
        body.innerHTML = `<div class="mg">
          <div class="mc"><div class="lb">CPU</div><div class="vl ${cpu > 50 ? 'yellow' : 'green'}">${cpu.toFixed(1)}<span class="un">%</span></div><div class="bar"><div class="bar-f" style="width:${Math.min(cpu, 100)}%;background:${cpu > 50 ? 'var(--a6)' : 'var(--a3)'}"></div></div></div>
          <div class="mc"><div class="lb">内存</div><div class="vl blue">${Math.round(mem)}<span class="un">MB / ${Math.round(memMax)}MB</span></div><div class="bar"><div class="bar-f" style="width:${memMax ? (mem / memMax * 100) : 0}%;background:var(--a)"></div></div></div>
          <div class="mc"><div class="lb">线程</div><div class="vl">${th}</div></div>
          <div class="mc"><div class="lb">GC</div><div class="vl">${gc}<span class="un">次</span></div></div>
          <div class="mc"><div class="lb">RX</div><div class="vl green">${rx}<span class="un">KB/s</span></div></div>
          <div class="mc"><div class="lb">TX</div><div class="vl blue">${tx}<span class="un">KB/s</span></div></div>
        </div>`;
      }).catch(() => { body.innerHTML = '<div style="padding:16px;color:var(--a5)">监控数据加载失败</div>'; });
    } else if (t === 'pr') {
      fetchMonitorProcesses(connId).then(d => {
        const procs = d.processes || [];
        body.innerHTML = `<table class="pt"><thead><tr><th>PID</th><th>名称</th><th>CPU%</th><th>MEM%</th><th>状态</th></tr></thead><tbody>
          ${procs.map(p => `<tr><td class="pid">${p.pid}</td><td>${p.name || p.cmd?.split(' ')[0] || '?'}</td><td>${(p.cpu || 0).toFixed(1)}%</td><td>${(p.mem_percent || 0).toFixed(1)}%</td><td><span class="st ${p.state === 'R' ? 'run' : 'sl'}">${p.state === 'R' ? '运行' : '休眠'}</span></td></tr>`).join('')}
        </tbody></table>`;
      }).catch(() => { body.innerHTML = '<div style="padding:16px;color:var(--a5)">进程数据加载失败</div>'; });
    } else if (t === 'nw') {
      fetchMonitorNetwork(connId).then(d => {
        const ifaces = d.interfaces || [];
        body.innerHTML = `<div class="ng">${ifaces.map(iface => `<div class="nc"><div class="nc-t">🌐 ${iface.name}</div><div class="nr"><span class="k">RX</span><span class="v">${formatBytes(iface.rx_bytes)}</span></div><div class="nr"><span class="k">TX</span><span class="v">${formatBytes(iface.tx_bytes)}</span></div></div>`).join('')}</div>`;
      }).catch(() => { body.innerHTML = '<div style="padding:16px;color:var(--a5)">网络数据加载失败</div>'; });
    } else if (t === 'ev') {
      fetchMonitorEvents(connId).then(d => {
        const events = d.events || [];
        body.innerHTML = `<div class="ev">${events.map(e => `<div class="ei"><span class="tm">${e.time || ''}</span><span class="tp ${e.type === 'Warning' ? 'w' : e.type === 'Error' ? 'e' : 'n'}">${e.type === 'Warning' ? '⚠️' : e.type === 'Error' ? '🔴' : '✅'}</span><span class="ms">${e.message || e.reason || ''}</span></div>`).join('') || '<div style="padding:16px;color:var(--tx3)">暂无事件</div>'}</div>`;
      }).catch(() => { body.innerHTML = '<div style="padding:16px;color:var(--a5)">事件数据加载失败</div>'; });
    } else if (t === 'dk') {
      fetchMonitorSnapshot(connId).then(d => {
        const disk = d.disk || {};
        body.innerHTML = `<div class="mg"><div class="mc"><div class="lb">/ 磁盘</div><div class="vl blue">${disk.used_gb || '?'}<span class="un">GB / ${disk.total_gb || '?'}GB</span></div><div class="bar"><div class="bar-f" style="width:${disk.total_gb ? (disk.used_gb / disk.total_gb * 100) : 0}%;background:var(--a)"></div></div></div></div>`;
      }).catch(() => { body.innerHTML = '<div style="padding:16px;color:var(--a5)">磁盘数据加载失败</div>'; });
    } else if (t === 'lg') {
      fetchMonitorLogs(connId).then(d => {
        body.innerHTML = `<div class="term" style="font-size:11px">${(d.logs || []).join('\n') || '暂无日志'}</div>`;
      }).catch(() => { body.innerHTML = '<div style="padding:16px;color:var(--a5)">日志加载失败</div>'; });
    } else if (t === 'cf') {
      body.innerHTML = `<div class="card"><div class="card-tt">容器配置</div>
        <div class="nr"><span class="k" style="color:var(--tx3)">CPU</span><span class="v">${c.runtime?.type || '?'} ${c.runtime?.version || ''}</span></div>
        <div class="nr"><span class="k" style="color:var(--tx3)">Pod</span><span class="v">${c.pod || '?'}</span></div>
        <div class="nr"><span class="k" style="color:var(--tx3)">集群</span><span class="v">${c.cluster || '?'} / ${c.namespace || '?'}</span></div></div>`;
    } else if (t === 'mt') {
      body.innerHTML = `<div class="card"><div class="card-tt">📈 CPU / 内存趋势</div><div id="monitorChart" style="height:150px;background:var(--bg2);border-radius:4px;display:flex;align-items:center;justify-content:center;color:var(--tx3);font-size:12px">加载中...</div></div>`;
      // 可扩展为实时图表
    }
  }

  function switchPm(tab) {
    const c = ConnectionStore.getFocusConnection();
    if (c) {
      ConnectionStore.updateConnection(c.id, { pmTab: tab });
      if (typeof window.switchPm === 'function') window.switchPm(tab);
    }
  }

  function renderSampling(el, c) {
    el.innerHTML = `<div style="padding:16px"><div class="card"><div class="card-tt">采样工具</div><div class="sg">
      <div class="sc" onclick="ConnectionWorkspace.startSample('CPU 采样','${c.id}')"><div class="ico">🔥</div><div class="nm">CPU</div><div class="ds">async-profiler</div></div>
      <div class="sc" onclick="ConnectionWorkspace.startSample('内存分配','${c.id}')"><div class="ico">🧠</div><div class="nm">内存分配</div><div class="ds">追踪分配路径</div></div>
      <div class="sc" onclick="ConnectionWorkspace.startSample('锁竞争','${c.id}')"><div class="ico">🔒</div><div class="nm">锁竞争</div><div class="ds">检测锁等待</div></div>
      <div class="sc" onclick="ConnectionWorkspace.startSample('Wall Time','${c.id}')"><div class="ico">⏱️</div><div class="nm">Wall Time</div><div class="ds">线程执行时间</div></div>
      <div class="sc" onclick="ConnectionWorkspace.startSample('JFR','${c.id}')"><div class="ico">📹</div><div class="nm">JFR</div><div class="ds">Flight Recorder</div></div>
      <div class="sc" onclick="ConnectionWorkspace.startSample('线程 Dump','${c.id}')"><div class="ico">🧵</div><div class="nm">线程 Dump</div><div class="ds">堆栈快照</div></div>
      <div class="sc" onclick="ConnectionWorkspace.startSample('Heap Dump','${c.id}')"><div class="ico">📦</div><div class="nm">Heap Dump</div><div class="ds">堆快照</div></div>
    </div></div></div>`;
  }

  let _sampIv = null;
  function startSample(type, connId) {
    const c = ConnectionStore.getConnection(connId);
    if (!c) return;
    ConnectionStore.updateConnection(connId, { sampSt: { type, sec: 0, done: false } });
    if (_sampIv) clearInterval(_sampIv);
    _sampIv = setInterval(() => {
      const c2 = ConnectionStore.getConnection(connId);
      if (c2?.sampSt && !c2.sampSt.done) {
        ConnectionStore.updateConnection(connId, { sampSt: { ...c2.sampSt, sec: c2.sampSt.sec + 1 } });
      }
    }, 1000);
    toast(type + ' 采集中...', 'info');
    setTimeout(() => {
      clearInterval(_sampIv);
      const c2 = ConnectionStore.getConnection(connId);
      const sec = c2?.sampSt?.sec || 0;
      ConnectionStore.updateConnection(connId, { sampSt: { type, sec, done: true } });
      toast(type + ' 完成（' + sec + 's）', 'success');
    }, 3000 + Math.random() * 3000);
  }

  function renderConsole(el, c) {
    const vm = normalizeConnection(c);
    const pid = vm.pid !== '?' ? vm.pid : '?';
    el.innerHTML = `<div style="padding:16px"><div class="card"><div class="card-tt">Arthas Console</div>
      <div class="term">[arthas@${pid}]$ dashboard

ID   NAME                          GROUP      PRIORITY  STATE    %CPU
1    main                          main       5         RUNNABLE 12.3

Memory: used/max = 345M/2048M(16.8%)
Classes: loaded=12840 total=25680</div></div></div>`;
  }

  function renderTerminal(el, c) {
    const s = (c.pod || '').split('-').slice(0, -2).join('-') || c.pod;
    el.innerHTML = `<div style="padding:16px"><div class="card"><div class="card-tt">终端</div>
      <div class="term">root@${s}:/# uname -a
Linux ${c.pod || '?'} 5.15.0-91-generic x86_64

root@${s}:/# java -version
openjdk version "${c.runtime?.version || '?'}" 2022-01-18 LTS</div></div></div>`;
  }

  function renderFiles(el, c) {
    el.innerHTML = `<div style="padding:16px"><div class="card"><div class="card-tt">文件浏览</div>
      <div class="fi"><span>📁</span><span class="nm">app/</span><span class="sz">-</span></div>
      <div class="fi"><span>📁</span><span class="nm">tmp/</span><span class="sz">-</span></div>
      <div class="fi"><span>📄</span><span class="nm">arthas-boot.jar</span><span class="sz">3.2 MB</span></div>
      <div class="fi"><span>📄</span><span class="nm">application.jar</span><span class="sz">42.1 MB</span></div>
    </div></div>`;
  }

  function renderHistory(el, c) {
    const name = (c.pod || '').split('-').slice(0, -2).join('-') || c.pod;
    el.innerHTML = `<div style="padding:16px"><div class="card"><div class="card-tt">历史 — ${name}</div>
      <table class="pt"><thead><tr><th>时间</th><th>类型</th><th>状态</th><th>操作</th></tr></thead><tbody>
        <tr><td>06-19 14:30</td><td>CPU 采样</td><td><span class="st run">完成</span></td><td style="color:var(--a);cursor:pointer">下载</td></tr>
        <tr><td>06-19 13:15</td><td>线程 Dump</td><td><span class="st run">完成</span></td><td style="color:var(--a);cursor:pointer">下载</td></tr>
      </tbody></table>
      <div style="margin-top:8px;font-size:11px;color:var(--tx3)">💡 数据独立于连接</div>
    </div></div>`;
  }

  function renderHotfix(el, c) {
    el.innerHTML = `<div style="padding:16px"><div class="card"><div class="card-tt">热修复</div>
      <div style="display:flex;gap:16px;align-items:center;flex-wrap:wrap">
        <div style="text-align:center"><div style="font-size:28px">📄</div><div style="font-size:11px;color:var(--tx3)">jad</div></div>
        <span style="color:var(--tx3)">→</span>
        <div style="text-align:center"><div style="font-size:28px">✏️</div><div style="font-size:11px;color:var(--tx3)">编辑</div></div>
        <span style="color:var(--tx3)">→</span>
        <div style="text-align:center"><div style="font-size:28px">🔨</div><div style="font-size:11px;color:var(--tx3)">mc</div></div>
        <span style="color:var(--tx3)">→</span>
        <div style="text-align:center"><div style="font-size:28px">⚡</div><div style="font-size:11px;color:var(--tx3)">redefine</div></div>
      </div>
    </div></div>`;
  }

  function renderDiag(el, c) {
    el.innerHTML = `<div style="padding:16px"><div class="card"><div class="card-tt">诊断中心</div>
      <div style="color:var(--tx3);text-align:center;padding:20px">按场景组织 JVM 与 Pod 诊断<br>
      <span style="font-size:11px;margin-top:8px;display:block">需要 Arthas 连接</span></div>
    </div></div>`;
  }

  // ── API 辅助函数 ──────────────────────────────────────────────

  async function fetchMonitorSnapshot(connId) {
    try {
      const r = await fetch(`${API}/monitor/snapshot`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'include',
        body: JSON.stringify({ connection_id: connId })
      });
      return await r.json();
    } catch { return {}; }
  }

  async function fetchMonitorProcesses(connId) {
    try {
      const r = await fetch(`${API}/monitor/pod`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'include',
        body: JSON.stringify({ connection_id: connId })
      });
      return await r.json();
    } catch { return {}; }
  }

  async function fetchMonitorNetwork(connId) {
    try {
      const r = await fetch(`${API}/monitor/snapshot`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'include',
        body: JSON.stringify({ connection_id: connId })
      });
      return await r.json();
    } catch { return {}; }
  }

  async function fetchMonitorEvents(connId) {
    try {
      const r = await fetch(`${API}/monitor/events`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'include',
        body: JSON.stringify({ connection_id: connId })
      });
      return await r.json();
    } catch { return {}; }
  }

  async function fetchMonitorLogs(connId) {
    try {
      const r = await fetch(`${API}/monitor/logs`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'include',
        body: JSON.stringify({ connection_id: connId })
      });
      return await r.json();
    } catch { return {}; }
  }

  function formatBytes(bytes) {
    if (!bytes || bytes === 0) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return (bytes / Math.pow(1024, i)).toFixed(1) + ' ' + units[i];
  }

  return { init, render, switchTab, switchPm, startSample, restoreLegacyPanel, resolveTab: resolveWorkspaceTab };
})();

window.ConnectionWorkspace = ConnectionWorkspace;
