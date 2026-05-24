/**
 * WorkspacePage - 工作页面基类
 * 提供连接上下文加载和工作区初始化
 */
class WorkspacePage {
    constructor() {
        this.connectionId = null;
        this.connectionData = null;
        this.init();
    }
    
    init() {
        this.parseQueryString();
        this.loadConnection();
        this.initWorkspace();
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
    
    initWorkspace() {
        // 子类应该重写此方法来初始化特定的工作区
        console.log('WorkspacePage.initWorkspace() - 子类应该重写此方法');
    }
    
    bindEvents() {
        // 绑定返回按钮事件
        const backBtn = document.getElementById('back-btn');
        if (backBtn) {
            backBtn.addEventListener('click', () => {
                if (this.connectionId) {
                    window.location.href = `/connection-detail?conn=${this.connectionId}`;
                } else {
                    window.location.href = '/';
                }
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
    if (typeof WorkspacePage !== 'undefined') {
        window.workspacePage = new WorkspacePage();
    }
});