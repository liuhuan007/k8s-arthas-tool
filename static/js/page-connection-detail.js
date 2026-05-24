/**
 * ConnectionDetailPage - 连接详情页面
 * 显示连接详情和两步连接UI
 */
class ConnectionDetailPage {
    constructor() {
        this.connectionId = null;
        this.connectionData = null;
        this.init();
    }
    
    init() {
        this.parseQueryString();
        this.loadConnection();
        this.initTwoStepConnection();
        this.bindEvents();
    }
    
    parseQueryString() {
        const params = new URLSearchParams(window.location.search);
        this.connectionId = params.get('conn');
    }
    
    loadConnection() {
        if (this.connectionId) {
            // 从连接存储中加载连接信息
            this.connectionData = this.getConnectionFromStore(this.connectionId);
            this.renderConnectionInfo();
        }
    }
    
    getConnectionFromStore(connectionId) {
        // 尝试从全局连接存储中获取连接信息
        if (typeof window.connectionStore !== 'undefined') {
            return window.connectionStore.getConnection(connectionId);
        }
        
        // 尝试从localStorage中获取
        try {
            const connections = JSON.parse(localStorage.getItem('connections') || '[]');
            return connections.find(conn => conn.id === connectionId);
        } catch (e) {
            console.error('Failed to load connection from localStorage:', e);
            return null;
        }
    }
    
    renderConnectionInfo() {
        const container = document.getElementById('connection-info');
        if (!container || !this.connectionData) return;
        
        const { cluster, namespace, pod, status } = this.connectionData;
        container.innerHTML = `
            <div class="connection-info-card">
                <h3>连接信息</h3>
                <div class="info-grid">
                    <div class="info-item">
                        <label>集群:</label>
                        <span>${cluster || '未知'}</span>
                    </div>
                    <div class="info-item">
                        <label>命名空间:</label>
                        <span>${namespace || '未知'}</span>
                    </div>
                    <div class="info-item">
                        <label>Pod:</label>
                        <span>${pod || '未知'}</span>
                    </div>
                    <div class="info-item">
                        <label>状态:</label>
                        <span class="status ${status || 'unknown'}">${status || '未知'}</span>
                    </div>
                </div>
            </div>
        `;
    }
    
    initTwoStepConnection() {
        // 初始化两步连接UI
        const container = document.getElementById('two-step-connection-container');
        if (!container) return;
        
        // 如果有连接数据，配置两步连接UI
        if (this.connectionData) {
            // 这里可以配置两步连接UI的目标
            // 例如：设置DOM目标、初始化连接状态等
        }
    }
    
    bindEvents() {
        // 绑定返回按钮事件
        const backBtn = document.getElementById('back-btn');
        if (backBtn) {
            backBtn.addEventListener('click', () => {
                window.location.href = '/';
            });
        }
    }
    
    getConnection() {
        return this.connectionData;
    }
    
    getConnectionId() {
        return this.connectionId;
    }
    
    hasConnection() {
        return this.connectionId !== null && this.connectionData !== null;
    }
}

// 页面加载后初始化
document.addEventListener('DOMContentLoaded', function() {
    if (typeof ConnectionDetailPage !== 'undefined') {
        window.connectionDetailPage = new ConnectionDetailPage();
    }
});