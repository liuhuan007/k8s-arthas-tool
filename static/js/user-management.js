// 用户管理页面逻辑

const API = (() => {
    if (typeof window !== 'undefined' && window.location.protocol.startsWith('http')) {
        return `${window.location.protocol}//${window.location.host}/api`;
    }
    return 'http://127.0.0.1:5001/api';
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
            // 不是管理员，重定向到主页
            alert('只有管理员可以访问此页面');
            window.location.href = '/';
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
window.escapeHtml = escapeHtml;
window.updateClusterAssignment = updateClusterAssignment;
