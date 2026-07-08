const API = (() => {
    if (typeof window !== 'undefined' && window.location.protocol.startsWith('http')) {
        return `${window.location.protocol}//${window.location.host}/api`;
    }
    return 'http://127.0.0.1:5005/api';
})();

let clusters = [];
let editingClusterId = null;
const clusterTestStatus = new Map();

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text == null ? '' : String(text);
    return div.innerHTML;
}

function toast(message, type) {
    const host = document.getElementById('toast');
    if (!host) return;
    const item = document.createElement('div');
    item.className = `toast-item${type ? ' toast-' + type : ''}`;
    item.textContent = message;
    host.appendChild(item);
    setTimeout(() => item.remove(), 3500);
}

function setPageError(message) {
    const el = document.getElementById('clusterPageError');
    if (!el) return;
    el.textContent = message || '';
    el.classList.toggle('show', !!message);
}

function setModalError(message) {
    const el = document.getElementById('clusterModalError');
    if (!el) return;
    el.textContent = message || '';
    el.classList.toggle('show', !!message);
}

async function checkAdminAndLoad() {
    try {
        const response = await fetch(API + '/auth/current', { credentials: 'same-origin' });
        const data = await response.json();
        if (!data.authenticated) {
            window.location.href = window.location.protocol.startsWith('http') ? '/login.html' : 'login.html';
            return;
        }
        if (data.user) {
            const userEl = document.getElementById('currentUser');
            if (userEl) userEl.textContent = data.user.username || '—';
        }
        if (!data.user || !data.user.is_admin) {
            if (window.self !== window.top && window.parent && typeof window.parent.switchTab === 'function') {
                window.parent.switchTab('connections');
            } else {
                window.location.href = '/';
            }
            return;
        }
        loadClusters();
    } catch (error) {
        console.error('Auth check failed:', error);
        window.location.href = '/';
    }
}

document.addEventListener('DOMContentLoaded', checkAdminAndLoad);

async function loadClusters() {
    const tbody = document.getElementById('clusterTableBody');
    if (tbody) tbody.innerHTML = '<tr><td colspan="5" class="empty-msg">加载中...</td></tr>';
    setPageError('');
    try {
        const response = await fetch(API + '/clusters', { credentials: 'same-origin' });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || '加载集群失败');
        clusters = data.clusters || [];
        renderClusterTable();
    } catch (error) {
        console.error('Failed to load clusters:', error);
        setPageError('加载集群失败：' + error.message);
        if (tbody) tbody.innerHTML = '<tr><td colspan="5" class="empty-msg">加载失败</td></tr>';
    }
}

function renderClusterTable() {
    const tbody = document.getElementById('clusterTableBody');
    if (!tbody) return;
    document.getElementById('clusterTotal').textContent = clusters.length;
    document.getElementById('clusterOk').textContent = Array.from(clusterTestStatus.values()).filter(x => x === 'ok').length;
    document.getElementById('clusterErr').textContent = Array.from(clusterTestStatus.values()).filter(x => x === 'err').length;

    if (!clusters.length) {
        tbody.innerHTML = '<tr><td colspan="5" class="empty-msg">暂无集群配置，请点击“添加集群”创建</td></tr>';
        return;
    }

    tbody.innerHTML = clusters.map(cluster => {
        const id = cluster.id || cluster.name;
        const status = clusterTestStatus.get(id) || 'unknown';
        const statusLabel = status === 'ok' ? '连接成功' : status === 'err' ? '连接失败' : status === 'testing' ? '测试中' : '未测试';
        const statusClass = status === 'ok' ? 'status-ok' : status === 'err' ? 'status-err' : status === 'testing' ? 'status-testing' : '';
        return `<tr>
            <td><div class="cluster-name">${escapeHtml(cluster.name)}</div><div class="mono-path">ID: ${escapeHtml(id)}</div></td>
            <td><div class="mono-path">${escapeHtml(cluster.kubeconfig || '-')}</div></td>
            <td>${escapeHtml(cluster.context || '默认')}</td>
            <td><span class="status-pill ${statusClass}" id="status-${escapeHtml(id)}">${statusLabel}</span></td>
            <td>
                <div class="btn-row">
                    <button class="ab ab-g ab-sm" onclick="testCluster('${escapeHtml(id)}')">测试</button>
                    <button class="ab ab-g ab-sm" onclick="openClusterModal('${escapeHtml(id)}')">编辑</button>
                    <button class="ab ab-d ab-sm" onclick="deleteCluster('${escapeHtml(id)}')">删除</button>
                </div>
            </td>
        </tr>`;
    }).join('');
}

function openClusterModal(clusterId) {
    editingClusterId = clusterId || null;
    const cluster = editingClusterId ? clusters.find(c => (c.id || c.name) === editingClusterId) : null;
    document.getElementById('clusterModalTitle').textContent = cluster ? `编辑集群：${cluster.name}` : '添加集群';
    document.getElementById('clusterName').value = cluster ? (cluster.name || '') : '';
    document.getElementById('clusterKubeconfig').value = cluster ? (cluster.kubeconfig || '') : '';
    document.getElementById('clusterContext').value = cluster ? (cluster.context || '') : '';
    setModalError('');
    document.getElementById('clusterModal').classList.add('open');
}

function closeClusterModal() {
    document.getElementById('clusterModal').classList.remove('open');
}

async function fetchClusterContexts() {
    const kubeconfig = document.getElementById('clusterKubeconfig').value.trim();
    const selectWrap = document.getElementById('clusterContextSelectWrap');
    const select = document.getElementById('clusterContextSelect');
    if (!kubeconfig) {
        setModalError('请先填写 KubeConfig 文件路径');
        return;
    }
    setModalError('');
    if (selectWrap) selectWrap.style.display = 'none';
    try {
        const response = await fetch(API + '/contexts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({ kubeconfig })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || '获取 Context 列表失败');
        const contexts = data.contexts || [];
        if (select) {
            select.innerHTML = '<option value="">—</option>' + contexts.map(c => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join('');
            if (data.current) {
                select.value = data.current;
                document.getElementById('clusterContext').value = data.current;
            }
        }
        if (selectWrap) selectWrap.style.display = 'block';
        toast(`找到 ${contexts.length} 个 Context`, 'success');
    } catch (error) {
        setModalError('获取 Context 失败：' + error.message);
        toast('获取 Context 失败：' + error.message, 'error');
    }
}

async function saveClusterConfig() {
    const name = document.getElementById('clusterName').value.trim();
    const kubeconfig = document.getElementById('clusterKubeconfig').value.trim();
    const context = document.getElementById('clusterContext').value.trim();
    const btn = document.getElementById('clusterSaveBtn');
    if (!name || !kubeconfig) {
        setModalError('集群名称和 KubeConfig 路径必填');
        return;
    }
    const oldText = btn.textContent;
    btn.disabled = true;
    btn.textContent = '保存中...';
    setModalError('');
    try {
        const url = editingClusterId ? `${API}/clusters/${encodeURIComponent(editingClusterId)}` : `${API}/clusters`;
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({ name, kubeconfig, context })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || '保存失败');
        closeClusterModal();
        toast('集群配置已保存', 'success');
        await loadClusters();
        if (window.parent && window.parent !== window && window.parent.ConnectionPool && typeof window.parent.ConnectionPool.loadClusters === 'function') {
            window.parent.ConnectionPool.loadClusters();
        }
    } catch (error) {
        setModalError(error.message);
    } finally {
        btn.disabled = false;
        btn.textContent = oldText;
    }
}

async function testCluster(clusterId) {
    clusterTestStatus.set(clusterId, 'testing');
    renderClusterTable();
    try {
        const response = await fetch(`${API}/clusters/${encodeURIComponent(clusterId)}${'/test'}`, {
            method: 'POST',
            credentials: 'same-origin'
        });
        const data = await response.json();
        clusterTestStatus.set(clusterId, data.ok ? 'ok' : 'err');
        renderClusterTable();
        toast(data.ok ? '集群连接测试成功' : '集群连接测试失败：' + (data.error || data.message || '请检查配置'), data.ok ? 'success' : 'error');
    } catch (error) {
        clusterTestStatus.set(clusterId, 'err');
        renderClusterTable();
        toast('集群连接测试失败：' + error.message, 'error');
    }
}

async function deleteCluster(clusterId) {
    const cluster = clusters.find(c => (c.id || c.name) === clusterId);
    const name = cluster ? cluster.name : clusterId;
    if (!confirm(`确定要删除集群配置 "${name}" 吗？`)) return;
    try {
        const response = await fetch(`${API}/clusters/${encodeURIComponent(clusterId)}`, {
            method: 'DELETE',
            credentials: 'same-origin'
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || '删除失败');
        clusterTestStatus.delete(clusterId);
        toast('集群配置已删除', 'success');
        await loadClusters();
        if (window.parent && window.parent !== window && window.parent.ConnectionPool && typeof window.parent.ConnectionPool.loadClusters === 'function') {
            window.parent.ConnectionPool.loadClusters();
        }
    } catch (error) {
        toast('删除失败：' + error.message, 'error');
    }
}

window.loadClusters = loadClusters;
window.renderClusterTable = renderClusterTable;
window.openClusterModal = openClusterModal;
window.closeClusterModal = closeClusterModal;
window.fetchClusterContexts = fetchClusterContexts;
window.saveClusterConfig = saveClusterConfig;
window.testCluster = testCluster;
window.deleteCluster = deleteCluster;
