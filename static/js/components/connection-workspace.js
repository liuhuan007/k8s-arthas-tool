/**
 * ConnectionWorkspace - per-connection 工作区
 * 根据焦点连接的层级动态生成 Tab 栏和内容
 */

const ConnectionWorkspace = (function() {
  'use strict';

  function init() {
    ConnectionStore.subscribe(() => render());
  }

  function render() {
    const focusId = ConnectionStore.getFocusId();
    const emptyEl = document.getElementById('wsEmpty');
    const contentEl = document.getElementById('wsContent');
    if (!focusId) {
      if (emptyEl) emptyEl.style.display = 'flex';
      if (contentEl) contentEl.style.display = 'none';
      return;
    }
    if (emptyEl) emptyEl.style.display = 'none';
    if (contentEl) contentEl.style.display = 'flex';

    const conn = ConnectionStore.getFocusConnection();
    if (!conn) return;

    renderHead(conn);
    renderTabs(conn);
    renderBody(conn);
  }

  // ── 头部 ──────────────────────────────────────────────────────

  function renderHead(c) {
    const dotColor = c.level === 'arthas' ? 'var(--a3)' : c.state === 'connected' ? 'var(--a)' : 'var(--a6)';
    const dot = document.getElementById('wsDot');
    if (dot) dot.style.background = dotColor;

    const pod = (c.pod || '').split('-').slice(0, -2).join('-') || c.pod;
    const podEl = document.getElementById('wsPod');
    if (podEl) podEl.textContent = pod;

    const nsEl = document.getElementById('wsNs');
    if (nsEl) nsEl.textContent = `${c.cluster || '?'} / ${c.namespace || '?'}`;

    const rtEl = document.getElementById('wsRt');
    if (rtEl) rtEl.textContent = `${c.runtime?.type || '?'} ${c.runtime?.version || ''} · PID:${c.pid || '?'}`;

    let actions = '';
    if (c.level !== 'arthas' && c.state === 'connected') {
      actions += `<button class="ws-btn" onclick="ConnectionPool.upgradeArthas('${c.id}')">🚀 Arthas</button>`;
    }
    if (c.level === 'arthas') {
      actions += `<button class="ws-btn" onclick="ConnectionPool.stopArthas('${c.id}')">⏹ Arthas</button>`;
    }
    if (c.state !== 'disconnected' && c.state !== 'dead') {
      actions += `<button class="ws-btn ws-btn-danger" onclick="ConnectionPool.disconnect('${c.id}')">断开</button>`;
    }
    const abEl = document.getElementById('wsActions');
    if (abEl) abEl.innerHTML = actions;
  }

  // ── Tab 栏 ────────────────────────────────────────────────────

  function renderTabs(c) {
    const tabs = [{ id: 'monitor', icon: '📊', label: '监控' }];

    if (c.level === 'arthas') {
      tabs.push(
        { id: 'sampling', icon: '🔥', label: '采样' },
        { id: 'console', icon: '⚡', label: 'Arthas' },
        { id: 'hotfix', icon: '🔧', label: '热修复' },
        { id: 'diag', icon: '🔬', label: '诊断' },
      );
    }

    if (c.state === 'connected') {
      tabs.push(
        { id: 'terminal', icon: '🖥️', label: '终端' },
        { id: 'files', icon: '📂', label: '文件' },
      );
    }

    tabs.push({ id: 'history', icon: '📋', label: '历史' });

    const el = document.getElementById('wsTabs');
    if (el) {
      el.innerHTML = tabs.map(t =>
        `<div class="ws-tab${t.id === c.tab ? ' active' : ''}"
              onclick="ConnectionWorkspace.switchTab('${t.id}')"
              role="tab" aria-selected="${t.id === c.tab}">${t.icon} ${t.label}</div>`
      ).join('');
    }
  }

  function switchTab(tabId) {
    const conn = ConnectionStore.getFocusConnection();
    if (conn) {
      ConnectionStore.updateConnection(conn.id, { tab: tabId });
      renderTabs(conn);
      renderBody(conn);
    }
  }

  // ── 内容渲染 ──────────────────────────────────────────────────

  function renderBody(c) {
    const el = document.getElementById('wsBody');
    if (!el) return;
    const tab = c.tab || 'monitor';

    switch (tab) {
      case 'monitor': renderMonitor(el, c); break;
      case 'sampling': renderSampling(el, c); break;
      case 'console': renderConsole(el, c); break;
      case 'terminal': renderTerminal(el, c); break;
      case 'files': renderFiles(el, c); break;
      case 'history': renderHistory(el, c); break;
      case 'hotfix': renderHotfix(el, c); break;
      case 'diag': renderDiag(el, c); break;
      default: renderMonitor(el, c);
    }
  }

  function renderMonitor(el, c) {
    const tabs = [
      { i: 'ov', ic: '📊', l: '概览' }, { i: 'mt', ic: '📈', l: '指标' },
      { i: 'pr', ic: '⚙️', l: '进程' }, { i: 'nw', ic: '🌐', l: '网络' },
      { i: 'dk', ic: '💾', l: '磁盘' }, { i: 'ev', ic: '🔔', l: '事件' },
      { i: 'lg', ic: '📄', l: '日志' }, { i: 'cf', ic: '🔧', l: '配置' },
    ];
    el.innerHTML = `
      <div class="pm-tabs">${tabs.map(t => `<div class="pm-tab${t.i === (c.pmTab || 'ov') ? ' active' : ''}"
        onclick="ConnectionWorkspace.switchPm('${t.i}')">${t.ic} ${t.l}</div>`).join('')}</div>
      <div id="pmBody" style="flex:1;overflow-y:auto;padding:16px">
        <div class="skeleton" style="height:200px;margin:16px"></div>
      </div>`;
    setTimeout(() => renderPmBody(el, c), 300);
  }

  function renderPmBody(el, c) {
    const body = el.querySelector('#pmBody') || document.getElementById('pmBody');
    if (!body) return;
    const t = c.pmTab || 'ov';

    if (t === 'ov') {
      const cpu = (Math.random() * 60 + 5).toFixed(1);
      const mem = Math.floor(Math.random() * 500 + 100);
      const th = Math.floor(Math.random() * 80 + 10);
      const gc = Math.floor(Math.random() * 20);
      const rx = Math.floor(Math.random() * 200 + 10);
      const tx = Math.floor(Math.random() * 80 + 5);
      body.innerHTML = `<div class="mg">
        <div class="mc"><div class="lb">CPU</div><div class="vl ${cpu > 50 ? 'yellow' : 'green'}">${cpu}<span class="un">%</span></div><div class="bar"><div class="bar-f" style="width:${cpu}%;background:${cpu > 50 ? 'var(--a6)' : 'var(--a3)'}"></div></div></div>
        <div class="mc"><div class="lb">内存</div><div class="vl blue">${mem}<span class="un">MB</span></div><div class="bar"><div class="bar-f" style="width:${mem / 40}%;background:var(--a)"></div></div></div>
        <div class="mc"><div class="lb">线程</div><div class="vl">${th}</div></div>
        <div class="mc"><div class="lb">GC</div><div class="vl">${gc}<span class="un">次</span></div></div>
        <div class="mc"><div class="lb">RX</div><div class="vl green">${rx}<span class="un">KB/s</span></div></div>
        <div class="mc"><div class="lb">TX</div><div class="vl blue">${tx}<span class="un">KB/s</span></div></div>
      </div>`;
    } else if (t === 'pr') {
      body.innerHTML = `<table class="pt"><thead><tr><th>PID</th><th>名称</th><th>CPU%</th><th>MEM%</th><th>状态</th></tr></thead><tbody>
        <tr><td class="pid">${c.pid || '?'}</td><td>${c.runtime?.type === 'java' ? 'java' : c.runtime?.type === 'node' ? 'node' : c.runtime?.type}</td><td>12.3%</td><td>345%</td><td><span class="st run">运行</span></td></tr>
      </tbody></table>`;
    } else if (t === 'nw') {
      body.innerHTML = `<div class="ng"><div class="nc"><div class="nc-t">🌐 eth0</div><div class="nr"><span class="k">RX</span><span class="v">1.2 GB</span></div><div class="nr"><span class="k">TX</span><span class="v">856 MB</span></div></div></div>`;
    } else if (t === 'ev') {
      body.innerHTML = `<div class="ev"><div class="ei"><span class="tm">14:30</span><span class="tp w">⚠️</span><span class="ms">内存超过 80%</span></div><div class="ei"><span class="tm">14:28</span><span class="tp n">✅</span><span class="ms">健康检查通过</span></div></div>`;
    } else if (t === 'dk') {
      body.innerHTML = `<div class="mg"><div class="mc"><div class="lb">/ 磁盘</div><div class="vl blue">12.3<span class="un">GB / 50GB</span></div></div></div>`;
    } else if (t === 'lg') {
      body.innerHTML = `<div class="term" style="font-size:11px">14:30:12 INFO  Application started\n14:30:12 INFO  Tomcat started on port 8080</div>`;
    } else if (t === 'cf') {
      body.innerHTML = `<div class="card"><div class="card-tt">容器配置</div><div class="nr"><span class="k" style="color:var(--tx3)">CPU</span><span class="v">500m / 2000m</span></div><div class="nr"><span class="k" style="color:var(--tx3)">Memory</span><span class="v">512Mi / 4Gi</span></div></div>`;
    } else if (t === 'mt') {
      body.innerHTML = `<div class="card"><div class="card-tt">📈 CPU / 内存趋势</div><div style="height:150px;background:var(--bg2);border-radius:4px;display:flex;align-items:center;justify-content:center;color:var(--tx3);font-size:12px">实时图表区域</div></div>`;
    }
  }

  function switchPm(tab) {
    const c = ConnectionStore.getFocusConnection();
    if (c) {
      ConnectionStore.updateConnection(c.id, { pmTab: tab });
      const tabs = { ov: '概览', mt: '指标', pr: '进程', nw: '网络', dk: '磁盘', ev: '事件', lg: '日志', cf: '配置' };
      document.querySelectorAll('.pm-tab').forEach(x => x.classList.toggle('active', x.textContent.includes(tabs[tab])));
      renderPmBody(document.getElementById('wsBody'), c);
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
    el.innerHTML = `<div style="padding:16px"><div class="card"><div class="card-tt">Arthas Console</div>
      <div class="term">[arthas@${c.pid || '?'}]$ dashboard

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

  return { init, render, switchTab, switchPm, startSample };
})();

window.ConnectionWorkspace = ConnectionWorkspace;
