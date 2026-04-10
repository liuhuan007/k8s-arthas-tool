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
  modal.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.7);display:flex;align-items:center;justify-content:center;z-index:1000;backdrop-filter:blur(4px)';
  modal.innerHTML = `
    <div style="background:linear-gradient(145deg,#1e2a3a 0%,#162029 100%);border:1px solid rgba(99,179,237,0.2);border-radius:16px;padding:28px 32px;max-width:480px;width:90%;box-shadow:0 20px 60px rgba(0,0,0,0.5),0 0 40px rgba(99,179,237,0.1)">
      <div style="display:flex;align-items:center;gap:12px;margin-bottom:20px">
        <div style="width:44px;height:44px;background:linear-gradient(135deg,#63b3ed 0%,#4299e1 100%);border-radius:12px;display:flex;align-items:center;justify-content:center;box-shadow:0 4px 15px rgba(99,179,237,0.4)">
          <span style="font-size:22px">🔑</span>
        </div>
        <div>
          <h3 style="font-size:17px;font-weight:600;color:#e2e8f0;margin:0">Token 创建成功</h3>
          <p style="font-size:12px;color:#94a3b8;margin:4px 0 0 0">${name ? esc(name) : '未命名 Token'}</p>
        </div>
      </div>
      <div style="background:rgba(15,23,42,0.8);border:1px solid rgba(99,179,237,0.15);border-radius:10px;padding:14px;margin-bottom:16px">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
          <span style="font-size:11px;color:#94a3b8;text-transform:uppercase;letter-spacing:0.5px">Access Token</span>
          <div style="flex:1;height:1px;background:rgba(99,179,237,0.1)"></div>
        </div>
        <div style="font-family:'JetBrains Mono','SF Mono',monospace;font-size:12px;word-break:break-all;color:#63b3ed;line-height:1.6" id="new-token-text">${esc(token)}</div>
      </div>
      <div style="background:rgba(245,158,11,0.1);border:1px solid rgba(245,158,11,0.2);border-radius:8px;padding:12px;margin-bottom:20px;display:flex;align-items:flex-start;gap:10px">
        <span style="font-size:16px;margin-top:1px">⚠️</span>
        <p style="font-size:12px;color:#fbbf24;margin:0;line-height:1.5"><strong>重要提示：</strong>请立即复制并妥善保存此 Token，关闭后将<strong>无法再次查看</strong></p>
      </div>
      <div style="display:flex;gap:10px;justify-content:flex-end">
        <button onclick="navigator.clipboard.writeText(document.getElementById('new-token-text').textContent);this.innerHTML='<span style=\\'margin-right:6px\\'>✓</span>已复制到剪贴板';this.style.background='rgba(34,197,94,0.2)';this.style.borderColor='rgba(34,197,94,0.4)';this.style.color='#4ade80'" style="background:rgba(99,179,237,0.1);border:1px solid rgba(99,179,237,0.3);border-radius:8px;padding:10px 18px;font-size:13px;color:#63b3ed;cursor:pointer;transition:all 0.2s;display:flex;align-items:center;gap:6px">
          <span>📋</span> 复制 Token
        </button>
        <button onclick="this.closest('div[style*=\\'linear-gradient\\']').parentElement.remove()" style="background:linear-gradient(135deg,#63b3ed 0%,#4299e1 100%);border:none;border-radius:8px;padding:10px 20px;font-size:13px;color:#0f172a;font-weight:600;cursor:pointer;box-shadow:0 4px 15px rgba(99,179,237,0.3);transition:all 0.2s">
          我已保存，关闭
        </button>
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
