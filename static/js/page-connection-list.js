// Connection List Page - 连接列表页面逻辑
// 负责渲染连接列表表格、过滤器和表格操作

class ConnectionListPage {
    constructor() {
        this.connections = [];
        this.init();
    }

    init() {
        this.loadConnections();
        this.bindEvents();
    }

    loadConnections() {
        // 从 connections.js 获取连接数据
        if (typeof getConnections === 'function') {
            this.connections = getConnections();
        }
        this.renderTable();
    }

    renderTable() {
        const tbody = document.getElementById('connection-table-body');
        if (!tbody) return;

        if (!this.connections || this.connections.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--tx3)">暂无连接</td></tr>';
            return;
        }

        tbody.innerHTML = this.connections.map(conn => `
            <tr data-conn-id="${conn.id || ''}">
                <td>${conn.cluster_name || '—'}</td>
                <td>${conn.namespace || '—'}</td>
                <td>${conn.pod_name || '—'}</td>
                <td><span class="conn-status ${conn.status || 'unknown'}">${conn.status || '未知'}</span></td>
                <td>
                    <button class="btn btn-sm" onclick="ConnectionListPage.viewDetail('${conn.id || ''}')">详情</button>
                    <button class="btn btn-sm danger" onclick="ConnectionListPage.remove('${conn.id || ''}')">删除</button>
                </td>
            </tr>
        `).join('');
    }

    bindEvents() {
        const addBtn = document.getElementById('add-connection-btn');
        if (addBtn) {
            addBtn.addEventListener('click', () => this.openAddConnection());
        }
    }

    openAddConnection() {
        // 打开添加连接的弹窗
        if (typeof openAddCluster === 'function') {
            openAddCluster();
        }
    }

    static viewDetail(connId) {
        if (connId) {
            window.location.href = `/connection-detail?conn=${connId}`;
        }
    }

    static remove(connId) {
        if (confirm('确定删除此连接？')) {
            // 删除连接逻辑
            if (typeof deleteConnection === 'function') {
                deleteConnection(connId);
            }
        }
    }
}

// 页面加载后初始化
document.addEventListener('DOMContentLoaded', () => {
    window.connectionListPage = new ConnectionListPage();
});
