// 审计日志页面 JavaScript
const API_BASE = (() => {
    if (typeof window !== 'undefined' && window.location.protocol.startsWith('http')) {
        return `${window.location.protocol}//${window.location.host}/api`;
    }
    return 'http://127.0.0.1:5001/api';
})();

let currentPage = 0;
const pageSize = 50;
let allLogs = [];

// 页面加载时获取用户列表和日志
document.addEventListener('DOMContentLoaded', async () => {
    // 检查登录状态
    try {
        const userRes = await fetch(`${API_BASE}/auth/current`, { credentials: 'include' });
        if (!userRes.ok) {
            window.location.href = 'login.html';
            return;
        }
        const userData = await userRes.json();
        if (!userData.user || userData.user.role !== 'admin') {
            alert('只有管理员可以查看审计日志');
            window.location.href = 'index.html';
            return;
        }
    } catch (e) {
        window.location.href = 'login.html';
        return;
    }

    // 加载用户列表
    loadUsers();
    // 加载日志
    loadLogs();
});

async function loadUsers() {
    try {
        const res = await fetch(`${API_BASE}/users`, { credentials: 'include' });
        if (res.ok) {
            const data = await res.json();
            const select = document.getElementById('filterUser');
            data.users.forEach(user => {
                const option = document.createElement('option');
                option.value = user.id;
                option.textContent = user.username;
                select.appendChild(option);
            });
        }
    } catch (e) {
        console.error('加载用户列表失败:', e);
    }
}

async function loadLogs() {
    const tbody = document.getElementById('logsTable');
    tbody.innerHTML = '<tr><td colspan="7" class="loading">加载中...</td></tr>';

    const params = new URLSearchParams();
    const userId = document.getElementById('filterUser').value;
    const action = document.getElementById('filterAction').value;
    const resourceType = document.getElementById('filterResourceType').value;
    const startDate = document.getElementById('filterStartDate').value;
    const endDate = document.getElementById('filterEndDate').value;

    if (userId) params.append('user_id', userId);
    if (action) params.append('action', action);
    if (resourceType) params.append('resource_type', resourceType);
    if (startDate) params.append('start_date', startDate);
    if (endDate) params.append('end_date', endDate);
    params.append('limit', pageSize);
    params.append('offset', currentPage * pageSize);

    try {
        const res = await fetch(`${API_BASE}/audit-logs?${params}`, { credentials: 'include' });
        if (!res.ok) {
            const err = await res.json();
            alert(err.error || '获取审计日志失败');
            tbody.innerHTML = '<tr><td colspan="7" class="empty-state">加载失败</td></tr>';
            return;
        }
        const data = await res.json();
        renderLogs(data.logs || []);
        updatePagination(data.logs?.length || 0);
    } catch (e) {
        console.error('加载审计日志失败:', e);
        tbody.innerHTML = '<tr><td colspan="7" class="empty-state">加载失败</td></tr>';
    }
}

function renderLogs(logs) {
    const tbody = document.getElementById('logsTable');
    if (!logs || logs.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="empty-state">暂无日志记录</td></tr>';
        return;
    }

    tbody.innerHTML = logs.map(log => {
        const time = log.timestamp ? new Date(log.timestamp).toLocaleString('zh-CN') : '-';
        const actionClass = getActionClass(log.action);
        const details = log.details || '-';
        const ip = log.ip_address || '-';

        return `
            <tr>
                <td style="color:var(--tx2)">${time}</td>
                <td style="font-weight:600">${log.username || '系统'}</td>
                <td><span class="badge ${actionClass}">${getActionText(log.action)}</span></td>
                <td>${log.resource_type || '-'}</td>
                <td style="font-family:var(--mono);font-size:11px;color:var(--tx2)">${log.resource_id || '-'}</td>
                <td title="${escapeHtml(details)}" style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${truncate(details, 50)}</td>
                <td style="color:var(--tx2);font-size:11px">${ip}</td>
            </tr>
        `;
    }).join('');
}

function getActionClass(action) {
    const map = {
        'login': 'bg-login',
        'login_failed': 'bg-fail',
        'logout': 'bg-logout',
        'connect': 'bg-connect',
        'disconnect': 'bg-connect',
        'create': 'bg-create',
        'delete': 'bg-delete',
        'download': 'bg-download',
        'task_start': 'bg-create',
        'task_cancel': 'bg-delete',
        'user_create': 'bg-create',
        'user_update': 'bg-create',
        'user_delete': 'bg-delete',
        'cluster_assign': 'bg-create'
    };
    return map[action] || '';
}

function getActionText(action) {
    const map = {
        'login': '登录',
        'login_failed': '登录失败',
        'logout': '登出',
        'connect': '连接',
        'disconnect': '断开',
        'create': '创建',
        'delete': '删除',
        'download': '下载',
        'task_start': '任务开始',
        'task_cancel': '任务取消',
        'user_create': '创建用户',
        'user_update': '更新用户',
        'user_delete': '删除用户',
        'cluster_assign': '分配集群'
    };
    return map[action] || action;
}

function truncate(text, maxLength) {
    if (!text) return '-';
    return text.length > maxLength ? text.substring(0, maxLength) + '...' : text;
}

function escapeHtml(text) {
    if (!text) return '';
    return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function updatePagination(count) {
    document.getElementById('pageInfo').textContent = `第 ${currentPage + 1} 页`;
    document.getElementById('prevBtn').disabled = currentPage === 0;
    document.getElementById('nextBtn').disabled = count < pageSize;
}

function prevPage() {
    if (currentPage > 0) {
        currentPage--;
        loadLogs();
    }
}

function nextPage() {
    currentPage++;
    loadLogs();
}

function resetFilters() {
    document.getElementById('filterUser').value = '';
    document.getElementById('filterAction').value = '';
    document.getElementById('filterResourceType').value = '';
    document.getElementById('filterStartDate').value = '';
    document.getElementById('filterEndDate').value = '';
    currentPage = 0;
    loadLogs();
}

async function exportLogs() {
    // 获取所有日志（不分页）用于导出
    const params = new URLSearchParams();
    const userId = document.getElementById('filterUser').value;
    const action = document.getElementById('filterAction').value;
    const resourceType = document.getElementById('filterResourceType').value;
    const startDate = document.getElementById('filterStartDate').value;
    const endDate = document.getElementById('filterEndDate').value;

    if (userId) params.append('user_id', userId);
    if (action) params.append('action', action);
    if (resourceType) params.append('resource_type', resourceType);
    if (startDate) params.append('start_date', startDate);
    if (endDate) params.append('end_date', endDate);
    params.append('limit', 10000); // 获取更多数据

    try {
        const res = await fetch(`${API_BASE}/audit-logs?${params}`, { credentials: 'include' });
        const data = await res.json();
        const logs = data.logs || [];

        // 转换为 CSV
        const headers = ['时间', '用户', '操作', '资源类型', '资源ID', '详情', 'IP', 'User-Agent'];
        const rows = logs.map(log => [
            log.timestamp || '',
            log.username || '',
            log.action || '',
            log.resource_type || '',
            log.resource_id || '',
            (log.details || '').replace(/,/g, ';'),
            log.ip_address || '',
            log.user_agent || ''
        ]);

        const csv = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
        const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `audit-logs-${new Date().toISOString().slice(0,10)}.csv`;
        a.click();
        URL.revokeObjectURL(url);
    } catch (e) {
        alert('导出失败: ' + e.message);
    }
}

// 检查是否有 API_BASE 定义
if (typeof API_BASE === 'undefined') {
    console.warn('未定义 API_BASE，使用默认值');
}

// ── 全局函数暴露 ─────────────────────────────────────────────────────────
window.loadLogs = loadLogs;
window.resetFilters = resetFilters;
window.exportLogs = exportLogs;
window.prevPage = prevPage;
window.nextPage = nextPage;