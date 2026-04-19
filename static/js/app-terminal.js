// ═══════════════════════════════════════════════════════════════════════════════
// TERMINAL  —  macOS / 阿里云 ECS 终端风格
// ═══════════════════════════════════════════════════════════════════════════════

const _T = {
  hist:      [],     // command history list
  histIdx:   -1,     // -1 = not browsing history
  cwd:       '/',    // current working directory inside pod
  host:      'pod',  // pod hostname
  user:      'root', // shell user
  running:   false,  // command executing
  connected: false,
};

// ── DOM helpers ────────────────────────────────────────────────────────────────
const termOut = () => document.getElementById('termOut');

function termScroll() {
  const el = termOut(); el.scrollTop = el.scrollHeight;
}

/** Append a line element to the output area */
function termLine(text, cls = 'xl') {
  const el = termOut();
  const d  = document.createElement('div');
  d.className = cls;
  if(text === '') { d.innerHTML = '&nbsp;'; }
  else { d.textContent = text; }
  el.appendChild(d);
  termScroll();
  return d;
}

/** Append a prompt + command echo line (the "$ cmd" line) */
function termEcho(cmd) {
  const el   = termOut();
  const row  = document.createElement('div');
  row.className = 'xterm-pline';
  row.innerHTML =
    `<span class="xterm-ps1">${termPs1Html()}</span>` +
    `<span class="xterm-cmd-echo">${esc(cmd)}</span>`;
  el.appendChild(row);
  termScroll();
}

// ── Prompt rendering ───────────────────────────────────────────────────────────
function termPs1Html() {
  const cwdShort = _T.cwd === `/home/${_T.user}` ? '~' :
    _T.cwd.startsWith(`/home/${_T.user}/`) ? '~' + _T.cwd.slice(`/home/${_T.user}`.length) :
    _T.cwd;
  return (
    `<span class="ps1-user">${esc(_T.user)}</span>` +
    `<span class="ps1-at">@</span>` +
    `<span class="ps1-host">${esc(_T.host)}</span>` +
    `<span class="ps1-sep">:</span>` +
    `<span class="ps1-path">${esc(cwdShort)}</span>` +
    `<span class="ps1-sym"> # </span>`
  );
}

function termUpdatePrompt() {
  const cwdShort = _T.cwd === `/home/${_T.user}` ? '~' :
    _T.cwd.startsWith(`/home/${_T.user}/`) ? '~' + _T.cwd.slice(`/home/${_T.user}`.length) :
    _T.cwd;
  const setEl = (id, val) => { const e = document.getElementById(id); if(e) e.textContent = val; };
  setEl('termUser',   _T.user);
  setEl('termHostP',  _T.host);
  setEl('termCwdP',   cwdShort);
  // Also update the titlebar
  const title = document.getElementById('termTitle');
  if(title) title.textContent = `${_T.user}@${_T.host}:${cwdShort}`;
}

// ── Connection ─────────────────────────────────────────────────────────────────
async function termInit() {
  if(window.ConnectionGuard && !ConnectionGuard.guard('terminal')) return;
  const t = getT();
  if(!t.cluster_name || !t.pod_name) {
    toast('请先在左侧配置集群和 Pod','warn');
    return;
  }

  const btn = document.getElementById('termConnBtn');
  btn.textContent = '连接中...';

  // Print connection banner
  if(!_T.connected) {
    termLine('');
    termLine('  ┌─────────────────────────────────────────────────────┐', 'xl-dim');
    termLine('  │              Pod Terminal — kubectl exec              │', 'xl-dim');
    termLine('  └─────────────────────────────────────────────────────┘', 'xl-dim');
    termLine('');
  }
  termLine(`Connecting to ${t.namespace}/${t.pod_name}...`, 'xl-sys');

  try {
    // Use 10s timeout for cwd check — kubectl exec can hang if pod is not ready
    const d = await safePost(`${API}/pod/exec/cwd`, t, 10000);
    _T.host      = d.hostname || t.pod_name.split('-').slice(0, 2).join('-') || 'pod';
    _T.cwd       = d.cwd || '/';
    _T.user      = d.user || 'root';
    _T.connected = true;

    termUpdatePrompt();
    btn.textContent = '已连接';
    btn.className   = 'xterm-conn live';
    document.getElementById('termTitle').textContent =
      `${_T.user}@${_T.host} — ${t.namespace}/${t.pod_name}`;

    termLine(`✓ 已连接  (${t.cluster_name} · ${t.namespace}/${t.pod_name})`, 'xl-ok');
    termLine(`  用户: ${_T.user}   主机: ${_T.host}   目录: ${_T.cwd}`, 'xl-dim');
    termLine('', 'xl-dim');
    document.getElementById('termInput').focus();

    // Auto run uname to show system info
    await _termRun('uname -sr 2>/dev/null || cat /etc/os-release 2>/dev/null | head -3 || echo "ready"', true);
  } catch(e) {
    const msg = e.message || String(e);
    termLine('', 'xl');
    termLine(`✗ 连接失败: ${msg}`, 'xl-err');
    if(msg.includes('超时') || msg.includes('timeout')) {
      termLine('  原因: kubectl exec 无响应，可能 Pod 未 Running 或无 shell', 'xl-dim');
      termLine('  请先在「Pod 监控」确认 Pod 状态为 Running', 'xl-dim');
    } else if(msg.includes('服务器') || msg.includes('server')) {
      termLine('  原因: server.py 未运行，请执行: python server.py', 'xl-dim');
    }
    btn.textContent = '重试连接';
    btn.className   = 'xterm-conn';
    _T.connected    = false;
  }
}

// ── Command execution ──────────────────────────────────────────────────────────
async function _termRun(cmd, silent = false) {
  const t = getT();
  _T.running = true;
  document.getElementById('termSpin').style.display = 'inline-block';
  document.getElementById('termInput').disabled = true;

  try {
    const d = await safePost(`${API}/pod/exec`, {
      ...t, command: cmd, cwd: _T.cwd, timeout: 30
    }, 35000);  // 35s fetch timeout (server timeout is 30s)

    // Process stdout line by line for coloring
    if(d.stdout) {
      const lines = d.stdout.split('\n');
      // Remove trailing empty line
      if(lines[lines.length - 1] === '') lines.pop();
      lines.forEach(line => {
        const clean = line.replace(/\x1b\[[0-9;]*[mGKHFJABCDsuhl]/g, '');
        if(!clean && lines.length === 1) return;
        const lo = clean.toLowerCase();
        let cls = 'xl';
        if(/^(error|fatal|exception|critical)/.test(lo))   cls = 'xl-err';
        else if(/^(warn(ing)?)/.test(lo))                  cls = 'xl-warn';
        else if(clean.startsWith('total ') || clean.match(/^d[rwx-]{9}/)) cls = 'xl'; // ls output
        termLine(clean, cls);
      });
    }
    if(d.stderr && d.stderr.trim()) {
      const slines = d.stderr.split('\n');
      if(slines[slines.length-1] === '') slines.pop();
      slines.forEach(l => termLine(l.replace(/\x1b\[[0-9;]*[mGKHFJABCDsuhl]/g,''), 'xl-err'));
    }
    if(d.rc !== 0 && d.rc !== undefined && (d.stderr || (!d.stdout && d.rc))) {
      // show exit code only on error without stderr already showing it
    }
    return d;
  } catch(e) {
    termLine(e.message, 'xl-err');
    return {rc: -1, stdout: '', stderr: e.message};
  } finally {
    _T.running = false;
    document.getElementById('termSpin').style.display = 'none';
    document.getElementById('termInput').disabled = false;
    document.getElementById('termInput').focus();
  }
}

async function termExec(cmd) {
  if(_T.running) return;

  const trimmed = cmd.trim();
  if(!trimmed) { termEcho(''); return; }

  // Update history
  if(_T.hist.length === 0 || _T.hist[_T.hist.length - 1] !== trimmed) {
    _T.hist.push(trimmed);
    if(_T.hist.length > 500) _T.hist.shift();
  }
  _T.histIdx = -1;

  // Render prompt + echoed command
  termEcho(trimmed);

  // ── Client-side built-ins ──────────────────────────────────────────────────
  if(trimmed === 'clear' || trimmed === 'cls') {
    termOut().innerHTML = ''; return;
  }

  if(!_T.connected) {
    termLine('Not connected. Press the green dot or click 连接 to connect.', 'xl-err');
    return;
  }

  // ── cd: handle client-side, update _T.cwd ──────────────────────────────
  if(trimmed === 'cd' || trimmed.startsWith('cd ') || trimmed.startsWith('cd\t')) {
    const target = trimmed.slice(2).trim() || '~';
    await termCd(target);
    return;
  }

  // ── Regular command ────────────────────────────────────────────────────────
  await _termRun(trimmed);
  termLine(''); // blank line after output for readability
}

async function termCd(target) {
  const t = getT();
  let newPath;
  if(target === '~' || target === '')
    newPath = `/home/${_T.user}`;
  else if(target.startsWith('/'))
    newPath = target;
  else if(target === '..')
    newPath = _T.cwd.split('/').slice(0,-1).join('/') || '/';
  else
    newPath = (_T.cwd === '/' ? '' : _T.cwd) + '/' + target;

  // Normalize
  newPath = newPath.replace(/\/\//g, '/').replace(/\/$/, '') || '/';

  try {
    const d = await safePost(`${API}/pod/exec`, {
      ...t, command: `cd '${newPath}' && pwd`, cwd: '/', timeout: 5
    });
    if(d.rc === 0 && d.stdout.trim()) {
      _T.cwd = d.stdout.trim();
      termUpdatePrompt();
    } else {
      termLine(`bash: cd: ${target}: No such file or directory`, 'xl-err');
    }
  } catch(e) {
    termLine(e.message, 'xl-err');
  }
}

// ── Tab completion ──────────────────────────────────────────────────────────────
let _tabCache = [], _tabPrefix = '', _tabIdx = 0;

// ── Tab completion with popup ──────────────────────────────────────────────────

function tabFileIcon(name) {
  if(name.endsWith('/')) return '📁';
  const ext = name.split('.').pop().toLowerCase();
  const m = {log:'📄',txt:'📄',sh:'⚡',bash:'⚡',py:'🐍',js:'📜',ts:'📜',
             json:'📋',yaml:'📋',yml:'📋',xml:'📋',conf:'⚙️',properties:'⚙️',
             jar:'☕',class:'☕',java:'☕',html:'🔥',jfr:'📊',hprof:'📊',
             zip:'📦',tar:'📦',gz:'📦'};
  return m[ext] || '📄';
}

function tabPopupShow(items, cmdPfx) {
  const popup = document.getElementById('tabPopup');
  if(!items.length) { tabPopupHide(); return; }
  _tabIdx = 0;
  const rows = items.slice(0, 60).map((item, i) => {
    const isDir  = item.endsWith('/');
    const icon   = isDir ? '📁' : tabFileIcon(item);
    const suffix = isDir ? 'dir' : (item.includes('.') ? item.split('.').pop() : '');
    return `<div class="tab-item${i===0?' sel':''}" data-val="${esc(item)}" data-pfx="${esc(cmdPfx)}"
      onclick="tabPickItem(this)" onmouseover="tabHover(this)">
      <span class="ti-icon">${icon}</span>
      <span class="ti-name">${esc(item)}</span>
      <span class="ti-type">${esc(suffix)}</span>
    </div>`;
  }).join('');
  const hint = items.length === 1 ? '' :
    `<div class="tab-count">共${items.length}项  Tab/↓=下一个  Shift+Tab/↑=上一个  Enter=选中  Esc=关闭</div>`;
  popup.innerHTML = rows + hint;
  popup.classList.add('show');
  popup.scrollTop = 0;
}

function tabPopupHide() {
  document.getElementById('tabPopup').classList.remove('show');
  document.getElementById('tabPopup').innerHTML = '';
  _tabCache = []; _tabPrefix = ''; _tabIdx = 0;
}

function tabHover(el) {
  document.querySelectorAll('#tabPopup .tab-item').forEach(e => e.classList.remove('sel'));
  el.classList.add('sel');
  _tabIdx = Array.from(el.parentElement.querySelectorAll('.tab-item')).indexOf(el);
}

function tabPickItem(el) {
  const val    = el.dataset.val;
  const cmdPfx = el.dataset.pfx;
  const input  = document.getElementById('termInput');
  input.value  = cmdPfx + val;
  tabPopupHide();
  input.focus();
  if(val.endsWith('/')) setTimeout(termTabComplete, 80);
}

function tabNavPopup(delta) {
  const items = document.querySelectorAll('#tabPopup .tab-item');
  if(!items.length) return;
  items[_tabIdx]?.classList.remove('sel');
  _tabIdx = ((_tabIdx + delta) + items.length) % items.length;
  items[_tabIdx].classList.add('sel');
  items[_tabIdx].scrollIntoView({ block: 'nearest' });
  // Update input value to show hovered item
  const input  = document.getElementById('termInput');
  const cmdPfx = items[_tabIdx].dataset.pfx;
  input.value  = cmdPfx + items[_tabIdx].dataset.val;
}

function tabConfirmPopup() {
  const sel = document.querySelector('#tabPopup .tab-item.sel');
  if(!sel) return false;
  tabPickItem(sel);
  return true;
}

async function termTabComplete() {
  const input = document.getElementById('termInput');
  const val   = input.value;
  const t     = getT();
  if(!t.pod_name || !_T.connected) return;

  const popup = document.getElementById('tabPopup');

  // Popup already open → just cycle items
  if(popup.classList.contains('show') && _tabCache.length > 1) {
    tabNavPopup(1);
    return;
  }

  // ── Parse input ────────────────────────────────────────────
  // Split into "everything before last token" and "the token being completed"
  const tokens  = val.match(/\S+|\s+/g) || [];       // keep whitespace segments
  const lastIdx = tokens.map((t,i)=>[t,i]).filter(([t])=>!/^\s+$/.test(t)).pop();
  const lastTok = lastIdx ? lastIdx[0] : '';
  const cmdPfx  = lastIdx ? tokens.slice(0, lastIdx[1]).join('') : val;

  // ── Resolve directory and filename prefix ───────────────────
  const slashIdx = lastTok.lastIndexOf('/');
  // dirPart: the directory portion of the token (may be empty, "/", or "/foo/")
  const dirPart  = slashIdx >= 0 ? lastTok.slice(0, slashIdx + 1) : '';
  const filePart = slashIdx >= 0 ? lastTok.slice(slashIdx + 1)    : lastTok;

  // Resolve absolute lookup path
  let lookDir;
  if(dirPart === '' ) { lookDir = _T.cwd; }
  else if(dirPart.startsWith('/')) { lookDir = dirPart.replace(/\/+$/, '') || '/'; }
  else { lookDir = (_T.cwd.replace(/\/+$/, '') + '/' + dirPart).replace(/\/+$/, ''); }
  if(lookDir === '') lookDir = '/';

  // ── Fetch candidates from Pod ───────────────────────────────
  // Strategy: ls -Ap (works on BusyBox & GNU), filter by prefix
  // Append '/' to dirs so we know they are directories
  const escapedFile = filePart.replace(/'/g, "'\''");
  const escapedDir  = lookDir.replace(/'/g, "'\''");
  const shellCmd =
    `ls -Ap '${escapedDir}' 2>/dev/null | grep -i "^${escapedFile}" | head -60`;

  let candidates = [];
  try {
    const d = await safePost(`${API}/pod/exec`, {
      ...t, command: shellCmd, cwd: _T.cwd, timeout: 5,
    }, 7000);
    candidates = (d.stdout || '').trim().split('\n')
      .map(s => s.trim()).filter(Boolean)
      .map(s => dirPart + s);           // prepend the dir prefix back
  } catch { return; }

  _tabCache  = candidates;
  _tabPrefix = lastTok;
  _tabIdx    = 0;

  if(!candidates.length) {
    termLine(`  (无匹配: ${lastTok})`, 'xl-dim');
    return;
  }

  // ── Apply result ─────────────────────────────────────────────
  if(candidates.length === 1) {
    input.value = cmdPfx + candidates[0];
    tabPopupHide();
    if(candidates[0].endsWith('/')) setTimeout(termTabComplete, 80);
    return;
  }

  // Multiple → show popup, pre-fill first item in input
  input.value = cmdPfx + candidates[0];
  tabPopupShow(candidates, cmdPfx);
}




// ── Keyboard handling ──────────────────────────────────────────────────────────
function termKeyDown(e) {
  const input = document.getElementById('termInput');

  if(e.key === 'Enter') {
    e.preventDefault();
    // If tab popup is open, Enter confirms selection
    const popup = document.getElementById('tabPopup');
    if(popup.classList.contains('show')) {
      if(tabConfirmPopup()) return;
    }
    const cmd = input.value; input.value = '';
    tabPopupHide();
    termExec(cmd);
    return;
  }

  if(e.key === 'Tab') {
    e.preventDefault();
    const popup = document.getElementById('tabPopup');
    if(popup.classList.contains('show')) {
      tabNavPopup(e.shiftKey ? -1 : 1);
    } else {
      termTabComplete();
    }
    return;
  }

  if(e.key === 'ArrowUp') {
    e.preventDefault();
    const popup2 = document.getElementById('tabPopup');
    if(popup2.classList.contains('show')) { tabNavPopup(-1); return; }
    if(_T.hist.length === 0) return;
    if(_T.histIdx === -1) _T.histIdx = _T.hist.length - 1;
    else if(_T.histIdx > 0) _T.histIdx--;
    input.value = _T.hist[_T.histIdx] || '';
    requestAnimationFrame(()=>{ input.selectionStart = input.selectionEnd = input.value.length; });
    return;
  }

  if(e.key === 'ArrowDown') {
    e.preventDefault();
    const popup3 = document.getElementById('tabPopup');
    if(popup3.classList.contains('show')) { tabNavPopup(1); return; }
    if(_T.histIdx === -1) return;
    _T.histIdx++;
    input.value = _T.histIdx >= _T.hist.length ? (_T.histIdx = -1, '') : _T.hist[_T.histIdx];
    return;
  }

  // Ctrl+L: clear screen
  if(e.key === 'l' && e.ctrlKey) {
    e.preventDefault(); termOut().innerHTML = ''; return;
  }
  // Ctrl+C: cancel current input
  if(e.key === 'c' && e.ctrlKey) {
    e.preventDefault();
    termEcho(input.value + '^C');
    input.value = '';
    termLine('');
    return;
  }
  // Ctrl+U: clear line
  if(e.key === 'u' && e.ctrlKey) {
    e.preventDefault(); input.value = ''; return;
  }

  // Escape: close tab popup
  if(e.key === 'Escape') {
    tabPopupHide();
    return;
  }

  // Reset tab cache on any other key (except navigation keys)
  if(!['Tab','Shift','ArrowUp','ArrowDown'].includes(e.key)) {
    // Hide popup but keep cache so next Tab re-fetches
    tabPopupHide();
  }
}

// termClear and termQuick kept for quick-button wrappers
function termClear() { termOut().innerHTML = ''; }
function termQuick(cmd) {
  const input = document.getElementById('termInput');
  input.value = '';
  document.getElementById('termInput').focus();
  termExec(cmd);
}
