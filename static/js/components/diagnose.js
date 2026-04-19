/**
 * 性能诊断模块 — 交互逻辑
 * 对接后端 api/performance_diagnose.py 和 api/ai_chat.py 的诊断工具
 */
(function() {
  'use strict';
  try {

  let _diagScene = 'system';
  let _diagData = null;   // 最近一次诊断结果
  let _diagConnId = null;
  let _diagConnOk = false;
  let _diagQuickTool = null;  // 选中的快速工具: 'dashboard'|'threads'|'trace'|'sys_cpu'|'sys_mem'|'sys_disk'|'sys_net'|'sys_proc'|null
  let _threadPageSize = 10; // 线程列表每页条数
  let _threadPages = {};   // 分页状态: key='dashboard'|'threads' → { page, all }

  // ═══════════════════════════════════════════════════════════
  // 连接层级判断（功能点2）
  // ═══════════════════════════════════════════════════════════

  /**
   * 获取当前连接层级
   * @returns {'arthas'|'pod'|'none'}
   */
  function diagGetConnectionLevel() {
    // 优先使用 ConnectionGuard
    if (window.ConnectionGuard) return ConnectionGuard.getCurrentLevel();
    const cs = window._connState;
    if (cs === 'arthas_ready') return 'arthas';
    if (cs === 'pod_connected') return 'pod';
    return 'none';
  }

  // ═══════════════════════════════════════════════════════════
  // 初始化
  // ═══════════════════════════════════════════════════════════

  window.diagInit = function() {
    diagRefreshConn();
    _updateStartBtn();
    // 每 5s 同步一次连接状态
    setInterval(diagRefreshConn, 5000);
  };

  // ═══════════════════════════════════════════════════════════
  // 连接状态
  // ═══════════════════════════════════════════════════════════

  function diagGetConn() {
    // 优先使用当前活跃连接
    if (window._currentConnId) {
      // 检查当前连接是否健康
      const h = window._connHealth && window._connHealth[window._currentConnId];
      // 如果没有健康记录（尚未检查）或健康记录显示存活，都视为可用
      if (!h || h.alive !== false) return window._currentConnId;
    }
    // 回退：从连接列表中找第一个存活的
    if (window._connections && window._connections.length > 0) {
      const alive = window._connections.filter(c => {
        const h = window._connHealth && window._connHealth[c.id];
        // 没有健康记录 或 健康记录显示存活 → 视为可用
        return !h || h.alive !== false;
      });
      if (alive.length > 0) return alive[0].id;
    }
    return null;
  }

  window.diagRefreshConn = function() {
    const level = diagGetConnectionLevel();
    const btn = document.getElementById('diagStartBtn');

    if (level === 'none') {
      _diagConnId = null;
      _diagConnOk = false;
      if (btn) btn.disabled = true;
      _updateSceneVisibility(level);
      return;
    }

    // Pod 或 Arthas 连接都可进入诊断 Tab
    const connId = diagGetConn();
    _diagConnId = connId;

    if (!connId) {
      if (btn) btn.disabled = true;
      _diagConnOk = false;
    } else {
      const conn = (window._connections || []).find(c => c.id === connId);
      const health = window._connHealth && window._connHealth[connId];
      const alive = health ? (health.alive !== false) : (conn && conn.status === 'connected');
      if (alive) {
        if (btn) btn.disabled = false;
        _diagConnOk = true;
      } else {
        if (btn) btn.disabled = true;
        _diagConnOk = false;
      }
    }
    _updateSceneVisibility(level);
  };

  /**
   * 根据连接层级更新场景/工具的可见性
   * @param {'arthas'|'pod'|'none'} level
   */
  function _updateSceneVisibility(level) {
    // JVM 场景（通用诊断、方法慢、线程阻塞、OOM）
    const jvmScenes = ['general', 'method_slow', 'thread_block', 'oom'];
    // 系统诊断场景（Pod 级即可）
    const sysScene = 'system';
    // JVM 快速工具
    const jvmTools = ['dashboard', 'threads', 'trace'];
    // Pod 级快捷工具
    const podTools = ['sys_cpu', 'sys_mem', 'sys_disk', 'sys_net', 'sys_proc'];

    const isArthas = level === 'arthas';
    const isPod = level === 'pod';

    // 场景可见性
    jvmScenes.forEach(s => {
      const el = document.getElementById('ds-' + s);
      if (el) {
        el.style.display = isArthas ? '' : 'none';
        // 如果当前选中的是 JVM 场景但不是 arthas，切换到 system
        if (!isArthas && _diagScene === s) {
          diagSelectScene(sysScene);
        }
      }
    });

    const sysEl = document.getElementById('ds-system');
    if (sysEl) {
      sysEl.style.display = (isPod || isArthas) ? '' : 'none';
    }

    // 快捷工具可见性
    jvmTools.forEach(t => {
      const el = document.getElementById('diagBtn' + t.charAt(0).toUpperCase() + t.slice(1));
      if (el) el.style.display = isArthas ? '' : 'none';
    });

    podTools.forEach(t => {
      const el = document.getElementById('diagBtn' + t.charAt(0).toUpperCase() + t.slice(1));
      if (el) el.style.display = (isPod || isArthas) ? '' : 'none';
    });

    // 层级提示
    const hintEl = document.getElementById('diagLevelHint');
    if (hintEl) {
      if (isPod) {
        hintEl.style.display = '';
        hintEl.innerHTML = '🖥️ Pod 连接模式 — 系统级诊断可用，JVM 深度诊断需启动 Arthas';
      } else if (isArthas) {
        hintEl.style.display = '';
        hintEl.innerHTML = '⚡ Arthas 模式 — 全部诊断功能已解锁';
      } else {
        hintEl.style.display = 'none';
      }
    }
  }

  // ═══════════════════════════════════════════════════════════
  // 场景选择
  // ═══════════════════════════════════════════════════════════

  window.diagSelectScene = function(scene) {
    _diagScene = scene;
    _diagQuickTool = null;  // 选中场景时清除快速工具

    document.querySelectorAll('.diag-sc').forEach(el => el.classList.remove('on'));
    const target = document.getElementById('ds-' + scene);
    if (target) target.classList.add('on');

    // 更新开始诊断按钮文案
    _updateStartBtn();

    // 清除快速工具按钮高亮
    document.querySelectorAll('.diag-tool-btn').forEach(b => b.classList.remove('active'));

    // 追踪参数：仅"方法慢"场景展开，其他场景隐藏
    const traceOpts = document.getElementById('diagTraceOpts');
    if (traceOpts) {
      if (scene === 'method_slow') {
        traceOpts.style.display = 'block';
        const cpInput = document.getElementById('diagClassPattern');
        if (cpInput && !cpInput.value) cpInput.focus();
      } else {
        traceOpts.style.display = 'none';
      }
    }
  };

  // ═══════════════════════════════════════════════════════════
  // 快速工具（dashboard / threads / trace）
  // ═══════════════════════════════════════════════════════════

  window.diagQuickTool = function(tool) {
    if (!_diagConnId) {
      diagShowError('请先在左侧连接目标');
      return;
    }

    // 功能点5: 降级检查 — 统一走 ConnectionGuard
    const jvmTools = ['dashboard', 'threads', 'trace'];
    const podTools = ['sys_cpu', 'sys_mem', 'sys_disk', 'sys_net', 'sys_proc'];

    if (window.ConnectionGuard) {
      const feature = jvmTools.includes(tool) ? 'diag.jvm' : 'diag.pod';
      if (!ConnectionGuard.guard(feature)) return;
    } else {
      // 降级：旧逻辑
      const level = diagGetConnectionLevel();
      if (jvmTools.includes(tool) && level !== 'arthas') {
        diagShowError('此工具需要 Arthas 连接，请先启动 Arthas 诊断环境');
        return;
      }
      if (podTools.includes(tool) && level === 'none') {
        diagShowError('请先建立 Pod 连接');
        return;
      }
    }

    // 切换选中状态：再次点击同一个工具取消选中
    if (_diagQuickTool === tool) {
      _diagQuickTool = null;
      document.querySelectorAll('.diag-tool-btn').forEach(b => b.classList.remove('active'));
      // 隐藏追踪参数
      const traceOpts = document.getElementById('diagTraceOpts');
      if (traceOpts) traceOpts.style.display = 'none';
      _updateStartBtn();
      return;
    }

    _diagQuickTool = tool;

    // 清除场景选中
    document.querySelectorAll('.diag-sc').forEach(el => el.classList.remove('on'));

    // 高亮当前工具按钮
    document.querySelectorAll('.diag-tool-btn').forEach(b => b.classList.remove('active'));
    const toolBtn = document.getElementById('diagBtn' + tool.charAt(0).toUpperCase() + tool.slice(1));
    if (toolBtn) toolBtn.classList.add('active');

    // 追踪参数：仅"方法追踪"展开
    const traceOpts = document.getElementById('diagTraceOpts');
    if (traceOpts) {
      if (tool === 'trace') {
        traceOpts.style.display = 'block';
        const cpInput = document.getElementById('diagClassPattern');
        if (cpInput && !cpInput.value) cpInput.focus();
      } else {
        traceOpts.style.display = 'none';
      }
    }
    _updateStartBtn();
  };

  const _toolNames = { dashboard: 'JVM 快照', threads: '线程分析', trace: '方法追踪', sys_cpu: 'CPU 概览', sys_mem: '内存概览', sys_disk: '磁盘概览', sys_net: '网络概览', sys_proc: '进程列表' };
  const _sceneNames = { general: '通用诊断', method_slow: '方法慢', thread_block: '线程阻塞', oom: '内存/OOM', system: '系统诊断' };

  function _updateStartBtn() {
    const btn = document.getElementById('diagStartBtn');
    if (!btn) return;
    if (_diagQuickTool) {
      btn.innerHTML = '&#128268; 执行 ' + (_toolNames[_diagQuickTool] || _diagQuickTool);
    } else {
      btn.innerHTML = '&#128268; 开始诊断 · ' + (_sceneNames[_diagScene] || _diagScene);
    }
  }

  // ═══════════════════════════════════════════════════════════
  // Pod 级快捷工具（功能点4：无需 Arthas）
  // ═══════════════════════════════════════════════════════════

  async function _diagExecPodTool(tool) {
    diagShowLoading('采集中...', '');
    diagSetBtnsDisabled(true);

    try {
      const resp = await fetch('/api/pod/diagnose', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          connection_id: _diagConnId,
          tool: tool,
        }),
      });
      const data = await resp.json();

      if (data.error) {
        diagShowError(data.error);
        return false;
      }

      diagRenderPodToolResult(tool, data);
      return true;
    } catch (e) {
      diagShowError('采集失败: ' + e.message);
      return false;
    } finally {
      diagSetBtnsDisabled(false);
      diagHideLoading();
    }
  }

  /**
   * 渲染 Pod 级工具结果
   */
  function diagRenderPodToolResult(tool, data) {
    const empty = document.getElementById('diagEmptyState');
    const content = document.getElementById('diagContent');
    if (!content) return;
    if (empty) empty.style.display = 'none';
    content.style.display = 'block';

    const titles = { sys_cpu: 'CPU 概览', sys_mem: '内存概览', sys_disk: '磁盘概览', sys_net: '网络概览', sys_proc: '进程列表' };
    let html = '<div class="diag-result-section">';
    html += `<div class="diag-section-title">&#128206; ${titles[tool] || tool}</div>`;

    const d = data.data || data;
    if (tool === 'sys_cpu') {
      const cpu = d.cpu_percent || d.cpu || 0;
      const cls = cpu < 50 ? 'ok' : cpu < 80 ? 'warn' : 'danger';
      html += '<div style="margin-bottom:8px">';
      html += `<div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:4px"><span style="color:var(--tx2)">CPU 使用率</span><span class="diag-metric-val ${cls}">${cpu.toFixed ? cpu.toFixed(1) : cpu}%</span></div>`;
      html += `<div class="diag-cpu-bar"><div class="diag-cpu-fill ${cls === 'ok' ? 'low' : cls === 'warn' ? 'mid' : 'danger'}" style="width:${Math.min(cpu, 100)}%"></div></div>`;
      html += '</div>';
      if (d.load_avg) html += `<div style="font-size:11px;color:var(--tx2)">负载均值: ${d.load_avg}</div>`;
      if (d.cpu_count) html += `<div style="font-size:11px;color:var(--tx2)">CPU 核数: ${d.cpu_count}</div>`;
    } else if (tool === 'sys_mem') {
      const total = d.total || d.mem_total || 0;
      const used = d.used || d.mem_used || 0;
      const pct = total > 0 ? (used / total * 100) : 0;
      const cls = pct < 70 ? 'ok' : pct < 90 ? 'warn' : 'danger';
      html += '<div style="margin-bottom:8px">';
      html += `<div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:4px"><span style="color:var(--tx2)">内存使用率</span><span class="diag-metric-val ${cls}">${pct.toFixed(1)}%</span></div>`;
      html += `<div class="diag-cpu-bar"><div class="diag-cpu-fill ${cls === 'ok' ? 'low' : cls === 'warn' ? 'mid' : 'danger'}" style="width:${Math.min(pct, 100)}%"></div></div>`;
      html += '</div>';
      html += `<div style="font-size:11px;color:var(--tx2)">已用: ${_fmtBytes(used)} / 总计: ${_fmtBytes(total)}</div>`;
      if (d.available) html += `<div style="font-size:11px;color:var(--tx2)">可用: ${_fmtBytes(d.available)}</div>`;
    } else if (tool === 'sys_disk') {
      if (d.partitions && d.partitions.length > 0) {
        d.partitions.forEach(p => {
          const pct = p.percent || p.use_percent || 0;
          const cls = pct < 70 ? 'ok' : pct < 90 ? 'warn' : 'danger';
          html += `<div style="margin-bottom:6px;padding:6px 8px;background:var(--bg);border:1px solid var(--ln);border-radius:4px">`;
          html += `<div style="display:flex;justify-content:space-between;font-size:11px"><span style="color:var(--tx)">${escapeHtml(p.mount || p.device || '?')}</span><span class="diag-metric-val ${cls}">${pct.toFixed ? pct.toFixed(1) : pct}%</span></div>`;
          html += `<div style="font-size:10px;color:var(--tx3)">${_fmtBytes(p.used || 0)} / ${_fmtBytes(p.total || 0)}</div>`;
          html += '</div>';
        });
      } else {
        html += '<div style="color:var(--tx3);font-size:11px">未获取到磁盘数据</div>';
      }
    } else if (tool === 'sys_net') {
      if (d.interfaces && d.interfaces.length > 0) {
        d.interfaces.forEach(i => {
          html += `<div style="margin-bottom:6px;padding:6px 8px;background:var(--bg);border:1px solid var(--ln);border-radius:4px;font-size:11px">`;
          html += `<div style="color:var(--tx);font-weight:500">${escapeHtml(i.name || '?')}</div>`;
          if (i.bytes_sent || i.bytes_recv) {
            html += `<div style="font-size:10px;color:var(--tx3)">发送: ${_fmtBytes(i.bytes_sent || 0)} / 接收: ${_fmtBytes(i.bytes_recv || 0)}</div>`;
          }
          html += '</div>';
        });
      } else {
        html += '<div style="color:var(--tx3);font-size:11px">未获取到网络数据</div>';
      }
    } else if (tool === 'sys_proc') {
      if (d.processes && d.processes.length > 0) {
        html += '<table class="ptbl"><tr><th>PID</th><th>名称</th><th>CPU%</th><th>MEM%</th><th>状态</th></tr>';
        d.processes.slice(0, 20).forEach(p => {
          const stCls = 'ps-' + (p.status || 'S').charAt(0);
          html += `<tr><td class="ppid">${p.pid || '?'}</td><td>${escapeHtml(p.name || '?')}</td><td class="pc">${(p.cpu_percent || 0).toFixed ? p.cpu_percent.toFixed(1) : p.cpu_percent || 0}</td><td class="pmem">${(p.mem_percent || 0).toFixed ? p.mem_percent.toFixed(1) : p.mem_percent || 0}</td><td class="${stCls}">${escapeHtml(p.status || '?')}</td></tr>`;
        });
        html += '</table>';
      } else {
        html += '<div style="color:var(--tx3);font-size:11px">未获取到进程数据</div>';
      }
    }

    html += '</div>';
    content.innerHTML = html;
    content.scrollTop = 0;
  }

  /**
   * 系统诊断场景执行（功能点4：Pod 级一键诊断）
   */
  async function _diagExecSystemScene() {
    diagShowLoading('系统诊断中...', 'CPU + 内存 + 磁盘 + 网络 + 进程 采集中');
    diagSetBtnsDisabled(true);
    diagHideError();

    try {
      const resp = await fetch('/api/pod/diagnose', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          connection_id: _diagConnId,
          tool: 'system_overview',
        }),
      });
      const data = await resp.json();

      if (data.error) {
        diagShowError(data.error);
        return;
      }

      _diagData = data;
      diagRenderSystemResult(data);

    } catch (e) {
      diagShowError('诊断请求失败: ' + e.message);
    } finally {
      diagSetBtnsDisabled(false);
      diagHideLoading();
    }
  }

  /**
   * 渲染系统诊断全景结果
   */
  function diagRenderSystemResult(data) {
    const empty = document.getElementById('diagEmptyState');
    const content = document.getElementById('diagContent');
    if (!content) return;
    if (empty) empty.style.display = 'none';
    content.style.display = 'block';

    const d = data.data || data;
    let html = '';

    // 概览标签
    let statusColor = 'ok';
    let statusLabel = '正常';
    if (d.cpu && d.cpu.cpu_percent > 80 || d.memory && d.memory.percent > 90) {
      statusColor = 'danger'; statusLabel = '异常';
    } else if (d.cpu && d.cpu.cpu_percent > 50 || d.memory && d.memory.percent > 70) {
      statusColor = 'warn'; statusLabel = '注意';
    }

    html += '<div class="diag-result-section">';
    html += '<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">';
    html += `<span class="diag-tag ${statusColor}">${statusLabel}</span>`;
    html += `<span style="font-size:11px;color:var(--tx3)">${data.timestamp || ''}</span>`;
    html += '</div>';
    html += '</div>';

    // CPU
    if (d.cpu) {
      const cpu = d.cpu.cpu_percent || 0;
      const cls = cpu < 50 ? 'ok' : cpu < 80 ? 'warn' : 'danger';
      html += '<div class="diag-result-section">';
      html += '<div class="diag-section-title">&#128187; CPU</div>';
      html += `<div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:4px"><span style="color:var(--tx2)">使用率</span><span class="diag-metric-val ${cls}">${cpu.toFixed ? cpu.toFixed(1) : cpu}%</span></div>`;
      html += `<div class="diag-cpu-bar"><div class="diag-cpu-fill ${cls === 'ok' ? 'low' : cls === 'warn' ? 'mid' : 'danger'}" style="width:${Math.min(cpu, 100)}%"></div></div>`;
      if (d.cpu.load_avg) html += `<div style="font-size:11px;color:var(--tx2);margin-top:4px">负载: ${d.cpu.load_avg} | 核数: ${d.cpu.cpu_count || '?'}</div>`;
      html += '</div>';
    }

    // 内存
    if (d.memory) {
      const pct = d.memory.percent || 0;
      const cls = pct < 70 ? 'ok' : pct < 90 ? 'warn' : 'danger';
      html += '<div class="diag-result-section">';
      html += '<div class="diag-section-title">&#128230; 内存</div>';
      html += `<div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:4px"><span style="color:var(--tx2)">使用率</span><span class="diag-metric-val ${cls}">${pct.toFixed ? pct.toFixed(1) : pct}%</span></div>`;
      html += `<div class="diag-cpu-bar"><div class="diag-cpu-fill ${cls === 'ok' ? 'low' : cls === 'warn' ? 'mid' : 'danger'}" style="width:${Math.min(pct, 100)}%"></div></div>`;
      html += `<div style="font-size:11px;color:var(--tx2);margin-top:4px">已用: ${_fmtBytes(d.memory.used || 0)} / 总计: ${_fmtBytes(d.memory.total || 0)}</div>`;
      html += '</div>';
    }

    // 磁盘
    if (d.disk && d.disk.partitions && d.disk.partitions.length > 0) {
      html += '<div class="diag-result-section">';
      html += '<div class="diag-section-title">&#128190; 磁盘</div>';
      d.disk.partitions.forEach(p => {
        const pct = p.percent || 0;
        const cls = pct < 70 ? 'ok' : pct < 90 ? 'warn' : 'danger';
        html += `<div style="display:flex;justify-content:space-between;font-size:11px;padding:3px 0"><span style="color:var(--tx)">${escapeHtml(p.mount || p.device || '?')}</span><span class="diag-metric-val ${cls}">${pct.toFixed ? pct.toFixed(1) : pct}%</span></div>`;
      });
      html += '</div>';
    }

    // 进程 TOP5
    if (d.processes && d.processes.length > 0) {
      html += '<div class="diag-result-section">';
      html += '<div class="diag-section-title">&#9881; TOP 进程</div>';
      html += '<table class="ptbl"><tr><th>PID</th><th>名称</th><th>CPU%</th><th>MEM%</th></tr>';
      d.processes.slice(0, 5).forEach(p => {
        html += `<tr><td class="ppid">${p.pid || '?'}</td><td>${escapeHtml(p.name || '?')}</td><td class="pc">${(p.cpu_percent || 0).toFixed ? p.cpu_percent.toFixed(1) : 0}</td><td class="pmem">${(p.mem_percent || 0).toFixed ? p.mem_percent.toFixed(1) : 0}</td></tr>`;
      });
      html += '</table>';
      html += '</div>';
    }

    content.innerHTML = html;
    content.scrollTop = 0;
  }

  // 执行快速工具采集（由 diagStart 调用）
  async function _diagExecQuickTool(tool) {
    // 方法追踪需要先填写类名
    if (tool === 'trace') {
      const cpInput = document.getElementById('diagClassPattern');
      const cp = cpInput && cpInput.value && cpInput.value.trim();
      if (!cp) {
        diagShowError('请填写类名模式后再执行方法追踪');
        if (cpInput) cpInput.focus();
        return false;
      }
    }

    diagShowLoading('快速采集中...', '');
    diagSetBtnsDisabled(true);

    try {
      const resp = await fetch('/api/diagnose/tool', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          connection_id: _diagConnId,
          tool: tool,
          args: tool === 'threads' ? { top_n: 15, check_deadlock: true }
               : tool === 'trace' ? {
                   class_pattern: (document.getElementById('diagClassPattern') || {}).value || '',
                   method_pattern: (document.getElementById('diagMethodPattern') || {}).value || '*',
                   skip_jdk: (document.getElementById('diagSkipJdk') || {}).checked !== false,
                   sample_count: parseInt((document.getElementById('diagSampleCount') || {}).value || '5'),
                 }
               : {},
        }),
      });
      const data = await resp.json();

      if (data.error) {
        if (data.need_config) {
          diagShowError(data.error);
          if (typeof aiOpenSettings === 'function') aiOpenSettings();
        } else {
          diagShowError(data.error);
        }
        return false;
      }

      if (tool === 'dashboard') {
        const raw = data.data ? JSON.stringify(data.data) : '';
        diagRenderQuickResult('JVM 快照', tool, { metrics_raw: raw });
      } else if (tool === 'threads') {
        diagRenderQuickResult('线程分析', tool, { threads_raw: JSON.stringify(data.data), deadlock: data.deadlock });
      } else if (tool === 'trace') {
        const cp = document.getElementById('diagClassPattern') && document.getElementById('diagClassPattern').value;
        const mp = document.getElementById('diagMethodPattern') && document.getElementById('diagMethodPattern').value;
        diagRenderQuickResult('方法追踪', tool, { trace_raw: JSON.stringify(data.data), class_pattern: cp, method_pattern: mp });
      }
      return true;
    } catch (e) {
      diagShowError('采集失败: ' + e.message);
      return false;
    } finally {
      diagSetBtnsDisabled(false);
      diagHideLoading();
    }
  }

  // ═══════════════════════════════════════════════════════════
  // 核心：一键诊断
  // ═══════════════════════════════════════════════════════════

  window.diagStart = async function() {
    if (!_diagConnId) {
      diagShowError('请先在左侧连接目标');
      return;
    }

    // 如果选中了快速工具，走快速工具路径
    if (_diagQuickTool) {
      // Pod 级快捷工具走独立路径
      const podTools = ['sys_cpu', 'sys_mem', 'sys_disk', 'sys_net', 'sys_proc'];
      if (podTools.includes(_diagQuickTool)) {
        await _diagExecPodTool(_diagQuickTool);
        return;
      }
      await _diagExecQuickTool(_diagQuickTool);
      return;
    }

    // 功能点4: Pod-only 分支 — 系统诊断场景
    if (_diagScene === 'system') {
      if (window.ConnectionGuard) {
        if (!ConnectionGuard.guard('diag.pod')) return;
      } else {
        if (diagGetConnectionLevel() === 'none') {
          diagShowError('请先建立 Pod 连接');
          return;
        }
      }
      await _diagExecSystemScene();
      return;
    }

    // JVM 场景需要 Arthas
    if (window.ConnectionGuard) {
      if (!ConnectionGuard.guard('diag.jvm')) return;
    } else {
      if (diagGetConnectionLevel() !== 'arthas') {
        diagShowError('JVM 深度诊断需要 Arthas 连接，请先启动 Arthas');
        return;
      }
    }

    if (_diagScene === 'method_slow') {
      const cp = (document.getElementById('diagClassPattern') || {}).value;
      if (!cp) {
        diagShowError('请填写类名模式（method_slow 场景必须）');
        return;
      }
    }

    diagShowLoading('正在诊断...', 'dashboard + threads + trace 采集中，请稍候');
    diagSetBtnsDisabled(true);
    diagHideError();

    try {
      const payload = {
        target: _diagScene,
      };
      if (_diagScene === 'method_slow') {
        payload.class_pattern = (document.getElementById('diagClassPattern') || {}).value || '';
        payload.method_pattern = (document.getElementById('diagMethodPattern') || {}).value || '';
      }

      const resp = await fetch(`/api/ai/diagnose_performance?connection_id=${encodeURIComponent(_diagConnId)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(payload),
      });

      const data = await resp.json();

      if (data.error) {
        if (data.need_config) {
          diagShowError(data.error);
          if (typeof aiOpenSettings === 'function') aiOpenSettings();
        } else {
          diagShowError(data.error);
        }
        return;
      }

      _diagData = data;
      diagRenderResult(data);

      // 启用 AI 报告按钮
      const reportBtn = document.getElementById('diagReportBtn');
      if (reportBtn) {
        reportBtn.disabled = false;
        reportBtn.style.opacity = '1';
      }

    } catch (e) {
      diagShowError('诊断请求失败: ' + e.message);
    } finally {
      diagSetBtnsDisabled(false);
      diagHideLoading();
    }
  };

  // ═══════════════════════════════════════════════════════════
  // AI 报告生成
  // ═══════════════════════════════════════════════════════════

  window.diagGenerateReport = async function() {
    if (!_diagData) {
      diagShowError('请先执行一次诊断');
      return;
    }
    const btn = document.getElementById('diagReportBtn');
    if (btn) { btn.disabled = true; btn.textContent = '生成中...'; }

    try {
      const resp = await fetch('/api/ai/diagnose_performance/report', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ diagnosis: _diagData, connection_id: _diagConnId }),
      });
      const data = await resp.json();

      if (data.error) {
        if (data.need_config) {
          diagShowError(data.error);
          if (typeof aiOpenSettings === 'function') aiOpenSettings();
        } else {
          diagShowError(data.error);
        }
        return;
      }

      // 追加 AI 报告到现有结果
      const content = document.getElementById('diagContent');
      if (content) {
        content.innerHTML += '<div class="diag-result-section"><div class="diag-section-title">📋 AI 分析报告</div><div class="diag-ai-report">' + renderMarkdown(data.report) + '</div></div>';
        content.scrollTop = content.scrollHeight;
      }
    } catch (e) {
      diagShowError('报告生成失败: ' + e.message);
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = '📋 AI 报告'; }
    }
  };

  window.diagClear = function() {
    _diagData = null;
    _threadPages = {};  // 重置分页状态
    _diagQuickTool = null;  // 重置快速工具选中
    _diagScene = 'system';  // 重置到系统诊断场景
    // 清除工具按钮高亮
    document.querySelectorAll('.diag-tool-btn').forEach(b => b.classList.remove('active'));
    _updateStartBtn();
    const content = document.getElementById('diagContent');
    const empty = document.getElementById('diagEmptyState');
    const reportBtn = document.getElementById('diagReportBtn');
    if (content) { content.style.display = 'none'; content.innerHTML = ''; }
    if (empty) empty.style.display = 'flex';
    if (reportBtn) { reportBtn.disabled = true; reportBtn.style.opacity = '.4'; }
  };

  // ═══════════════════════════════════════════════════════════
  // 结果渲染
  // ═══════════════════════════════════════════════════════════

  function diagRenderResult(data) {
    const empty = document.getElementById('diagEmptyState');
    const content = document.getElementById('diagContent');
    if (!content) return;
    if (empty) empty.style.display = 'none';
    content.style.display = 'block';

    let html = '';

    // 概览标签
    const triggered = data.rules_triggered || [];
    let statusColor = triggered.length === 0 ? 'ok' : (triggered.length <= 2 ? 'warn' : 'danger');
    let statusLabel = triggered.length === 0 ? '正常' : (triggered.length <= 2 ? '注意' : '异常');
    html += '<div class="diag-result-section">';
    html += '<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">';
    html += `<span class="diag-tag ${statusColor}">${statusLabel}</span>`;
    html += `<span style="font-size:11px;color:var(--tx3)">${data.timestamp || ''}</span>`;
    if (data.namespace && data.pod) {
      html += `<span style="font-size:11px;color:var(--tx3);margin-left:auto">${data.namespace}/${data.pod}</span>`;
    }
    html += '</div>';
    html += `<div style="font-size:12px;color:var(--tx);padding:8px 10px;background:var(--bg);border:1px solid var(--ln);border-radius:5px">${escapeHtml(data.summary || '无数据')}</div>`;
    html += '</div>';

    // 规则触发
    if (triggered.length > 0) {
      html += '<div class="diag-result-section">';
      html += '<div class="diag-section-title">&#128293; 触发规则</div>';
      triggered.forEach(r => {
        const ruleMap = {
          'slow_method': ['slow_method', '慢方法', 'warn'],
          'very_slow_method': ['very_slow_method', '极慢方法', 'danger'],
          'high_old_gen': ['high_old_gen', 'Old区偏高', 'warn'],
          'critical_old_gen': ['critical_old_gen', 'Old区危险', 'danger'],
          'high_cpu': ['high_cpu', 'CPU偏高', 'warn'],
          'critical_cpu': ['critical_cpu', 'CPU危险', 'danger'],
          'thread_blocked': ['thread_blocked', 'BLOCKED线程', 'danger'],
          'deadlock': ['deadlock', '死锁', 'danger'],
          'high_gc_freq': ['high_gc_freq', 'GC频繁', 'warn'],
          'fullgc': ['fullgc', 'FullGC', 'danger'],
        };
        const info = ruleMap[r] || [r, r, 'warn'];
        html += `<span class="diag-tag ${info[2]}">${info[1] || r}</span>`;
      });
      html += '</div>';
    }

    // 优化建议
    const recs = data.recommendations || [];
    if (recs.length > 0) {
      html += '<div class="diag-result-section">';
      html += '<div class="diag-section-title">&#128161; 优化建议</div>';
      recs.forEach(rec => {
        html += `<div class="diag-rec"><div class="diag-rec-icon">&#10145;</div><div class="diag-rec-text">${escapeHtml(rec)}</div></div>`;
      });
      html += '</div>';
    }

    // JVM 指标
    const metrics = data.metrics || {};
    if (metrics.dashboard) {
      html += '<div class="diag-result-section">';
      html += '<div class="diag-section-title">&#128202; JVM 基线</div>';
      html += diagParseDashboard(metrics.dashboard);
      html += '</div>';
    }

    // 线程摘要
    if (metrics.threads) {
      html += '<div class="diag-result-section">';
      html += '<div class="diag-section-title">&#129534; 线程快照</div>';
      html += diagParseThreads(metrics.threads);
      html += '</div>';
    }

    // 慢方法
    if (metrics.trace) {
      html += '<div class="diag-result-section">';
      html += '<div class="diag-section-title">&#128640; 慢方法追踪</div>';
      html += '<div style="background:var(--bg);border:1px solid var(--ln);border-radius:5px;padding:10px;font-size:11px;font-family:var(--mono);white-space:pre-wrap;word-break:break-all;max-height:300px;overflow-y:auto;color:var(--tx2)">' + escapeHtml(diagParseTrace(metrics.trace)) + '</div>';
      html += '</div>';
    }

    // 高亮
    const highlights = data.highlights || [];
    if (highlights.length > 0) {
      html += '<div class="diag-result-section">';
      html += '<div class="diag-section-title">&#9888; 关键发现</div>';
      highlights.forEach(h => {
        html += `<div class="diag-rec"><div class="diag-rec-icon" style="color:var(--a4)">&#9888;</div><div class="diag-rec-text">${escapeHtml(h)}</div></div>`;
      });
      html += '</div>';
    }

    content.innerHTML = html;
    content.scrollTop = 0;
  }

  function diagParseDashboard(raw) {
    // 解析 dashboard 原始输出，提取 CPU 和内存信息
    // Arthas 返回格式: {state:"SUCCEEDED", body: {results: [{threads, memoryInfo, gcInfos, ...}]}}
    // 或简化格式: {body: {threads, memoryInfo, gcInfos}}
    let data = null;
    try {
      data = JSON.parse(raw);
    } catch (e) {
      // 不是 JSON，用文本解析
    }

    // 从 Arthas 响应中提取核心数据
    let threads = [], memoryInfo = {}, gcInfos = [], runtimeInfo = {};
    if (data) {
      const body = data.body || data;
      // 处理 results 数组格式
      const results = body.results || [];
      let r0 = results.length > 0 ? results[0] : body;

      // 深层嵌套兜底: results[0] 可能又是 {results: [...]} 格式
      if (r0 && r0.results && r0.results.length > 0 && !r0.threads && !r0.memoryInfo) {
        r0 = r0.results[0];
      }

      threads = r0.threads || r0.busyThreads || [];
      memoryInfo = r0.memoryInfo || r0.memory || {};
      gcInfos = r0.gcInfos || r0.gcInfo || [];
      runtimeInfo = r0.runtimeInfo || r0.runtime || {};
    }

    let html = '';

    // 运行时信息
    if (runtimeInfo.javaVersion || runtimeInfo.jdkVersion || runtimeInfo.pid) {
      html += '<div style="font-size:10px;color:var(--tx3);margin-bottom:6px">';
      if (runtimeInfo.javaVersion || runtimeInfo.jdkVersion) {
        html += `<div>JVM: ${escapeHtml(runtimeInfo.javaVersion || runtimeInfo.jdkVersion)}</div>`;
      }
      if (runtimeInfo.pid) html += `<div>PID: ${runtimeInfo.pid}</div>`;
      html += '</div>';
    }

    // CPU 使用率（从线程数据中取最高值）
    let cpu = 0;
    threads.forEach(t => { if (t.cpu != null && t.cpu > cpu) cpu = t.cpu; });
    if (cpu > 0 || threads.length > 0) {
      const cls = cpu < 50 ? 'ok' : cpu < 80 ? 'warn' : 'danger';
      html += '<div style="margin-bottom:8px">';
      html += `<div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:4px"><span style="color:var(--tx2)">CPU 使用率</span><span class="diag-metric-val ${cls}">${cpu.toFixed(1)}%</span></div>`;
      html += `<div class="diag-cpu-bar"><div class="diag-cpu-fill ${cls}" style="width:${Math.min(cpu, 100)}%"></div></div>`;
      html += '</div>';
    }

    // 内存信息
    if (memoryInfo.heap || memoryInfo.nonheap) {
      html += '<div style="font-size:11px;color:var(--tx2);margin-bottom:6px">';
      const heap = memoryInfo.heap || [];
      const nonheap = memoryInfo.nonheap || [];
      heap.forEach(h => {
        const used = h.used || h.usedBytes || 0;
        const max = h.max || h.maxBytes || 0;
        const pct = max > 0 ? (used / max * 100).toFixed(1) : '?';
        html += `<div>堆内存: ${_fmtBytes(used)} / ${_fmtBytes(max)} (${pct}%)</div>`;
      });
      html += '</div>';
    }

    // GC 信息
    if (gcInfos.length > 0) {
      html += '<div style="font-size:11px;color:var(--tx2)">';
      gcInfos.forEach(gc => {
        html += `<div>${escapeHtml(gc.name || '?')}: ${gc.collectionCount || 0} 次, ${((gc.collectionTime || 0) / 1000).toFixed(1)}s</div>`;
      });
      html += '</div>';
    }

    // 线程概要 — 支持分页展开
    if (threads.length > 0) {
      let blocked = 0, waiting = 0;
      threads.forEach(t => {
        if (t.state === 'BLOCKED') blocked++;
        if (t.state === 'WAITING' || t.state === 'TIMED_WAITING') waiting++;
      });
      html += `<div style="font-size:11px;color:var(--tx2);margin-top:4px">线程: ${threads.length} 总计 | <span style="color:var(--a5)">BLOCKED: ${blocked}</span> | <span style="color:var(--a6)">WAITING: ${waiting}</span></div>`;

      // 分页展示线程列表
      const key = 'dashboard';
      _threadPages[key] = { all: threads, page: (_threadPages[key] && _threadPages[key].page) || 1 };
      html += `<div id="diag-thread-pager-${key}">${_renderThreadPage(key)}</div>`;
    }

    if (html) return html;

    // 解析不到结构化数据，显示原始文本
    if (raw && raw.length > 2) {
      return '<div style="color:var(--tx3);font-size:11px">未解析到指标数据</div>'
        + '<details style="margin-top:6px"><summary style="cursor:pointer;font-size:10px;color:var(--tx3)">原始数据</summary>'
        + '<pre style="font-size:10px;color:var(--tx3);max-height:200px;overflow:auto;white-space:pre-wrap;word-break:break-all">'
        + escapeHtml(raw.substring(0, 2000)) + '</pre></details>';
    }
    return '<div style="color:var(--tx3);font-size:11px">未获取到数据</div>';
  }

  function _fmtBytes(bytes) {
    if (bytes < 0) return '?';
    const units = ['B', 'KB', 'MB', 'GB'];
    let i = 0;
    let val = bytes;
    while (val >= 1024 && i < units.length - 1) { val /= 1024; i++; }
    return val.toFixed(i > 0 ? 1 : 0) + units[i];
  }

  function diagParseThreads(raw) {
    try {
      const data = JSON.parse(raw);
      const body = data.body || data;
      // Arthas thread 命令返回格式: {body: {results: [{busyThreads: [...]}]}}
      // 或简化格式: {body: {busyThreads: [...]}}
      const results = body.results || [];
      let threads;
      if (results.length > 0 && results[0].busyThreads) {
        threads = results[0].busyThreads;
      } else if (results.length > 0 && results[0].threads) {
        threads = results[0].threads;
      } else {
        threads = body.busyThreads || body.threads || [];
      }
      let html = '';
      let blocked = 0, waiting = 0, total = 0;
      threads.forEach(th => {
        total++;
        if (th.state === 'BLOCKED') blocked++;
        if (th.state === 'WAITING' || th.state === 'TIMED_WAITING') waiting++;
      });
      html += '<div style="display:flex;gap:16px;margin-bottom:8px;font-size:11px">';
      html += `<span>总计: <b style="color:var(--tx)">${total}</b></span>`;
      html += `<span style="color:var(--a5)">BLOCKED: <b>${blocked}</b></span>`;
      html += `<span style="color:var(--a6)">WAITING: <b>${waiting}</b></span>`;
      html += '</div>';
      if (blocked > 0) {
        html += '<div style="font-size:11px;color:var(--a5);margin-bottom:6px">⚠️ 存在 BLOCKED 线程</div>';
      }
      // 分页渲染
      const key = 'threads';
      _threadPages[key] = { all: threads, page: (_threadPages[key] && _threadPages[key].page) || 1 };
      html += `<div id="diag-thread-pager-${key}">${_renderThreadPage(key)}</div>`;
      return html || '<div style="color:var(--tx3);font-size:11px">未获取到线程数据</div>';
    } catch (e) {
      return '<div style="color:var(--tx3);font-size:11px">线程数据解析失败</div>';
    }
  }

  function _renderThreadPage(key) {
    const st = _threadPages[key];
    if (!st || !st.all || st.all.length === 0) return '';
    const all = st.all;
    const page = st.page;
    const pageSize = _threadPageSize;
    const totalPages = Math.ceil(all.length / pageSize);
    const start = (page - 1) * pageSize;
    const end = Math.min(start + pageSize, all.length);
    const slice = all.slice(start, end);

    let html = '';
    slice.forEach(th => {
      const stCls = th.state || '?';
      html += `<div class="diag-thread-item">
        <span class="diag-thread-name">${escapeHtml(th.name || '?')}</span>
        <span class="diag-thread-state ${stCls}">${stCls}</span>
        <span style="margin-left:8px;font-size:10px;color:var(--tx3)">cpu: ${(th.cpu || 0).toFixed(1)}%</span>
      </div>`;
    });

    // 分页控件
    if (all.length > pageSize) {
      html += '<div style="display:flex;align-items:center;gap:6px;margin-top:8px;font-size:11px">';
      if (page > 1) {
        html += `<button class="ib" style="font-size:10px;padding:2px 8px" onclick="diagThreadPage('${key}', ${page - 1})">上一页</button>`;
      }
      html += `<span style="color:var(--tx3)">${start + 1}-${end} / ${all.length}</span>`;
      if (page < totalPages) {
        html += `<button class="ib" style="font-size:10px;padding:2px 8px" onclick="diagThreadPage('${key}', ${page + 1})">下一页</button>`;
      }
      html += '</div>';
    }
    return html;
  }

  window.diagThreadPage = function(key, page) {
    if (!_threadPages[key]) return;
    _threadPages[key].page = page;
    // 找到对应的分页容器并重新渲染
    const container = document.getElementById('diag-thread-pager-' + key);
    if (container) {
      container.innerHTML = _renderThreadPage(key);
    }
  };

  function diagParseTrace(raw) {
    // 解析 trace 原始输出（可能是 JSON 字符串），提取耗时信息
    let text = raw;
    try {
      const parsed = JSON.parse(raw);
      if (parsed && parsed.body) {
        const body = parsed.body;
        // 处理 results 数组格式
        const results = body.results || [];
        if (results.length > 0) {
          text = JSON.stringify(results, null, 2);
        } else if (typeof body === 'object') {
          text = JSON.stringify(body, null, 2);
        }
      }
    } catch (e) {
      // 不是 JSON，直接使用原始文本
    }
    return text.substring(0, 3000);
  }

  function diagRenderQuickResult(title, tool, data) {
    const empty = document.getElementById('diagEmptyState');
    const content = document.getElementById('diagContent');
    if (!content) return;
    if (empty) empty.style.display = 'none';
    content.style.display = 'block';

    let html = '<div class="diag-result-section">';
    html += `<div class="diag-section-title">&#128206; ${title} — 快速工具</div>`;

    if (data.error) {
      html += `<div style="color:var(--a5);font-size:12px">错误: ${escapeHtml(data.error)}</div>`;
    } else if (tool === 'dashboard') {
      const raw = data.metrics_raw || JSON.stringify(data.metrics || data.data || data);
      html += diagParseDashboard(raw);
    } else if (tool === 'threads') {
      // data 格式: {ok: true, data: arthasResp, deadlock: ...}
      const raw = data.threads_raw || JSON.stringify(data.data || data);
      html += diagParseThreads(raw);
      if (data.deadlock) {
        html += '<div style="margin-top:8px;padding:8px 10px;background:rgba(248,113,113,.08);border:1px solid var(--a5);border-radius:5px;font-size:11px;color:var(--a5)">⚠️ 检测到死锁信息</div>';
      }
    } else if (tool === 'trace') {
      // 尝试从原始输出中解析耗时
      const raw = data.trace_raw || JSON.stringify(data.data || data);
      const costMatches = raw.match(/(\d+(?:\.\d+)?)\s*(ms|us|s)/g);
      if (costMatches && costMatches.length > 0) {
        html += '<div style="background:var(--bg);border:1px solid var(--ln);border-radius:5px;padding:10px;font-size:11px;font-family:var(--mono);white-space:pre-wrap;word-break:break-all;max-height:300px;overflow-y:auto;color:var(--tx2)">' + escapeHtml(raw.substring(0, 3000)) + '</div>';
      } else {
        html += `<div style="font-size:12px;color:var(--tx2)">${escapeHtml(data.summary || '未采样到数据')}</div>`;
      }
    }

    html += '</div>';
    content.innerHTML = html;
    content.scrollTop = 0;
  }

  // ═══════════════════════════════════════════════════════════
  // 辅助
  // ═══════════════════════════════════════════════════════════

  function diagShowLoading(text, sub) {
    const loading = document.getElementById('diagLoading');
    const empty = document.getElementById('diagEmptyState');
    const content = document.getElementById('diagContent');
    if (empty) empty.style.display = 'none';
    if (content) content.style.display = 'none';
    if (loading) {
      loading.style.display = 'block';
      const lbl = document.getElementById('diagLoadingText');
      const subLbl = document.getElementById('diagLoadingSub');
      if (lbl) lbl.textContent = text || '采集中...';
      if (subLbl) subLbl.textContent = sub || '';
    }
  }

  function diagHideLoading() {
    const loading = document.getElementById('diagLoading');
    if (loading) loading.style.display = 'none';
  }

  function diagShowError(msg) {
    const el = document.getElementById('diagError');
    if (el) { el.textContent = msg; el.style.display = 'block'; }
  }

  function diagHideError() {
    const el = document.getElementById('diagError');
    if (el) el.style.display = 'none';
  }

  function diagSetBtnsDisabled(disabled) {
    ['diagBtnDashboard', 'diagBtnThreads', 'diagBtnTrace', 'diagStartBtn'].forEach(id => {
      const btn = document.getElementById(id);
      if (btn) btn.disabled = disabled;
    });
  }

  function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
  }

  // 简单 Markdown 渲染（用于 AI 报告）
  function renderMarkdown(text) {
    if (!text) return '';
    let html = escapeHtml(text);

    // 代码块 ```code```
    html = html.replace(/```(\w*)\n([\s\S]*?)```/g, function(_, lang, code) {
      return '<pre style="background:var(--bg);border:1px solid var(--ln);border-radius:5px;padding:10px;font-size:11px;font-family:var(--mono);white-space:pre-wrap;word-break:break-all;max-height:300px;overflow-y:auto;color:var(--tx2);margin:8px 0">' + code.trim() + '</pre>';
    });

    // 行内代码 `code`
    html = html.replace(/`([^`]+)`/g, '<code style="background:var(--bg3);padding:1px 5px;border-radius:3px;font-family:var(--mono);font-size:11px;color:var(--a)">$1</code>');

    // 标题 ### ## #
    html = html.replace(/^### (.+)$/gm, '<h4 style="font-size:13px;font-weight:600;color:var(--tx);margin:12px 0 6px 0">$1</h4>');
    html = html.replace(/^## (.+)$/gm, '<h3 style="font-size:14px;font-weight:600;color:var(--tx);margin:14px 0 8px 0">$1</h3>');
    html = html.replace(/^# (.+)$/gm, '<h2 style="font-size:15px;font-weight:600;color:var(--tx);margin:16px 0 8px 0">$1</h2>');

    // 粗体 **text**
    html = html.replace(/\*\*([^*]+)\*\*/g, '<strong style="font-weight:600;color:var(--tx)">$1</strong>');

    // 列表 - 或 1.
    html = html.replace(/^- (.+)$/gm, '<div style="display:flex;gap:6px;margin:2px 0"><span style="color:var(--a)">•</span><span>$1</span></div>');
    html = html.replace(/^\d+\. (.+)$/gm, '<div style="display:flex;gap:6px;margin:2px 0"><span style="color:var(--a);min-width:18px">$&</span><span>$1</span></div>');

    // 段落（连续两个换行）
    html = html.replace(/\n\n/g, '</p><p style="margin:8px 0">');
    html = '<p style="margin:8px 0">' + html + '</p>';

    return html;
  }

  } catch(e) {
    console.error('❌ diagnose.js IIFE error:', e);
  }
})();

