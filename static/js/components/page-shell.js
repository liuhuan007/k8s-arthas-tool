/**
 * PageShell - 共享页面外壳组件
 * 提供页面头部、AI抽屉和状态栏
 */
class PageShell {
    constructor() {
        this.init();
    }
    
    init() {
        this.renderHeader();
        this.renderAIDrawer();
        this.renderStatusBar();
    }
    
    renderHeader() {
        const header = document.createElement('header');
        header.className = 'page-header';
        header.innerHTML = `
            <div class="header-left">
                <h1 class="page-title">K8s Arthas Tool</h1>
            </div>
            <div class="header-right">
                <button id="ai-drawer-btn" class="btn btn-icon">AI</button>
            </div>
        `;
        document.body.prepend(header);
    }
    
    renderAIDrawer() {
        const drawer = document.createElement('div');
        drawer.id = 'ai-drawer';
        drawer.className = 'ai-drawer hidden';
        drawer.innerHTML = `
            <div class="ai-drawer-header">
                <h3>AI 助手</h3>
                <button id="close-ai-drawer" class="btn btn-icon">×</button>
            </div>
            <div class="ai-drawer-content">
                <!-- AI 内容 -->
            </div>
        `;
        document.body.appendChild(drawer);
    }
    
    renderStatusBar() {
        const statusBar = document.createElement('div');
        statusBar.id = 'conn-status-bar';
        statusBar.className = 'conn-status-bar';
        statusBar.innerHTML = `
            <div class="status-bar-content">
                <span class="connection-info">未连接</span>
                <button id="view-detail-btn" class="btn btn-link">查看详情</button>
            </div>
        `;
        document.body.appendChild(statusBar);
    }
}

// 页面加载后初始化
document.addEventListener('DOMContentLoaded', function() {
    if (typeof PageShell !== 'undefined') {
        window.pageShell = new PageShell();
    }
});