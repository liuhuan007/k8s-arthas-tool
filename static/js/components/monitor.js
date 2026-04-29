/**
 * 指标监控组件
 * 处理 Pod CPU/内存/网络/进程等指标采集和展示
 */

// ── State ─────────────────────────────────────────────────────────────────
// _metricsPolling, _metricsTimer, _metricsCache 在 app-ui.js 中声明，使用 window 访问

// 获取缓存的指标
function getMetrics(cluster, ns, pod) {
  const key = `${cluster}/${ns}/${pod}`;
  if (!window._metricsCache) window._metricsCache = new Map();
  return window._metricsCache.get(key) || null;
}

// 设置缓存的指标
function setMetrics(cluster, ns, pod, data) {
  const key = `${cluster}/${ns}/${pod}`;
  if (!window._metricsCache) window._metricsCache = new Map();
  window._metricsCache.set(key, {
    data,
    timestamp: Date.now()
  });
}

// 启动指标轮询
function startMetricsPolling(cluster, ns, pod) {
  if (window._metricsTimer) {
    clearInterval(window._metricsTimer);
  }
  window._metricsPolling = true;
  
  fetchMetrics(cluster, ns, pod);
  
  window._metricsTimer = setInterval(() => {
    if (window._metricsPolling) {
      fetchMetrics(cluster, ns, pod);
    }
  }, 5000);
}

// 停止指标轮询
function stopMetricsPolling() {
  window._metricsPolling = false;
  if (window._metricsTimer) {
    clearInterval(window._metricsTimer);
    window._metricsTimer = null;
  }
}

// 获取指标数据
async function fetchMetrics(cluster, ns, pod) {
  try {
    const resp = await safePost('/api/monitor/pod', {
      cluster,
      namespace: ns,
      pod
    });
    
    if (resp.metrics) {
      setMetrics(cluster, ns, pod, resp.metrics);
      // 触发指标更新事件
      document.dispatchEvent(new CustomEvent('metrics-updated', {
        detail: { cluster, ns, pod, metrics: resp.metrics }
      }));
    }
  } catch (e) {
    console.error('获取指标失败:', e);
  }
}

// 渲染指标概览
function renderOverview(snap) {
  const el = document.getElementById('metricsOverview');
  if (!el) return;
  
  if (!snap) {
    el.innerHTML = '<div class="empty-state">暂无指标数据</div>';
    return;
  }
  
  const cpu = snap.cpu || {};
  const mem = snap.memory || {};
  
  el.innerHTML = `
    <div class="metric-cards">
      <div class="metric-card">
        <div class="metric-label">CPU</div>
        <div class="metric-value">${cpu.usagePercent?.toFixed(1) || '—'}%</div>
        <div class="metric-detail">${cpu.usage || '—'} / ${cpu.limit || '—'}</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">内存</div>
        <div class="metric-value">${mem.usagePercent?.toFixed(1) || '—'}%</div>
        <div class="metric-detail">${fmtSz(mem.usageBytes)} / ${fmtSz(mem.limitBytes)}</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">网络 RX</div>
        <div class="metric-value">${fmtSz(snap.network?.rxBytes || 0)}/s</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">网络 TX</div>
        <div class="metric-value">${fmtSz(snap.network?.txBytes || 0)}/s</div>
      </div>
    </div>`;
}

// 渲染进程列表
function renderProcs(snap) {
  const el = document.getElementById('procsTable');
  if (!el) return;
  
  const procs = snap.processes || snap.container_metrics?.processes || [];
  if (procs.length === 0) {
    el.innerHTML = '<tr><td colspan="6" class="empty-state">无进程数据</td></tr>';
    return;
  }
  const normProc = p => ({
    pid: p.pid || '?',
    user: p.user || '—',
    cpu: p.cpu ?? p.cpu_percent ?? 0,
    mem: p.mem ?? p.mem_percent ?? 0,
    stat: p.stat || p.status || '—',
    cmd: p.cmd || p.name || '—',
  });
  
  el.innerHTML = procs.slice(0, 20).map(raw => {
    const p = normProc(raw);
    return `
    <tr>
      <td style="font-family:monospace;color:var(--a)">${esc(p.pid)}</td>
      <td>${esc(p.user)}</td>
      <td>${esc(p.cpu)}%</td>
      <td>${esc(p.mem)}%</td>
      <td>${esc(p.stat)}</td>
      <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis" title="${esc(p.cmd)}">${esc(p.cmd)}</td>
    </tr>`;
  }).join('');
}

// 导出
if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    getMetrics,
    setMetrics,
    startMetricsPolling,
    stopMetricsPolling,
    fetchMetrics,
    renderOverview,
    renderProcs
  };
}