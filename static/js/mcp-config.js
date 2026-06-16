/**
 * MCP 配置页面逻辑
 */
const API = '/api';

// ─── 全局状态 ─────────────────────────────────────────────────────
let _connections = [];
let _tokens = [];
let _selectedConn = '';
let _currentConfigs = null;
let _currentClientType = 'cherry_studio_cline';

// ─── 初始化 ───────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  loadConnections();
  loadTokens();
});

// ─── Toast ────────────────────────────────────────────────────────
function showToast(msg, type = 'ok') {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = `toast ${type} show`;
  setTimeout(() => el.className = 'toast', 2500);
}

// ─── 加载连接列表 ────────────────────────────────────────────────
async function loadConnections() {
  const el = document.getElementById('conn-list');
  try {
    const parentState = await getParentConnectionState();
    let sourceConnections = parentState.connections;
    let healthMap = parentState.health;

    // 嵌入主工作区时，连接中心状态是权威来源；独立打开时才回退后端接口
    if (!sourceConnections.length) {
      const resp = await fetch(`${API}/mcp/connections`, { credentials: 'include' });
      const data = await resp.json();
      sourceConnections = data.connections || [];
      healthMap = {};
    }

    _connections = normalizeMcpConnections(sourceConnections, healthMap);
    if (_selectedConn && !_connections.some(c => c.id === _selectedConn)) {
      _selectedConn = '';
      document.getElementById('selected-conn').value = '';
    }

    if (!_connections.length) {
      el.innerHTML = '<div class="empty">暂无可用 Arthas 连接<br><span style="font-size:11px">请先在连接中心连接 Pod，并启动 Arthas</span></div>';
      return;
    }

    el.innerHTML = _connections.map(c => `
      <div class="conn-option ${_selectedConn === c.id ? 'selected' : ''}" onclick="selectConn('${escAttr(c.id)}')">
        <div class="dot ${c.alive ? 'alive' : 'dead'}"></div>
        <div class="info">
          <div class="path">${esc(c.cluster || c.cluster_name || c.id)}</div>
          <div class="meta">${c.namespace ? esc(c.namespace) + ' / ' : ''}${esc(c.pod || c.pod_name || c.id)}${c.local_port ? ' · port ' + c.local_port : ''}</div>
        </div>
      </div>
    `).join('');
  } catch (e) {
    el.innerHTML = '<div class="empty" style="color:var(--err)">加载失败</div>';
  }
}

async function getParentConnectionState() {
  const result = { connections: [], health: {} };
  if (window.parent && window.parent !== window) {
    try {
      const parentWin = window.parent;
      if (typeof parentWin.checkConnectionsHealth === 'function') {
        await parentWin.checkConnectionsHealth();
      }
      result.connections = Array.isArray(parentWin._connections) ? parentWin._connections : [];
      result.health = parentWin._connHealth || {};
    } catch (e) {
      console.warn('读取连接中心状态失败，回退后端连接列表:', e);
    }
  }
  return result;
}

function normalizeMcpConnections(connections, healthMap = {}) {
  return (connections || [])
    .map(c => {
      const id = c.id || c.connection_id;
      const h = healthMap[id] || {};
      const level = inferMcpConnLevel(c);
      const alive = h.alive ?? c.alive ?? c.status === 'connected' || c.status === 'db_only';
      const podExists = h.pod_exists ?? c.pod_exists;
      return {
        id,
        alive,
        pod_exists: podExists,
        level,
        local_port: c.local_port || 0,
        cluster: c.cluster || c.cluster_name || '',
        cluster_name: c.cluster_name || c.cluster || '',
        namespace: c.namespace || '',
        pod: c.pod || c.pod_name || '',
        pod_name: c.pod_name || c.pod || '',
        mcp_available: c.mcp_available,
      };
    })
    .filter(c => c.id)
    .filter(c => c.level === 'arthas')
    .filter(c => c.pod_exists !== false)
    .filter(c => c.alive !== false || c.status === 'db_only')
    .filter(c => Boolean(c.local_port));
}

function inferMcpConnLevel(c) {
  if (c.level) return c.level;
  if (c.local_port || c.java_pid || c.arthas_version || c.arthas_address) return 'arthas';
  return 'pod';
}

function selectConn(connId) {
  _selectedConn = connId;
  document.getElementById('selected-conn').value = connId;
  // 重新渲染连接列表高亮
  loadConnections();
}

// ─── 创建 Token ──────────────────────────────────────────────────
async function createToken() {
  if (!_selectedConn) {
    showToast('请先选择一个连接', 'err');
    return;
  }

  const name = document.getElementById('token-name').value.trim();
  try {
    const resp = await fetch(`${API}/mcp/tokens`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({
        name: name || undefined,
        connection_id: _selectedConn,
      }),
    });
    const data = await resp.json();
    if (data.error) {
      showToast(data.error, 'err');
      return;
    }

    showToast('Token 创建成功！');
    // 显示 Token（仅此一次）
    showTokenCreated(data.token, data.name);
    loadTokens();
    document.getElementById('token-name').value = '';
  } catch (e) {
    showToast('创建失败: ' + e.message, 'err');
  }
}

function showTokenCreated(token, name) {
  // 注入弹窗样式（仅一次）
  if (!document.getElementById('token-modal-css')) {
    const s = document.createElement('style');
    s.id = 'token-modal-css';
    s.textContent = `
      .tm-overlay{position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.75);display:flex;align-items:center;justify-content:center;z-index:10000;backdrop-filter:blur(6px);-webkit-backdrop-filter:blur(6px);animation:tmFadeIn .25s ease}
      @keyframes tmFadeIn{from{opacity:0}to{opacity:1}}
      @keyframes tmSlideUp{from{transform:translateY(20px);opacity:0}to{transform:translateY(0);opacity:1}}
      .tm-card{background:var(--bg1);border:1px solid rgba(122,162,247,.2);border-radius:14px;padding:26px 30px;max-width:460px;width:92%;box-shadow:0 24px 80px rgba(0,0,0,.6),0 0 0 1px rgba(122,162,247,.08);animation:tmSlideUp .3s ease}
      .tm-header{display:flex;align-items:center;gap:14px;margin-bottom:22px}
      .tm-icon{width:46px;height:46px;background:linear-gradient(135deg,var(--a) 0%,#4f8ff7 100%);border-radius:12px;display:flex;align-items:center;justify-content:center;font-size:22px;box-shadow:0 6px 20px rgba(122,162,247,.35)}
      .tm-title{font-size:17px;font-weight:700;color:var(--tx);margin:0}
      .tm-subtitle{font-size:12px;color:var(--tx2);margin:3px 0 0 0}
      .tm-token-box{background:var(--bg);border:1px solid rgba(122,162,247,.12);border-radius:10px;padding:14px 16px;margin-bottom:18px}
      .tm-token-label{font-size:10px;color:var(--tx3);text-transform:uppercase;letter-spacing:1px;margin-bottom:8px}
      .tm-token-value{font-family:'SF Mono',Menlo,Consolas,monospace;font-size:12px;word-break:break-all;color:var(--a);line-height:1.7;user-select:all}
      .tm-warn{background:rgba(210,153,34,.08);border:1px solid rgba(210,153,34,.2);border-radius:8px;padding:12px 14px;margin-bottom:22px;display:flex;align-items:flex-start;gap:10px;font-size:12px;color:var(--warn);line-height:1.6}
      .tm-warn strong{color:#e8b339}
      .tm-actions{display:flex;gap:10px;justify-content:flex-end}
      .tm-btn-copy{background:rgba(122,162,247,.1);border:1px solid rgba(122,162,247,.25);border-radius:8px;padding:9px 18px;font-size:13px;color:var(--a);cursor:pointer;transition:all .2s;display:flex;align-items:center;gap:6px}
      .tm-btn-copy:hover{background:rgba(122,162,247,.18);border-color:var(--a)}
      .tm-btn-copy.copied{background:rgba(63,185,80,.12);border-color:rgba(63,185,80,.35);color:var(--ok)}
      .tm-btn-close{background:linear-gradient(135deg,var(--a) 0%,#4f8ff7 100%);border:none;border-radius:8px;padding:9px 20px;font-size:13px;color:#000;font-weight:600;cursor:pointer;box-shadow:0 4px 16px rgba(122,162,247,.3);transition:all .2s}
      .tm-btn-close:hover{box-shadow:0 6px 24px rgba(122,162,247,.45);transform:translateY(-1px)}
    `;
    document.head.appendChild(s);
  }

  const modal = document.createElement('div');
  modal.className = 'tm-overlay';
  modal.innerHTML = `
    <div class="tm-card">
      <div class="tm-header">
        <div class="tm-icon">🔑</div>
        <div>
          <h3 class="tm-title">Token 创建成功</h3>
          <p class="tm-subtitle">${name ? esc(name) : '未命名 Token'}</p>
        </div>
      </div>
      <div class="tm-token-box">
        <div class="tm-token-label">Access Token</div>
        <div class="tm-token-value" id="new-token-text">${esc(token)}</div>
      </div>
      <div class="tm-warn">
        <span>⚠️</span>
        <span><strong>重要提示：</strong>请立即复制并妥善保存此 Token，关闭后将<strong>无法再次查看</strong></span>
      </div>
      <div class="tm-actions">
        <button class="tm-btn-copy" id="tm-copy-btn">
          <span>📋</span> 复制 Token
        </button>
        <button class="tm-btn-close" id="tm-close-btn">
          我已保存，关闭
        </button>
      </div>
    </div>
  `;
  document.body.appendChild(modal);

  // 绑定事件
  modal.querySelector('#tm-copy-btn').onclick = function() {
    navigator.clipboard.writeText(document.getElementById('new-token-text').textContent);
    this.innerHTML = '<span>✓</span> 已复制到剪贴板';
    this.classList.add('copied');
  };
  modal.querySelector('#tm-close-btn').onclick = function() {
    modal.remove();
  };
  // 点击遮罩关闭
  modal.addEventListener('click', function(e) {
    if (e.target === modal) modal.remove();
  });
}

// ─── 加载 Token 列表 ─────────────────────────────────────────────
async function loadTokens() {
  const el = document.getElementById('token-list');
  try {
    const resp = await fetch(`${API}/mcp/tokens`, { credentials: 'include' });
    const data = await resp.json();
    _tokens = data.tokens || [];

    if (!_tokens.length) {
      el.innerHTML = '<div class="empty">暂无 Token，请先创建</div>';
      return;
    }

    el.innerHTML = _tokens.map(t => `
      <div class="token-item">
        <span class="name">${esc(t.name)}</span>
        <span class="conn">${esc(t.connection_id)}</span>
        <span class="time">${t.created_at || ''}</span>
        <span class="status ${t.is_active ? 'active' : 'inactive'}">${t.is_active ? '启用' : '禁用'}</span>
        <button class="btn btn-sm" onclick="showConfig(${t.id})" style="cursor:pointer">📋 配置</button>
        <button class="btn btn-sm" onclick="toggleToken(${t.id}, ${t.is_active})" style="cursor:pointer">${t.is_active ? '禁用' : '启用'}</button>
        <button class="btn btn-sm btn-danger" onclick="deleteToken(${t.id})" style="cursor:pointer">删除</button>
      </div>
    `).join('');
  } catch (e) {
    el.innerHTML = '<div class="empty" style="color:var(--err)">加载失败</div>';
  }
}

// ─── 切换 Token 状态 ─────────────────────────────────────────────
async function toggleToken(id, currentActive) {
  try {
    const resp = await fetch(`${API}/mcp/tokens/${id}/toggle`, {
      method: 'POST', credentials: 'include',
    });
    const data = await resp.json();
    if (data.error) { showToast(data.error, 'err'); return; }
    showToast(data.is_active ? '已启用' : '已禁用');
    loadTokens();
  } catch (e) {
    showToast('操作失败', 'err');
  }
}

// ─── 删除 Token ──────────────────────────────────────────────────
async function deleteToken(id) {
  if (!confirm('确定删除此 Token？删除后 AI 客户端将无法连接')) return;
  try {
    const resp = await fetch(`${API}/mcp/tokens/${id}`, {
      method: 'DELETE', credentials: 'include',
    });
    const data = await resp.json();
    if (data.error) { showToast(data.error, 'err'); return; }
    showToast('已删除');
    loadTokens();
    // 如果正在显示此 Token 的配置，关闭
    document.getElementById('config-card').style.display = 'none';
  } catch (e) {
    showToast('删除失败', 'err');
  }
}

// ─── 显示客户端配置 ──────────────────────────────────────────────
async function showConfig(tokenId) {
  try {
    const resp = await fetch(`${API}/mcp/config/${tokenId}`, { credentials: 'include' });
    const data = await resp.json();
    if (data.error) { showToast(data.error, 'err'); return; }

    _currentConfigs = data.configs;
    renderConfig(_currentClientType);

    const card = document.getElementById('config-card');
    card.style.display = '';
    card.scrollIntoView({ behavior: 'smooth' });
  } catch (e) {
    showToast('加载配置失败', 'err');
  }
}

function renderConfig(clientType) {
  if (!_currentConfigs || !_currentConfigs[clientType]) return;
  const json = JSON.stringify(_currentConfigs[clientType], null, 2);
  document.getElementById('config-json').textContent = json;
}

function switchClientTab(el) {
  document.querySelectorAll('.client-tab').forEach(t => t.classList.remove('active'));
  el.classList.add('active');
  _currentClientType = el.dataset.client;
  renderConfig(_currentClientType);
}

function copyConfig() {
  const text = document.getElementById('config-json').textContent;
  navigator.clipboard.writeText(text).then(() => showToast('已复制到剪贴板'));
}

// ─── 工具函数 ─────────────────────────────────────────────────────
function esc(s) {
  if (!s) return '';
  const d = document.createElement('div');
  d.textContent = String(s);
  return d.innerHTML;
}

function escAttr(s) {
  return esc(s).replace(/'/g, '&#39;');
}
