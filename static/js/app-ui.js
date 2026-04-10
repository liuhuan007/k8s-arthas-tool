

// ── 工具函数 ──────────────────────────────────────────────────────────────────
function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text || '';
  return div.innerHTML;
}

// ── 认证工具 ──────────────────────────────────────────────────────────────────
// auth.js 已定义 AUTH_KEY, AUTH_USER，不要重复声明

async function doLogout() {
  // 用原生 fetch 调用后端登出，避免 safePost 的 401 自动跳转副作用
  try {
    await fetch(`${API}/auth/logout`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
      credentials: 'include'
    });
  } catch (e) {
    console.log('Logout API error (ignore):', e.message);
  }
  // 清除本地存储
  sessionStorage.removeItem(AUTH_KEY);
  sessionStorage.removeItem(AUTH_USER);
  localStorage.removeItem(AUTH_KEY);
  localStorage.removeItem(AUTH_USER);
  localStorage.removeItem('arthas_remember');
  // HTTP 模式（K8s/Docker）跳到 /login.html，file:// 模式跳到 login.html
  window.location.href = window.location.protocol.startsWith('http') ? '/login.html' : 'login.html';
}

function initUserDisplay() {
  // 解析用户信息
  let user = null, role = 'user', username = '游客';
  try {
    const userStr = sessionStorage.getItem(AUTH_USER) || localStorage.getItem(AUTH_USER);
    user = userStr ? JSON.parse(userStr) : null;
  } catch {}
  if (user) {
    username = user.username || '未知';
    role = user.role || 'user';
  }
  
  const el = document.getElementById('loginUser');
  if(el) el.textContent = username;
  
  // 根据角色控制管理员链接的显示
  document.querySelectorAll('.admin-only').forEach(el => {
    el.style.display = role === 'admin' ? '' : 'none';
  });
}


// 生成时间戳字符串 格式: 20260322153847
function fmtNowTs() {
  const n = new Date();
  return n.getFullYear().toString()
    + String(n.getMonth()+1).padStart(2,'0')
    + String(n.getDate()).padStart(2,'0')
    + String(n.getHours()).padStart(2,'0')
    + String(n.getMinutes()).padStart(2,'0')
    + String(n.getSeconds()).padStart(2,'0');
}

// Safe fetch helper: 使用 api.js 中的 safePost

// ── State ──────────────────────────────────────────────────────────────────────
let _clusters = [], _ac = null;
let _connections = [], _currentConnId = null;
let _connected = false, _ap = null;
let _connHealth = {};  // { connId: { alive, pod_exists, pod_phase, reason } }
// 同步模块内部状态到 window，供 ai-chat.js / MCP 弹窗等外部模块读取
function _syncState() {
  window._connections  = _connections;
  window._currentConnId = _currentConnId;
  window._connHealth   = _connHealth;
}
let _sid = null, _cid = null, _pollTimer = null, _polling = false;
let _cmdHist = [], _histIdx = -1, _selCmd = null;
let _pfTaskId = null, _pfPollTimer = null, _pfStart = null, _pfDur = 60, _pfLL = 0;
let _pfPollingForConn = null; // 记录当前轮询是为哪个连接服务
let _pfTaskInfo = { type: '-', event: '-', duration: 0, status: '-' }; // 当前任务信息
let _snap = null, _histData = [], _logRaw = '', _logWrap = true;
let _fbSelected = null, _fbCurPath = '/tmp';
// 每个连接的采样任务状态缓存
let _pfTasksByConn = {}; // { connId: { taskId, startTime, duration, logLines, status } }
let _metricsPolling = false, _metricsTimer = null;
let _metricsCache = new Map();

// ── Helpers ───────────────────────────────────────────────────────────────────
// esc, fmtSz, fmtTs, mkv, gRow, toast 已在 utils.js 中定义

// ── Sidebar Pod Target Collapse ──────────────────────────────────────────────
function togglePodTarget() {
  const el = document.getElementById('podTarget');
  const arrow = document.getElementById('ptCollapseArrow');
  if (!el) return;
  el.classList.toggle('collapsed');
  if (arrow) arrow.classList.toggle('up', !el.classList.contains('collapsed'));
}

// ── Connection Management ─────────────────────────────────────────────────────
function renderConnList() {
  const el = document.getElementById('connList');
  if (_connections.length === 0) {
    el.innerHTML = '<div class="sb-empty">暂无连接<br>使用下方添加</div>';
    return;
  }
  let html = '';
  _connections.forEach(c => {
    const isActive = c.id === _currentConnId;
    const h = _connHealth[c.id];
    // 健康状态图标与样式
    let statusIcon = '', statusStyle = '', statusHint = '';
    if (h) {
      if (h.pod_exists === false) {
        statusIcon = '⚠'; statusStyle = 'color:var(--a5)'; statusHint = 'Pod 不存在，建议删除';
      } else if (h.reason && h.reason.startsWith('pod_')) {
        statusIcon = '◉'; statusStyle = 'color:#f59e0b'; statusHint = `Pod 状态: ${h.pod_phase || h.reason}`;
      } else if (h.alive === false) {
        statusIcon = '◈'; statusStyle = 'color:#f59e0b'; statusHint = 'Arthas 连接已断开，点击可重连';
      } else if (h.pod_exists === true && h.alive !== false) {
        statusIcon = '●'; statusStyle = 'color:var(--a3)'; statusHint = '连接正常';
      } else if (h.reason === 'cluster_unavailable') {
        statusIcon = '⊘'; statusStyle = 'color:var(--a5)'; statusHint = '集群不可用';
      }
    }
    html += `
      <div class="conn-itm ${isActive?'on':''}" onclick="switchConnection('${c.id}')" title="集群: ${esc(c.cluster_name)}\n环境: ${c.namespace}\nPod: ${c.pod_name}\n端口: ${c.local_port}${c.arthas_version ? '\nArthas: ' + c.arthas_version : ''}${c.arthas_address ? '\n地址: ' + c.arthas_address : ''}${statusHint ? '\n' + statusHint : ''}">
        <div style="flex:1;overflow:hidden">
          <div style="font-weight:600;color:${isActive?'var(--a)':'var(--tx)'};margin-bottom:3px">
            ${statusIcon ? `<span style="font-size:9px;${statusStyle};margin-right:3px" title="${statusHint}">${statusIcon}</span>` : '<span style="font-size:11px">🔹</span>'} ${esc(c.cluster_name)}
          </div>
          <div style="font-size:10px;color:var(--tx2)">
            <span style="opacity:0.8">${c.namespace}</span>
            <span style="margin:0 4px;opacity:0.5">/</span>
            <span style="font-weight:500;color:${isActive?'var(--a)':'var(--tx)'}">${c.pod_name}</span>
          </div>
        </div>
        <button class="del-conn" onclick="event.stopPropagation();deleteConnection('${c.id}')" title="删除连接">✕</button>
      </div>
    `;
  });
  el.innerHTML = html;
}

async function loadConnectionCommands(connId) {
  // 加载连接的命令历史
  try {
    const r = await fetch(`${API}/arthas/commands?connection_id=${connId}&limit=50`);
    const d = await r.json();
    if (d.ok && d.commands) {
      // 清空当前输出区
      const co = coEl();
      co.innerHTML = '<div class="o-dim">── Arthas K8s 诊断台 ─────────────────────────────────────────────────────</div>';

      // 按时间倒序显示（最新的在上面）
      d.commands.reverse().forEach(cmd => {
        clog(esc(cmd.command), 'cmd');
        if (cmd.error) {
          clog('✗ ' + esc(cmd.error), 'err');
        } else if (cmd.output) {
          clog(esc(cmd.output));
        }
      });
    }
  } catch(e) {
    console.error('Load commands error:', e);
  }
}

async function switchConnection(connId) {
  if (connId === _currentConnId) return;
  const conn = _connections.find(c => c.id === connId);
  if (!conn) return;

  // 构建连接参数
  const t = {
    cluster_name: conn.cluster_name,
    namespace: conn.namespace,
    pod_name: conn.pod_name,
    container: conn.container,
    arthas_jar: conn.arthas_jar
  };

  // 显示加载状态
  setConnStatus('dim', `正在切换到 ${conn.cluster_name} / ${conn.namespace} / ${conn.pod_name} ...`);

  try {
    // 调用后端 connect 接口重新建立连接
    const r = await fetch(`${API}/arthas/connect`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({...t, connection_id: connId})
    });
    const d = await r.json();

    if (d.ok) {
      // 保存旧连接的采样任务状态（必须在设置 _currentConnId 之前）
      const oldConnId = _currentConnId;
      const hadRunningTask = _pfTaskId && _pfPollTimer;
      if (oldConnId && hadRunningTask) {
        _pfTasksByConn[oldConnId] = {
          taskId: _pfTaskId,
          pollTimer: null,  // 不保存定时器引用
          startTime: _pfStart,
          duration: _pfDur,
          logLines: _pfLL,
          status: 'running',
          type: _pfTaskInfo.type,
          event: _pfTaskInfo.event
        };
      } else if (oldConnId) {
        // 如果任务已完成或没有运行，清除旧连接的缓存状态
        delete _pfTasksByConn[oldConnId];
      }

      // 现在可以设置新的当前连接
      _currentConnId = connId;
      _connected = true;
      _ap = t;

      // 切换成功后，立即标记为健康状态
      _connHealth[connId] = { alive: true, pod_exists: true, pod_phase: 'Running' };
      // 更新连接对象的状态 + 后端返回的元数据
      conn.status = 'connected';
      conn.local_port = d.local_port;
      if (d.java_pid) conn.java_pid = d.java_pid;
      if (d.arthas_version) conn.arthas_version = d.arthas_version;
      if (d.arthas_address) conn.arthas_address = d.arthas_address;
      if (d.http_url) conn.http_url = d.http_url;
      if (d.mcp_available !== undefined) conn.mcp_available = d.mcp_available;

      // 【关键修复】同步状态到 window
      _syncState();
      renderConnList();
      if (typeof aiRefreshConnSelect === 'function') aiRefreshConnSelect();

      // 清理当前会话状态
      _polling = false;
      if (_pollTimer) { clearTimeout(_pollTimer); _pollTimer = null; }
      _sid = null;
      _cid = null;

      // 停止当前采样轮询
      if (_pfPollTimer) {
        clearInterval(_pfPollTimer);
        _pfPollTimer = null;
      }

      _pfTaskId = null;
      _pfLL = 0;

      // 更新 UI
      renderConnList();
      const _switchVerSuffix = conn.arthas_version ? `  Arthas ${conn.arthas_version}` : '';
      const _switchAddr = conn.arthas_address || conn.http_url || `http://127.0.0.1:${conn.local_port}`;
      setConnStatus('ok', `✓ ${conn.cluster_name} / ${conn.namespace} / ${conn.pod_name}   local port: ${conn.local_port}${conn.java_pid ? `   PID: ${conn.java_pid}` : ''}${_switchVerSuffix}   ${_switchAddr}`);
      setCpSt('ok', `✓ 已连接  (port:${conn.local_port})`);
      // 切换连接时设置 conTitle（含悬浮 tooltip）
      const _switchConTitle = document.getElementById('conTitle');
      if (_switchConTitle) {
        const _switchTipHtml = [
          `<b>集群:</b> ${esc(conn.cluster_name)}`,
          `<b>命名空间:</b> ${esc(conn.namespace)}`,
          `<b>Pod:</b> ${esc(conn.pod_name)}`,
          conn.java_pid ? `<b>Java PID:</b> ${esc(String(conn.java_pid))}` : '',
          `<b>本地端口:</b> ${esc(String(conn.local_port))}`,
          `<b>Arthas 地址:</b> ${esc(_switchAddr)}`,
          conn.arthas_version ? `<b>Arthas 版本:</b> ${esc(conn.arthas_version)}` : '',
          `<b>MCP:</b> ${conn.mcp_available ? '✓ 可用' : '✗ 不可用'}`,
        ].filter(Boolean).join('\n');
        _switchConTitle.innerHTML = `${esc(conn.cluster_name)}/${esc(conn.namespace)}/${esc(conn.pod_name)}<span class="ct-tip">${_switchTipHtml}</span>`;
      }
      // 切换连接时更新 Arthas 版本徽章
      const _verBadgeSwitch = document.getElementById('arthasVerBadge');
      if (_verBadgeSwitch) {
        if (conn.arthas_version) {
          _verBadgeSwitch.textContent = `Arthas v${conn.arthas_version}`;
          _verBadgeSwitch.style.display = '';
        } else {
          _verBadgeSwitch.style.display = 'none';
        }
      }
      document.getElementById('runBtn').disabled = false;

      // 切换连接后自动折叠 Pod 目标区
      const podTarget = document.getElementById('podTarget');
      const ptArrow = document.getElementById('ptCollapseArrow');
      if (podTarget && !podTarget.classList.contains('collapsed')) {
        podTarget.classList.add('collapsed');
        if (ptArrow) ptArrow.classList.add('up');
      }

      // 更新 Pod 目标选择器
      const ptNs = document.getElementById('ptNs');
      const ptPod = document.getElementById('ptPod');
      if (ptNs && ptPod) {
        ptNs.value = conn.namespace;
        ptPod.value = conn.pod_name;
      }

      // 加载该连接的命令历史
      await loadConnectionCommands(connId);

      // 加载该连接的采样日志
      const profilerTab = document.getElementById('tab-profiler');
      if (profilerTab && profilerTab.classList.contains('on')) {
        loadConnectionProfilerLogs(connId);
      }

      // 恢复该连接的采样任务状态（如果有缓存的 task_id）
      const targetTask = _pfTasksByConn[connId];
      const hasCachedTask = targetTask && targetTask.taskId;

      if (hasCachedTask) {
        // 先从后端查询任务真实状态
        try {
          const statusResp = await fetch(`${API}/profile/${targetTask.taskId}`);
          const statusData = await statusResp.json();

          if (statusData.status === 'running') {
            // 任务仍在运行，恢复轮询
            _pfTaskId = targetTask.taskId;
            // 恢复 _pfStart：优先用缓存的 startTime，否则从 created_at 推算
            if (targetTask.startTime) {
              _pfStart = targetTask.startTime;
            } else if (statusData.created_at) {
              _pfStart = new Date(statusData.created_at).getTime();
            } else {
              _pfStart = Date.now();  // 兜底
            }
            _pfDur = targetTask.duration || statusData.duration || 60;
            _pfLL = 0;
            _pfPollingForConn = connId;

            _pfTaskInfo = {
              taskId: targetTask.taskId,
              type: targetTask.type || statusData.type || 'profiler',
              event: targetTask.event || statusData.event || '-',
              duration: _pfDur,
              status: 'running',
              outputFile: statusData.output_file
            };
            updatePfTaskInfo();

            _pfPollTimer = setInterval(pfPoll, 2000);

            const pfProg = document.getElementById('pfProg');
            const pfProgFill = document.getElementById('pfProgFill');
            const pfProgPct = document.getElementById('pfProgPct');
            const pfProgLbl = document.getElementById('pfProgLbl');
            const pfBtn = document.getElementById('pfBtn');
            if (pfProg) pfProg.style.display = 'block';
            if (pfProgFill) pfProgFill.style.width = `${Math.min((Date.now() - _pfStart) / 1000 / _pfDur * 100, 100)}%`;
            if (pfProgPct) pfProgPct.textContent = `${Math.min(Math.floor((Date.now() - _pfStart) / 1000), _pfDur)}s`;
            if (pfProgLbl) pfProgLbl.textContent = `采集中...`;
            if (pfBtn) {
              pfBtn.disabled = true;
              pfBtn.textContent = '⏳ 采集中';
            }

            // 加载该连接的采样日志
            await loadConnectionProfilerLogs(connId);

          } else if (statusData.status === 'completed') {
            // 任务已完成，显示完成状态和下载链接
            delete _pfTasksByConn[connId];
            _pfTaskId = null;
            _pfPollingForConn = null;

            _pfTaskInfo = {
              taskId: targetTask.taskId,
              type: targetTask.type || statusData.type || 'profiler',
              event: targetTask.event || statusData.event || '-',
              duration: statusData.duration || targetTask.duration || '-',
              status: 'completed',
              progress: '100%',
              outputFile: statusData.output_file
            };
            updatePfTaskInfo();

            // 显示进度条完成状态
            const pfProg = document.getElementById('pfProg');
            const pfProgFill = document.getElementById('pfProgFill');
            const pfProgPct = document.getElementById('pfProgPct');
            const pfProgLbl = document.getElementById('pfProgLbl');
            const pfBtn = document.getElementById('pfBtn');
            if (pfProg) pfProg.style.display = 'block';
            if (pfProgFill) pfProgFill.style.width = '100%';
            if (pfProgPct) pfProgPct.textContent = '100%';
            if (pfProgLbl) pfProgLbl.textContent = '已完成';
            if (pfBtn) {
              pfBtn.disabled = false;
              pfBtn.textContent = '▶ 开始';
            }

            // 加载该连接的采样日志和文件列表
            await loadConnectionProfilerLogs(connId);
            loadLocalFiles();

          } else {
            // 任务失败或取消，清理缓存
            delete _pfTasksByConn[connId];
            _pfTaskId = null;
            _pfPollingForConn = null;
            hidePfTaskInfo();

            const pfProg = document.getElementById('pfProg');
            const pfBtn = document.getElementById('pfBtn');
            if (pfProg) pfProg.style.display = 'none';
            if (pfBtn) {
              pfBtn.disabled = false;
              pfBtn.textContent = '▶ 开始';
            }

            // 加载该连接的采样日志
            await loadConnectionProfilerLogs(connId);
          }
        } catch (e) {
          // 查询失败，清理缓存
          console.error('Failed to query task status:', e);
          delete _pfTasksByConn[connId];
          _pfPollingForConn = null;
          hidePfTaskInfo();
          const pfProg = document.getElementById('pfProg');
          const pfBtn = document.getElementById('pfBtn');
          if (pfProg) pfProg.style.display = 'none';
          if (pfBtn) {
            pfBtn.disabled = false;
            pfBtn.textContent = '▶ 开始';
          }
        }
      } else {
        // 没有缓存的任务，重置 UI
        _pfPollingForConn = null;
        hidePfTaskInfo();
        const pfProg = document.getElementById('pfProg');
        const pfProgFill = document.getElementById('pfProgFill');
        const pfProgPct = document.getElementById('pfProgPct');
        const pfProgLbl = document.getElementById('pfProgLbl');
        const pfBtn = document.getElementById('pfBtn');
        const pfLogPanel = document.getElementById('pfl-panel-log');
        const pfLogCnt = document.getElementById('pfLogCnt');
        if (pfProg) pfProg.style.display = 'none';
        if (pfProgFill) pfProgFill.style.width = '0%';
        if (pfProgPct) pfProgPct.textContent = '0%';
        if (pfProgLbl) pfProgLbl.textContent = '启动中...';
        if (pfBtn) {
          pfBtn.disabled = false;
          pfBtn.textContent = '▶ 开始';
        }
        if (pfLogPanel) pfLogPanel.innerHTML = '<div class="o-dim">等待启动...</div>';
        if (pfLogCnt) pfLogCnt.textContent = '0行';
      }

      // 如果当前标签是 Pod 监控，重新加载数据
      const monitorTab = document.getElementById('tab-monitor');
      if (monitorTab && monitorTab.classList.contains('on')) {
        loadSnap();
      }

      // 如果采样工具的历史记录面板是打开的，则刷新
      const historyPanel = document.getElementById('pfl-panel-history');
      if (historyPanel && historyPanel.style.display !== 'none') {
        loadPfHistoryForCurrentConn();
      }

      // 显示切换提示
      const tip = document.createElement('div');
      tip.style.cssText = 'position:fixed;top:60px;right:20px;background:var(--bg1);border:1px solid var(--a);border-radius:6px;padding:12px 16px;font-size:12px;z-index:9999;box-shadow:0 4px 12px rgba(0,0,0,0.3);animation:slideIn 0.3s ease-out';
      tip.innerHTML = `
        <div style="font-weight:600;color:var(--a);margin-bottom:6px">✓ 已切换连接</div>
        <div style="color:var(--tx2);line-height:1.6">
          <div><span style="color:var(--tx3)">集群:</span> ${conn.cluster_name}</div>
          <div><span style="color:var(--tx3)">环境:</span> ${conn.namespace}</div>
          <div><span style="color:var(--tx3)">Pod:</span> ${conn.pod_name}</div>
        </div>
      `;
      document.body.appendChild(tip);

      // 添加动画样式
      if (!document.getElementById('switch-tip-style')) {
        const style = document.createElement('style');
        style.id = 'switch-tip-style';
        style.textContent = `@keyframes slideIn {from{transform:translateX(100px);opacity:0}to{transform:translateX(0);opacity:1}}`;
        document.head.appendChild(style);
      }

      setTimeout(() => {
        tip.style.opacity = '0';
        tip.style.transform = 'translateX(100px)';
        tip.style.transition = 'all 0.3s ease-out';
        setTimeout(() => tip.remove(), 300);
      }, 2500);

      saveConnections();
    } else {
      // 切换失败
      setConnStatus('fail', '✗ 切换失败: ' + d.message);
      toast('切换连接失败: ' + d.message, 'error');
    }
  } catch(e) {
    setConnStatus('fail', '✗ 切换失败: ' + e.message);
    toast('切换连接失败', 'error');
    console.error('Switch connection error:', e);
  }
}

function deleteConnection(connId) {
  if (!confirm('确定删除此连接吗？')) return;
  // 通知后端断开连接，释放资源
  fetch(`${API}/arthas/disconnect`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    credentials: 'same-origin',
    body: JSON.stringify({conn_id: connId})
  }).catch(() => {});  // 忽略错误，可能后端已无此连接
  _connections = _connections.filter(c => c.id !== connId);
  delete _connHealth[connId];
  if (_currentConnId === connId) {
    _currentConnId = null;
    _connected = false;
    _ap = null;
    setConnStatus('', '');
    setPtStat('', '');
    setCpSt('', '');
    document.getElementById('conTitle').innerHTML = '等待连接...';
    const _verBadgeDel = document.getElementById('arthasVerBadge');
    if (_verBadgeDel) _verBadgeDel.style.display = 'none';
    document.getElementById('runBtn').disabled = true;
  }
  _syncState();  // 【关键修复】同步状态到 window
  renderConnList();
  saveConnections();
  if (typeof aiRefreshConnSelect === 'function') aiRefreshConnSelect();
}

// 批量检查所有连接的健康状态
async function checkConnectionsHealth() {
  if (_connections.length === 0) return;
  try {
    const r = await fetch(`${API}/arthas/connections/check`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      credentials: 'same-origin',
      body: JSON.stringify({connections: _connections.map(c => ({
        id: c.id, cluster_name: c.cluster_name, namespace: c.namespace, pod_name: c.pod_name
      }))}),
      signal: AbortSignal.timeout(15000)
    });
    const d = await r.json();
    if (d.results) {
      _connHealth = d.results;
      // 同步健康状态到连接对象的 status 字段
      for (const c of _connections) {
        const h = _connHealth[c.id];
        if (h) {
          c.status = (h.alive && h.pod_exists !== false) ? 'connected' : 'disconnected';
        }
      }
      renderConnList();
      _syncState();  // 【关键修复】同步到 window
      if (typeof aiUpdateConnIndicator === 'function') aiUpdateConnIndicator();
    }
  } catch(e) {
    console.warn('连接健康检查失败:', e);
  }
}

// 一键清理所有失效连接（Pod 不存在 或 集群不可用）
async function cleanupStaleConnections() {
  const staleIds = [];
  for (const c of _connections) {
    const h = _connHealth[c.id];
    if (h && (h.pod_exists === false || h.reason === 'cluster_unavailable')) {
      staleIds.push(c.id);
    }
  }
  if (staleIds.length === 0) {
    toast('没有需要清理的失效连接', 'info');
    return;
  }
  if (!confirm(`发现 ${staleIds.length} 个失效连接（Pod 不存在或集群不可用），是否清理？`)) return;
  staleIds.forEach(id => {
    // 通知后端断开
    fetch(`${API}/arthas/disconnect`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      credentials: 'same-origin',
      body: JSON.stringify({conn_id: id})
    }).catch(() => {});
  });
  _connections = _connections.filter(c => !staleIds.includes(c.id));
  staleIds.forEach(id => delete _connHealth[id]);
  if (staleIds.includes(_currentConnId)) {
    _currentConnId = null;
    _connected = false;
    _ap = null;
    setConnStatus('', '');
    document.getElementById('conTitle').innerHTML = '等待连接...';
    const _verBadgeStale = document.getElementById('arthasVerBadge');
    if (_verBadgeStale) _verBadgeStale.style.display = 'none';
    document.getElementById('runBtn').disabled = true;
  }
  _syncState();  // 【关键修复】同步状态到 window
  renderConnList();
  saveConnections();
  toast(`已清理 ${staleIds.length} 个失效连接`, 'success');
}

function saveConnections() {
  // 按用户隔离连接数据，不同用户看不到彼此的连接
  const user = getCurrentUser();
  const key = user ? `arthas_connections_${user.username}` : 'arthas_connections';
  localStorage.setItem(key, JSON.stringify(_connections));
  // 【关键修复】同步到 window
  _syncState();
}

function loadConnections() {
  try {
    // 按用户隔离：只加载当前用户的连接数据
    const user = getCurrentUser();
    const key = user ? `arthas_connections_${user.username}` : 'arthas_connections';
    const data = localStorage.getItem(key);
    if (data) {
      _connections = JSON.parse(data);
      renderConnList();
    } else {
      _connections = [];
      renderConnList();
    }
    // 【关键修复】同步到 window，供 ai-chat.js / MCP 弹窗等外部模块读取
    _syncState();
  } catch(e) {
    console.error('加载连接失败:', e);
    _connections = [];
    _syncState();
  }
}

function switchTab(n) {
  // 支持数字索引和字符串索引
  // 新 tab 顺序: profiler, console, terminal, monitor, filebrowser, ai, history
  const tabMap = {0:'profiler', 1:'console', 2:'terminal', 3:'monitor', 4:'filebrowser', 5:'ai', 6:'history'};
  const tab = typeof n === 'number' ? tabMap[n] : n;

  ['console','profiler','monitor','filebrowser','terminal','ai','history'].forEach(x => {
    document.getElementById('tab-'+x)?.classList.toggle('on', x===tab);
    document.getElementById('panel-'+x)?.classList.toggle('on', x===tab);
  });

  // Show Arthas JAR path only for Arthas/JProfiler tabs
  const needsArthas = ['console','profiler'].includes(tab);
  const jarWrap = document.getElementById('ptArthasWrap');
  if(jarWrap) jarWrap.style.display = needsArthas ? 'block' : 'none';

  // Adapt connect button: Arthas tabs show "⚡ 连接", others show "🖥️ 终端连接"
  const connBtn = document.getElementById('ptConnBtn');
  if(connBtn) {
    if(tab === 'terminal') {
      connBtn.textContent = '🖥️ 终端连接';
      connBtn.onclick = () => { termInit(); };
    } else {
      // Restore default Arthas connect if not already connected
      if(!_connected) connBtn.textContent = '⚡ 连接';
      connBtn.onclick = () => arthasConnect();
    }
  }

  if(tab==='history') loadHistory();
  // 离开监控 tab 时清理 history 轮询
  if(tab!=='monitor') {
    clearInterval(window._histTimer);
    window._histTimer = null;
  }
  if(tab==='profiler') {
    setTimeout(() => {
      // 不再在这里加载历史，因为顶部历史显示全部，采样工具有自己的历史面板
      // 如果历史面板是打开的，则刷新当前连接的历史
      const historyPanel = document.getElementById('pfl-panel-history');
      if (historyPanel && historyPanel.style.display !== 'none') {
        loadPfHistoryForCurrentConn();
      }
      // 加载当前连接的采样日志
      if (_currentConnId) {
        loadConnectionProfilerLogs(_currentConnId);
      }
    }, 100);
  }
  if(tab==='terminal') { setTimeout(()=>{ document.getElementById('termInput')?.focus(); },100); }
  if(tab==='ai') { setTimeout(()=>{ aiRefreshConnSelect(); document.getElementById('aiInput')?.focus(); },100); }
  if(tab==='monitor') {
    // 切换到监控 tab 时：已有数据直接渲染，否则加载一次快照
    if (_snap && !_snap.error) {
      renderOverview(_snap); renderProcs(_snap); renderNetwork(_snap); renderDisk(_snap); renderEvents(_snap); renderConfig(_snap);
    } else {
      loadSnap();
    }
  }
}

function switchHistTab(name) {
  ['profiler','files'].forEach(n => {
    document.getElementById('hist-'+n)?.classList.toggle('on', n===name);
    const p = document.getElementById('hist-panel-'+n);
    if(p) p.style.display = n===name ? 'block' : 'none';
  });
}



function switchPm(n) {
  const tabs = ['ov','mt','pr','nw','dk','ev','lg','cf'];
  tabs.forEach(x => {
    document.getElementById('pms-'+x)?.classList.toggle('on', x===n);
    const p = document.getElementById('pmp-'+x);
    if(p) { p.style.display = x===n ? 'block' : 'none'; p.classList.toggle('on', x===n); }
  });
  // Fix logs panel flex
  const lg = document.getElementById('pmp-lg');
  if(lg && n==='lg') lg.style.display = 'flex'; // override block
  if(n==='mt' && _snap) renderMetrics(_snap);
  if(n==='dk' && _snap) renderDisk(_snap);
}

// ── Server health ──────────────────────────────────────────────────────────────
async function checkHealth() {
  try {
    const r = await fetch(`${API}/health`, {signal: AbortSignal.timeout(2000)});
    const ok = r.ok;
    document.getElementById('svDot').className = 'dot' + (ok ? ' live' : '');
    document.getElementById('svLbl').textContent = ok ? '服务在线' : '服务离线';
    return ok;
  } catch {
    document.getElementById('svDot').className = 'dot';
    document.getElementById('svLbl').textContent = '服务离线';
    return false;
  }
}

// ── Target helpers ─────────────────────────────────────────────────────────────
function getT() {
  return {
    cluster_name: _ac || '',
    namespace: document.getElementById('ptNs').value || 'default',
    pod_name: document.getElementById('ptPod').value.trim(),
    container: document.getElementById('ptCtr').value,
    arthas_jar: document.getElementById('ptArthas').value,
  };
}

function setPtStat(type, msg) {
  const el = document.getElementById('ptStat');
  el.style.display = msg ? 'block' : 'none';
  el.className = 'pt-stat' + (type ? ' ' + type : '');
  el.textContent = msg;
}

async function loadPods() {
  if(!_ac) { toast('请先选择集群','warn'); return; }
  const ns = document.getElementById('ptNs').value || 'default';
  try {
    const r = await fetch(`${API}/clusters/${encodeURIComponent(_ac)}/pods?namespace=${ns}`);
    const d = await r.json();
    const pods = d.pods || [];
    const sel = document.getElementById('ptPodSel');
    sel.innerHTML = '<option value="">— 选择 Pod —</option>' +
      pods.map(p => `<option value="${p.name}" data-c="${p.containers.join(',')}">${p.name} [${p.phase}]</option>`).join('');
    sel.style.display = 'block';
    toast(`找到 ${pods.length} 个 Pod`);
  } catch(e) { toast('加载失败: ' + e.message, 'error'); }
}

function onPodSel(name) {
  document.getElementById('ptPod').value = name;
  const sel = document.getElementById('ptPodSel');
  const opt = sel.options[sel.selectedIndex];
  const ctrs = (opt?.dataset.c || '').split(',').filter(Boolean);
  const csel = document.getElementById('ptCtr');
  csel.innerHTML = '<option value="">默认容器</option>' + ctrs.map(c => `<option value="${c}">${c}</option>`).join('');
  const lcsel = document.getElementById('logCtr');
  if(lcsel) lcsel.innerHTML = ctrs.map(c => `<option value="${c}">${c}</option>`).join('');
}

async function checkPod() {
  const t = getT();
  if(!t.cluster_name) { toast('请选择集群','warn'); return; }
  if(!t.pod_name) { toast('请填写 Pod 名称','warn'); return; }
  setPtStat('info', '检查中...');
  try {
    const r = await fetch(`${API}/check`, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(t)});
    const d = await r.json();
    if(d.error) setPtStat('fail', `✗ ${d.error}`);
    else if(d.java_processes && d.java_processes.length > 0) {
      // 存储检测结果供后续使用
      window._lastCheckResult = d;
      
      if(d.has_multiple_jvms) {
        // 多个 Java 进程，提示用户选择
        setPtStat('warn', `检测到 ${d.java_processes.length} 个 Java 进程，请选择`);
        showPidSelector(d.java_processes);
      } else {
        setPtStat('ok', `✓ 检测到 Java PID: ${d.java_pid} (${d.java_processes[0].description})`);
        window._selectedJavaPid = d.java_pid;
      }
    }
    else setPtStat('warn', '未检测到 Java 进程');
  } catch(e) { setPtStat('fail', '失败: ' + e.message); }
}

// 显示 PID 选择弹窗
function showPidSelector(processes) {
  // 移除已存在的弹窗
  const existing = document.getElementById('pidSelectorModal');
  if(existing) existing.remove();
  
  const options = processes.map(p => 
    `<option value="${p.pid}">${p.pid} - ${escapeHtml(p.description)}</option>`
  ).join('');
  
  const modal = document.createElement('div');
  modal.id = 'pidSelectorModal';
  modal.innerHTML = `
    <div style="position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.6);z-index:9999;display:flex;align-items:center;justify-content:center;">
      <div style="background:var(--bg2);border-radius:8px;padding:24px;min-width:400px;max-width:600px;box-shadow:0 4px 20px rgba(0,0,0,0.5);">
        <h3 style="margin:0 0 16px 0;color:var(--fg);">选择要连接的 Java 进程</h3>
        <p style="margin:0 0 12px 0;color:var(--muted);font-size:13px;">检测到多个 Java 进程，请选择 Arthas 要附加的目标进程：</p>
        <select id="pidSelect" style="width:100%;padding:10px;border-radius:4px;background:var(--bg);color:var(--fg);border:1px solid var(--border);font-size:14px;">
          ${options}
        </select>
        <div style="margin-top:20px;display:flex;gap:12px;justify-content:flex-end;">
          <button id="pidCancelBtn" style="padding:8px 20px;border-radius:4px;border:1px solid var(--border);background:transparent;color:var(--fg);cursor:pointer;">取消</button>
          <button id="pidConfirmBtn" style="padding:8px 20px;border-radius:4px;border:none;background:var(--accent);color:#fff;cursor:pointer;font-weight:500;">确认</button>
        </div>
      </div>
    </div>
  `;
  document.body.appendChild(modal);
  
  document.getElementById('pidCancelBtn').onclick = () => modal.remove();
  document.getElementById('pidConfirmBtn').onclick = () => {
    const selectedPid = document.getElementById('pidSelect').value;
    const selectedProcess = processes.find(p => p.pid === selectedPid);
    window._selectedJavaPid = selectedPid;
    setPtStat('ok', `✓ 已选择 Java PID: ${selectedPid} (${selectedProcess?.description || ''})`);
    modal.remove();
  };
  
  // 点击背景关闭
  modal.querySelector('div > div').parentElement.onclick = (e) => {
    if(e.target === modal.querySelector('div > div').parentElement) modal.remove();
  };
}

// ── Arthas Connect ─────────────────────────────────────────────────────────────
async function arthasConnect() {
  const t = getT();
  if(!t.cluster_name || !t.pod_name) { toast('请先配置集群和 Pod','warn'); return; }
  
  // 检查是否需要选择 Java PID
  if(window._lastCheckResult && window._lastCheckResult.has_multiple_jvms && !window._selectedJavaPid) {
    showPidSelector(window._lastCheckResult.java_processes);
    return;
  }
  
      // 添加用户选择的 Java PID 到请求参数
      if(window._selectedJavaPid) {
        t.java_pid = window._selectedJavaPid;
      }

      const ptBtn = document.getElementById('ptConnBtn');
      ptBtn.disabled = true; ptBtn.textContent = '连接中...';
      setCpSt('', ''); setConnStatus('dim', `正在连接 ${t.cluster_name} / ${t.namespace} / ${t.pod_name} ...`);
      try {
        const r = await fetch(`${API}/arthas/connect`, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(t)});
        const d = await r.json();
        if(d.ok) {
          // 使用后端返回的 connection_id
          const connId = d.connection_id || d.conn_id;
          const newConn = {
            id: connId,
            cluster_name: t.cluster_name,
            namespace: t.namespace,
            pod_name: t.pod_name,
            container: t.container,
            arthas_jar: t.arthas_jar,
            local_port: d.local_port,
            mcp_available: !!d.mcp_available,
            arthas_version: d.arthas_version || '',
            arthas_address: d.arthas_address || d.http_url || '',
            status: 'connected',
            message: d.message,
            created_at: new Date().toISOString()
          };

          // 检查是否已存在相同的 Pod 连接
          const existingIndex = _connections.findIndex(c =>
            c.cluster_name === t.cluster_name && c.namespace === t.namespace && c.pod_name === t.pod_name
          );

          if (existingIndex >= 0) {
            // 更新现有连接
            _connections[existingIndex] = newConn;
            _currentConnId = newConn.id;
          } else {
            // 添加新连接
            _connections.push(newConn);
            _currentConnId = newConn.id;
          }

          _connected = true;
          _ap = t;
          ptBtn.textContent = '⚡ 连接'; ptBtn.className = 'pt-btn'; ptBtn.disabled = false;

          // 连接成功后，立即标记为健康状态
          _connHealth[connId] = { alive: true, pod_exists: true, pod_phase: 'Running' };

          // 【关键修复】同步状态到 window
          _syncState();
          renderConnList();
          if (typeof aiRefreshConnSelect === 'function') aiRefreshConnSelect();
      setCpSt('ok', `✓ ${d.message}  (port:${d.local_port})`);
      document.getElementById('runBtn').disabled = false;
      const _verSuffix = d.arthas_version ? `  Arthas ${d.arthas_version}` : '';
      const _addrInfo = d.arthas_address || d.http_url || `http://127.0.0.1:${d.local_port}`;
      // conTitle 悬浮 tooltip 展示完整连接信息
      const _conTitleEl = document.getElementById('conTitle');
      if (_conTitleEl) {
        const _tipHtml = [
          `<b>集群:</b> ${esc(t.cluster_name)}`,
          `<b>命名空间:</b> ${esc(t.namespace)}`,
          `<b>Pod:</b> ${esc(t.pod_name)}`,
          d.java_pid ? `<b>Java PID:</b> ${esc(String(d.java_pid))}` : '',
          `<b>本地端口:</b> ${esc(String(d.local_port))}`,
          `<b>Arthas 地址:</b> ${esc(_addrInfo)}`,
          d.arthas_version ? `<b>Arthas 版本:</b> ${esc(d.arthas_version)}` : '',
          `<b>MCP:</b> ${d.mcp_available ? '✓ 可用' : '✗ 不可用'}`,
        ].filter(Boolean).join('\n');
        _conTitleEl.innerHTML = `${esc(t.cluster_name)}/${esc(t.namespace)}/${esc(t.pod_name)}<span class="ct-tip">${_tipHtml}</span>`;
      }
      // 在 conTitle 旁显示 Arthas 版本徽章
      const _verBadge = document.getElementById('arthasVerBadge');
      if (_verBadge) {
        if (d.arthas_version) {
          _verBadge.textContent = `Arthas v${d.arthas_version}`;
          _verBadge.style.display = '';
        } else {
          _verBadge.style.display = 'none';
        }
      }
      setPtStat('ok', d.java_pid ? `Arthas 已连接 (PID: ${d.java_pid})${_verSuffix}` : `Arthas 已连接${_verSuffix}`);
      setConnStatus('ok', `✓ ${t.cluster_name} / ${t.namespace} / ${t.pod_name}   local port: ${d.local_port}${d.java_pid ? `   PID: ${d.java_pid}` : ''}${_verSuffix}   ${_addrInfo}`);
      // 在控制台输出区显示连接信息
      clog(`── Arthas 已连接 ──`, 'dim');
      clog(`PID: ${d.java_pid || '?'}   Port: ${d.local_port}   Address: ${_addrInfo}`, 'dim');
      if (d.arthas_version) clog(`Arthas Version: ${d.arthas_version}`, 'ok');
      saveConnections();
      toast('连接成功', 'success');
      // 连接成功后自动折叠 Pod 目标区，节省侧边栏空间
      const podTarget = document.getElementById('podTarget');
      const ptArrow = document.getElementById('ptCollapseArrow');
      if (podTarget && !podTarget.classList.contains('collapsed')) {
        podTarget.classList.add('collapsed');
        if (ptArrow) ptArrow.classList.add('up');
      }
    } else {
      setCpSt('fail', '✗ ' + d.message); setPtStat('fail', d.message);
      clog('✗ ' + d.message, 'err'); toast('连接失败','error');
      ptBtn.disabled = false; ptBtn.textContent = '⚡ 连接'; ptBtn.className = 'pt-btn';
    }
  } catch(e) {
    clog('✗ ' + e.message, 'err');
    ptBtn.disabled = false; ptBtn.textContent = '⚡ 连接'; ptBtn.className = 'pt-btn';
  }
}

async function arthasDC() {
  _polling = false; if(_pollTimer) { clearTimeout(_pollTimer); _pollTimer = null; }
  if(_sid && _ap) try { await fetch(`${API}/arthas/session/close`, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({..._ap, session_id: _sid})}); } catch {}
  if(_ap) try { await fetch(`${API}/arthas/disconnect`, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(_ap)}); } catch {}
  _connected = false; _ap = null; _sid = null; _cid = null;
  window._selectedJavaPid = null;  // 清除选中的 PID
  const ptBtn = document.getElementById('ptConnBtn');
  ptBtn.disabled = false; ptBtn.textContent = '⚡ 连接'; ptBtn.className = 'pt-btn';
  document.getElementById('runBtn').disabled = true;
  setCpSt('', ''); setPtStat('', ''); setConnStatus('', '');
  document.getElementById('btnStop').style.display = 'none';
  document.getElementById('conTitle').innerHTML = '等待连接...';
  const _verBadgeDisc = document.getElementById('arthasVerBadge');
  if (_verBadgeDisc) _verBadgeDisc.style.display = 'none';
  clog('── 已断开连接 ──', 'dim'); toast('已断开','info');
}

function setConnStatus(type, msg) {
  const el = document.getElementById('connStatus');
  if (!el) return;
  if (!msg) { el.style.display = 'none'; el.textContent = ''; return; }
  el.style.display = 'block';
  el.className = type === 'ok' ? 'conn-status ok' : type === 'dim' ? 'conn-status dim' : 'conn-status';
  el.textContent = msg;
}

function setCpSt(type, msg) {
  const el = document.getElementById('cpSt');
  el.style.display = msg ? 'block' : 'none';
  el.className = 'cp-cst' + (type ? ' ' + type : '');
  el.textContent = msg;
}

// ── Console output ─────────────────────────────────────────────────────────────
const coEl = () => document.getElementById('conOut');

// ── 高性能输出：批量写入 + RAF 滚动，避免每次 DOM 操作触发 reflow ──────────
const _logCls = {line:'o-line',dim:'o-dim',ok:'o-ok',err:'o-err',warn:'o-warn',cmd:'o-cmd'};
let   _logRaf = null;   // requestAnimationFrame handle
let   _logFrag = null;  // pending DocumentFragment

function clog(msg, cls='line') {
  if(!_logFrag) _logFrag = document.createDocumentFragment();
  const d = document.createElement('div');
  d.className = _logCls[cls] || 'o-line';
  d.innerHTML = msg;
  _logFrag.appendChild(d);
  // Flush at most once per animation frame
  if(!_logRaf) {
    _logRaf = requestAnimationFrame(() => {
      const el = coEl();
      if(_logFrag && el) {
        el.appendChild(_logFrag);
        // Only scroll if user is near bottom (within 120px)
        if(el.scrollHeight - el.scrollTop - el.clientHeight < 120) {
          el.scrollTop = el.scrollHeight;
        }
      }
      _logFrag = null;
      _logRaf  = null;
    });
  }
}

function _flushLog() {
  // Force-flush pending log entries immediately (e.g. before clearing)
  if(_logRaf) { cancelAnimationFrame(_logRaf); _logRaf = null; }
  const el = coEl();
  if(_logFrag && el) { el.appendChild(_logFrag); _logFrag = null; }
}

function clearConOut() { _flushLog(); coEl().innerHTML = ''; }
function oSep() {
  const d = document.createElement('div'); d.className = 'o-sep';
  if(!_logFrag) _logFrag = document.createDocumentFragment();
  _logFrag.appendChild(d);
  if(!_logRaf) {
    _logRaf = requestAnimationFrame(() => {
      const el = coEl(); if(_logFrag && el) el.appendChild(_logFrag);
      _logFrag = null; _logRaf = null;
    });
  }
}

// ── Arthas Command Catalogue ───────────────────────────────────────────────────
// 命令数据结构:
//   id       — 唯一标识
//   name     — 实际执行的命令名
//   icon     — 面板图标
//   type     — once(一次性) | stream(持续输出Session) | profiler(采样)
//   desc     — 简短描述（面板列表展示）
//   tip      — 详细说明 + 典型场景（选中命令时展示）
//   example  — 典型用法示例（选中命令时展示）
//   params   — 参数构建器字段
//   doc      — 官方文档链接
// 参考: https://arthas.aliyun.com/en/doc/commands.md
// ─────────────────────────────────────────────────────────────────────────────
const CMDS = [

  { cat: '🖥️ JVM 基础信息', cmds: [
    { id:'dashboard', name:'dashboard', icon:'📊', type:'stream',
      desc:'实时仪表板 — 线程/内存/GC/系统资源一览',
      tip:`每隔5秒刷新，展示线程状态/内存用量/GC频次/CPU负载。\n适用：快速定位 CPU 飙高、内存告警、线程阻塞的第一步。`,
      example:`dashboard\ndashboard -i 2000  # 2s刷新\ndashboard -n 5     # 输出5次退出`,
      doc:`https://arthas.aliyun.com/en/doc/dashboard.html`,
      params:[] },
    { id:'jvm', name:'jvm', icon:'☕', type:'once',
      desc:'JVM 详细信息（版本/编译器/GC/ClassPath）',
      tip:`输出 JVM 运行时信息：JDK版本、JVM参数、GC算法、编译器状态、ClassPath。\n适用：确认生产环境 JVM 配置是否符合预期。`,
      example:`jvm`,
      doc:`https://arthas.aliyun.com/en/doc/jvm.html`,
      params:[] },
    { id:'memory', name:'memory', icon:'🧠', type:'once',
      desc:'内存各区域用量（heap/metaspace/direct...）',
      tip:`详细展示各内存区域的 used/total/max：heap(eden/survivor/old)、non-heap(metaspace)、direct buffer。\n适用：定位内存泄漏区域，判断是堆内还是堆外内存问题。`,
      example:`memory`,
      doc:`https://arthas.aliyun.com/en/doc/memory.html`,
      params:[] },
    { id:'sysprop', name:'sysprop', icon:'📋', type:'once',
      desc:'系统属性 System.getProperties()',
      tip:`读取/设置 Java System.properties。可单独查询某个属性，也可动态修改（如修改日志路径）。\n注意：修改仅影响当前 JVM 实例，重启后失效。`,
      example:`sysprop                    # 列出所有\nsysprop file.encoding      # 查指定属性\nsysprop user.timezone UTC  # 动态修改`,
      doc:`https://arthas.aliyun.com/en/doc/sysprop.html`,
      params:[{k:'key', ph:'属性名（可选，留空=全部）', def:''}] },
    { id:'sysenv', name:'sysenv', icon:'🌍', type:'once',
      desc:'环境变量 System.getenv()',
      tip:`只读，仅查看。适用于确认容器环境变量是否正确注入（K8s ConfigMap/Secret）。`,
      example:`sysenv\nsysenv JAVA_OPTS`,
      doc:`https://arthas.aliyun.com/en/doc/sysenv.html`,
      params:[{k:'key', ph:'变量名（可选，留空=全部）', def:''}] },
    { id:'vmoption', name:'vmoption', icon:'⚙️', type:'once',
      desc:'查看/修改 JVM 运行期参数（如 HeapDumpOnOOM）',
      tip:`查看或动态修改 JVM flag（DiagnosticOptions）。\n常用：开启 OOM 自动 dump、修改 GC 日志。\n注意：并非所有参数支持运行时修改。`,
      example:`vmoption\nvmoption HeapDumpOnOutOfMemoryError\nvmoption HeapDumpOnOutOfMemoryError true`,
      doc:`https://arthas.aliyun.com/en/doc/vmoption.html`,
      params:[{k:'name', ph:'参数名（留空=列出所有）', def:''},{k:'value', ph:'新值（留空=仅查看）', def:''}] },
    { id:'perfcounter', name:'perfcounter', icon:'⚡', type:'once',
      desc:'JVM PerfCounter 计数器（GC次数/编译次数等）',
      tip:`输出 JVM 内部 PerfData 计数器，包含 GC 次数/时间、JIT 编译次数、类加载数量等底层指标。\n适用：metrics-server 不可用时的轻量指标查看。`,
      example:`perfcounter\nperfcounter -d sun.gc`,
      doc:`https://arthas.aliyun.com/en/doc/perfcounter.html`,
      params:[] },
    { id:'version', name:'version', icon:'🏷️', type:'once',
      desc:'Arthas 版本信息',
      tip:`输出当前 Arthas 版本号，用于确认版本兼容性。`,
      example:`version`,
      doc:`https://arthas.aliyun.com/en/doc/version.html`,
      params:[] },
    { id:'session', name:'session', icon:'🔌', type:'once',
      desc:'查看当前 Arthas Session 信息',
      tip:`查看当前 Session 的 sessionId、consumerId、目标 PID 等。`,
      example:`session`,
      doc:`https://arthas.aliyun.com/en/doc/session.html`,
      params:[] },
  ]},

  { cat: '🧵 线程分析', cmds: [
    { id:'thread', name:'thread', icon:'🧵', type:'once',
      desc:'线程列表 + CPU 占用（-n 最忙N个，-b 检测死锁）',
      tip:`输出所有线程或指定线程的状态和 CPU 占用。\n-n N：输出 CPU 最高的前N个线程及堆栈，排查 CPU 飙高的核心命令。\n-b：检测处于 BLOCKED 的线程，定位死锁。\ntid：指定线程ID查看完整调用栈。`,
      example:`thread\nthread -n 3\nthread 12\nthread -b\nthread --state BLOCKED`,
      doc:`https://arthas.aliyun.com/en/doc/thread.html`,
      params:[
        {k:'-n', ph:'最忙前N个线程', def:''},
        {k:'tid', ph:'线程 ID（查看具体堆栈）', def:''},
        {k:'--state', ph:'BLOCKED/WAITING/TIMED_WAITING', def:''},
        {k:'-b', ph:'检测死锁', def:'-b', toggle:true},
      ] },
    { id:'thread_all', name:'thread -all', icon:'📋', type:'once',
      desc:'输出所有线程完整堆栈（等同于 jstack）',
      tip:`输出所有线程的完整调用栈，等价于 jstack。\n也可用「🔥 JProfiler → 💾 Dump → 线程 Dump」一键导出并下载。`,
      example:`thread -all`,
      doc:`https://arthas.aliyun.com/en/doc/thread.html`,
      params:[] },
    { id:'thread_block', name:'thread -b', icon:'🔒', type:'once',
      desc:'专项检测死锁/阻塞线程',
      tip:`查找处于 BLOCKED 状态且持有或等待锁的线程，直接定位死锁根因。\n输出格式：阻塞线程 → 持锁线程 的调用链路。`,
      example:`thread -b`,
      doc:`https://arthas.aliyun.com/en/doc/thread.html`,
      params:[] },
  ]},

  { cat: '🔍 类与类加载器', cmds: [
    { id:'sc', name:'sc', icon:'🔍', type:'once',
      desc:'搜索已加载的类（Search Class）',
      tip:`搜索 JVM 中已加载的类，支持通配符。\n-d 显示类的详细信息（继承关系/ClassLoader/字节码来源JAR）。\n适用：确认某个类是否被加载、排查 ClassNotFound / 类冲突。`,
      example:`sc *UserService*\nsc -d com.example.Demo\nsc -d -f com.example.Demo`,
      doc:`https://arthas.aliyun.com/en/doc/sc.html`,
      params:[
        {k:'pattern', ph:'类名，支持通配符 *Service*', def:'', req:true},
        {k:'-d', ph:'显示类详情', def:'-d', toggle:true},
        {k:'-f', ph:'显示字段信息', def:'', toggle:true},
        {k:'-x', ph:'字段展开层级', def:'2'},
      ] },
    { id:'sm', name:'sm', icon:'🔎', type:'once',
      desc:'搜索类的方法（Search Method）',
      tip:`搜索已加载类中的方法。-d 显示方法签名/返回类型/参数类型/注解。\n适用：watch/trace 之前确认方法名和签名，避免拼写错误导致监控无效。`,
      example:`sm com.example.UserService\nsm com.example.UserService get*\nsm -d com.example.UserService login`,
      doc:`https://arthas.aliyun.com/en/doc/sm.html`,
      params:[
        {k:'class', ph:'类名', def:'', req:true},
        {k:'method', ph:'方法名（支持通配符）', def:''},
        {k:'-d', ph:'显示方法详情', def:'-d', toggle:true},
      ] },
    { id:'classloader', name:'classloader', icon:'📦', type:'once',
      desc:'类加载器统计（层级/数量/加载类数）',
      tip:`列出所有 ClassLoader 的层级关系、已加载类的数量。\n-c hash 可查看指定 ClassLoader 加载的类。\n适用：Spring Boot fat jar、热部署框架的类加载问题排查。`,
      example:`classloader\nclassloader -t\nclassloader -c 3d4eac69`,
      doc:`https://arthas.aliyun.com/en/doc/classloader.html`,
      params:[
        {k:'-t', ph:'树形展示继承关系', def:'-t', toggle:true},
        {k:'-l', ph:'列出所有 ClassLoader', def:'', toggle:true},
        {k:'-c', ph:'指定 ClassLoader hash', def:''},
      ] },
    { id:'jad', name:'jad', icon:'📄', type:'once',
      desc:'反编译类源码（可指定方法）',
      tip:`将运行中字节码反编译为 Java 源码，是确认代码是否正确部署的利器。\n可指定方法名，只反编译某个方法。`,
      example:`jad com.example.UserService\njad com.example.UserService login\njad --source-only com.example.UserService`,
      doc:`https://arthas.aliyun.com/en/doc/jad.html`,
      params:[
        {k:'class', ph:'全限定类名', def:'', req:true},
        {k:'method', ph:'方法名（可选，留空=整个类）', def:''},
      ] },
    { id:'dump', name:'dump', icon:'💾', type:'once',
      desc:'导出类字节码 .class 文件',
      tip:`将 JVM 中运行的类字节码 dump 到本地文件，可用于反编译分析或与源码比对。\n提示：dump 后的 .class 可用「📂 文件下载」标签下载到本地。`,
      example:`dump com.example.UserService\ndump -d /tmp com.example.Demo.*`,
      doc:`https://arthas.aliyun.com/en/doc/dump.html`,
      params:[
        {k:'class', ph:'全限定类名，支持通配符', def:'', req:true},
        {k:'-d', ph:'输出目录', def:'/tmp'},
      ] },
    { id:'mc', name:'mc', icon:'🔨', type:'once',
      desc:'内存编译 .java 为 .class（配合 retransform）',
      tip:`在 JVM 内存中直接编译 .java 文件，无需在 Pod 外安装 JDK。\n热修复工作流：jad 反编译 → 修改源码 → mc 编译 → retransform 热加载。`,
      example:`mc /tmp/UserService.java\nmc -d /tmp /tmp/UserService.java`,
      doc:`https://arthas.aliyun.com/en/doc/mc.html`,
      params:[
        {k:'file', ph:'/tmp/YourClass.java', def:'', req:true},
        {k:'-d', ph:'输出目录', def:'/tmp'},
      ] },
    { id:'retransform', name:'retransform', icon:'♻️', type:'once',
      desc:'热重载 .class 文件（生产热修复首选）',
      tip:`将 .class 文件热加载到 JVM 中，替换正在运行的类实现，无需重启。\n注意：不能新增/删除方法，不能修改字段类型。`,
      example:`retransform /tmp/UserService.class`,
      doc:`https://arthas.aliyun.com/en/doc/retransform.html`,
      params:[{k:'file', ph:'/tmp/YourClass.class', def:'', req:true}] },
    { id:'redefine', name:'redefine', icon:'🔧', type:'once',
      desc:'重新定义类（旧版热修复，推荐用 retransform）',
      tip:`旧版热修复命令，推荐优先使用 retransform（更安全，不能与 retransform 混用）。`,
      example:`redefine /tmp/UserService.class`,
      doc:`https://arthas.aliyun.com/en/doc/redefine.html`,
      params:[{k:'file', ph:'/tmp/YourClass.class', def:'', req:true}] },
  ]},

  { cat: '👁 方法监控与追踪', cmds: [
    { id:'watch', name:'watch', icon:'👁', type:'stream',
      desc:'观察方法调用：入参/返回值/异常（每次调用实时输出）',
      tip:`最常用的诊断命令，每次方法被调用时实时输出入参/返回值/异常。\nOGNL表达式：{params}参数 {returnObj}返回值 {throwExp}异常 params[0]第一个参数\n-b 调用前观察，-e 仅在异常时输出，-x 展开层级（建议2~3）`,
      example:`watch com.example.UserService login "{params,returnObj,throwExp}" -x 2 -n 5\nwatch com.example.OrderService * "{params[0]}" -b\nwatch com.example.Demo * "{params}" -e`,
      doc:`https://arthas.aliyun.com/en/doc/watch.html`,
      params:[
        {k:'class', ph:'类名（全限定或通配符）', def:'', req:true},
        {k:'method', ph:'方法名', def:'', req:true},
        {k:'expr', ph:'OGNL表达式', def:'"{params,returnObj,throwExp}"'},
        {k:'-x', ph:'对象展开层级', def:'2'},
        {k:'-n', ph:'最多观察次数', def:'5'},
        {k:'-b', ph:'方法调用前观察', def:'', toggle:true},
        {k:'-e', ph:'方法异常时观察', def:'', toggle:true},
      ] },
    { id:'trace', name:'trace', icon:'🔬', type:'stream',
      desc:'追踪方法调用树及各节点耗时（找性能瓶颈）',
      tip:`输出方法调用的完整调用树，每个子调用的耗时一目了然，快速定位性能瓶颈。\n--skipJDKMethod false 包含 JDK 内部方法调用。\n注意：对被追踪方法有一定性能影响，建议限制 -n 次数。`,
      example:`trace com.example.UserService login -n 5\ntrace com.example.OrderService processOrder --skipJDKMethod false`,
      doc:`https://arthas.aliyun.com/en/doc/trace.html`,
      params:[
        {k:'class', ph:'类名', def:'', req:true},
        {k:'method', ph:'方法名', def:'', req:true},
        {k:'-n', ph:'追踪次数', def:'5'},
        {k:'--skipJDKMethod', ph:'跳过 JDK 方法', def:'', toggle:true},
      ] },
    { id:'monitor', name:'monitor', icon:'📈', type:'stream',
      desc:'统计方法 QPS/RT/成功率（持续监控，按周期输出）',
      tip:`按统计周期输出方法的调用次数(QPS)/平均耗时(RT)/成功率/失败次数。\n不侵入方法内部，性能影响极低，适合长时间挂载监控。\n适用：接口调用量异常、响应时间波动分析。`,
      example:`monitor com.example.UserService login -c 5\nmonitor com.example.OrderService * -c 10 -n 6`,
      doc:`https://arthas.aliyun.com/en/doc/monitor.html`,
      params:[
        {k:'class', ph:'类名', def:'', req:true},
        {k:'method', ph:'方法名', def:'', req:true},
        {k:'-c', ph:'统计周期（秒）', def:'5'},
        {k:'-n', ph:'统计轮次', def:'10'},
      ] },
    { id:'stack', name:'stack', icon:'📚', type:'stream',
      desc:'打印方法被调用时的调用栈（谁调了我？）',
      tip:`每次目标方法被调用时，打印完整的调用链（从哪里调用的）。\n与 trace 的区别：trace 向下追踪被调方法，stack 向上追踪调用者。\n适用：定位某个方法的触发来源，如接口从哪条链路进来的。`,
      example:`stack com.example.UserService login -n 5\nstack java.lang.Thread sleep`,
      doc:`https://arthas.aliyun.com/en/doc/stack.html`,
      params:[
        {k:'class', ph:'类名', def:'', req:true},
        {k:'method', ph:'方法名', def:'', req:true},
        {k:'-n', ph:'最多打印次数', def:'5'},
      ] },
    { id:'tt', name:'tt', icon:'⏱', type:'stream',
      desc:'时间隧道：记录方法调用历史，可重放/对比入参',
      tip:`记录方法每次调用的入参/返回值/异常/耗时，可事后查看和重放。\n-t 开始记录，-l 列出历史，-i index 查看详情，-p -i index 重放。\n适用：偶发性错误复现、参数对比分析。`,
      example:`tt -t com.example.UserService login -n 10\ntt -l\ntt -i 1000\ntt -p -i 1000`,
      doc:`https://arthas.aliyun.com/en/doc/tt.html`,
      params:[
        {k:'action', ph:'-t class method（记录）/ -l（列表）/ -i N（详情）/ -p -i N（重放）', def:''},
        {k:'class', ph:'类名（-t 时用）', def:''},
        {k:'method', ph:'方法名（-t 时用）', def:''},
        {k:'-n', ph:'最大记录次数', def:'5'},
      ] },
  ]},

  { cat: '🧮 OGNL & 变量操作', cmds: [
    { id:'ognl', name:'ognl', icon:'🧮', type:'once',
      desc:'执行任意 OGNL 表达式（读写静态变量/调用方法）',
      tip:`在运行中的 JVM 执行 OGNL 表达式，可读取/修改静态变量、调用任意方法。\n语法：@Class@field 读取静态字段，@Class@method(args) 调用静态方法。\n-c 指定 ClassLoader hash（多 ClassLoader 环境必须指定）。`,
      example:`ognl "@java.lang.System@currentTimeMillis()"\nognl "@com.example.Config@instance.timeout"\nognl "#conf=@com.example.Config@instance, #conf.timeout=3000"`,
      doc:`https://arthas.aliyun.com/en/doc/ognl.html`,
      params:[
        {k:'expr', ph:'"@java.lang.System@currentTimeMillis()"', def:'', req:true},
        {k:'-x', ph:'结果展开层级', def:'3'},
        {k:'-c', ph:'指定 ClassLoader hash', def:''},
      ] },
    { id:'getstatic', name:'getstatic', icon:'📌', type:'once',
      desc:'获取静态字段值（快捷方式）',
      tip:`getstatic 是 ognl 读取静态字段的快捷命令。\n适用：快速查看单例对象的状态、配置值等。`,
      example:`getstatic com.example.Config timeout\ngetstatic -x 2 com.example.Config instance`,
      doc:`https://arthas.aliyun.com/en/doc/getstatic.html`,
      params:[
        {k:'class', ph:'全限定类名', def:'', req:true},
        {k:'field', ph:'字段名', def:'', req:true},
        {k:'-x', ph:'展开层级', def:'2'},
      ] },
    { id:'vmtool', name:'vmtool', icon:'🛠', type:'once',
      desc:'获取 JVM 堆中对象实例（-a getInstances）',
      tip:`直接从堆内存中获取指定类的所有实例对象，无需 heapdump。还支持强制触发 GC。\n适用：检查单例是否真的单例、查看缓存内容、强制 GC 后观察内存变化。\n注意：对象数量大时可能有性能影响，建议用 -l 限制数量。`,
      example:`vmtool --action getInstances --className com.example.UserService -x 2\nvmtool --action getInstances --className com.example.Cache -l 5 -x 3\nvmtool --action forceGc`,
      doc:`https://arthas.aliyun.com/en/doc/vmtool.html`,
      params:[
        {k:'--action', ph:'getInstances / forceGc', def:'getInstances', req:true},
        {k:'--className', ph:'全限定类名', def:''},
        {k:'-x', ph:'结果展开层级', def:'2'},
        {k:'-l', ph:'最大实例数', def:'10'},
      ] },
    { id:'logger', name:'logger', icon:'📝', type:'once',
      desc:'查看/动态修改 Logger 日志级别（无需重启）',
      tip:`无需重启 JVM，动态修改 Logback/Log4j 的日志级别。\n生产排查时临时开启 DEBUG 日志，排查完后改回 INFO，不影响服务运行。`,
      example:`logger\nlogger --name ROOT\nlogger --name com.example --level DEBUG\nlogger --name com.example --level INFO`,
      doc:`https://arthas.aliyun.com/en/doc/logger.html`,
      params:[
        {k:'--name', ph:'Logger 名称（如 com.example）', def:''},
        {k:'--level', ph:'新日志级别：DEBUG/INFO/WARN/ERROR', def:''},
      ] },
  ]},

  { cat: '🔥 性能分析', cmds: [
    { id:'p_start', name:'profiler start', icon:'▶️', type:'profiler',
      desc:'async-profiler: 开始采样（支持 cpu/alloc/lock/wall）',
      tip:`async-profiler 低开销采样，所有 JDK 版本可用。\n推荐使用右侧「🔥 JProfiler」面板操作，支持可视化配置和一键下载。\n直接命令适合在 Arthas 终端快速操作。`,
      example:`profiler start\nprofiler start --event alloc\nprofiler start --event lock`,
      doc:`https://arthas.aliyun.com/en/doc/profiler.html`,
      params:[{k:'--event', ph:'事件：cpu/alloc/lock/wall/itimer', def:'cpu'}] },
    { id:'p_status', name:'profiler status', icon:'📊', type:'once',
      desc:'查看当前 async-profiler 采样状态',
      tip:`查看当前采样事件类型和已运行时长。`,
      example:`profiler status`,
      doc:`https://arthas.aliyun.com/en/doc/profiler.html`,
      params:[] },
    { id:'p_getSamples', name:'profiler getSamples', icon:'🔢', type:'once',
      desc:'获取已采集的样本数量',
      tip:`查看当前已采集的样本数，判断采样是否正常进行。`,
      example:`profiler getSamples`,
      doc:`https://arthas.aliyun.com/en/doc/profiler.html`,
      params:[] },
    { id:'p_list', name:'profiler list', icon:'📋', type:'once',
      desc:'列出当前平台支持的所有采样事件',
      tip:`不同 OS/内核版本支持的事件不同，先用此命令确认可用事件。`,
      example:`profiler list`,
      doc:`https://arthas.aliyun.com/en/doc/profiler.html`,
      params:[] },
    { id:'p_stop_html', name:'profiler stop', icon:'⏹', type:'profiler',
      desc:'停止采样 → 生成 HTML 火焰图',
      tip:`停止采样并生成报告文件。推荐使用「🔥 JProfiler」面板操作，支持自动下载。`,
      example:`profiler stop\nprofiler stop --format html --file /tmp/profiler.html\nprofiler stop --format jfr  --file /tmp/profiler.jfr`,
      doc:`https://arthas.aliyun.com/en/doc/profiler.html`,
      params:[
        {k:'--format', ph:'html/jfr/collapsed/md', def:'html'},
        {k:'--file', ph:'输出路径', def:'/tmp/profiler.html'},
      ] },
    { id:'jfr_start', name:'jfr start', icon:'📊', type:'once',
      desc:'JDK JFR 录制启动（需 JDK 8u262+ 或 JDK 11+）',
      tip:`JDK 原生 Flight Recorder，需要 JDK 8u262+ 或 JDK 11+。推荐使用右侧「🔥 JProfiler → 📊 JDK JFR」面板操作。\n-d 指定录制时长后自动停止，-s 选择录制配置。`,
      example:`jfr start -n myRec -s default -d 60s -f /tmp/my.jfr\njfr status -n myRec\njfr stop -n myRec`,
      doc:`https://arthas.aliyun.com/en/doc/jfr.html`,
      params:[
        {k:'-n', ph:'录制名称', def:'arthas-jfr'},
        {k:'-s', ph:'配置: default / profile', def:'default'},
        {k:'-d', ph:'录制时长，如 60s', def:'60s'},
        {k:'-f', ph:'输出文件路径', def:'/tmp/arthas.jfr'},
      ] },
    { id:'jfr_status', name:'jfr status', icon:'ℹ️', type:'once',
      desc:'查看 JFR 录制状态',
      tip:`查看指定录制任务的状态（running/stopped）。`,
      example:`jfr status -n arthas-jfr`,
      doc:`https://arthas.aliyun.com/en/doc/jfr.html`,
      params:[{k:'-n', ph:'录制名称', def:'arthas-jfr'}] },
    { id:'jfr_stop', name:'jfr stop', icon:'⏹', type:'once',
      desc:'停止 JFR 录制（文件自动保存）',
      tip:`停止录制，文件写入启动时指定的路径。`,
      example:`jfr stop -n arthas-jfr`,
      doc:`https://arthas.aliyun.com/en/doc/jfr.html`,
      params:[
        {k:'-n', ph:'录制名称', def:'arthas-jfr'},
        {k:'-f', ph:'另存路径（可选）', def:''},
      ] },
    { id:'jfr_dump', name:'jfr dump', icon:'💾', type:'once',
      desc:'导出 JFR 录制（录制继续运行）',
      tip:`在录制运行期间导出当前数据，录制本身不停止。`,
      example:`jfr dump -n arthas-jfr -f /tmp/dump.jfr`,
      doc:`https://arthas.aliyun.com/en/doc/jfr.html`,
      params:[
        {k:'-n', ph:'录制名称', def:'arthas-jfr'},
        {k:'-f', ph:'输出文件路径', def:'/tmp/dump.jfr'},
      ] },
    { id:'heapdump', name:'heapdump', icon:'🗂', type:'once',
      desc:'导出 Heap Dump（OOM/内存泄漏分析，会触发 STW）',
      tip:`导出堆内存快照，用于 MAT/JVisualVM 分析。\n--live 只导出存活对象，可大幅减小文件体积。\n警告：会触发 Full GC 并暂停 JVM（STW），大堆可能需要数分钟，生产环境慎用。\n推荐使用右侧「💾 Dump」面板操作，支持自动下载。`,
      example:`heapdump /tmp/heap.hprof\nheapdump --live /tmp/heap-live.hprof`,
      doc:`https://arthas.aliyun.com/en/doc/heapdump.html`,
      params:[
        {k:'file', ph:'输出路径', def:'/tmp/heap.hprof'},
        {k:'--live', ph:'仅 live 对象（减小文件体积）', def:'--live', toggle:true},
      ] },
  ]},

  { cat: '🔧 工具命令', cmds: [
    { id:'mbean', name:'mbean', icon:'🔧', type:'once',
      desc:'查看/订阅 JMX MBean 属性（线程池/连接池等）',
      tip:`通过 JMX 查看或订阅 MBean 属性，适合监控连接池/线程池/GC 等标准 JMX 指标。\n-i ms 按毫秒间隔持续输出。\n常用：java.lang:type=Memory  java.lang:type=Threading  Catalina:type=ThreadPool`,
      example:`mbean java.lang:type=Memory\nmbean java.lang:type=Threading\nmbean -i 1000 java.lang:type=GarbageCollector,*`,
      doc:`https://arthas.aliyun.com/en/doc/mbean.html`,
      params:[
        {k:'mbean-pattern', ph:'java.lang:type=Memory', def:'java.lang:type=Memory'},
        {k:'attribute-pattern', ph:'属性名（留空=全部）', def:''},
        {k:'-i', ph:'订阅间隔 ms（持续监控）', def:''},
      ] },
    { id:'options', name:'options', icon:'⚙️', type:'once',
      desc:'查看/修改 Arthas 全局开关（如 save-result）',
      tip:`查看或修改 Arthas 全局配置开关，如是否保存命令结果到文件。`,
      example:`options\noptions save-result true`,
      doc:`https://arthas.aliyun.com/en/doc/options.html`,
      params:[
        {k:'name', ph:'选项名（留空=列出全部）', def:''},
        {k:'value', ph:'新值（留空=仅查看）', def:''},
      ] },
    { id:'echo', name:'echo', icon:'📢', type:'once',
      desc:'打印文本（调试脚本用）',
      tip:`在控制台打印字符串，用于批量脚本中添加分隔符/注释。`,
      example:`echo hello arthas`,
      doc:`https://arthas.aliyun.com/en/doc/echo.html`,
      params:[{k:'text', ph:'要打印的内容', def:'hello arthas', req:true}] },
    { id:'cat', name:'cat', icon:'📖', type:'once',
      desc:'打印文件内容（如配置文件）',
      tip:`在 Arthas 会话中读取 Pod 内文件内容，也可用「📂 文件下载」标签浏览下载。`,
      example:`cat /proc/version\ncat /app/config/application.yml`,
      doc:`https://arthas.aliyun.com/en/doc/cat.html`,
      params:[{k:'file', ph:'文件路径', def:'', req:true}] },
    { id:'pwd', name:'pwd', icon:'📂', type:'once',
      desc:'打印 Arthas 当前工作目录',
      tip:`输出 Arthas 进程的当前工作目录（通常是 JVM 启动目录）。`,
      example:`pwd`,
      doc:`https://arthas.aliyun.com/en/doc/pwd.html`,
      params:[] },
    { id:'history', name:'history', icon:'🕐', type:'once',
      desc:'打印命令执行历史',
      tip:`输出最近执行的命令历史，方便回顾和重复执行。`,
      example:`history\nhistory 20`,
      doc:`https://arthas.aliyun.com/en/doc/history.html`,
      params:[{k:'n', ph:'最近 N 条', def:'20'}] },
  ]},
];

// 记录各分组折叠状态（默认全展开）
const _catCollapsed = {};

function renderCmdPal(filter='') {
  const el = document.getElementById('cmdPal');
  const fl = filter.toLowerCase();
  let html = '';
  for(let gi = 0; gi < CMDS.length; gi++) {
    const cat  = CMDS[gi];
    const gid  = `cg${gi}`;
    const cmds = fl
      ? cat.cmds.filter(c => c.name.includes(fl) || c.desc.toLowerCase().includes(fl))
      : cat.cmds;
    if(!cmds.length) continue;
    const collapsed = !fl && _catCollapsed[gid];  // 搜索时强制展开
    const arrow = collapsed ? '▶' : '▼';
    html += `<div class="cp-cat-hd" data-gid="${gid}" onclick="toggleCmdCat('${gid}')">
      <span class="cp-cat-arrow">${arrow}</span>${cat.cat}
      <span class="cp-cat-cnt">${cmds.length}</span>
    </div>`;
    if(!collapsed) {
      html += `<div class="cp-cat-body" id="${gid}">`;
      for(const cmd of cmds) {
        const bt = cmd.type==='stream'?'badge-stream':cmd.type==='profiler'?'badge-prof':'badge-once';
        const bl = cmd.type==='stream'?'持续':cmd.type==='profiler'?'prof':'once';
        html += `<div class="cp-cmd" data-id="${cmd.id}" onclick="selCmd('${cmd.id}')">
          <span class="cp-ci">${cmd.icon}</span>
          <div><div class="cp-cn">${esc(cmd.name)}<span class="cp-badge ${bt}">${bl}</span></div>
          <div class="cp-cd">${esc(cmd.desc)}</div></div>
        </div>`;
      }
      html += `</div>`;
    }
  }
  el.innerHTML = html || '<div style="color:var(--tx3);padding:10px;font-size:11px">无匹配命令</div>';
}

function toggleCmdCat(gid) {
  _catCollapsed[gid] = !_catCollapsed[gid];
  // Toggle DOM directly — no full rebuild needed
  const body = document.getElementById(gid);
  const hdr  = document.querySelector(`[data-gid="${gid}"]`);
  if(body) body.style.display = _catCollapsed[gid] ? 'none' : 'block';
  if(hdr) {
    const arrow = hdr.querySelector('.cp-cat-arrow');
    if(arrow) arrow.textContent = _catCollapsed[gid] ? '▶' : '▼';
  }
}

let _filterTimer = null;
function filterCmds(v) {
  clearTimeout(_filterTimer);
  _filterTimer = setTimeout(() => renderCmdPal(v), 150);
}
function findCmd(id) { for(const c of CMDS) { const f=c.cmds.find(x=>x.id===id); if(f) return f; } return null; }

function selCmd(id) {
  document.querySelectorAll('.cp-cmd').forEach(e => e.classList.toggle('active', e.dataset.id===id));
  _selCmd = findCmd(id); if(!_selCmd) return;
  const bldr = document.getElementById('cmdBldr');

  // Build tip/example section
  let infoHtml = '';
  if(_selCmd.tip || _selCmd.example) {
    infoHtml = `<div class="bldr-tip">`;
    if(_selCmd.tip) {
      infoHtml += `<div class="bldr-tip-text">${esc(_selCmd.tip).replace(/\\n/g,'<br>')}</div>`;
    }
    if(_selCmd.example) {
      infoHtml += `<div class="bldr-tip-ex"><span class="bldr-tip-exlbl">示例</span><pre class="bldr-tip-code">${esc(_selCmd.example)}</pre></div>`;
    }
    if(_selCmd.doc) {
      infoHtml += `<a class="bldr-tip-doc" href="${esc(_selCmd.doc)}" target="_blank">📖 官方文档 ↗</a>`;
    }
    infoHtml += `</div>`;
  }

  if(_selCmd.params && _selCmd.params.length) {
    bldr.style.display = 'block';
    document.getElementById('bldrLbl').textContent = `${_selCmd.icon} ${_selCmd.name}`;
    document.getElementById('bldrFlds').innerHTML =
      infoHtml +
      _selCmd.params.map((p,i) => `<div class="bldr-f"><label>${esc(p.k)}${p.req?' *':''}</label>
        ${p.toggle
          ? `<select id="bf${i}"><option value="">${p.k} 关</option><option value="${esc(p.def)}" selected>${p.k} 开</option></select>`
          : `<input id="bf${i}" type="text" value="${esc(p.def||'')}" placeholder="${esc(p.ph||'')}">`
        }</div>`).join('') +
      `<button class="bldr-send" onclick="buildAndRun()">▶ 执行</button>`;
  } else {
    bldr.style.display = infoHtml ? 'block' : 'none';
    if(infoHtml) {
      document.getElementById('bldrLbl').textContent = `${_selCmd.icon} ${_selCmd.name}`;
      document.getElementById('bldrFlds').innerHTML = infoHtml +
        `<button class="bldr-send" onclick="buildAndRun()">▶ 执行</button>`;
    }
    document.getElementById('cmdTa').value = _selCmd.name;
    autoResize(document.getElementById('cmdTa'));
  }
}

function buildAndRun() {
  if(!_selCmd) return;
  let parts = [_selCmd.name];
  _selCmd.params.forEach((p,i) => {
    const v = (document.getElementById(`bf${i}`)?.value||'').trim();
    if(!v) return;
    if(p.toggle) { parts.push(v); return; }
    const pos = ['class','method','pattern','expr','mbean','file','key','action'];
    if(pos.includes(p.k)) parts.push(v); else parts.push(`${p.k} ${v}`);
  });
  document.getElementById('cmdTa').value = parts.join(' ');
  autoResize(document.getElementById('cmdTa'));
  runCmd();
}

function handleKey(e) {
  if(e.key==='Enter' && !e.shiftKey) { e.preventDefault(); runCmd(); return; }
  if(e.key==='ArrowUp') { e.preventDefault(); navHist(-1); }
  if(e.key==='ArrowDown') { e.preventDefault(); navHist(1); }
}
function navHist(d) {
  _histIdx = Math.max(-1, Math.min(_cmdHist.length-1, _histIdx+d));
  const ta = document.getElementById('cmdTa');
  ta.value = _histIdx>=0 ? _cmdHist[_cmdHist.length-1-_histIdx] : '';
  autoResize(ta);
}
let _resizeTimer = null;
function autoResize(ta) {
  // Debounce: only measure scrollHeight after typing pauses
  clearTimeout(_resizeTimer);
  _resizeTimer = setTimeout(() => {
    ta.style.height = 'auto';
    ta.style.height = Math.min(ta.scrollHeight, 96) + 'px';
  }, 50);
}

async function runCmd() {
  if(!_connected) { toast('请先连接 Arthas','warn'); return; }
  const ta = document.getElementById('cmdTa'); const command = ta.value.trim(); if(!command) return;
  ta.value=''; autoResize(ta); _cmdHist.push(command); _histIdx=-1;
  oSep(); clog(esc(command), 'cmd');
  // TODO: Re-enable streaming commands for dashboard/watch/trace/monitor/stack/tt - issue #XXX
  // 暂时全部使用 runOnce，流式功能后续实现
  await runOnce(command);
}

async function runOnce(command) {
  document.getElementById('runBtn').disabled = true;
  try {
    const r = await fetch(`${API}/arthas/exec`, {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({..._ap, command, connection_id: _currentConnId, timeout_ms: 60000})});
    const d = await r.json();
    if(!d.state && d.error) { clog('✗ ' + esc(d.error), 'err'); }
    else { renderRes(d); }
  } catch(e) { clog('✗ ' + esc(e.message), 'err'); }
  document.getElementById('runBtn').disabled = false;
}

async function runStream(command) {
  document.getElementById('runBtn').disabled = true;
  document.getElementById('btnStop').style.display = 'inline-flex';
  if(!_sid) {
    try {
      const r = await fetch(`${API}/arthas/session/create`, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(_ap)});
      const d = await r.json();
      if(d.state !== 'SUCCEEDED') { clog('✗ Session 创建失败: ' + esc(JSON.stringify(d)), 'err'); stopPoll(); return; }
      _sid = d.sessionId; _cid = d.consumerId;
      clog(`Session: ${d.sessionId}`, 'dim');
    } catch(e) { clog('✗ ' + esc(e.message), 'err'); stopPoll(); return; }
  }
  try {
    const r = await fetch(`${API}/arthas/session/exec`, {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({..._ap, command, session_id: _sid})});
    const d = await r.json();
    if(d.state === 'FAILED') { clog('✗ ' + esc(d.message), 'err'); stopPoll(); return; }
  } catch(e) { clog('✗ ' + esc(e.message), 'err'); stopPoll(); return; }
  _polling = true; let empty = 0;
  const poll = async () => {
    if(!_polling) return;
    try {
      const r = await fetch(`${API}/arthas/session/pull`, {method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({..._ap, session_id: _sid, consumer_id: _cid})});
      const d = await r.json(); let has = false;
      for(const res of d.body?.results||[]) {
        if(['input_status','welcome','message'].includes(res.type)) continue;
        renderRes({state:'SUCCEEDED', body:{results:[res]}}); has = true;
      }
      if(!has) empty++;
      if(empty < 60 && _polling) _pollTimer = setTimeout(poll, 1500); else stopPoll();
    } catch { stopPoll(); }
  };
  _pollTimer = setTimeout(poll, 1000);
}

function stopPoll() {
  _polling = false; if(_pollTimer) { clearTimeout(_pollTimer); _pollTimer = null; }
  document.getElementById('runBtn').disabled = false;
  document.getElementById('btnStop').style.display = 'none';
}

async function interruptCmd() {
  _polling = false; if(_pollTimer) { clearTimeout(_pollTimer); _pollTimer = null; }
  if(_sid && _ap) try {
    await fetch(`${API}/arthas/session/interrupt`, {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({..._ap, session_id: _sid})});
  } catch {}
  stopPoll(); clog('── 命令已中断 ──', 'dim');
}

// ── Arthas result rendering ────────────────────────────────────────────────────
// ─────────────────────────────────────────────────────────────────────────────
// Arthas 命令结果渲染器
// 每种 result type 对应官方文档的字段结构，渲染为可读的 HTML
// ─────────────────────────────────────────────────────────────────────────────

/** 通用工具 */
const R = {
  // key-value 行
  kv: (k, v, vCls='') =>
    `<div class="r-kv"><span class="r-k">${esc(k)}</span><span class="r-v ${vCls}">${v}</span></div>`,
  // 表格
  table: (cols, rows) => {
    const ths = cols.map(c => `<th>${esc(c)}</th>`).join('');
    const trs = rows.map(row =>
      `<tr>${row.map(c => `<td>${c}</td>`).join('')}</tr>`
    ).join('');
    return `<table class="r-tbl"><thead><tr>${ths}</tr></thead><tbody>${trs}</tbody></table>`;
  },
  // 代码块
  code: (text, lang='java') =>
    `<pre class="o-code r-code">${esc(String(text||''))}</pre>`,
  // 标签
  badge: (txt, color='#4ade80') =>
    `<span style="background:${color}22;color:${color};border:1px solid ${color}44;border-radius:3px;padding:1px 6px;font-size:10px;font-weight:600">${esc(String(txt))}</span>`,
  // 状态颜色
  stateColor: s => ({
    RUNNABLE:'#4ade80', BLOCKED:'#f87171', WAITING:'#fb923c',
    TIMED_WAITING:'#fbbf24', NEW:'#94a3b8', TERMINATED:'#94a3b8'
  }[s] || '#94a3b8'),
  // 用量 bar
  bar: (used, total, max) => {
    const pct = total > 0 ? Math.round(used/total*100) : 0;
    const color = pct > 90 ? '#f87171' : pct > 75 ? '#fb923c' : '#4ade80';
    const usedStr = R.fmtBytes(used), totalStr = R.fmtBytes(total);
    return `<div class="r-bar-wrap">
      <div class="r-bar" style="width:${pct}%;background:${color}"></div>
      <span class="r-bar-lbl">${usedStr} / ${totalStr} (${pct}%)</span>
    </div>`;
  },
  fmtBytes: b => {
    if(!b || b < 0) return '—';
    if(b < 1024) return b + 'B';
    if(b < 1048576) return (b/1024).toFixed(1) + 'K';
    if(b < 1073741824) return (b/1048576).toFixed(1) + 'M';
    return (b/1073741824).toFixed(2) + 'G';
  },
  fmtMs: ms => ms > 1000 ? (ms/1000).toFixed(2)+'s' : ms+'ms',
  // 折叠块
  collapsible: (header, body, open=false) => {
    const id = 'rc_' + Math.random().toString(36).slice(2);
    return `<div class="r-coll ${open?'open':''}">
      <div class="r-coll-h" onclick="document.getElementById('${id}').classList.toggle('open')">
        <span class="r-coll-arr">▶</span>${header}</div>
      <div class="r-coll-b" id="${id}">${body}</div>
    </div>`;
  },
};

/** 各命令专属渲染函数 */
const RENDERERS = {

  // ── dashboard ────────────────────────────────────────────────────────────
  dashboard(r) {
    let html = '';
    // Threads table
    const threads = r.threads || r.busyThreads || [];
    if(threads.length) {
      const rows = threads.map(t => [
        `<span style="color:#c0caf5">${esc(t.name||'')}</span>`,
        `<span style="color:${R.stateColor(t.state)}">${esc(t.state||'')}</span>`,
        t.cpu != null ? `<span style="color:#4ade80">${t.cpu}%</span>` : '—',
        t.deltaTime != null ? `${t.deltaTime}ms` : '—',
        `<span style="color:#565f89">${t.id||''}</span>`,
        t.daemon ? '<span style="color:#565f89">D</span>' : '',
      ]);
      html += `<div class="r-sec-lbl">🧵 Threads</div>`;
      html += R.table(['Name','State','CPU%','ΔTime','Id','D'], rows);
    }
    // Memory
    const mem = r.memoryInfo || r.memory || {};
    if(Object.keys(mem).length) {
      html += `<div class="r-sec-lbl" style="margin-top:10px">🧠 Memory</div>`;
      for(const [zone, info] of Object.entries(mem)) {
        if(!info || typeof info !== 'object') continue;
        const used = info.used ?? info.usedBytes ?? 0;
        const total= info.total ?? info.totalBytes ?? info.committed ?? 0;
        const max  = info.max ?? info.maxBytes ?? 0;
        html += `<div style="margin:3px 0">${R.kv(zone, R.bar(used,total,max), '')}`;
        html += `</div>`;
      }
    }
    // Runtime info
    const rt = r.runtimeInfo || {};
    if(Object.keys(rt).length) {
      const rows = Object.entries(rt).map(([k,v]) => [
        `<span style="color:#7aa2f7">${esc(k)}</span>`,
        `<span style="color:#a9b1d6">${esc(String(v??''))}</span>`
      ]);
      html += `<div class="r-sec-lbl" style="margin-top:10px">⚙️ Runtime</div>`;
      html += R.table(['Key','Value'], rows);
    }
    return html || RENDERERS._fallback(r);
  },

  // ── thread ────────────────────────────────────────────────────────────────
  thread(r) {
    const threads = r.busyThreads || r.threads || [];
    if(!threads.length) return RENDERERS._fallback(r);
    let html = `<div class="r-sec-lbl">🧵 Threads (${threads.length})</div>`;
    for(const t of threads) {
      const sc = t.state==='BLOCKED'?'#f87171':t.state==='RUNNABLE'?'#4ade80':t.state==='WAITING'||t.state==='TIMED_WAITING'?'#fb923c':'#94a3b8';
      const cpu_s = t.cpu != null ? ` <span style="color:#4ade80;font-size:10px">cpu=${t.cpu}%</span>` : '';
      const dt_s  = t.deltaTime != null && t.deltaTime > 0 ? ` <span style="color:#fb923c;font-size:10px">+${t.deltaTime}ms</span>` : '';
      const head  = `<span style="color:#c0caf5;font-weight:600">${esc(t.name||'')}</span>
        <span style="color:#565f89;font-size:11px"> Id=${t.id}</span>${cpu_s}${dt_s}
        <span style="color:${sc};font-size:10px;margin-left:6px">${esc(t.state||'')}</span>`;
      const frames = (t.stackTrace||[]).map(f => {
        const loc = f.lineNumber===-2 ? 'Native Method' : (f.fileName ? `${f.fileName}:${f.lineNumber}` : 'Unknown');
        const parts = (f.className||'').split('.');
        const cls = parts.pop(); const pkg = parts.join('.');
        return `<div style="font-size:12px;color:#565f89;padding:1px 0">
          <span style="color:#3b4261">${esc(pkg?pkg+'.':'')}</span><span style="color:#7dcfff">${esc(cls)}</span>.<span style="color:#73daca">${esc(f.methodName||'')}</span>(<span style="color:#e0af68">${esc(loc)}</span>)
        </div>`;
      }).join('');
      const lock = t.lockName ? `<div style="color:#f7768e;font-size:11px">⏸ waiting on ${esc(t.lockName)}</div>` : '';
      html += R.collapsible(head, lock + frames, t.state==='BLOCKED');
    }
    return html;
  },

  // ── jvm ───────────────────────────────────────────────────────────────────
  jvm(r) {
    // result is the whole r object — each key is a JVM category
    const skip = new Set(['type','jobId','statusCode']);
    let html = '';
    for(const [cat, entries] of Object.entries(r)) {
      if(skip.has(cat) || !entries) continue;
      let body = '';

      // 格式化值，处理嵌套对象
      const formatValue = (v) => {
        if (v === null || v === undefined) return '';
        if (typeof v === 'string') return v;
        if (typeof v === 'number' || typeof v === 'boolean') return String(v);
        if (typeof v === 'object') {
          return JSON.stringify(v, null, 2);
        }
        return String(v);
      };

      if(Array.isArray(entries)) {
        body = R.table(['Name','Value'], entries.map(e => [
          `<span style="color:#7aa2f7">${esc(e.name||e.key||'')}</span>`,
          `<span style="color:#a9b1d6;white-space:pre-wrap;font-family:monospace;font-size:11px">${esc(formatValue(e.value??e.val??''))}</span>`
        ]));
      } else if(typeof entries === 'object') {
        body = R.table(['Key','Value'], Object.entries(entries).map(([k,v]) => [
          `<span style="color:#7aa2f7">${esc(k)}</span>`,
          `<span style="color:#a9b1d6;white-space:pre-wrap;font-family:monospace;font-size:11px">${esc(formatValue(v))}</span>`
        ]));
      } else {
        body = `<span style="color:#a9b1d6">${esc(String(entries))}</span>`;
      }
      html += R.collapsible(`<span style="color:#c0caf5;font-weight:600">${esc(cat)}</span>`, body, true);
    }
    return html || RENDERERS._fallback(r);
  },

  // ── memory ────────────────────────────────────────────────────────────────
  memory(r) {
    const zones = r.heap || r.heapMemory || [];
    const nonheap = r.nonHeap || r.nonheap || [];
    const buffers = r.buffer || r.bufferPool || [];
    let html = '';
    const renderZones = (label, arr) => {
      if(!arr || !arr.length) return '';
      let s = `<div class="r-sec-lbl">${label}</div>`;
      for(const z of arr) {
        const used = z.used ?? z.usedBytes ?? 0;
        const total= z.total ?? z.totalBytes ?? z.committed ?? 0;
        const max  = z.max ?? z.maxBytes ?? 0;
        s += `<div style="margin:4px 0">
          <span style="color:#7aa2f7;font-size:11px">${esc(z.name||z.type||'')}</span>
          ${R.bar(used, total, max)}
        </div>`;
      }
      return s;
    };
    html += renderZones('Heap', zones);
    html += renderZones('Non-Heap', nonheap);
    html += renderZones('Buffer', buffers);
    return html || RENDERERS._fallback(r);
  },

  // ── sysprop / sysenv ──────────────────────────────────────────────────────
  sysprop(r) {
    const props = r.props || r.sysprops || r;
    const skip = new Set(['type','jobId','statusCode']);
    const entries = Object.entries(props).filter(([k]) => !skip.has(k));
    if(!entries.length) return RENDERERS._fallback(r);
    const rows = entries.map(([k,v]) => [
      `<span style="color:#7aa2f7">${esc(k)}</span>`,
      `<span style="color:#a9b1d6;word-break:break-all">${esc(String(v??''))}</span>`
    ]);
    return R.table(['Property','Value'], rows);
  },
  sysenv(r) {
    const env = r.env || r;
    const skip = new Set(['type','jobId','statusCode']);
    const entries = Object.entries(env).filter(([k]) => !skip.has(k));
    if(!entries.length) return RENDERERS._fallback(r);
    const rows = entries.map(([k,v]) => [
      `<span style="color:#7aa2f7">${esc(k)}</span>`,
      `<span style="color:#a9b1d6;word-break:break-all">${esc(String(v??''))}</span>`
    ]);
    return R.table(['Variable','Value'], rows);
  },

  // ── vmoption ──────────────────────────────────────────────────────────────
  vmoption(r) {
    const opts = r.vmOptions || r.vmOption ? [r.vmOption].filter(Boolean) : [];
    const list = opts.length ? opts : (r.vmOptions || []);
    if(!list.length) return RENDERERS._fallback(r);
    const rows = list.map(o => [
      `<span style="color:#7aa2f7">${esc(o.name||'')}</span>`,
      `<span style="color:#4ade80">${esc(String(o.value??''))}</span>`,
      o.writeable ? '<span style="color:#4ade80">✓</span>' : '<span style="color:#565f89">✗</span>'
    ]);
    return R.table(['Name','Value','Writeable'], rows);
  },

  // ── perfcounter ───────────────────────────────────────────────────────────
  perfcounter(r) {
    const counters = r.perfCounters || r.counters || r.content || [];
    if(!Array.isArray(counters) || !counters.length) return RENDERERS._fallback(r);
    const rows = counters.map(c => [
      `<span style="color:#7aa2f7">${esc(c.name||c.key||'')}</span>`,
      `<span style="color:#4ade80">${esc(String(c.value??''))}</span>`,
      `<span style="color:#565f89">${esc(c.units||c.unit||'')}</span>`
    ]);
    return R.table(['Counter','Value','Unit'], rows);
  },

  // ── sc ────────────────────────────────────────────────────────────────────
  sc(r) {
    const items = r.classInfo || r.classes || [];
    if(!items.length) { clog(`<span style="color:#565f89">No classes found</span>`, 'line'); return ''; }
    return items.map(c => {
      const name = c.name || c.className || '';
      const cl   = c.classLoader || c.classLoaderHash || '';
      const src  = c.codeSource || c.location || '';
      const isI  = c.isInterface;
      const body = [
        cl  ? R.kv('ClassLoader', `<span style="color:#7aa2f7">${esc(cl)}</span>`) : '',
        src ? R.kv('CodeSource',  `<span style="color:#565f89">${esc(src)}</span>`) : '',
        c.superClass ? R.kv('Super', `<span style="color:#7aa2f7">${esc(c.superClass)}</span>`) : '',
        c.interfaces?.length ? R.kv('Implements', c.interfaces.map(i=>`<span style="color:#7dcfff">${esc(i)}</span>`).join(', ')) : '',
      ].filter(Boolean).join('');
      const hdr = `<span style="color:${isI?'#bb9af7':'#7dcfff'};font-weight:600">${esc(name)}</span>
        ${isI ? R.badge('interface','#bb9af7') : ''}`;
      return R.collapsible(hdr, body || '<span style="color:#565f89">No details</span>', false);
    }).join('');
  },

  // ── sm ────────────────────────────────────────────────────────────────────
  sm(r) {
    const items = r.methodInfo || r.methods || [];
    if(!items.length) return `<span style="color:#565f89">No methods found</span>`;
    const rows = items.map(m => [
      `<span style="color:#7aa2f7">${esc(m.declaringClass||m.className||'')}</span>`,
      `<span style="color:#73daca;font-weight:600">${esc(m.methodName||m.name||'')}</span>`,
      `<span style="color:#a9b1d6;font-size:11px">${esc((m.paramTypes||m.params||[]).join(', '))}</span>`,
      `<span style="color:#e0af68">${esc(m.returnType||m.returnTypeName||'')}</span>`,
      `<span style="color:#565f89">${esc(m.modifier||m.modifiers||'')}</span>`,
    ]);
    return R.table(['Class','Method','Params','Return','Modifier'], rows);
  },

  // ── jad ───────────────────────────────────────────────────────────────────
  jad(r) {
    let html = '';
    if(r.location) html += `<div style="color:#565f89;font-size:11px;margin-bottom:4px">📍 ${esc(r.location)}</div>`;
    if(r.classInfo) html += `<div style="color:#7aa2f7;font-size:11px;margin-bottom:4px">${esc(r.classInfo)}</div>`;
    html += R.code(r.source || JSON.stringify(r, null, 2));
    return html;
  },

  // ── classloader ───────────────────────────────────────────────────────────
  classloader(r) {
    const cls = r.classLoaders || r.classloaders || [];
    if(!cls.length) return RENDERERS._fallback(r);
    const rows = cls.map(c => [
      `<span style="color:#7dcfff">${esc(c.name||c.className||'')}</span>`,
      `<span style="color:#4ade80">${c.loadedCount ?? c.classCount ?? '—'}</span>`,
      `<span style="color:#565f89">${esc(c.hash||c.hashCode||'')}</span>`,
      `<span style="color:#a9b1d6;font-size:11px">${esc(c.parent||'')}</span>`,
    ]);
    return R.table(['ClassLoader','Loaded','Hash','Parent'], rows);
  },

  // ── watch / getstatic / ognl ──────────────────────────────────────────────
  watch(r) {
    let html = '';
    const cost = r.cost ?? r.ts;
    if(cost != null) html += `<div style="color:#e0af68;font-size:11px;margin-bottom:4px">⏱ cost=${R.fmtMs(cost)}</div>`;
    if(r.isThrow) html += `<div style="color:#f7768e;font-size:11px;margin-bottom:4px">💥 Exception thrown</div>`;
    const val = r.object ?? r.value ?? r.returnValue ?? r.result;
    if(val !== undefined) html += R.code(typeof val === 'string' ? val : JSON.stringify(val, null, 2));
    else html += RENDERERS._fallback(r);
    return html;
  },
  ognl(r)      { return RENDERERS.watch(r); },
  getstatic(r) { return RENDERERS.watch(r); },

  // ── trace ─────────────────────────────────────────────────────────────────
  trace(r) {
    const root = r.threadTrace || r.traceTree || r;
    const renderNode = (node, depth=0) => {
      if(!node || typeof node !== 'object') return '';
      const cls  = node.className  || '';
      const mth  = node.methodName || '';
      const cost = node.cost ?? node.duration;
      const color = cost > 500 ? '#f87171' : cost > 100 ? '#fb923c' : '#4ade80';
      const costStr = cost != null ? `<span style="color:${color};font-size:11px"> [${R.fmtMs(cost)}]</span>` : '';
      const indent = depth * 16;
      let html = `<div style="padding-left:${indent}px;font-size:12px;line-height:1.8">
        <span style="color:#7dcfff">${esc(cls)}</span>.<span style="color:#73daca;font-weight:600">${esc(mth)}</span>()${costStr}
      </div>`;
      for(const child of (node.children || [])) {
        html += renderNode(child, depth + 1);
      }
      return html;
    };
    return `<div style="font-family:var(--mono)">${renderNode(root)}</div>`;
  },
  stack(r)     { return RENDERERS.trace(r); },

  // ── monitor ───────────────────────────────────────────────────────────────
  monitor(r) {
    const stats = r.monitorStatistics || r.statistics || r.data || [];
    if(!Array.isArray(stats) || !stats.length) return RENDERERS._fallback(r);
    const rows = stats.map(s => [
      `<span style="color:#7aa2f7">${esc(s.className||s.clazz||'')}</span>`,
      `<span style="color:#73daca">${esc(s.methodName||s.method||'')}</span>`,
      `<span style="color:#4ade80">${s.total??'—'}</span>`,
      `<span style="color:#4ade80">${s.success??'—'}</span>`,
      `<span style="color:#f87171">${s.failed??s.fail??'—'}</span>`,
      s.avgRt!=null ? `<span style="color:#e0af68">${R.fmtMs(s.avgRt)}</span>` : (s.avg!=null ? `<span style="color:#e0af68">${R.fmtMs(s.avg)}</span>` : '—'),
      s.maxRt!=null ? `<span style="color:#fb923c">${R.fmtMs(s.maxRt)}</span>` : '—',
      s.failureRate!=null ? `<span style="color:${s.failureRate>0?'#f87171':'#4ade80'}">${(s.failureRate*100).toFixed(1)}%</span>` : '—',
    ]);
    return R.table(['Class','Method','Total','Success','Fail','Avg RT','Max RT','Fail%'], rows);
  },

  // ── tt ────────────────────────────────────────────────────────────────────
  tt(r) {
    const idx = r.index ?? r.indexNum;
    const cost = r.cost;
    const isRet = r.isReturn; const isThr = r.isThrow;
    let html = '<div class="r-tt-card">';
    if(idx != null) html += R.kv('Index', `<span style="color:#7aa2f7">${idx}</span>`);
    if(cost != null) html += R.kv('Cost',  `<span style="color:#e0af68">${R.fmtMs(cost)}</span>`);
    if(isRet != null) html += R.kv('Return', isRet ? '<span style="color:#4ade80">true</span>' : '<span style="color:#565f89">false</span>');
    if(isThr != null) html += R.kv('Throw',  isThr ? '<span style="color:#f87171">true</span>'  : '<span style="color:#565f89">false</span>');
    const params = r.params ?? r.args;
    if(params != null) html += R.kv('Params', '') + R.code(JSON.stringify(params, null, 2));
    const ret = r.returnValue ?? r.returnObj;
    if(ret != null) html += R.kv('Return Value', '') + R.code(JSON.stringify(ret, null, 2));
    html += '</div>';
    return html;
  },

  // ── vmtool ────────────────────────────────────────────────────────────────
  vmtool(r) {
    if(r.action === 'forceGc' || r.forceGc) {
      return `<span style="color:#4ade80">✓ Force GC completed</span>`;
    }
    const instances = r.instances || r.objects || r.result || [];
    if(!Array.isArray(instances)) return RENDERERS._fallback(r);
    let html = `<div style="color:#565f89;font-size:11px;margin-bottom:6px">${instances.length} instance(s)</div>`;
    instances.forEach((obj, i) => {
      const preview = typeof obj === 'string' ? obj : JSON.stringify(obj, null, 2);
      html += R.collapsible(
        `<span style="color:#7dcfff">Instance [${i}]</span>`,
        R.code(preview), i === 0
      );
    });
    return html;
  },

  // ── logger ────────────────────────────────────────────────────────────────
  logger(r) {
    const loggers = r.loggers || r.loggerInfos || [];
    if(!Array.isArray(loggers) || !loggers.length) return RENDERERS._fallback(r);
    const levelColor = l => ({
      ERROR:'#f87171', WARN:'#fb923c', INFO:'#4ade80',
      DEBUG:'#7aa2f7', TRACE:'#94a3b8'
    }[l?.toUpperCase()] || '#9aa5ce');
    const rows = loggers.map(lg => [
      `<span style="color:#c0caf5">${esc(lg.name||lg.loggerName||'')}</span>`,
      `<span style="color:${levelColor(lg.level)};font-weight:600">${esc(lg.level||'')}</span>`,
      `<span style="color:${levelColor(lg.effectiveLevel||lg.configLevel)}">${esc(lg.effectiveLevel||lg.configLevel||'')}</span>`,
      `<span style="color:#565f89;font-size:11px">${(lg.appenders||[]).map(a=>esc(a.name||a)).join(', ')}</span>`,
    ]);
    return R.table(['Logger','Level','Effective','Appenders'], rows);
  },

  // ── mbean ─────────────────────────────────────────────────────────────────
  mbean(r) {
    const beans = r.mBeanInfo || r.mbeanInfo || [];
    if(!Array.isArray(beans)) return RENDERERS._fallback(r);
    return beans.map(b => {
      const name = esc(b.objectName || b.name || '');
      const attrs = (b.attributes || []).map(a =>
        R.kv(a.name || a.key || '', `<span style="color:#a9b1d6">${esc(String(a.value ?? ''))}</span>`)
      ).join('');
      return R.collapsible(
        `<span style="color:#7aa2f7;font-weight:600">${name}</span>`,
        attrs || '<span style="color:#565f89">No attributes</span>',
        false
      );
    }).join('');
  },

  // ── profiler ──────────────────────────────────────────────────────────────
  profiler(r) {
    const action = r.action || '';
    const file   = r.outputFile || r.file || '';
    const event  = r.event || '';
    let html = '';
    if(action) html += R.kv('Action', `<span style="color:#7aa2f7">${esc(action)}</span>`);
    if(event)  html += R.kv('Event',  `<span style="color:#4ade80">${esc(event)}</span>`);
    if(file)   html += R.kv('Output', `<span style="color:#e0af68">${esc(file)}</span>`);
    const result = r.executeResult || r.result || '';
    if(result) html += `<div style="color:#a9b1d6;font-size:12px;margin-top:4px">${esc(String(result))}</div>`;
    return html || RENDERERS._fallback(r);
  },

  // ── heapdump ──────────────────────────────────────────────────────────────
  heapdump(r) {
    const loc = r.location || r.file || r.outputFile || '';
    return `<div>${R.kv('File', `<span style="color:#e0af68">${esc(loc)}</span>`)}</div>`;
  },

  // ── jfr ───────────────────────────────────────────────────────────────────
  jfr(r) {
    const out = r.jfrOutput || r.output || r.result || '';
    return `<div style="color:#a9b1d6;font-size:12px;white-space:pre-wrap">${esc(String(out))}</div>`;
  },

  // ── version ───────────────────────────────────────────────────────────────
  version(r) {
    return R.kv('Arthas Version', `<span style="color:#4ade80;font-weight:700">${esc(r.version||'')}</span>`);
  },

  // ── pwd ───────────────────────────────────────────────────────────────────
  pwd(r) {
    const path = r.workingDir || r.dir || r.path || '';
    return R.kv('Working Dir', `<span style="color:#e0af68">${esc(path)}</span>`);
  },

  // ── history ───────────────────────────────────────────────────────────────
  history(r) {
    const cmds = r.commands || r.history || r.entries || [];
    if(!Array.isArray(cmds) || !cmds.length) return RENDERERS._fallback(r);
    const rows = cmds.map((c, i) => [
      `<span style="color:#565f89">${i+1}</span>`,
      `<span style="color:#a9b1d6">${esc(c.command||c.cmd||String(c))}</span>`
    ]);
    return R.table(['#','Command'], rows);
  },

  // ── echo / cat / grep / tee ───────────────────────────────────────────────
  echo(r) {
    return `<div style="color:#a9b1d6;white-space:pre-wrap">${esc(r.text||r.content||r.output||'')}</div>`;
  },
  cat(r)  { return RENDERERS.echo(r); },

  // ── fallback: pretty JSON ─────────────────────────────────────────────────
  _fallback(r) {
    const skip = new Set(['type','jobId','statusCode']);
    const filtered = Object.fromEntries(Object.entries(r).filter(([k]) => !skip.has(k)));
    return R.code(JSON.stringify(filtered, null, 2));
  },
};

/** 主渲染入口 */
function renderRes(resp) {
  if(!resp) return;
  if(resp.state==='FAILED' || resp.state==='REFUSED') {
    clog('✗ ' + esc(resp.message || JSON.stringify(resp)), 'err');
    return;
  }
  // 兼容旧格式 {error: "..."} 或 {ok: false}
  if(resp.error && !resp.body) {
    clog('✗ ' + esc(resp.error), 'err');
    return;
  }
  const results = resp.body?.results || [];
  if(!results.length && resp.body) {
    clog(`<pre class="o-code">${esc(JSON.stringify(resp.body, null, 2))}</pre>`, 'line');
    return;
  }
  if(!results.length) {
    // SUCCEEDED 但无 results，输出完整响应用于调试
    clog(`<pre class="o-code">${esc(JSON.stringify(resp, null, 2))}</pre>`, 'line');
    return;
  }
  // Collect ALL result HTML into one string → one clog call → one DOM insert
  const parts = [];
  for(const r of results) {
    const t = r.type || '';
    if(['status','message','welcome','input_status'].includes(t)) continue;
    const renderer = RENDERERS[t];
    const html = renderer ? renderer(r) : RENDERERS._fallback(r);
    if(html) parts.push(html);
  }
  if(parts.length) clog(parts.join('<hr class="r-hr">'), 'line');
}

// ── 性能分析 & Dump ───────────────────────────────────────────────────────────
let _pfMode = 'profiler'; // 'profiler' | 'jfr' | 'dump'

const PF_MODE_DESC = {
  profiler: 'async-profiler: 低开销采样分析，支持 CPU/内存/锁等事件，生成火焰图。适用所有 JDK 版本。',
  jfr:      'JDK JFR (Java Flight Recorder): JDK 内置事件录制，需要 JDK 11+。通过 Arthas jfr 命令控制，生成 .jfr 文件，用 JDK Mission Control 分析。',
  dump:     '快照导出: 线程 Dump 分析死锁/卡顿；Heap Dump 分析内存泄漏/OOM。文件自动下载到本地。',
  gclog:    'GC 日志分析: 自动探测 JVM 的 GC 日志配置（-Xloggc / -Xlog:gc），读取日志内容，支持下载。无 GC 日志配置时给出启用建议。',
};

function pfSetMode(mode) {
  _pfMode = mode;
  ['profiler','jfr','dump','gclog'].forEach(m => {
    document.getElementById(`pfMode-${m}`)?.classList.toggle('on', m === mode);
    const cfg = document.getElementById(`pfCfg-${m}`);
    if(cfg) cfg.style.display = m === mode ? 'block' : 'none';
  });
  const desc = document.getElementById('pfModeDesc');
  if(desc) desc.textContent = PF_MODE_DESC[mode] || '';
  const btn = document.getElementById('pfBtn');
  if(btn) btn.textContent = mode === 'gclog' ? '🔍 探测 GC 日志' : mode === 'dump' ? '▶ 导出' : '▶ 开始采样';
  // Show/hide dump sub-options
  pfUpdateDumpOpts();
}

function pfUpdateDumpOpts() {
  const heapOpts = document.getElementById('dumpHeapOpts');
  const dumpSel  = document.getElementById('dumpType');
  if(heapOpts && dumpSel) {
    heapOpts.style.display = dumpSel.value === 'heap' ? 'block' : 'none';
  }
}

function pfDurSync(val, from) {
  const v = Math.max(30, Math.min(7200, parseInt(val)||60));
  if(from !== 'num') { const n = document.getElementById('pfDurNum'); if(n) n.value = v; }
  const slider = document.getElementById('pfDur');
  if(slider) slider.value = Math.min(v, parseInt(slider.max));
}
function pfSetDur(s) {
  const sl = document.getElementById('pfDur');     if(sl) sl.value = Math.min(s, 1800);
  const nm = document.getElementById('pfDurNum');  if(nm) nm.value = s;
}

async function pfStart() {
  const t = getT();
  if(!t.cluster_name || !t.pod_name) { toast('请先配置集群和 Pod','warn'); return; }

  if(_pfMode === 'dump')  { await pfRunDump(t);  return; }
  if(_pfMode === 'jfr')   { await pfRunJfr(t);   return; }
  if(_pfMode === 'gclog') { await pfRunGcLog(t); return; }

  // ── async-profiler (profiler start/stop) ──────────────────────────────────
  _pfDur   = Math.max(30, parseInt(document.getElementById('pfDurNum')?.value || document.getElementById('pfDur')?.value) || 60);
  _pfStart = Date.now();
  const event  = document.getElementById('pfEvent')?.value  || 'cpu';
  const fmt    = document.getElementById('pfFmt')?.value    || 'html';

  // 更新任务信息面板
  _pfTaskInfo = { type: 'async-profiler', event: event, duration: _pfDur, status: 'starting' };
  updatePfTaskInfo();

  document.getElementById('pfBtn').disabled = true;
  document.getElementById('pfProg').style.display = 'block';
  pfClearLog();
  pfLog(`提交任务... 事件=${event} 格式=${fmt} 时长=${_pfDur}s`, 'dim');
  try {
    const r = await fetch(`${API}/profile/start`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({...t, duration: _pfDur, format: fmt, event}),
    });
    const d = await r.json(); 
    if(!r.ok) {
      // 409 = 已有运行中任务，恢复按钮并提示
      if (r.status === 409) {
        document.getElementById('pfBtn').disabled = false;
        toast(d.message || '该连接已有运行中的任务', 'warn');
        pfLog('⚠ ' + (d.message || '已有运行中的任务'), 'warn');
        hidePfTaskInfo();
        return;
      }
      throw new Error(d.error || d.message || '失败');
    }
    if(d.error) throw new Error(d.error);
    _pfTaskId = d.task_id;
    _pfTaskInfo.taskId = d.task_id;
    _pfTaskInfo.status = 'running';
    updatePfTaskInfo();
    pfLog(`任务已创建: ${d.task_id}`, 'ok');
    _pfPollingForConn = _currentConnId;  // 设置轮询连接标记
    _pfPollTimer = setInterval(pfPoll, 2000);
  } catch(e) { pfLog('失败: '+e.message, 'err'); document.getElementById('pfBtn').disabled = false; hidePfTaskInfo(); }
}

async function pfRunJfr(t) {
  // ── JDK JFR via Arthas jfr command ──────────────────────────────────────
  // 正确用法: jfr start [name] [settings] → jfr stop [name] [filename]
  // 注意: JFR 需要 JDK 11+，不同于 async-profiler 的 "profiler stop --format jfr"
  const name     = document.getElementById('jfrName')?.value.trim() || 'arthas-jfr';
  const dur      = Math.max(10, parseInt(document.getElementById('jfrDurNum')?.value) || 60);
  const settings = document.getElementById('jfrSettings')?.value || 'default';
  const _jts    = fmtNowTs();
  const jfrFile  = `/tmp/jfr-${name}-${_jts}.jfr`;

  _pfStart = Date.now(); _pfDur = dur;

  // 更新任务信息面板
  _pfTaskInfo = { type: 'JDK JFR', event: settings, duration: dur, status: 'starting' };
  updatePfTaskInfo();

  document.getElementById('pfBtn').disabled = true;
  document.getElementById('pfProg').style.display = 'block';
  pfClearLog();
  pfLog(`JFR 录制: name=${name} settings=${settings} duration=${dur}s`, 'dim');
  pfLog('注意: JFR 需要 JDK 8u262+ 或 JDK 11+', 'warn');

  try {
    const r = await fetch(`${API}/profile/start`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({...t, mode: 'jfr', jfr_name: name,
                            jfr_settings: settings, jfr_file: jfrFile,
                            duration: dur, format: 'jfr', event: settings}),
    });
    const d = await r.json(); 
    if(!r.ok) {
      if (r.status === 409) {
        document.getElementById('pfBtn').disabled = false;
        toast(d.message || '该连接已有运行中的任务', 'warn');
        pfLog('⚠ ' + (d.message || '已有运行中的任务'), 'warn');
        hidePfTaskInfo();
        return;
      }
      throw new Error(d.error || d.message || '失败');
    }
    if(d.error) throw new Error(d.error);
    _pfTaskId = d.task_id;
    _pfTaskInfo.taskId = d.task_id;
    _pfTaskInfo.status = 'running';
    updatePfTaskInfo();
    pfLog(`JFR 任务已创建: ${d.task_id}`, 'ok');
    _pfPollingForConn = _currentConnId;  // 设置轮询连接标记
    _pfPollTimer = setInterval(pfPoll, 2000);
  } catch(e) { pfLog('失败: '+e.message, 'err'); document.getElementById('pfBtn').disabled = false; hidePfTaskInfo(); }
}

async function pfRunDump(t) {
  // ── Dump: thread dump or heap dump ────────────────────────────────────────
  const dumpType = document.getElementById('dumpType')?.value || 'thread';

  // 更新任务信息面板
  _pfTaskInfo = { type: dumpType === 'thread' ? 'Thread Dump' : 'Heap Dump', event: '-', duration: '-', status: 'starting' };
  updatePfTaskInfo();

  document.getElementById('pfBtn').disabled = true;
  pfClearLog();

  if(dumpType === 'thread') {
    pfLog('导出线程 Dump...', 'dim');
    try {
      const r = await fetch(`${API}/profile/start`, {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({...t, mode: 'threaddump', duration: 0, format: 'html'}),
      });
      const d = await r.json(); 
      if(!r.ok) {
        if (r.status === 409) {
          document.getElementById('pfBtn').disabled = false;
          toast(d.message || '该连接已有运行中的任务', 'warn');
          pfLog('⚠ ' + (d.message || '已有运行中的任务'), 'warn');
          hidePfTaskInfo();
          return;
        }
        throw new Error(d.error || d.message || '失败');
      }
      if(d.error) throw new Error(d.error);
      _pfTaskId = d.task_id;
      _pfTaskInfo.taskId = d.task_id;
      _pfTaskInfo.status = 'running';
      updatePfTaskInfo();
      pfLog(`线程 Dump 任务: ${d.task_id}`, 'ok');
      pfLog('正在采集，通常 5~10 秒完成...', 'dim');
      _pfPollingForConn = _currentConnId;  // 设置轮询连接标记
      _pfPollTimer = setInterval(pfPoll, 1500);
    } catch(e) { pfLog('失败: '+e.message, 'err'); document.getElementById('pfBtn').disabled = false; hidePfTaskInfo(); }
  } else {
    // heap dump
    // 路径仅用于界面显示，实际文件名由后端用时间戳生成
    const file    = '';  // 后端自动生成: heap-{pod}-{ts}.hprof
    // Update UI input to show actual path
    const _hfEl = document.getElementById('dumpHeapFile');
    if(_hfEl) _hfEl.value = file;
    const liveOnly = document.getElementById('dumpHeapLive')?.checked ?? true;
    pfLog(`导出 Heap Dump → ${file}`, 'dim');
    pfLog('警告: Heap Dump 会暂停 JVM（STW），大堆可能需要数分钟', 'warn');
    try {
      const r = await fetch(`${API}/profile/start`, {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({...t, mode: 'heapdump', heap_file: file,
                              heap_live: liveOnly, duration: 0, format: 'hprof'}),
      });
      const d = await r.json(); 
      if(!r.ok) {
        if (r.status === 409) {
          document.getElementById('pfBtn').disabled = false;
          toast(d.message || '该连接已有运行中的任务', 'warn');
          pfLog('⚠ ' + (d.message || '已有运行中的任务'), 'warn');
          hidePfTaskInfo();
          return;
        }
        throw new Error(d.error || d.message || '失败');
      }
      if(d.error) throw new Error(d.error);
      _pfTaskId = d.task_id;
      _pfTaskInfo.taskId = d.task_id;
      _pfTaskInfo.status = 'running';
      updatePfTaskInfo();
      pfLog(`Heap Dump 任务: ${d.task_id}`, 'ok');
      pfLog('采集中，请等待...', 'dim');
      _pfPollingForConn = _currentConnId;  // 设置轮询连接标记
      _pfPollTimer = setInterval(pfPoll, 2000);
    } catch(e) { pfLog('失败: '+e.message, 'err'); document.getElementById('pfBtn').disabled = false; hidePfTaskInfo(); }
  }
}

async function pfRunGcLog(t) {
  const btn = document.getElementById('pfBtn');
  if(btn) btn.disabled = true;
  pfClearLog();
  pfLog('探测 GC 日志配置...', 'dim');

  const gcInfo = document.getElementById('gcLogInfo');
  const gcHint = document.getElementById('gcHint');
  if(gcInfo) gcInfo.style.display = 'none';
  if(gcHint) gcHint.style.display = 'none';

  try {
    const r = await fetch(`${API}/gc/info`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify(t),
    });
    const d = await r.json();
    if(!r.ok || d.error) throw new Error(d.error || '探测失败');

    pfLog(`进程 PID: ${d.pid}`, 'dim');

    if(d.gc_enabled) {
      // ── 左侧：显示 GC 参数 + 文件路径列表 ─────────────────────────────
      const flagsEl = document.getElementById('gcFlagsDisplay');
      if(flagsEl) flagsEl.textContent = d.gc_flags?.join('\n') || '（未发现具名 GC 参数）';

      // 构建路径列表（支持多个路径 + stdout）
      const pathListEl = document.getElementById('gcPathList');
      if(pathListEl) {
        const paths = d.stdout_gc ? ['stdout'] : (d.log_paths || []);
        if(paths.length === 0 && d.log_path_used) paths.push(d.log_path_used);

        pathListEl.innerHTML = paths.map(p => `
          <div style="display:flex;gap:5px;align-items:center">
            <input class="fi" value="${esc(p)}" readonly
              style="flex:1;font-size:11px;color:var(--a);font-family:var(--mono)">
            ${p !== 'stdout' ? `
              <button class="ib" onclick="gcDownloadPath('${esc(p)}')"
                style="font-size:11px;padding:3px 8px;white-space:nowrap">↓ 下载</button>
              <button class="ib" onclick="gcPreviewPath('${esc(p)}')"
                style="font-size:11px;padding:3px 8px;white-space:nowrap">👁 预览</button>
            ` : `<span style="font-size:11px;color:var(--a4)">→ Pod监控日志</span>`}
          </div>`).join('');
      }
      if(gcInfo) gcInfo.style.display = 'block';

      // ── 右侧日志面板：显示探测结果 ──────────────────────────────────────
      if(d.gc_flags?.length) {
        pfLog(`GC 参数 (${d.gc_flags.length}个):`, 'ok');
        d.gc_flags.forEach(f => pfLog(`  ${f}`, 'info'));
      }
      if(d.stdout_gc) {
        pfLog('GC 输出到 stdout → 请在「Pod 监控 → 日志」查看', 'warn');
      } else if(d.log_path_used) {
        pfLog(`✓ 日志文件: ${d.log_path_used}`, 'ok');
        if(d.log_content && !d.log_content.startsWith('文件不可读')) {
          const lines = d.log_content.split('\n').filter(l => l.trim());
          pfLog(`最后 ${Math.min(lines.length, 30)} 行:`, 'dim');
          lines.slice(-30).forEach(l => pfLog(l, 'info'));
        } else {
          pfLog(d.log_content || '无法读取内容', 'warn');
        }
      }
    } else {
      pfLog('⚠ 未检测到 GC 日志配置', 'warn');
      if(gcHint) { gcHint.textContent = d.hint || ''; gcHint.style.display = 'block'; }
      pfLog('启用 GC 日志需要重启 JVM，添加启动参数（见左侧提示框）', 'dim');
    }

    if(d.cmdline_snippet) {
      pfLog(`cmdline: ${d.cmdline_snippet.slice(0, 200)}`, 'dim');
    }

  } catch(e) {
    pfLog('探测失败: ' + e.message, 'err');
  } finally {
    if(btn) btn.disabled = false;
  }
}

async function gcDownloadPath(path) {
  const t = getT();
  if(!t.pod_name) { toast('请先配置 Pod', 'warn'); return; }
  pfLog(`下载: ${path}`, 'dim');
  try {
    const r = await fetch(`${API}/gc/download`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({...t, log_path: path}),
    });
    if(!r.ok) { const e = await r.json(); throw new Error(e.error||'下载失败'); }
    const blob = await r.blob();
    const ts   = new Date().toISOString().replace(/[:.]/g,'-').slice(0,19);
    const fname = `gc-${t.pod_name}-${fmtNowTs()}.log`;
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href=url; a.download=fname; a.click();
    URL.revokeObjectURL(url);
    toast('GC 日志已下载', 'success');
    pfLog(`✓ 已下载: ${fname}`, 'ok');
  } catch(e) { toast(e.message, 'error'); pfLog('下载失败: '+e.message, 'err'); }
}

async function gcPreviewPath(path) {
  const t = getT();
  if(!t.pod_name) { toast('请先配置 Pod', 'warn'); return; }
  pfLog(`预览: ${path}`, 'dim');
  try {
    const d = await safePost(`${API}/pod/files/tail`, {...t, path, lines: 100});
    if(d.error) { pfLog('预览失败: '+d.error, 'err'); return; }
    const lines = (d.content||'').split('\n');
    pfLog(`── GC 日志末尾 ${lines.length} 行 ──────────────────────────`, 'dim');
    lines.forEach(l => {
      const cls = /pause|stop-the-world|full gc|gc overhead/i.test(l) ? 'err'
                : /young|minor/i.test(l) ? 'ok' : 'info';
      pfLog(l || ' ', cls);
    });
  } catch(e) { pfLog('预览失败: '+e.message, 'err'); }
}

// 兼容旧版 gcDownload 调用
async function gcDownload() {
  const path = document.getElementById('gcLogPath')?.value;
  if(path) { await gcDownloadPath(path); }
  else { toast('未检测到 GC 日志路径', 'warn'); }
}

// 更新任务信息面板
function updatePfTaskInfo() {
  const el = document.getElementById('pfTaskInfo');
  if (!el) return;
  el.style.display = 'block';
  const info = _pfTaskInfo || {};
  document.getElementById('pfInfoTaskId').textContent = info.taskId || '-';
  // 友好的类型/事件名称
  const typeLabels = {
    'Thread Dump': '线程转储',
    'Heap Dump': '堆转储',
    'async-profiler': 'async-profiler',
    'JDK JFR': 'JDK JFR'
  };
  const eventLabels = {
    'threaddump': '线程转储',
    'heapdump': '堆转储',
    'cpu': 'CPU 采样',
    'alloc': '内存分配',
    'lock': '锁竞争',
    'wall': 'Wall 时间',
    'default': '默认配置',
    'profile': 'Profile 配置'
  };
  const typeDisplay = typeLabels[info.type] || info.type || '-';
  const eventDisplay = eventLabels[info.event] || info.event || '-';
  document.getElementById('pfInfoType').textContent = typeDisplay;
  document.getElementById('pfInfoEvent').textContent = eventDisplay;
  // 时长显示：dump 类型或 duration 为 0/空 显示 '-'
  const isDump = info.type === 'Thread Dump' || info.type === 'Heap Dump' || info.event === 'threaddump' || info.event === 'heapdump';
  const durDisplay = isDump || !info.duration || info.duration === '-' || info.duration === 0 ? '-' : `${info.duration}s`;
  document.getElementById('pfInfoDur').textContent = durDisplay;
  document.getElementById('pfInfoProgress').textContent = info.progress || '-';
  const statusEl = document.getElementById('pfInfoStatus');
  statusEl.textContent = info.status || '-';
  // 状态颜色
  if (info.status === 'running') statusEl.style.color = 'var(--a)';
  else if (info.status === 'completed') statusEl.style.color = 'var(--a3)';
  else if (info.status === 'failed') statusEl.style.color = 'var(--a5)';
  else statusEl.style.color = 'var(--tx2)';

  // 任务完成时显示下载按钮
  const downloadWrap = document.getElementById('pfInfoDownloadWrap');
  const downloadBtn = document.getElementById('pfInfoDownloadBtn');
  if (downloadWrap && downloadBtn) {
    if (info.status === 'completed') {
      downloadWrap.style.display = 'inline';
      // 优先通过 task_id 下载（支持权限校验），备选通过文件名下载
      if (info.taskId) {
        const fname = info.outputFile || `profiler-${info.taskId}.html`;
        downloadBtn.onclick = () => downloadProfilerTask(info.taskId, fname);
      } else if (info.outputFile) {
        downloadBtn.onclick = () => downloadOutputFile(info.outputFile);
      } else {
        downloadWrap.style.display = 'none';
      }
    } else {
      downloadWrap.style.display = 'none';
    }
  }
}

// 隐藏任务信息面板
function hidePfTaskInfo() {
  const el = document.getElementById('pfTaskInfo');
  if (el) el.style.display = 'none';
  _pfTaskInfo = { type: '-', event: '-', duration: 0, status: '-' };
}

// 安全下载文件（带认证）
async function safeDownload(url, filename) {
  try {
    const fullUrl = url.startsWith('http') ? url : `${API}${url}`;
    const r = await fetch(fullUrl, { credentials: 'include' });
    
    if (r.status === 401) {
      toast('登录已过期，请刷新页面重新登录', 'error');
      return;
    }
    if (!r.ok) {
      const errData = await r.json().catch(() => ({}));
      toast(errData.error || `下载失败 (${r.status})`, 'error');
      return;
    }
    
    const blob = await r.blob();
    const blobUrl = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = blobUrl;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(blobUrl);
    toast(`已下载: ${filename}`, 'success');
  } catch (e) {
    toast('下载失败: ' + e.message, 'error');
  }
}

// 下载采样任务结果
async function downloadProfilerTask(taskId, filename) {
  await safeDownload(`/profile/${taskId}/download`, filename || `profiler-${taskId}.html`);
}

// 下载本地输出文件
async function downloadOutputFile(filename) {
  await safeDownload(`/files/${encodeURIComponent(filename)}`, filename);
}

async function pfPoll() {
  if(!_pfTaskId) return;
  try {
    const r = await fetch(`${API}/profile/${_pfTaskId}`); const d = await r.json();

    // 只为当前连接输出日志和更新 UI
    if (_pfPollingForConn === _currentConnId) {
      (d.logs||[]).slice(_pfLL).forEach(l => pfLog(l.message, l.level));
      _pfLL = d.logs?.length||0;
      const el = (Date.now()-_pfStart)/1000;
      const totalDur = _pfDur || 30;
      const overtime = el > totalDur;  // 是否超时
      const pct = Math.min(95, (el/(totalDur+30))*100);  // 进度条上限提高到 95%
      document.getElementById('pfProgFill').style.width = pct+'%';
      document.getElementById('pfProgPct').textContent = Math.round(pct)+'%';
      
      // 进度文本：区分正常采样和超时下载阶段
      if (d.status === 'running') {
        if (overtime) {
          document.getElementById('pfProgLbl').textContent = `${_pfMode === 'dump' ? '导出' : '采样'}完成，下载中...`;
          document.getElementById('pfProgLbl').style.color = 'var(--a3)';
        } else {
          document.getElementById('pfProgLbl').textContent = `${_pfMode === 'dump' ? '导出中' : '采样'} ${Math.round(el)}s/${_pfDur}s`;
          document.getElementById('pfProgLbl').style.color = 'var(--tx2)';
        }
      } else {
        document.getElementById('pfProgLbl').textContent = d.status;
      }

      // 更新任务信息面板（从后端同步 type 和 event）
      _pfTaskInfo.status = d.status || 'running';
      if (d.type) _pfTaskInfo.type = d.type;
      if (d.event) _pfTaskInfo.event = d.event;
      if (overtime && d.status === 'running') {
        _pfTaskInfo.progress = `采样完成，下载中 (${Math.round(el)}s)`;
      } else {
        _pfTaskInfo.progress = `${Math.round(el)}s / ${_pfDur}s`;
      }
      updatePfTaskInfo();

      if(d.status==='completed'||d.status==='failed') {
        clearInterval(_pfPollTimer); _pfPollTimer = null; _pfLL = 0;
        _pfPollingForConn = null;  // 清空轮询连接标记
        document.getElementById('pfBtn').disabled = false;
        if(d.status==='completed') {
          document.getElementById('pfProgFill').style.width='100%';
          document.getElementById('pfProgPct').textContent='100%';
          _pfTaskInfo.progress = '100%';
          _pfTaskInfo.status = 'completed';
          _pfTaskInfo.outputFile = d.output_file;  // 保存输出文件名
          updatePfTaskInfo();
          toast('完成！','success'); loadLocalFiles(); loadPfHistory();
        } else {
          _pfTaskInfo.status = 'failed';
          updatePfTaskInfo();
          toast('失败','error');
        }

        // 清除该连接的任务状态缓存
        if (_currentConnId && _pfTasksByConn[_currentConnId]) {
          delete _pfTasksByConn[_currentConnId];
        }
        _pfTaskId = null;
      }
    } else {
      // 不是当前连接，只更新日志位置计数，不输出到 DOM
      _pfLL = d.logs?.length||0;
    }
  } catch {}
}

async function pfLog(msg, lv='info') {
  const el = document.getElementById('pfl-panel-log');
  if(el && el.children.length===1 && el.children[0].textContent==='等待启动...') el.innerHTML='';
  const cls = {info:'o-line',dim:'o-dim',ok:'o-ok',error:'o-err',warn:'o-warn',success:'o-ok'}[lv]||'o-line';
  const d = document.createElement('div');
  d.className = cls;
  // 使用 innerHTML 而不是 textContent，保留换行符
  d.innerHTML = msg.replace(/\n/g, '<br>');
  el.appendChild(d);
  el.scrollTop = el.scrollHeight;

  const _cntEl = document.getElementById('pfLogCnt');
  if(_cntEl) _cntEl.textContent = (el?.children.length||0) + '行';

  // 保存到数据库
  if (_currentConnId) {
    try {
      await fetch(`${API}/profile/logs`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          connection_id: _currentConnId,
          message: msg,
          level: lv
        })
      });
    } catch(e) {
      console.error('Failed to save profiler log:', e);
    }
  }
}
function pfClearLog() {
  const el = document.getElementById('pfl-panel-log');
  if(el) el.innerHTML='<div class="o-dim">等待启动...</div>';
  const c = document.getElementById('pfLogCnt'); if(c) c.textContent='0行';

  // 注意：不再删除数据库中的历史任务记录
  // 之前 pfClearLog() 会调用 DELETE /api/profile/logs/{conn_id}，
  // 导致该连接下所有 profiler_tasks 被删除，重复采集时历史数据丢失

  // 清空当前连接的任务状态缓存（如果任务已完成或被取消）
  if (_currentConnId && _pfTasksByConn[_currentConnId] && !_pfTaskId) {
    delete _pfTasksByConn[_currentConnId];
  }
}

function togglePfHistory() {
  const logPanel = document.getElementById('pfl-panel-log');
  const historyPanel = document.getElementById('pfl-panel-history');
  const btn = document.querySelector('#pfl-panel-history').closest('.pf-log').querySelector('button[onclick*="togglePfHistory"]');

  if (historyPanel.style.display === 'none') {
    // 显示历史记录面板
    historyPanel.style.display = 'block';
    if (btn) {
      btn.textContent = '📋 返回日志';
      btn.title = '返回采样日志';
    }
    loadPfHistoryForCurrentConn();
  } else {
    // 显示日志面板
    historyPanel.style.display = 'none';
    if (btn) {
      btn.textContent = '📋 本地历史';
      btn.title = '查看当前连接的历史记录';
    }
  }
}

async function loadPfHistoryForCurrentConn() {
  try {
    const r = await fetch(`${API}/profile/tasks`); const allTasks = await r.json();

    // 过滤出当前连接的采样任务
    let currentTasks = allTasks;
    if (_currentConnId) {
      const currentConn = _connections.find(c => c.id === _currentConnId);
      if (currentConn) {
        currentTasks = allTasks.filter(t =>
          t.config.cluster === currentConn.cluster_name &&
          t.config.namespace === currentConn.namespace &&
          t.config.pod === currentConn.pod_name
        );
      }
    }

    // 更新连接名称显示
    const connNameEl = document.getElementById('pfHistConnName');
    if (connNameEl && _currentConnId) {
      const currentConn = _connections.find(c => c.id === _currentConnId);
      if (currentConn) {
        connNameEl.textContent = `${currentConn.cluster_name}/${currentConn.namespace}/${currentConn.pod_name}`;
      }
    }

    // 渲染历史记录
    const el = document.getElementById('pfl-history-list');
    if (!currentTasks.length) {
      el.innerHTML = '<div style="color:var(--tx3);text-align:center;padding:20px">暂无历史记录</div>';
      return;
    }

    const icons = {completed:'✅',failed:'❌',running:'⏳',starting:'⏳'};
    const labels = {completed:'完成',failed:'失败',running:'运行中',starting:'启动中'};
    const bcls = {completed:'st-ok',failed:'st-fail',running:'st-run',starting:'st-run'};
    const showUser = typeof isAdmin === 'function' && isAdmin();

    el.innerHTML = currentTasks.map(t => {
      const mode = t.config.mode || 'profiler';
      const event = t.config.event || '-';
      const duration = t.config.duration || 0;
      const format = t.config.format || 'html';

      // 友好的事件类型名称
      const eventLabels = {
        'threaddump': '线程转储',
        'heapdump': '堆转储',
        'cpu': 'CPU 采样',
        'alloc': '内存分配',
        'lock': '锁竞争',
        'wall': 'Wall 时间',
        'default': 'JFR 默认',
        'profile': 'JFR Profile'
      };
      const eventDisplay = eventLabels[event] || event;

      // 时长显示：dump 类型显示 "-"，其他显示秒数
      const durationDisplay = (mode === 'threaddump' || mode === 'heapdump' || duration === 0) ? '-' : `${duration}s`;

      // 格式显示
      const formatDisplay = mode === 'threaddump' ? 'HTML' : mode === 'heapdump' ? 'HPROF' : format;

      const metaParts = [`事件: ${eventDisplay}`, `时长: ${durationDisplay} · 格式: ${formatDisplay}`];
      if (showUser && t.username) metaParts.push(`<span style="color:var(--a)">@${esc(t.username)}</span>`);
      return `
      <div style="padding:10px;background:var(--bg1);border:1px solid var(--ln);border-radius:6px;margin-bottom:8px">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
          <span style="font-size:14px">${icons[t.status]||'❓'}</span>
          <span style="font-size:11px;color:var(--tx2)">${mode}</span>
          <span class="st-badge ${bcls[t.status]||''}" style="font-size:10px">${labels[t.status]||t.status}</span>
          <span style="margin-left:auto;font-size:10px;color:var(--tx3)">${fmtTs(t.created_at)}</span>
        </div>
        <div style="font-size:10px;color:var(--tx2);line-height:1.5">
          ${metaParts.map(p => `<div>${p}</div>`).join('')}
        </div>
        ${t.has_file?`<div style="margin-top:6px;padding:6px 8px;background:rgba(122,162,247,.08);border-radius:4px;font-size:10px;font-family:monospace;color:var(--a)">
          📄 ${t.file_name||'output'}
        </div><button class="btn btn-dl" style="display:inline-block;margin-top:6px;padding:4px 10px;font-size:10px;cursor:pointer" onclick="downloadProfilerTask('${t.id}', '${t.file_name||'output'}')">↓ 下载</button>`:''}
      </div>
    `;
    }).join('');
  } catch(e) {
    console.error('Failed to load current connection history:', e);
  }
}

async function loadConnectionProfilerLogs(connId) {
  // 从数据库加载连接的采样日志
  const el = document.getElementById('pfl-panel-log');
  if (!el) return;

  try {
    const r = await fetch(`${API}/profile/logs/${connId}`);
    const d = await r.json();
    const logs = d.logs || [];

    if (logs.length === 0) {
      el.innerHTML = '<div class="o-dim">暂无采样日志</div>';
      const c = document.getElementById('pfLogCnt');
      if (c) c.textContent = '0行';
      return;
    }

    el.innerHTML = '';
    logs.forEach(log => {
      const cls = {info:'o-line',dim:'o-dim',ok:'o-ok',error:'o-err',warn:'o-warn',success:'o-ok'}[log.level]||'o-line';
      const d = document.createElement('div');
      d.className = cls;
      // 使用 innerHTML 保留换行符
      d.innerHTML = log.message.replace(/\n/g, '<br>');
      el.appendChild(d);
    });
    el.scrollTop = el.scrollHeight;

    const c = document.getElementById('pfLogCnt');
    if (c) c.textContent = logs.length + '行';
  } catch(e) {
    console.error('Failed to load profiler logs:', e);
    el.innerHTML = '<div class="o-dim">加载日志失败</div>';
  }
}

// ── Pod Monitor ───────────────────────────────────────────────────────────────
async function loadSnap(silent = false) {
  const t = getT();
  if(!t.cluster_name || !t.pod_name) { toast('请先配置集群和 Pod','warn'); return; }
  // 静默刷新时不显示 loading，避免闪烁
  if (!silent) {
    const loadingHtml = '<div style="color:var(--tx3);padding:30px;text-align:center"><div style="font-size:14px;margin-bottom:8px">⏳ 加载监控数据中...</div><div style="font-size:11px">首次加载可能需要 10-20 秒（kubectl 采集）</div></div>';
    document.getElementById('pmp-ov').innerHTML = loadingHtml;
    document.getElementById('pmp-dk').innerHTML = loadingHtml;
    document.getElementById('pmp-pr').innerHTML = loadingHtml;
    document.getElementById('pmp-nw').innerHTML = loadingHtml;
  }
  try {
    // snapshot 接口涉及多次 kubectl 调用，超时设为 60 秒
    _snap = await safePost(`${API}/monitor/snapshot`, t, 60000);
    if(_snap.error) { if(!silent) toast(_snap.error, 'error'); return; }
    document.getElementById('pmTs').textContent = new Date().toLocaleTimeString('zh-CN',{hour12:false});
    renderOverview(_snap); renderProcs(_snap); renderNetwork(_snap); renderDisk(_snap); renderEvents(_snap); renderConfig(_snap);
    const ctrs = _snap.pod_info?.containers||[];
    const lcsel = document.getElementById('logCtr');
    if(lcsel) lcsel.innerHTML = ctrs.map(c => `<option value="${c.name}">${c.name}</option>`).join('');
    // start history polling
    fetch(`${API}/monitor/start-polling`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(t)}).catch(()=>{});
    clearInterval(window._histTimer);
    window._histTimer = setInterval(async () => {
      // 只在监控 tab 激活且指标子 tab 可见时才请求
      const monitorTab = document.getElementById('tab-monitor');
      if (!monitorTab || !monitorTab.classList.contains('on')) return;
      const r2 = await fetch(`${API}/monitor/history`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(t)}).catch(()=>null);
      if(r2) { _histData = await r2.json(); if(document.getElementById('pms-mt')?.classList.contains('on')) renderMetrics(_snap); }
    }, 16000);
  } catch(e) { if(!silent) toast('加载失败: '+e.message, 'error'); }
}

// ── 监控面板自动刷新 ─────────────────────────────────────────────────────────────
window._monitorAutoTimer = null;

function toggleAutoRefresh(seconds) {
  seconds = parseInt(seconds) || 0;
  if (window._monitorAutoTimer) {
    clearInterval(window._monitorAutoTimer);
    window._monitorAutoTimer = null;
  }
  if (seconds > 0) {
    // 立即静默刷新一次
    loadSnap(true);
    // 设置定时静默刷新（避免闪烁）
    window._monitorAutoTimer = setInterval(() => {
      const monitorTab = document.getElementById('tab-monitor');
      if (monitorTab && monitorTab.classList.contains('on')) {
        loadSnap(true);
      }
    }, seconds * 1000);
  }
}

function renderOverview(snap) {
  const info = snap.pod_info, top = snap.top_metrics||{}, cm = snap.container_metrics||{};
  const ctrs = info.containers||[];
  const readyN = ctrs.filter(c=>c.ready).length, restN = ctrs.reduce((s,c)=>s+c.restart_count,0);
  const mu = cm.cgroup_mem_usage_bytes||0, ml = cm.cgroup_mem_limit_bytes||0;
  const mp = ml ? Math.round(mu/ml*100) : 0;
  const dp = cm.disk_use_pct ? parseInt(cm.disk_use_pct) : 0;
  const dc = dp>85?'var(--a5)':dp>70?'var(--a4)':'var(--a3)';
  // 获取当前 Arthas 版本
  const curConn = _connections.find(c => c.id === _currentConnId);
  const arthasVer = curConn?.arthas_version || '';
  const arthasVerHtml = arthasVer ? `<div class="sc" style="--sc-ac:var(--a)"><div class="sc-lbl">Arthas</div><div class="sc-val" style="font-size:16px;color:var(--a3)">v${esc(arthasVer)}</div><div class="sc-sub">${curConn?.local_port ? 'port: ' + curConn.local_port : ''}</div></div>` : '';

  let html = `<div class="sg">
    <div class="sc" style="--sc-ac:var(--a)"><div class="sc-lbl">状态</div><div class="sc-val" style="font-size:16px;color:${info.phase==='Running'?'var(--a3)':'var(--a4)'}">${info.phase}</div><div class="sc-sub">${info.namespace}/${info.name}</div></div>
    <div class="sc" style="--sc-ac:var(--a3)"><div class="sc-lbl">容器就绪</div><div class="sc-val">${readyN}<span style="font-size:14px;color:var(--tx2)">/${ctrs.length}</span></div><div class="sc-sub">重启合计: ${restN}</div></div>
    <div class="sc" style="--sc-ac:var(--a4)"><div class="sc-lbl">CPU</div><div class="sc-val" style="font-size:16px">${top.cpu_raw||'—'}</div><div class="sc-sub">毫核 (kubectl top)</div></div>
    <div class="sc" style="--sc-ac:var(--a2)"><div class="sc-lbl">内存</div><div class="sc-val" style="font-size:16px">${mu?fmtSz(mu):(top.memory_raw||'—')}</div><div class="sc-sub">限制: ${ml?fmtSz(ml):'—'}${mp?' · '+mp+'%':''}</div></div>
  </div>
  <div class="sg">
    <div class="sc" style="--sc-ac:var(--a)"><div class="sc-lbl">节点</div><div class="sc-val" style="font-size:13px">${info.node_name||'—'}</div><div class="sc-sub">HostIP: ${info.host_ip||'—'}</div></div>
    <div class="sc" style="--sc-ac:var(--a6)"><div class="sc-lbl">Pod IP</div><div class="sc-val" style="font-size:14px">${info.pod_ip||'—'}</div><div class="sc-sub">QoS: ${info.qos_class||'—'}</div></div>
    <div class="sc" style="--sc-ac:var(--a3)"><div class="sc-lbl">运行时长</div><div class="sc-val">${info.age||'—'}</div><div class="sc-sub">${fmtTs(info.creation_timestamp)}</div></div>
    <div class="sc" style="--sc-ac:${dc}"><div class="sc-lbl">磁盘 /</div><div class="sc-val" style="color:${dc}">${cm.disk_use_pct||'—'}</div><div class="sc-sub">${cm.disk_used||''}/${cm.disk_total||''}${cm.disk_mounts?.length?' · '+cm.disk_mounts.length+'挂载点':''}</div></div>
    ${arthasVerHtml}
  </div>`;

  html += `<div style="margin-bottom:10px"><div style="font-size:10px;color:var(--tx2);text-transform:uppercase;letter-spacing:1px;margin-bottom:7px">Pod 条件</div>
  <div class="conds">${(info.conditions||[]).map(c => `<div class="cond"><div class="cond-t">${c.type}</div><div class="cond-v" style="color:${c.status==='True'?'var(--a3)':'var(--a5)'}">${c.status==='True'?'✓':'✗'} ${c.status}</div></div>`).join('')}</div></div>`;

  html += `<div style="font-size:10px;color:var(--tx2);text-transform:uppercase;letter-spacing:1px;margin-bottom:7px">容器 (${ctrs.length})</div>
  ${ctrs.map((c,i) => {
    const sc = c.state==='running'?'bg':c.state==='waiting'?'by':'br';
    return `<div class="ctr-card">
      <div class="ctr-hd">
        <div><div class="ctr-nm">${esc(c.name)}</div><div class="ctr-img">${esc(c.image)}</div></div>
        <div class="ctr-badges">
          <span class="badge ${sc}">${c.state}</span>
          <span class="badge ${c.ready?'bg':'by'}">${c.ready?'Ready':'NotReady'}</span>
          ${c.restart_count>0?`<span class="badge br">×${c.restart_count}</span>`:''}
          ${c.liveness_probe?'<span class="badge bb">Liveness</span>':''}
          ${c.readiness_probe?'<span class="badge bb">Readiness</span>':''}
        </div>
      </div>
      <div class="ctr-body" id="ctrbd${i}">
        <div class="ctr-res">
          <div class="ctr-ri"><div class="ctr-rl">CPU 请求</div><div class="ctr-rv">${c.requests_cpu||'—'}</div></div>
          <div class="ctr-ri"><div class="ctr-rl">CPU 限制</div><div class="ctr-rv">${c.limits_cpu||'—'}</div></div>
          <div class="ctr-ri"><div class="ctr-rl">内存 请求</div><div class="ctr-rv">${c.requests_mem||'—'}</div></div>
          <div class="ctr-ri"><div class="ctr-rl">内存 限制</div><div class="ctr-rv">${c.limits_mem||'—'}</div></div>
        </div>
        ${c.ports.length?`<div style="font-size:11px;margin-bottom:6px"><b style="color:var(--tx2)">Ports:</b> ${c.ports.map(p=>`<code>${p.containerPort}/${p.protocol||'TCP'}</code>`).join(' ')}</div>`:''}
        ${c.state_reason?`<div style="font-size:11px;color:var(--a4)">原因: ${esc(c.state_reason)}</div>`:''}
        ${c.state_message?`<div style="font-size:10px;color:var(--tx2);margin-top:3px">${esc(c.state_message)}</div>`:''}
      </div>
    </div>`;
  }).join('')}`;

  html += `<div class="two-col">
    <div class="ic"><div class="ic-hd"><span>🏷️</span><span class="ic-tt">Labels</span></div>
    <div class="ic-bd"><div class="tagw">${Object.entries(info.labels||{}).map(([k,v])=>`<div class="ltag"><b>${esc(k)}</b>: ${esc(v)}</div>`).join('')||'<span style="color:var(--tx3)">无</span>'}</div></div></div>
    <div class="ic"><div class="ic-hd"><span>ℹ️</span><span class="ic-tt">基本信息</span></div>
    <div class="ic-bd">${mkv('Service Account',info.service_account||'—')}${mkv('Restart Policy',info.restart_policy)}${mkv('QoS Class',info.qos_class||'—')}${cm.open_fds!=null?mkv('打开 FD 数',cm.open_fds):''}</div></div>
  </div>`;
  document.getElementById('pmp-ov').innerHTML = html;
}
function toggleCtr(i) { const el = document.getElementById(`ctrbd${i}`); if(el) el.classList.toggle('open'); }

function renderMetrics(snap) {
  const cm = snap?.container_metrics||{}, top = snap?.top_metrics||{};
  const mu = cm.cgroup_mem_usage_bytes||0, ml = cm.cgroup_mem_limit_bytes||0, mp = ml?Math.round(mu/ml*100):0;
  const dp = cm.disk_use_pct?parseInt(cm.disk_use_pct):0;
  const lc = snap?.pod_info?.containers?.[0]?.limits_cpu||'';
  let lm = 0; if(lc.endsWith('m')) lm=parseFloat(lc); else if(lc) lm=parseFloat(lc)*1000;
  const cpuM = top.cpu_millicores||0, cp = lm>0?Math.min(100,Math.round(cpuM/lm*100)):0;
  const cc = cp>85?'var(--a5)':cp>70?'var(--a4)':'var(--a)';
  const mc = mp>85?'var(--a5)':mp>70?'var(--a4)':'var(--a2)';
  const dc = dp>85?'var(--a5)':dp>70?'var(--a4)':'var(--a3)';
  const gauge = (pct,color,lbl,unit) => {
    const r=30,cx=38,cy=38,ci=2*Math.PI*r,fill=ci*(1-Math.min(pct,100)/100);
    return `<div class="gauge-ring"><svg viewBox="0 0 76 76"><circle class="gr-bg" cx="${cx}" cy="${cy}" r="${r}"/><circle class="gr-f" cx="${cx}" cy="${cy}" r="${r}" stroke="${color}" stroke-dasharray="${ci}" stroke-dashoffset="${fill}"/></svg><div class="gauge-lbl"><span class="gauge-pct" style="color:${color}">${lbl}</span><span class="gauge-unit">${unit}</span></div></div>`;
  };
  let html = `<div class="ch-grid">
    <div class="gauge-card"><div class="gauge-hd"><div class="gauge-live"></div><span class="gauge-tt">CPU</span><span class="gauge-bv" style="color:${cc}">${top.cpu_raw||'—'}</span></div>
    <div class="gauge-in">${gauge(cp,cc,cp+'%','CPU')}<div class="gauge-rows">${gRow('当前',top.cpu_raw||'—')}${gRow('限制',lc||'未设置')}${gRow('使用率',lm?cp+'%':'—')}${gRow('节流次数',cm.cpu_nr_throttled||'—')}</div></div></div>

    <div class="gauge-card"><div class="gauge-hd"><div class="gauge-live"></div><span class="gauge-tt">内存</span><span class="gauge-bv" style="color:${mc}">${mu?fmtSz(mu):(top.memory_raw||'—')}</span></div>
    <div class="gauge-in">${gauge(mp,mc,mp+'%','MEM')}<div class="gauge-rows">${gRow('cgroup用量',mu?fmtSz(mu):'—')}${gRow('cgroup限制',ml?fmtSz(ml):'—')}${gRow('kubectl top',top.memory_raw||'—')}${gRow('使用率',mp?mp+'%':'—')}</div></div></div>

    <div class="gauge-card"><div class="gauge-hd"><div class="gauge-live"></div><span class="gauge-tt">磁盘 /</span><span class="gauge-bv" style="color:${dc}">${cm.disk_use_pct||'—'}</span></div>
    <div class="gauge-in">${gauge(dp,dc,cm.disk_use_pct||'—','DISK')}<div class="gauge-rows">${gRow('总量',cm.disk_total||'—')}${gRow('已用',cm.disk_used||'—')}${gRow('可用',cm.disk_avail||'—')}</div></div></div>

    <div class="gauge-card"><div class="gauge-hd"><span class="gauge-tt">其他指标</span></div>
    <div class="gauge-in"><div class="gauge-rows" style="width:100%">
      ${gRow('打开 FD 数',cm.open_fds||'—')}
      ${gRow('CPU 节流时间',cm.cpu_throttled_time!=null?(cm.cpu_throttled_time/1e9).toFixed(2)+'s':'—')}
      ${gRow('CPU 节流次数',cm.cpu_nr_throttled||'—')}
      ${gRow('Restart 合计',snap?.pod_info?.containers?.reduce((s,c)=>s+c.restart_count,0)||0)}
      ${gRow('QoS Class',snap?.pod_info?.qos_class||'—')}
    </div></div></div>
  </div>`;

  html += _histData.length>=2
    ? `<div class="ch-grid">
        <div class="ch-card"><div class="ch-hd"><span class="ch-tt">CPU 历史 (毫核)</span><span id="hcv" style="font-size:14px;color:var(--a)"></span></div><div class="ch-body"><canvas id="chCpu" height="70"></canvas></div></div>
        <div class="ch-card"><div class="ch-hd"><span class="ch-tt">内存历史</span><span id="hmv" style="font-size:14px;color:var(--a2)"></span></div><div class="ch-body"><canvas id="chMem" height="70"></canvas></div></div>
      </div>`
    : '<div style="color:var(--tx3);font-size:11px;padding:10px">历史趋势图将在后台采集 15 秒后可用（每 15s 一个采样点）</div>';

  document.getElementById('pmp-mt').innerHTML = html;
  if(_histData.length>=2) {
    const last = _histData[_histData.length-1];
    const cv = document.getElementById('hcv'), mv = document.getElementById('hmv');
    if(cv) cv.textContent = last.cpu_raw||Math.round(last.cpu_m)+'m';
    if(mv) mv.textContent = last.mem_raw||fmtSz(last.mem_bytes||0);
    drawSpark('chCpu', _histData.map(d=>d.cpu_m||0), '#38bdf8');
    drawSpark('chMem', _histData.map(d=>d.mem_bytes||0), '#a78bfa');
  }
}

function drawSpark(id, vals, color) {
  const c = document.getElementById(id); if(!c) return;
  const W = c.parentElement.clientWidth-24, H = 70; c.width=W; c.height=H;
  const ctx = c.getContext('2d'); ctx.clearRect(0,0,W,H);
  const max = Math.max(...vals,1), rng = max||1;
  ctx.strokeStyle='rgba(255,255,255,.05)'; ctx.lineWidth=1;
  for(let i=1;i<4;i++){const y=H*i/4;ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(W,y);ctx.stroke();}
  const pts = vals.map((v,i)=>({x:i/(vals.length-1)*W, y:H-(v/rng)*(H-10)-5}));
  ctx.beginPath(); pts.forEach((p,i)=>i===0?ctx.moveTo(p.x,p.y):ctx.lineTo(p.x,p.y));
  ctx.lineTo(W,H); ctx.lineTo(0,H); ctx.closePath();
  const g=ctx.createLinearGradient(0,0,0,H); g.addColorStop(0,color+'44'); g.addColorStop(1,color+'00');
  ctx.fillStyle=g; ctx.fill();
  ctx.beginPath(); pts.forEach((p,i)=>i===0?ctx.moveTo(p.x,p.y):ctx.lineTo(p.x,p.y));
  ctx.strokeStyle=color; ctx.lineWidth=2; ctx.stroke();
}

function renderProcs(snap) {
  const procs = snap.container_metrics?.processes||[];
  const el = document.getElementById('pmp-pr');
  if(!procs.length) { el.innerHTML='<div style="color:var(--tx3);padding:30px;text-align:center">无进程数据 (需要 Pod Running 且 ps 可用)</div>'; return; }
  // 调试：打印进程数据结构
  console.log('[renderProcs] processes data:', procs.slice(0, 2));
  el.innerHTML = `<div style="background:var(--bg2);border:1px solid var(--ln);border-radius:7px;overflow:hidden;margin-bottom:8px">
    <table class="ptbl"><thead><tr><th>PID</th><th>USER</th><th>%CPU</th><th>%MEM</th><th>STAT</th><th>命令</th></tr></thead>
    <tbody>${procs.map(p=>`<tr><td class="ppid">${esc(p.pid)}</td><td style="color:var(--tx2)">${esc(p.user||'—')}</td><td class="pc">${esc(p.cpu)}%</td><td class="pmem">${esc(p.mem)}%</td><td class="ps-${(p.stat||'S')[0]}">${esc(p.stat||'')}</td><td style="max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(p.cmd)}">${esc(p.cmd)}</td></tr>`).join('')}</tbody>
    </table></div>
  <div style="font-size:10px;color:var(--tx3)">STAT: <code>R</code>=运行中 <code>S</code>=睡眠 <code>D</code>=不可中断 <code>Z</code>=僵尸</div>`;
}

function renderNetwork(snap) {
  const net = snap.container_metrics?.network||[], info = snap.pod_info;
  const el = document.getElementById('pmp-nw');
  let html = `<div class="two-col">
    <div class="ic"><div class="ic-hd"><span>🌐</span><span class="ic-tt">Pod 网络</span></div>
    <div class="ic-bd">${mkv('Pod IP',info.pod_ip||'—')}${mkv('Host IP',info.host_ip||'—')}${mkv('节点',info.node_name||'—')}</div></div>
    <div class="ic"><div class="ic-hd"><span>🔌</span><span class="ic-tt">暴露端口</span></div>
    <div class="ic-bd">${(info.containers||[]).flatMap(c=>c.ports.map(p=>mkv(c.name+':'+p.containerPort,p.protocol||'TCP'))).join('')||mkv('无','—')}</div></div>
  </div>`;
  if(net.length) {
    html += `<div style="background:var(--bg2);border:1px solid var(--ln);border-radius:7px;overflow:hidden">
    <table class="ptbl"><thead><tr><th>接口</th><th>RX 字节</th><th>RX 包</th><th>RX 错误</th><th>TX 字节</th><th>TX 包</th><th>TX 错误</th></tr></thead>
    <tbody>${net.map(n=>`<tr><td style="color:var(--a)">${esc(n.iface)}</td><td style="color:var(--a3)">${fmtSz(n.rx_bytes)}</td><td style="color:var(--a3)">${n.rx_packets.toLocaleString()}</td><td class="${n.rx_errors?'pc':''}">${n.rx_errors}</td><td style="color:var(--a4)">${fmtSz(n.tx_bytes)}</td><td style="color:var(--a4)">${n.tx_packets.toLocaleString()}</td><td class="${n.tx_errors?'pc':''}">${n.tx_errors}</td></tr>`).join('')}</tbody>
    </table></div>
    <div style="font-size:10px;color:var(--tx3);margin-top:6px">注：数据为 Pod 启动至今累计值，非实时速率</div>`;
  }
  el.innerHTML = html;
}

function renderDisk(snap) {
  const cm = snap.container_metrics || {};
  const mounts = cm.disk_mounts || [];
  const el = document.getElementById('pmp-dk');
  if (!mounts.length) {
    el.innerHTML = '<div style="color:var(--tx3);padding:30px;text-align:center">无磁盘数据 (需要 Pod Running 且 df 可用)</div>';
    return;
  }

  // 网络挂载关键字
  const netFs = ['nfs','nfs4','cifs','smb','fuse.sshfs','glusterfs','ceph','9p'];
  const isNet = m => netFs.some(nf => (m.fs_type||'').toLowerCase().includes(nf) || m.filesystem.toLowerCase().includes(nf)) || m.filesystem.includes(':');

  let html = `<div style="font-size:10px;color:var(--tx2);text-transform:uppercase;letter-spacing:1px;margin-bottom:7px">磁盘挂载点 (${mounts.length})</div>`;
  html += `<div style="background:var(--bg2);border:1px solid var(--ln);border-radius:7px;overflow:hidden;margin-bottom:8px">
    <table class="ptbl" style="font-size:11px"><thead><tr><th>Filesystem</th><th>Type</th><th>Size</th><th>Used</th><th>Avail</th><th>Use%</th><th>Mounted on</th></tr></thead>
    <tbody>${mounts.map(m => {
      const pct = m.use_pct_val || 0;
      const barColor = pct > 85 ? 'var(--a5)' : pct > 70 ? 'var(--a4)' : 'var(--a3)';
      const net = isNet(m);
      const netTag = net ? '<span style="font-size:9px;color:var(--a);background:var(--bg3);border-radius:3px;padding:1px 5px;margin-left:4px">网络</span>' : '';
      const fsType = m.fs_type || '';
      return `<tr style="${net?'background:rgba(0,212,255,0.04)':''}">
        <td style="color:var(--tx2);max-width:240px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(m.filesystem)}">${esc(m.filesystem)}${netTag}</td>
        <td style="color:var(--tx3)">${esc(fsType)}</td>
        <td>${esc(m.size)}</td>
        <td style="color:var(--a4)">${esc(m.used)}</td>
        <td style="color:var(--a3)">${esc(m.avail)}</td>
        <td><div style="display:flex;align-items:center;gap:4px"><div style="background:var(--bg3);border-radius:2px;width:50px;height:6px;overflow:hidden;flex-shrink:0"><div style="background:${barColor};height:100%;width:${Math.min(pct,100)}%;border-radius:2px"></div></div><span style="color:${barColor};font-weight:600;min-width:32px">${esc(m.use_pct)}</span></div></td>
        <td style="color:var(--a);font-weight:600">${esc(m.mount)}</td>
      </tr>`;
    }).join('')}</tbody></table></div>`;

  // 网络挂载详情
  const netMounts = mounts.filter(isNet);
  if (netMounts.length) {
    html += `<div style="font-size:10px;color:var(--tx2);text-transform:uppercase;letter-spacing:1px;margin:10px 0 7px">网络挂载详情 (${netMounts.length})</div>`;
    html += netMounts.map(m => {
      const pct = m.use_pct_val || 0;
      const barColor = pct > 85 ? 'var(--a5)' : pct > 70 ? 'var(--a4)' : 'var(--a3)';
      return `<div style="background:var(--bg2);border:1px solid var(--ln);border-radius:7px;padding:12px;margin-bottom:8px;border-left:3px solid var(--a)">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
          <span style="font-size:13px;color:var(--a);font-weight:700">${esc(m.mount)}</span>
          <span style="font-size:11px;color:var(--tx3);background:var(--bg3);border-radius:3px;padding:1px 6px">${esc(m.fs_type||'—')}</span>
          <span style="margin-left:auto;font-size:14px;font-weight:700;color:${barColor}">${esc(m.use_pct)}</span>
        </div>
        <div style="background:var(--bg3);border-radius:3px;height:8px;overflow:hidden;margin-bottom:10px">
          <div style="background:${barColor};height:100%;width:${Math.min(pct,100)}%;border-radius:3px;transition:width .3s"></div>
        </div>
        <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:6px;font-size:11px;margin-bottom:8px">
          <div style="background:var(--bg3);border-radius:4px;padding:6px 8px"><div style="font-size:9px;color:var(--tx3);margin-bottom:2px">总量</div><div style="color:var(--a)">${esc(m.size)}</div></div>
          <div style="background:var(--bg3);border-radius:4px;padding:6px 8px"><div style="font-size:9px;color:var(--tx3);margin-bottom:2px">已用</div><div style="color:var(--a4)">${esc(m.used)}</div></div>
          <div style="background:var(--bg3);border-radius:4px;padding:6px 8px"><div style="font-size:9px;color:var(--tx3);margin-bottom:2px">可用</div><div style="color:var(--a3)">${esc(m.avail)}</div></div>
          <div style="background:var(--bg3);border-radius:4px;padding:6px 8px"><div style="font-size:9px;color:var(--tx3);margin-bottom:2px">使用率</div><div style="color:${barColor}">${esc(m.use_pct)}</div></div>
        </div>
        <div style="font-size:11px;border-top:1px solid var(--ln);padding-top:8px;display:grid;grid-template-columns:auto 1fr;gap:4px 12px">
          <span style="color:var(--tx3)">挂载源</span><span style="color:var(--a);word-break:break-all">${esc(m.mount_source||m.filesystem)}</span>
          <span style="color:var(--tx3)">文件系统</span><span style="color:var(--tx2)">${esc(m.fs_type||'—')}</span>
          <span style="color:var(--tx3)">挂载选项</span><span style="color:var(--tx2);word-break:break-all;font-size:10px">${esc(m.mount_options||'—')}</span>
        </div>
      </div>`;
    }).join('');
  }

  el.innerHTML = html;
}

function renderEvents(snap) {
  const events = snap.events||[], el = document.getElementById('pmp-ev');
  const warns = events.filter(e=>e.type==='Warning').length;
  const bdg = document.getElementById('evBdg');
  if(bdg) bdg.innerHTML = warns>0 ? `<span style="margin-left:4px;background:var(--a4);color:#0b0f18;border-radius:10px;padding:1px 6px;font-size:9px">${warns}</span>` : '';
  if(!events.length) { el.innerHTML='<div style="color:var(--tx3);padding:30px;text-align:center">无事件记录</div>'; return; }
  const icons = {Warning:'⚠️',Normal:'✅',Error:'❌'};
  el.innerHTML = `<div class="ev-list">${events.map(e=>`<div class="ev-item ${e.type||'Normal'}">
    <div class="ev-icon">${icons[e.type]||'ℹ️'}</div>
    <div class="ev-body">
      <div class="ev-reason">${esc(e.reason)}${e.count>1?`<span class="ev-cnt">×${e.count}</span>`:''}</div>
      <div class="ev-msg">${esc(e.message)}</div>
      <div class="ev-meta">${esc(e.source||'')}  ${fmtTs(e.last_time)}</div>
    </div>
  </div>`).join('')}</div>`;
}

function renderConfig(snap) {
  const info = snap.pod_info, el = document.getElementById('pmp-cf');
  const ann = info.annotations||{}, vols = info.volumes||{}, ctrs = info.containers||[];
  el.innerHTML = `<div class="two-col">
    <div class="ic"><div class="ic-hd"><span>📌</span><span class="ic-tt">Annotations</span></div>
    <div class="ic-bd" style="max-height:180px;overflow-y:auto">
      ${Object.keys(ann).length ? Object.entries(ann).map(([k,v])=>mkv(k,v.length>80?v.slice(0,80)+'…':v)).join('') : '<span style="color:var(--tx3)">无</span>'}
    </div></div>
    <div class="ic"><div class="ic-hd"><span>💾</span><span class="ic-tt">Volumes (${(vols||[]).length})</span></div>
    <div class="ic-bd">${(vols||[]).map(v=>mkv(v.name,`<code>${v.type}</code>`,true)).join('')||'<span style="color:var(--tx3)">无</span>'}</div></div>
  </div>
  ${ctrs.map(c=>`<div class="ic" style="margin-bottom:10px">
    <div class="ic-hd"><span>📦</span><span class="ic-tt">容器: ${esc(c.name)}</span></div>
    <div class="ic-bd">
      <div class="two-col" style="margin:0">
        <div>${mkv('Image',c.image)}${mkv('Pull Policy',c.image_pull_policy)}${mkv('State',c.state)}${mkv('Ready',c.ready?'✓ true':'✗ false')}${mkv('Restart Count',c.restart_count)}</div>
        <div>${mkv('CPU Requests',c.requests_cpu||'—')}${mkv('CPU Limits',c.limits_cpu||'—')}${mkv('Mem Requests',c.requests_mem||'—')}${mkv('Mem Limits',c.limits_mem||'—')}</div>
      </div>
      ${c.env.length?`<div style="margin-top:9px"><div style="font-size:10px;color:var(--tx2);text-transform:uppercase;letter-spacing:1px;margin-bottom:5px">环境变量 (前20)</div><div style="max-height:160px;overflow-y:auto">${c.env.map(e=>mkv(e.name,typeof e.value==='string'?e.value:'[valueFrom]')).join('')}</div></div>`:''}
      ${c.volume_mounts.length?`<div style="margin-top:9px"><div style="font-size:10px;color:var(--tx2);text-transform:uppercase;letter-spacing:1px;margin-bottom:5px">Volume Mounts</div>${c.volume_mounts.map(vm=>mkv(vm.name,`${vm.mountPath}${vm.readOnly?' (ro)':''}`)).join('')}</div>`:''}
    </div>
  </div>`).join('')}
  ${info.tolerations?.length?`<div class="ic"><div class="ic-hd"><span>🔑</span><span class="ic-tt">Tolerations</span></div><div class="ic-bd">${info.tolerations.map(t=>mkv(t.key||'(全部)',`${t.operator||'Exists'}${t.effect?' : '+t.effect:''}`)).join('')}</div></div>`:''}`;
}

// ── Logs ──────────────────────────────────────────────────────────────────────
async function loadLogs() {
  const t = getT();
  if(!t.cluster_name || !t.pod_name) { toast('请先配置目标 Pod','warn'); return; }
  const container = document.getElementById('logCtr').value;
  const tail = parseInt(document.getElementById('logTail').value);
  const since = document.getElementById('logSince').value;
  const filter = document.getElementById('logFilt').value.trim();
  const box = document.getElementById('logBox');
  box.innerHTML = '<div class="o-dim">加载中...</div>';
  try {
    const r = await fetch(`${API}/monitor/logs`, {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({...t, container, tail, since})});
    // 先检查 Content-Type，防止 server 返回 HTML 错误页被误当 JSON 解析
    const ct = r.headers.get('content-type') || '';
    if(!ct.includes('application/json')) {
      const text = await r.text();
      throw new Error(`服务器返回非 JSON 响应 (${r.status})。\n请确认 server.py 正在运行（python server.py）\n响应前100字符: ${text.slice(0,100)}`);
    }
    if(!r.ok) {
      const e = await r.json();
      throw new Error(e.error || `请求失败 (${r.status})`);
    }
    const d = await r.json(); _logRaw = d.logs||'';
    renderLogs(_logRaw, filter);
    document.getElementById('logStat').textContent = `${_logRaw.split('\n').length} 行`;
    document.getElementById('btnDlLog').disabled = !_logRaw;
  } catch(e) {
    box.innerHTML = `<div class="o-err" style="white-space:pre-wrap;font-size:11px">加载失败: ${esc(e.message)}</div>`;
  }
}

function renderLogs(raw, filter) {
  const box = document.getElementById('logBox');
  const lines = raw.split('\n');
  const html = lines.map(line => {
    let cls = 'll-i';
    const ll = line.toLowerCase();
    if(ll.includes('error')||ll.includes('exception')||ll.includes('fatal')) cls='ll-e';
    else if(ll.includes('warn')) cls='ll-w';
    else if(ll.includes('debug')||ll.includes('trace')) cls='ll-d';
    let content = esc(line), hiCls = '';
    if(filter && line.toLowerCase().includes(filter.toLowerCase())) {
      hiCls = ' ll-hi';
      const re = new RegExp(filter.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'), 'gi');
      content = content.replace(re, m => `<mark style="background:rgba(251,191,36,.25);color:var(--a6)">${esc(m)}</mark>`);
    }
    return `<div class="${cls}${hiCls}">${content}</div>`;
  }).join('');
  box.innerHTML = html; box.scrollTop = box.scrollHeight;
}

function toggleWrap() {
  _logWrap = !_logWrap;
  document.getElementById('logBox').style.whiteSpace = _logWrap ? 'pre-wrap' : 'pre';
}

function downloadLogsFile() {
  if(!_logRaw) { toast('请先加载日志','warn'); return; }
  const t = getT();
  const ctr = document.getElementById('logCtr').value || 'default';
  const fname = `logs-${t.pod_name}-${ctr||'default'}-${fmtNowTs()}.log`;
  const blob = new Blob([_logRaw], {type:'text/plain;charset=utf-8'});
  const url = URL.createObjectURL(blob); const a = document.createElement('a');
  a.href=url; a.download=fname; a.click(); URL.revokeObjectURL(url);
  toast(`已下载: ${fname}`, 'success');
}

// ── Pod File Browser ──────────────────────────────────────────────────────────
async function fbList() {
  const t = getT();
  if(!t.cluster_name || !t.pod_name) { toast('请先配置集群和 Pod','warn'); return; }
  const path = document.getElementById('fbPath').value || '/tmp';
  _fbCurPath = path; _fbSelected = null;
  document.getElementById('fbDlBtn').disabled = true;
  document.getElementById('fbPreviewBtn').disabled = true;
  document.getElementById('fbSelInfo').textContent = '';
  document.getElementById('fbStatus').textContent = '加载中...';
  document.getElementById('fbCurPath').textContent = path;
  document.getElementById('fbPreviewBox').classList.remove('show');

  try {
    const r = await fetch(`${API}/pod/files`, {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({...t, path})});
    const d = await r.json();
    if(d.error) { document.getElementById('fbStatus').textContent = ''; document.getElementById('fbList').innerHTML = `<div style="color:var(--a5);padding:20px;font-size:12px">✗ ${esc(d.error)}</div>`; return; }
    const files = d.files||[];
    document.getElementById('fbStatus').textContent = '';
    document.getElementById('fbCount').textContent = `  ${files.length} 项`;

    let html = '';
    // Parent dir shortcut
    if(path !== '/') {
      html += `<div class="fb-item fb-dir" onclick="fbNav('..')">
        <span class="fb-icon">📁</span>
        <span class="fb-name">..</span>
        <span class="fb-meta" style="color:var(--tx3)">上级目录</span>
      </div>`;
    }
    if(!files.length) { html += `<div style="color:var(--tx3);padding:20px;text-align:center;font-size:12px">目录为空</div>`; }
    for(const f of files) {
      const icon = f.is_dir ? '📁' : getFileIcon(f.name);
      html += `<div class="fb-item ${f.is_dir?'fb-dir':''}"
        data-path="${esc(f.path)}" data-name="${esc(f.name)}" data-isdir="${f.is_dir}"
        onclick="fbSelectEl(this)" ondblclick="fbDblClickEl(this)">
        <span class="fb-icon">${icon}</span>
        <span class="fb-name" title="${esc(f.path)}">${esc(f.name)}${f.is_link?' ↗':''}</span>
        <span class="fb-size">${f.is_dir?'':esc(f.size)}</span>
        <span class="fb-meta">${esc(f.modified)}</span>
      </div>`;
    }
    document.getElementById('fbList').innerHTML = html;
  } catch(e) { document.getElementById('fbStatus').textContent = ''; document.getElementById('fbList').innerHTML = `<div style="color:var(--a5);padding:20px;font-size:12px">✗ ${esc(e.message)}</div>`; }
}

function getFileIcon(name) {
  const n = name.toLowerCase();
  if(n.endsWith('.log')||n.endsWith('.txt')) return '📄';
  if(n.endsWith('.java')||n.endsWith('.class')) return '☕';
  if(n.endsWith('.json')||n.endsWith('.yaml')||n.endsWith('.yml')) return '📋';
  if(n.endsWith('.sh')||n.endsWith('.bash')) return '⚡';
  if(n.endsWith('.html')||n.endsWith('.htm')) return '🔥';
  if(n.endsWith('.jfr')||n.endsWith('.hprof')) return '📊';
  if(n.endsWith('.zip')||n.endsWith('.tar')||n.endsWith('.gz')) return '📦';
  if(n.endsWith('.xml')||n.endsWith('.properties')||n.endsWith('.conf')) return '⚙️';
  return '📄';
}

function fbSelectEl(el) {
  document.querySelectorAll('.fb-item').forEach(e => e.classList.remove('selected'));
  el.classList.add('selected');
  const path  = el.dataset.path;
  const name  = el.dataset.name;
  const isDir = el.dataset.isdir === 'true';
  if(!isDir) {
    _fbSelected = path;
    document.getElementById('fbDlBtn').disabled = false;
    document.getElementById('fbPreviewBtn').disabled = false;
    document.getElementById('fbSelInfo').textContent = `已选: ${name}`;
    document.getElementById('fbPreviewBox').classList.remove('show');
  } else {
    _fbSelected = null;
    document.getElementById('fbDlBtn').disabled = true;
    document.getElementById('fbPreviewBtn').disabled = true;
    document.getElementById('fbSelInfo').textContent = `目录: ${name}`;
  }
}

function fbDblClickEl(el) {
  const path  = el.dataset.path;
  const isDir = el.dataset.isdir === 'true';
  if(isDir) { document.getElementById('fbPath').value = path; fbList(); }
}

function fbNav(relative) {
  const cur = document.getElementById('fbPath').value || '/';
  let newPath;
  if(relative === '..') {
    const parts = cur.split('/').filter(Boolean);
    parts.pop();
    newPath = '/' + parts.join('/') || '/';
  } else {
    newPath = (cur.endsWith('/') ? cur : cur+'/') + relative;
  }
  document.getElementById('fbPath').value = newPath;
  fbList();
}

function fbUp() {
  fbNav('..');
}

async function fbDownload() {
  if(!_fbSelected) { toast('请先选择文件','warn'); return; }
  const t = getT();
  if(!t.cluster_name || !t.pod_name) { toast('请先配置集群和 Pod','warn'); return; }
  document.getElementById('fbDlBtn').disabled = true;
  document.getElementById('fbStatus').textContent = '下载中...';
  try {
    // Use form POST to trigger browser download
    const form = document.createElement('form'); form.method='POST'; form.action=`${API}/pod/files/download`;
    form.style.display='none'; form.target='_blank';
    // Can't directly POST JSON to get file download, so use fetch+blob
    console.log('fbDownload:', {t, path: _fbSelected});
    const r = await fetch(`${API}/pod/files/download`, {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({...t, path: _fbSelected})
    });
    if(!r.ok) {
      const e = await r.json();
      const detail = [e.error, e.debug ? JSON.stringify(e.debug) : null].filter(Boolean).join('\n');
      throw new Error(detail || '下载失败');
    }
    const blob = await r.blob();
    const fname = _fbSelected.split('/').pop();
    const url = URL.createObjectURL(blob); const a = document.createElement('a');
    a.href=url; a.download=fname; a.click(); URL.revokeObjectURL(url);
    toast(`已下载: ${fname}`, 'success');
    document.getElementById('fbStatus').textContent = `✓ 已下载 ${fname}`;
  } catch(e) {
    const msg = e.message || String(e);
    toast(msg.split('\n')[0], 'error');
    document.getElementById('fbStatus').textContent = '✗ ' + msg.split('\n')[0];
  }
  document.getElementById('fbDlBtn').disabled = false;
}

async function fbPreview() {
  if(!_fbSelected) return;
  const t = getT();
  const box = document.getElementById('fbPreviewBox');
  box.textContent = '加载中...'; box.classList.add('show');
  try {
    const d = await safePost(`${API}/pod/files/tail`, {...t, path: _fbSelected, lines: 200});
    if(d.error) { box.textContent = '✗ ' + d.error; return; }
    box.textContent = d.content || '(空文件)';
  } catch(e) { box.textContent = '✗ ' + e.message; }
}

// ── Cluster management ─────────────────────────────────────────────────────────
async function loadClusters() {
  try { const r = await fetch(`${API}/clusters`); const d = await r.json(); _clusters = d.clusters || d || []; } catch { _clusters = []; }
  // 恢复上次选中的集群（或自动选中第一个）
  if (!_ac && _clusters.length) {
    const saved = (() => { try { return localStorage.getItem('arthas_ac'); } catch { return null; } })();
    const found = saved && _clusters.find(c => c.name === saved);
    // 优先恢复上次选中，没有则自动选第一个
    const target = found ? found.name : _clusters[0].name;
    _ac = target;
    try { localStorage.setItem('arthas_ac', target); } catch {}
  }
  renderSidebar();
  // 自动 ping 当前集群
  if (_ac) pingCluster(_ac);
}

function renderSidebar() {
  const el = document.getElementById('sbCls');
  if(!_clusters.length) { el.innerHTML='<div class="sb-empty">暂无集群<br>点击 ＋ 添加</div>'; return; }
  el.innerHTML = _clusters.map((c, idx) => {
    const safeName = esc(c.name);
    // 使用 data 属性存储集群名称，避免 HTML 属性中的字符串转义问题
    return `
    <div class="sb-itm ${_ac===c.name?'on':''}" data-cluster-name="${safeName}" data-cluster-idx="${idx}">
      <div class="sb-dt" id="sbd_${btoa(encodeURIComponent(c.name)).replace(/[^a-zA-Z0-9]/g,'_')}"></div>
      <span class="sb-nm" title="${safeName}">${safeName}</span>
      <button class="sb-edit" data-action="edit" title="编辑">✎</button>
      <button class="sb-del" data-action="del" title="删除">✕</button>
    </div>`;
  }).join('');
  
  // 绑定事件委托，避免内联 onclick 的字符串转义问题
  el.querySelectorAll('.sb-itm').forEach(item => {
    const name = item.dataset.clusterName;
    item.addEventListener('click', (e) => {
      if (e.target.tagName === 'BUTTON') return; // 按钮有单独处理
      selCluster(name);
    });
    item.querySelector('[data-action="edit"]').addEventListener('click', (e) => {
      e.stopPropagation();
      openEditCluster(name);
    });
    item.querySelector('[data-action="del"]').addEventListener('click', (e) => {
      e.stopPropagation();
      delCluster(name);
    });
  });
}

function selCluster(name) {
  _ac = name;
  try { localStorage.setItem('arthas_ac', name); } catch {}
  renderSidebar(); pingCluster(name);
  // Auto-load namespaces for this cluster
  const cached = window._clusterNs && window._clusterNs[name];
  if(cached) { populateNsList(cached); }
  else { autoLoadNs(name); }
}

async function pingCluster(name) {
  const did = 'sbd_' + btoa(encodeURIComponent(name)).replace(/[^a-zA-Z0-9]/g,'_');
  const dot = document.getElementById(did); if(dot) dot.className='sb-dt pinging';
  try {
    const r = await fetch(`${API}/clusters/${encodeURIComponent(name)}/test`, {method:'POST'});
    const d = await r.json();
    if(dot) dot.className = 'sb-dt ' + (d.ok?'ok':'err');
  } catch { if(dot) dot.className='sb-dt err'; }
}

async function delCluster(name) {
  if(!confirm(`删除集群 "${name}"？`)) return;
  await fetch(`${API}/clusters/${encodeURIComponent(name)}`, {method:'DELETE'});
  if(_ac===name) _ac=null; loadClusters();
}

let _editingCluster = null;

function openAddCluster() {
  _editingCluster = null;
  document.getElementById('mName').value = '';
  document.getElementById('mKc').value   = '';
  document.getElementById('mCtx').value  = '';
  document.getElementById('mCtxWrap').style.display = 'none';
  document.getElementById('mErr').style.display = 'none';
  document.getElementById('m-tt').textContent = '添加 K8s 集群';
  document.getElementById('clModal').classList.add('open');
}

function openEditCluster(name) {
  const c = _clusters.find(x => x.name===name);
  if(!c) return;
  _editingCluster = name;
  document.getElementById('mName').value = c.name;
  document.getElementById('mKc').value   = c.kubeconfig;
  document.getElementById('mCtx').value  = c.context||'';
  document.getElementById('mCtxWrap').style.display = 'none';
  document.getElementById('mErr').style.display = 'none';
  document.getElementById('m-tt').textContent = `编辑集群: ${name}`;
  document.getElementById('clModal').classList.add('open');
}

async function autoLoadNs(clusterName) {
  // Auto-populate namespace selector after cluster add/select
  try {
    const r = await fetch(`${API}/clusters/${encodeURIComponent(clusterName)}/namespaces`);
    const d = await r.json();
    const ns = d.namespaces||[];
    if(!ns.length) return;
    // store in global for reuse
    window._clusterNs = window._clusterNs||{};
    window._clusterNs[clusterName] = ns;
    // If this is the active cluster, populate pt-sel
    if(clusterName === _ac) populateNsList(ns);
  } catch {}
}

function populateNsList(nsList) {
  let dl = document.getElementById('nsList');
  if(!dl) { dl=document.createElement('datalist'); dl.id='nsList'; document.body.appendChild(dl); }
  dl.innerHTML = nsList.map(n=>`<option value="${n}">`).join('');
  document.getElementById('ptNs').setAttribute('list','nsList');
}
function closeModal() { document.getElementById('clModal').classList.remove('open'); }

async function fetchCtxs() {
  const kc = document.getElementById('mKc').value.trim();
  if(!kc) { toast('请先填写 kubeconfig 路径','warn'); return; }
  try {
    // 使用专用接口直接获取 contexts，不创建/删除临时集群，避免服务器崩溃
    const r2 = await fetch(`${API}/contexts`, {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({kubeconfig: kc}),
    });
    if(!r2.ok) { const e=await r2.json(); toast(e.error || '获取失败', 'error'); return; }
    const d = await r2.json();
    const sel = document.getElementById('mCtxSel');
    sel.innerHTML = '<option value="">—</option>' + (d.contexts||[]).map(c=>`<option value="${c}">${c}</option>`).join('');
    if(d.current) {
      sel.value = d.current;
      document.getElementById('mCtx').value = d.current;  // 同步到文本框，保存时能读取
    }
    document.getElementById('mCtxWrap').style.display = 'block';
    toast(`找到 ${(d.contexts||[]).length} 个 context`);
  } catch(e) { toast('获取失败: '+e.message, 'error'); }
}

async function saveCluster() {
  const name = document.getElementById('mName').value.trim();
  const kc   = document.getElementById('mKc').value.trim();
  const ctx  = document.getElementById('mCtx').value.trim();
  const err  = document.getElementById('mErr');
  if(!name || !kc) { err.textContent='名称和路径必填'; err.style.display='block'; return; }
  err.style.display='none';
  try {
    // 编辑已有集群用 POST（避免某些代理/防火墙拦截 PUT），新增也用 POST
    // 编辑时 URL 带旧名称，后端通过 URL 参数识别是更新操作
    const url    = _editingCluster
      ? `${API}/clusters/${encodeURIComponent(_editingCluster)}`
      : `${API}/clusters`;
    console.log('[saveCluster] _editingCluster=', _editingCluster, 'url=', url);
    const r = await fetch(url, {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({name, kubeconfig:kc, context:ctx}),
    });
    const d = await r.json();
    if(!r.ok) { err.textContent = d.error; err.style.display='block'; return; }
    const wasEditing = !!_editingCluster;
    _editingCluster = null;
    closeModal();
    toast(wasEditing ? '集群已更新' : '集群已添加', 'success');
    await loadClusters();
    // 选中集群但不立即 ping（ping 是异步的，不阻塞保存响应）
    _ac = name;
    try { localStorage.setItem('arthas_ac', name); } catch {}
    renderSidebar();
    // 延迟 ping，避免 kubectl 阻塞导致前端报错
    setTimeout(() => pingCluster(name), 800);
    // Auto-load namespaces for sidebar display
    autoLoadNs(name);
  } catch(e) { err.textContent=e.message; err.style.display='block'; }
}

// ── Tasks & Files ──────────────────────────────────────────────────────────────
async function loadHistory() {
  await loadPfHistory(false); // 显示所有连接的历史
  await loadLocalFiles();
  const t = (window._pfTasksCount||0) + (window._dlFilesCount||0);
  const el = document.getElementById('cntHistory');
  if(el) el.textContent = t;
}

async function loadPfHistory(filterByCurrentConn = false) {
  try {
    const r = await fetch(`${API}/profile/tasks`); const tasks = await r.json();

    // 如果指定只显示当前连接的历史，则过滤任务
    let filteredTasks = tasks;
    if (filterByCurrentConn && _currentConnId) {
      const currentConn = _connections.find(c => c.id === _currentConnId);
      if (currentConn) {
        filteredTasks = tasks.filter(t =>
          t.config.cluster === currentConn.cluster_name &&
          t.config.namespace === currentConn.namespace &&
          t.config.pod === currentConn.pod_name
        );
      }
    }

    window._pfTasksCount = filteredTasks.length;
    document.getElementById('cntPfTasks').textContent = filteredTasks.length;

    // Update history panel only
    const el = document.getElementById('hist-panel-profiler');
    if(!el) return;
    if(!filteredTasks.length) {
      el.innerHTML='<div style="color:var(--tx3);text-align:center;padding:40px">暂无任务</div>';
      return;
    }
    const icons = {completed:'✅',failed:'❌',running:'⏳',starting:'⏳'};
    const labels = {completed:'完成',failed:'失败',running:'运行中',starting:'启动中'};
    const bcls = {completed:'st-ok',failed:'st-fail',running:'st-run',starting:'st-run'};
    const showUser = typeof isAdmin === 'function' && isAdmin();  // admin 显示用户名
    const eventLabels = {
      'threaddump': '线程转储',
      'heapdump': '堆转储',
      'cpu': 'CPU',
      'alloc': '内存分配',
      'lock': '锁竞争',
      'wall': 'Wall',
      'default': 'JFR默认',
      'profile': 'JFR Profile'
    };
    el.innerHTML = filteredTasks.map(t => {
      const mode = t.config.mode || 'profiler';
      const event = t.config.event || '';
      const duration = t.config.duration || 0;
      const eventDisplay = eventLabels[event] || event;
      const durationDisplay = (mode === 'threaddump' || mode === 'heapdump' || duration === 0) ? '-' : `${duration}s`;
      const metaParts = [`${esc(t.config.cluster)}/${esc(t.config.namespace)}`, mode, eventDisplay, durationDisplay, t.config.format, fmtTs(t.created_at)];
      if (showUser && t.username) metaParts.push(`<span style="color:var(--a)">@${esc(t.username)}</span>`);
      return `<div class="tc">
      <div class="tc-inner">
        <div style="font-size:18px;flex-shrink:0">${icons[t.status]||'❓'}</div>
        <div class="tc-info">
          <div class="tc-title">${esc(t.config.pod)} <span class="st-badge ${bcls[t.status]||''}">${labels[t.status]||t.status}</span></div>
          <div class="tc-meta">${metaParts.join(' · ')}</div>
        </div>
        ${t.has_file?`<button class="btn btn-dl" style="padding:5px 10px;font-size:11px;cursor:pointer" onclick="downloadProfilerTask('${t.id}', '${t.file_name||'output'}')">↓ 下载</button>`:''}
      </div>
    </div>`;
    }).join('');
  } catch {}
}

async function loadLocalFiles() {
  try {
    const r = await fetch(`${API}/files`); const files = await r.json();
    window._dlFilesCount = files.length;
    document.getElementById('cntDlFiles').textContent = files.length;
    const el = document.getElementById('hist-panel-files');
    if(!el) return;
    if(!files.length) { el.innerHTML='<div style="color:var(--tx3);text-align:center;padding:40px">暂无下载记录</div>'; return; }
    const icon = n => n.endsWith('.html')?'🔥':n.endsWith('.jfr')?'📊':n.endsWith('.log')?'📄':'💾';
    const showUser = typeof isAdmin === 'function' && isAdmin();  // 只有 admin 显示用户名
    
    // 根据是否 admin 显示不同表头
    let headerHtml = '';
    if (showUser) {
      headerHtml = `<div style="font-size:11px;color:var(--tx2);margin-bottom:10px;display:flex;align-items:center;gap:8px">
        <span>包含：JProfiler 采样报告 + 文件浏览器下载的文件</span>
        <span style="color:var(--a);background:rgba(122,162,247,0.1);padding:2px 6px;border-radius:3px;font-size:10px">按用户隔离</span>
      </div>`;
    } else {
      headerHtml = `<div style="font-size:11px;color:var(--tx2);margin-bottom:10px">
        包含：JProfiler 采样报告 + 文件浏览器下载的文件（均保存在 <code>profiler_output/</code>）
      </div>`;
    }
    
    el.innerHTML = headerHtml + files.map(f => {
      // meta 信息：大小 · 时间 · 用户（admin 才显示）
      const metaParts = [fmtSz(f.size), fmtTs(f.modified)];
      if (showUser && f.username) {
        metaParts.push(`<span style="color:var(--a)">@${esc(f.username)}</span>`);
      }
      return `<div class="frow">
        <div style="font-size:16px">${icon(f.name)}</div>
        <div class="fi-info"><div class="fi-nm">${esc(f.name)}</div><div class="fi-meta">${metaParts.join(' · ')}</div></div>
        <button class="btn btn-dl" style="padding:5px 10px;font-size:11px;cursor:pointer" onclick="downloadOutputFile('${esc(f.name)}')">↓</button>
      </div>`;
    }).join('');
  } catch {}
}

// ── Init ────────────────────────────────────────────────────────────────────────
// 等待 DOM 加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
  initUserDisplay();
  loadConnections();
  renderCmdPal();
  checkHealth();
  setInterval(checkHealth, 8000);
  // 连接健康检查：加载后 3 秒首次检查，之后每 60 秒检查一次
  setTimeout(checkConnectionsHealth, 3000);
  setInterval(checkConnectionsHealth, 60000);
  loadClusters();
  loadLocalFiles();
  
  // Pre-load history counts after a short delay
  setTimeout(loadHistory, 1500);
});

// Pre-cache namespaces for all clusters
setTimeout(async () => {
  if (_clusters && Array.isArray(_clusters)) {
    for (const c of _clusters) {
      await autoLoadNs(c.name).catch(() => {});
    }
  }
}, 2500);

// Fix pm-lg panel: it should be hidden initially, shown by switchPm()
const _pmLg = document.querySelector('#pmp-lg');
if (_pmLg) _pmLg.style.display = 'none';

// ── 全局函数暴露 ─────────────────────────────────────────────────────────
// 将所有需要在 HTML onclick 中调用的函数暴露到 window 对象
// 注意：所有函数必须在暴露之前定义完成

// 集群相关
window.openAddCluster = openAddCluster;
window.openEditCluster = openEditCluster;
window.closeModal = closeModal;
window.saveCluster = saveCluster;
window.delCluster = delCluster;
window.selCluster = selCluster;
window.pingCluster = pingCluster;
window.fetchCtxs = fetchCtxs;
window.autoLoadNs = autoLoadNs;
window.loadPods = loadPods;
window.loadClusters = loadClusters;

// 连接相关
window.renderConnList = renderConnList;
window.switchConnection = switchConnection;
window.deleteConnection = deleteConnection;
window.checkPod = checkPod;
window.arthasConnect = arthasConnect;

// 标签页切换
window.switchTab = switchTab;
window.switchPm = switchPm;
window.switchHistTab = switchHistTab;

// 命令执行
window.runCmd = runCmd;
window.interruptCmd = interruptCmd;
window.clearConOut = clearConOut;

// Profiler
window.pfStart = pfStart;
window.pfSetMode = pfSetMode;
window.pfSetDur = pfSetDur;
window.pfClearLog = pfClearLog;
window.togglePfHistory = togglePfHistory;

// 监控
window.loadSnap = loadSnap;
window.toggleAutoRefresh = toggleAutoRefresh;
window.loadLogs = loadLogs;
window.downloadLogsFile = downloadLogsFile;
window.toggleWrap = toggleWrap;

// 文件浏览器
window.fbList = fbList;
window.fbUp = fbUp;
window.fbNav = fbNav;
window.fbDownload = fbDownload;
window.fbPreview = fbPreview;
window.fbSelectEl = fbSelectEl;
window.fbDblClickEl = fbDblClickEl;

// 终端
window.termInit = termInit;
window.termClear = termClear;

// 命令面板
window.toggleCmdCat = toggleCmdCat;
window.selCmd = selCmd;
window.buildAndRun = buildAndRun;

// 其他
window.doLogout = doLogout;
window.loadHistory = loadHistory;
window.gcDownloadPath = gcDownloadPath;
window.gcPreviewPath = gcPreviewPath;
window.toggleCtr = toggleCtr;

// 来自 utils.js 的工具函数
window.mkv = mkv;
window.gRow = gRow;
window.toast = toast;

// ── 组件模块函数暴露 ─────────────────────────────────────────────────────
// 来自 components/connections.js
window.addConnection = addConnection;
window.removeConnection = removeConnection;



// 来自 components/profiler.js
window.pfSetTask = pfSetTask;
window.pfGetTask = pfGetTask;
window.getPfState = getPfState;
window.renderProfilerStatus = renderProfilerStatus;

// 来自 components/monitor.js
window.getMetrics = getMetrics;
window.setMetrics = setMetrics;
window.startMetricsPolling = startMetricsPolling;
window.stopMetricsPolling = stopMetricsPolling;
window.renderOverview = renderOverview;
window.renderProcs = renderProcs;

// 来自 components/filebrowser.js
window.fbGetCurPath = fbGetCurPath;
window.fbSetCurPath = fbSetCurPath;
window.fbGetFiles = fbGetFiles;
window.renderFileBrowser = renderFileBrowser;
