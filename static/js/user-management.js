// 用户管理页面逻辑

const API = (() => {
    if (typeof window !== 'undefined' && window.location.protocol.startsWith('http')) {
        return `${window.location.protocol}//${window.location.host}/api`;
    }
    return 'http://127.0.0.1:5005/api';
})();

// 页面加载时检查权限并加载数据
document.addEventListener('DOMContentLoaded', async function() {
    // 检查用户权限
    try {
        const response = await fetch(API + '/auth/current');
        const data = await response.json();

        if (!data.authenticated) {
            // 未登录，重定向到登录页
            window.location.href = window.location.protocol.startsWith('http') ? '/login.html' : 'login.html';
            return;
        }

        if (!data.user.is_admin) {
            // 不是管理员，嵌入模式下交给父页面回到连接中心，避免 iframe 反复弹窗/跳转
            if (window.self !== window.top && window.parent && typeof window.parent.switchTab === 'function') {
                window.parent.switchTab('connections');
            } else {
                window.location.href = '/';
            }
            return;
        }

        // 加载数据
        loadUsers();
    } catch (error) {
        console.error('Auth check failed:', error);
        window.location.href = '/';
    }
});

// 加载用户列表
async function loadUsers() {
    try {
        const response = await fetch(API + '/users', {
            credentials: 'same-origin'
        });
        const data = await response.json();
        renderUserTable(data.users);
    } catch (error) {
        console.error('Failed to load users:', error);
        const el = document.getElementById('createUserError');
        if (el) { el.textContent = '加载用户列表失败: ' + error.message; el.classList.add('show'); }
    }
}

// 渲染用户表格
function renderUserTable(users) {
    const tbody = document.getElementById('userTableBody');
    tbody.innerHTML = '';

    if (!users || users.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:#6b7280;">暂无用户</td></tr>';
        return;
    }

    users.forEach(user => {
        const statusBadge = user.status === 'active'
            ? '<span class="badge bg-active">启用</span>'
            : '<span class="badge bg-disabled">停用</span>';

        const roleBadge = user.role === 'admin'
            ? '<span class="badge bg-admin">管理员</span>'
            : '<span class="badge bg-user">普通用户</span>';

        const createdAt = new Date(user.created_at).toLocaleString('zh-CN', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit'
        });

        const row = document.createElement('tr');
        row.innerHTML = `
            <td style="font-weight:600;color:var(--a)">${escapeHtml(user.username)}</td>
            <td>${roleBadge}</td>
            <td>${statusBadge}</td>
            <td style="color:var(--tx2)">${createdAt}</td>
            <td>
                <div class="btn-row">
                    <button class="ab ab-g ab-sm" onclick="showClusterModal(${user.id}, '${escapeHtml(user.username)}')">
                        管理集群
                    </button>
                    <button class="ab ab-g ab-sm" onclick="showNamespaceModal(${user.id}, '${escapeHtml(user.username)}')">
                        管理namespace
                    </button>
                    ${user.username !== 'admin' ? `
                    <button class="ab ab-g ab-sm" onclick="editUser(${user.id}, '${escapeHtml(user.username)}', '${user.role}', '${user.status}')">
                        编辑
                    </button>
                    <button class="ab ab-d ab-sm" onclick="deleteUser(${user.id}, '${escapeHtml(user.username)}')">
                        删除
                    </button>
                    ` : `
                    <span style="color:var(--tx3);font-size:11px">（系统账户）</span>
                    `}
                </div>
            </td>
        `;
        tbody.appendChild(row);
    });
}

// 显示模态框
function showModal(modalId) {
    document.getElementById(modalId).classList.add('open');
}

// 显示创建用户模态框
function showCreateUserModal() {
    document.getElementById('newUsername').value = '';
    document.getElementById('newPassword').value = '';
    document.getElementById('newRole').value = 'user';
    document.getElementById('newStatus').value = 'active';
    document.getElementById('createUserError').classList.remove('show');
    showModal('createUserModal');
}

// 关闭模态框
function closeModal(modalId) {
    document.getElementById(modalId).classList.remove('open');
}

// 创建用户
async function createUser() {
    const username = document.getElementById('newUsername').value.trim();
    const password = document.getElementById('newPassword').value;
    const role = document.getElementById('newRole').value;
    const status = document.getElementById('newStatus').value;

    if (!username || !password) {
        document.getElementById('createUserError').textContent = '用户名和密码必填';
        document.getElementById('createUserError').classList.add('show');
        return;
    }

    if (password.length < 6) {
        document.getElementById('createUserError').textContent = '密码长度至少6位';
        document.getElementById('createUserError').classList.add('show');
        return;
    }

    try {
        const response = await fetch(API + '/users', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({ username, password, role, status })
        });

        const data = await response.json();

        if (response.ok) {
            closeModal('createUserModal');
            loadUsers();
            alert('用户创建成功');
        } else {
            document.getElementById('createUserError').textContent = data.error || '创建失败';
            document.getElementById('createUserError').classList.add('show');
        }
    } catch (error) {
        console.error('Failed to create user:', error);
        document.getElementById('createUserError').textContent = '请求失败: ' + error.message;
        document.getElementById('createUserError').classList.add('show');
    }
}

// 编辑用户
async function editUser(userId, username, role, status) {
    const newUsername = prompt('请输入新用户名:', username);
    if (newUsername === null) return;

    if (newUsername.trim() === '') {
        alert('用户名不能为空');
        return;
    }

    try {
        const response = await fetch(API + `/users/${userId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({ username: newUsername.trim(), role, status })
        });

        const data = await response.json();

        if (response.ok) {
            loadUsers();
            alert('用户更新成功');
        } else {
            alert(data.error.data || '更新失败');
        }
    } catch (error) {
        console.error('Failed to edit user:', error);
        alert('请求失败');
    }
}

// 删除用户
async function deleteUser(userId, username) {
    if (!confirm(`确定要删除用户 "${username}" 吗`)) {
        return;
    }

    try {
        const response = await fetch(API + `/users/${userId}`, {
            method: 'DELETE',
            credentials: 'same-origin'
        });

        const data = await response.json();

        if (response.ok) {
            loadUsers();
            alert('用户删除成功');
        } else {
            alert(data.error || '删除失败');
        }
    } catch (error) {
        console.error('Failed to delete user:', error);
        alert('请求失败');
    }
}

// 显示集群分配模态框
async function showClusterModal(userId, username) {
    try {
        // 加载可用集群（保留完整对象以获取 id 和 name）
        const clusterResponse = await fetch(API + '/clusters');
        const clusterData = await clusterResponse.json();
        const allClusters = clusterData.clusters || [];

        // 加载用户已分配的集群
        const userClusterResponse = await fetch(API + `/user-clusters/${userId}`);
        const assignedData = await userClusterResponse.json();
        const assignedClusterIds = (assignedData.clusters || []).map(uc => uc.cluster_id);

        // 未分配的集群（用 id 匹配，因为 cluster_id 存的是集群 id）
        const unassignedClusters = allClusters.filter(c => !assignedClusterIds.includes(c.id));

        // 渲染可用（未分配）集群列表
        const availableList = document.getElementById('availableClusters');
        availableList.innerHTML = '';
        if (unassignedClusters.length === 0) {
            availableList.innerHTML = '<div style="text-align:center;color:var(--tx3);padding:16px;font-size:11px">无可用集群</div>';
        }
        unassignedClusters.forEach(cluster => {
            const item = document.createElement('div');
            item.className = 'cluster-item';
            item.innerHTML = `
                <label>
                    <input type="checkbox"
                           value="${escapeHtml(cluster.id)}"
                           data-name="${escapeHtml(cluster.name)}"
                           onchange="updateClusterAssignment(this)">
                    <span>${escapeHtml(cluster.name)}</span>
                </label>
            `;
            availableList.appendChild(item);
        });

        // 渲染已分配集群列表（通过 id 查找集群名称来显示）
        const assignedList = document.getElementById('assignedClusters');
        assignedList.innerHTML = '';
        if (assignedClusterIds.length === 0) {
            assignedList.innerHTML = '<div style="text-align:center;color:var(--tx3);padding:16px;font-size:11px">暂无已分配集群</div>';
        }
        assignedClusterIds.forEach(cid => {
            const clusterObj = allClusters.find(c => c.id === cid);
            const displayName = clusterObj ? clusterObj.name : cid;
            const item = document.createElement('div');
            item.className = 'cluster-item';
            item.innerHTML = `
                <label>
                    <input type="checkbox"
                           value="${escapeHtml(cid)}"
                           data-name="${escapeHtml(displayName)}"
                           checked
                           onchange="updateClusterAssignment(this)">
                    <span>${escapeHtml(displayName)}</span>
                </label>
            `;
            assignedList.appendChild(item);
        });

        document.getElementById('clusterModalUser').textContent = username;
        // 存储 userId 到模态框的 data 属性
        document.getElementById('clusterModal').dataset.userId = userId;
        showModal('clusterModal');
        document.getElementById('clusterError').classList.remove('show');
    } catch (error) {
        console.error('Failed to load clusters:', error);
        alert('加载集群列表失败');
    }
}

// 保存集群分配
async function saveClusterAssignment() {
    const modal = document.getElementById('clusterModal');
    const userId = modal.dataset.userId;
    if (!userId) {
        alert('用户ID丢失，请重新打开窗口');
        return;
    }

    // 已分配列表中的所有集群就是最终要保留的分配
    const assignedItems = document.querySelectorAll('#assignedClusters .cluster-item input[type="checkbox"]');
    const targetClusters = Array.from(assignedItems).map(cb => cb.value);

    try {
        // 先删除该用户所有现有分配
        const existingResp = await fetch(API + `/user-clusters/${userId}`);
        const existingData = await existingResp.json();
        const existingClusters = (existingData.clusters || []);
        for (const row of existingClusters) {
            await fetch(API + `/user-clusters/by-user-cluster?user_id=${userId}&cluster_id=${encodeURIComponent(row.cluster_id)}`, {
                method: 'DELETE',
                credentials: 'same-origin'
            });
        }

        // 添加新分配
        for (const cluster of targetClusters) {
            const resp = await fetch(API + '/user-clusters', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'same-origin',
                body: JSON.stringify({ user_id: parseInt(userId), cluster_id: cluster })
            });
            if (!resp.ok) {
                const data = await resp.json();
                // 已存在则忽略
                if (!data.error || !data.error.includes('已存在')) {
                    throw new Error(data.error || '分配失败');
                }
            }
        }

        closeModal('clusterModal');
        alert('集群分配保存成功');
    } catch (error) {
        console.error('Failed to save cluster assignment:', error);
        alert('保存失败: ' + error.message);
        document.getElementById('clusterError').textContent = '保存失败: ' + error.message;
        document.getElementById('clusterError').classList.add('show');
    }
}

// 移除集群分配
async function removeClusterAssignment(cluster, userId, silent = false) {
    try {
        const response = await fetch(API + `/user-clusters/by-user-cluster?user_id=${userId}&cluster_id=${encodeURIComponent(cluster)}`, {
            method: 'DELETE',
            credentials: 'same-origin'
        });
        
        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.error || '删除失败');
        }

        if (!silent) {
            console.log(`Removed cluster assignment: ${cluster} for user ${userId}`);
        }
    } catch (error) {
        console.error('Failed to remove cluster assignment:', error);
        if (!silent) {
            alert('移除失败: ' + error.message);
        }
    }
}

// 更新集群分配显示
function updateClusterAssignment(checkbox) {
    const availableList = document.getElementById('availableClusters');
    const assignedList = document.getElementById('assignedClusters');

    if (checkbox.checked) {
        // 移动到已分配列表
        const item = checkbox.closest('.cluster-item');
        assignedList.appendChild(item);
    } else {
        // 移动回可用列表
        const item = checkbox.closest('.cluster-item');
        availableList.appendChild(item);
    }
}

// Namespace 授权管理
async function showNamespaceModal(userId, username) {
    const modal = document.getElementById('namespaceModal');
    modal.dataset.userId = userId;
    document.getElementById('namespaceModalUser').textContent = username;
    document.getElementById('namespaceError').classList.remove('show');

    try {
        const [clusterResponse, namespaceResponse] = await Promise.all([
            fetch(API + '/clusters', { credentials: 'same-origin' }),
            fetch(API + `/user-namespaces/${userId}`, { credentials: 'same-origin' })
        ]);
        const clusterData = await clusterResponse.json();
        const namespaceData = await namespaceResponse.json();
        const clusters = clusterData.clusters || [];
        const namespaceClusterNameMap = {};
        clusters.forEach(c => { namespaceClusterNameMap[c.id] = c.name || c.id; });
        modal.dataset.clusterNameMap = JSON.stringify(namespaceClusterNameMap);

        const select = document.getElementById('namespaceClusterSelect');
        select.innerHTML = clusters.map(c => `<option value="${escapeHtml(c.id)}">${escapeHtml(c.name || c.id)}</option>`).join('');
        select.dataset.clusters = JSON.stringify(clusters.map(c => ({ id: c.id, name: c.name })));

        renderAssignedNamespaces(namespaceData.namespaces || [], namespaceClusterNameMap);
        showModal('namespaceModal');
        await loadNamespacesForSelectedCluster();
    } catch (error) {
        console.error('Failed to load namespace permissions:', error);
        alert('加载 namespace 授权失败: ' + error.message);
    }
}

async function loadNamespacesForSelectedCluster() {
    const select = document.getElementById('namespaceClusterSelect');
    const clusterId = select.value;
    const options = document.getElementById('namespaceOptions');
    options.innerHTML = '';
    if (!clusterId) return;
    try {
        const resp = await fetch(API + `/clusters/${encodeURIComponent(clusterId)}/namespaces`, { credentials: 'same-origin' });
        const data = await resp.json();
        const namespaces = data.namespaces || [];
        options.innerHTML = namespaces.map(ns => `<option value="${escapeHtml(ns)}"></option>`).join('') + '<option value="*"></option>';
    } catch (error) {
        console.warn('Failed to load namespace options:', error);
        options.innerHTML = '<option value="default"></option><option value="*"></option>';
    }
}

function renderAssignedNamespaces(rows, namespaceClusterNameMap) {
    const list = document.getElementById('assignedNamespaces');
    const clusterNameMap = namespaceClusterNameMap || (() => {
        try { return JSON.parse(document.getElementById('namespaceModal').dataset.clusterNameMap || '{}'); }
        catch { return {}; }
    })();
    list.innerHTML = '';
    if (!rows || rows.length === 0) {
        list.innerHTML = '<div style="text-align:center;color:var(--tx3);padding:16px;font-size:11px">暂无 namespace 授权</div>';
        return;
    }
    rows.forEach(row => {
        const displayCluster = clusterNameMap[row.cluster_id] || row.cluster_name || row.cluster_id;
        const item = document.createElement('div');
        item.className = 'namespace-chip';
        item.innerHTML = `
            <span><code>${escapeHtml(displayCluster)}</code> / <code>${escapeHtml(row.namespace)}</code></span>
            <button class="ab ab-d ab-sm" onclick="removeNamespacePermission(${row.id}, '${escapeHtml(row.cluster_id)}', '${escapeHtml(row.namespace)}')">取消</button>
        `;
        list.appendChild(item);
    });
}

async function assignNamespace() {
    const modal = document.getElementById('namespaceModal');
    const userId = parseInt(modal.dataset.userId, 10);
    const clusterId = document.getElementById('namespaceClusterSelect').value;
    const namespace = document.getElementById('namespaceInput').value.trim();
    const err = document.getElementById('namespaceError');
    err.classList.remove('show');

    if (!userId || !clusterId || !namespace) {
        err.textContent = '用户、集群和 namespace 必填';
        err.classList.add('show');
        return;
    }

    try {
        const resp = await fetch(API + '/user-namespaces', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({ user_id: userId, cluster_id: clusterId, namespace })
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.error || '授权失败');
        document.getElementById('namespaceInput').value = '';
        const refreshed = await fetch(API + `/user-namespaces/${userId}`, { credentials: 'same-origin' }).then(r => r.json());
        renderAssignedNamespaces(refreshed.namespaces || []);
    } catch (error) {
        err.textContent = '授权失败: ' + error.message;
        err.classList.add('show');
    }
}

async function removeNamespacePermission(assignmentId, clusterId, namespace) {
    const modal = document.getElementById('namespaceModal');
    const userId = parseInt(modal.dataset.userId, 10);
    if (!confirm(`确定取消 ${clusterId}/${namespace} 授权吗？`)) return;
    try {
        const endpoint = assignmentId
            ? API + `/user-namespaces/${assignmentId}`
            : API + `/user-namespaces/by-user-cluster-namespace?user_id=${userId}&cluster_id=${encodeURIComponent(clusterId)}&namespace=${encodeURIComponent(namespace)}`;
        const resp = await fetch(endpoint, { method: 'DELETE', credentials: 'same-origin' });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.error || '取消授权失败');
        const refreshed = await fetch(API + `/user-namespaces/${userId}`, { credentials: 'same-origin' }).then(r => r.json());
        renderAssignedNamespaces(refreshed.namespaces || []);
    } catch (error) {
        const err = document.getElementById('namespaceError');
        err.textContent = '取消授权失败: ' + error.message;
        err.classList.add('show');
    }
}

// HTML 转义
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ── 全局函数暴露 ─────────────────────────────────────────────────────────
window.loadUsers = loadUsers;
window.showCreateUserModal = showCreateUserModal;
window.closeModal = closeModal;
window.createUser = createUser;
window.saveClusterAssignment = saveClusterAssignment;
window.showClusterModal = showClusterModal;
window.showNamespaceModal = showNamespaceModal;
window.assignNamespace = assignNamespace;
window.removeNamespacePermission = removeNamespacePermission;
window.loadNamespacesForSelectedCluster = loadNamespacesForSelectedCluster;
window.escapeHtml = escapeHtml;
window.updateClusterAssignment = updateClusterAssignment;
