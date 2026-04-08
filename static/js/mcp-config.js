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
    const resp = await fetch(`${API}/mcp/connections`);
    const data = await resp.json();
    _connections = data.connections || [];

    if (!_connections.length) {
      el.innerHTML = '<div class="empty">暂无可用连接<br><span style="font-size:11px">请先在主界面连接 Pod</span></div>';
      return;
    }

    el.innerHTML = _connections.map(c => `
      <div class="conn-option ${_selectedConn === c.id ? 'selected' : ''}" onclick="selectConn('${c.id}')">
        <div class="dot ${c.alive ? 'alive' : 'dead'}"></div>
        <div class="info">
          <div class="path">${esc(c.id)}</div>
          <div class="meta">port: ${c.local_port}</div>
        </div>
      </div>
    `).join('');
  } catch (e) {
    el.innerHTML = '<div class="empty" style="color:var(--err)">加载失败</div>';
  }
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
  // 用一个临时模态框显示 Token
  const modal = document.createElement('div');
  modal.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.6);display:flex;align-items:center;justify-content:center;z-index:1000';
  modal.innerHTML = `
    <div style="background:var(--bg1);border:1px solid var(--ln);border-radius:12px;padding:24px;max-width:500px;width:90%">
      <h3 style="font-size:15px;margin-bottom:12px">🔑 Token 已创建</h3>
      <p style="font-size:12px;color:var(--tx2);margin-bottom:10px">请妥善保存以下 Token，<strong style="color:var(--warn)">关闭后将无法再次查看</strong></p>
      <div style="background:var(--bg);border:1px solid var(--ln);border-radius:6px;padding:10px;font-family:monospace;font-size:11px;word-break:break-all;color:var(--a);margin-bottom:14px" id="new-token-text">${esc(token)}</div>
      <div style="display:flex;gap:8px;justify-content:flex-end">
        <button class="btn btn-sm" onclick="navigator.clipboard.writeText(document.getElementById('new-token-text').textContent);this.textContent='已复制'" style="cursor:pointer">📋 复制 Token</button>
        <button class="btn btn-primary btn-sm" onclick="this.closest('div[style]').parentElement.remove()" style="cursor:pointer">我已保存</button>
      </div>
    </div>
  `;
  document.body.appendChild(modal);
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
