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
    
    elementExists(selector) {
        return document.querySelector(selector) !== null;
    }
    
    renderHeader() {
        // 如果页面已有topbar，则不创建新的header
        if (this.elementExists('.topbar')) {
            // 确保AI按钮存在
            if (!this.elementExists('#ai-drawer-btn')) {
                const aiBtn = document.createElement('button');
                aiBtn.id = 'ai-drawer-btn';
                aiBtn.className = 'btn btn-icon';
                aiBtn.textContent = 'AI';
                aiBtn.onclick = () => this.toggleAIDrawer();
                // 将按钮添加到topbar的右侧区域
                const tbRight = document.querySelector('.tb-right');
                if (tbRight) {
                    tbRight.insertBefore(aiBtn, tbRight.firstChild);
                }
            }
            return;
        }
        
        // 如果没有topbar，创建页面头部
        if (!this.elementExists('.page-header')) {
            const header = document.createElement('header');
            header.className = 'page-header';
            header.innerHTML = `
                <div class="header-left">
                    <h1 class="page-title">K8s Arthas Tool</h1>
                </div>
                <div class="header-right">
                    <button id="ai-drawer-btn" class="btn btn-icon" onclick="pageShell.toggleAIDrawer()">AI</button>
                </div>
            `;
            document.body.prepend(header);
        }
    }
    
    renderAIDrawer() {
        // 如果AI抽屉已存在，则不创建
        if (this.elementExists('#ai-drawer')) {
            return;
        }
        
        const drawer = document.createElement('div');
        drawer.id = 'ai-drawer';
        drawer.className = 'ai-drawer hidden';
        drawer.innerHTML = `
            <div class="ai-drawer-header">
                <h3>AI 助手</h3>
                <button id="close-ai-drawer" class="btn btn-icon" onclick="pageShell.toggleAIDrawer()">×</button>
            </div>
            <div class="ai-drawer-content">
                <!-- AI 内容 -->
            </div>
        `;
        document.body.appendChild(drawer);
    }
    
    renderStatusBar() {
        // 如果状态栏已存在，则不创建
        if (this.elementExists('#conn-status-bar')) {
            return;
        }
        
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
    
    toggleAIDrawer() {
        const drawer = document.getElementById('ai-drawer');
        if (drawer) {
            drawer.classList.toggle('hidden');
        }
    }
}

// 页面加载后初始化
document.addEventListener('DOMContentLoaded', function() {
    if (typeof PageShell !== 'undefined') {
        window.pageShell = new PageShell();
    }
});

// 全局函数，用于HTML onclick属性
function toggleAIDrawer() {
    if (window.pageShell) {
        window.pageShell.toggleAIDrawer();
    }
}