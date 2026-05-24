/**
 * ConnectionPageContext - 连接页面上下文辅助函数
 * 解析查询字符串中的连接ID，加载连接信息，并提供页面间导航
 */
class ConnectionPageContext {
    constructor() {
        this.connectionId = null;
        this.connectionData = null;
        this.init();
    }
    
    init() {
        this.parseQueryString();
        this.loadConnection();
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
    
    getConnection() {
        return this.connectionData;
    }
    
    getConnectionId() {
        return this.connectionId;
    }
    
    hasConnection() {
        return this.connectionId !== null && this.connectionData !== null;
    }
    
    navigateTo(page) {
        if (this.connectionId) {
            window.location.href = `/${page}?conn=${this.connectionId}`;
        } else {
            window.location.href = `/${page}`;
        }
    }
    
    navigateToDetail() {
        this.navigateTo('connection-detail');
    }
    
    navigateToTerminal() {
        this.navigateTo('terminal');
    }
    
    navigateToMonitor() {
        this.navigateTo('monitor');
    }
    
    navigateToWorkspace() {
        this.navigateTo('workspace');
    }
}

// 页面加载后初始化
document.addEventListener('DOMContentLoaded', function() {
    if (typeof ConnectionPageContext !== 'undefined') {
        window.connectionPageContext = new ConnectionPageContext();
    }
});