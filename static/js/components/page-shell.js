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
                <h3>🤖 AI 助手</h3>
                <div class="ai-drawer-header-actions">
                    <button class="btn btn-icon" onclick="if(typeof agentPanelClearChat==='function') agentPanelClearChat()" title="清空对话">🗑️</button>
                    <button id="close-ai-drawer" class="btn btn-icon" onclick="pageShell.toggleAIDrawer()">×</button>
                </div>
            </div>
            <div id="agentPanelContainer" style="flex:1;overflow:hidden"></div>
        `;
        document.body.appendChild(drawer);
        // 延迟渲染 agent panel（等 DOM 就绪）
        setTimeout(() => {
            if (typeof renderAgentPanel === 'function') {
                renderAgentPanel('agentPanelContainer');
            }
        }, 100);
    }
    
    sendAIMessage() {
        // 委托给 agent panel
        if (typeof agentPanelSend === 'function') {
            agentPanelSend();
        }
    }
    
    _syncDrawerWithMain(role, content) {
        // 将 ai-chat.js 的消息同步显示到抽屉
        const drawerMessages = document.getElementById('aiDrawerMessages');
        if (!drawerMessages) return;
        
        const welcome = drawerMessages.querySelector('.ai-welcome');
        if (welcome) welcome.remove();
        
        // 添加消息到抽屉
        const msgDiv = document.createElement('div');
        msgDiv.className = `ai-message ai-message-${role}`;
        msgDiv.innerHTML = `
            <div class="ai-message-avatar">${role === 'user' ? '👤' : '🤖'}</div>
            <div class="ai-message-content">${this._escHtml(content)}</div>
        `;
        drawerMessages.appendChild(msgDiv);
        drawerMessages.scrollTop = drawerMessages.scrollHeight;
    }
    
    _escHtml(text) {
        if (!text) return '';
        const d = document.createElement('div');
        d.textContent = text;
        return d.innerHTML;
    }
    
    addAIMessage(role, content) {
        const messagesContainer = document.getElementById('aiDrawerMessages');
        if (!messagesContainer) return;
        
        // 移除欢迎信息
        const welcome = messagesContainer.querySelector('.ai-welcome');
        if (welcome) welcome.remove();
        
        const messageDiv = document.createElement('div');
        messageDiv.className = `ai-message ai-message-${role}`;
        messageDiv.innerHTML = `
            <div class="ai-message-avatar">${role === 'user' ? '👤' : '🤖'}</div>
            <div class="ai-message-content">${content}</div>
        `;
        messagesContainer.appendChild(messageDiv);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }
    
    autoResizeInput(textarea) {
        textarea.style.height = 'auto';
        textarea.style.height = Math.min(textarea.scrollHeight, 120) + 'px';
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