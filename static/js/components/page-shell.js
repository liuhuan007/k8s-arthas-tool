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
                    <button class="btn btn-icon" onclick="if(typeof aiClearChat==='function') aiClearChat()" title="清空对话">🗑️</button>
                    <button id="close-ai-drawer" class="btn btn-icon" onclick="pageShell.toggleAIDrawer()">×</button>
                </div>
            </div>
            <div class="ai-drawer-messages" id="aiDrawerMessages">
                <div class="ai-welcome">
                    <div class="ai-welcome-icon">🤖</div>
                    <div class="ai-welcome-title">Java 诊断 AI 助手</div>
                    <div class="ai-welcome-desc">我可以帮你分析 Java 应用性能问题，通过 Arthas 命令自动诊断 Pod 中的应用。</div>
                    <div class="ai-welcome-tips">
                        <div class="ai-tip" onclick="if(typeof aiQuickAsk==='function') aiQuickAsk('CPU 占用很高怎么排查？')">🔥 CPU 飙高排查</div>
                        <div class="ai-tip" onclick="if(typeof aiQuickAsk==='function') aiQuickAsk('接口响应慢如何定位？')">⏱️ 接口慢定位</div>
                        <div class="ai-tip" onclick="if(typeof aiQuickAsk==='function') aiQuickAsk('内存泄漏怎么排查？')">💾 内存泄漏排查</div>
                        <div class="ai-tip" onclick="if(typeof aiQuickAsk==='function') aiQuickAsk('线程死锁怎么检测？')">🔒 线程死锁检测</div>
                    </div>
                </div>
            </div>
            <div class="ai-drawer-input-area">
                <div class="ai-drawer-input-wrap">
                    <textarea id="aiDrawerInput" class="ai-drawer-input" placeholder="描述你的 Java 应用问题..." rows="1"
                        onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();pageShell.sendAIMessage()}"
                        oninput="pageShell.autoResizeInput(this)"></textarea>
                    <button class="ai-drawer-send-btn" onclick="pageShell.sendAIMessage()">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/></svg>
                    </button>
                </div>
            </div>
        `;
        document.body.appendChild(drawer);
    }
    
    sendAIMessage() {
        const input = document.getElementById('aiDrawerInput');
        if (!input || !input.value.trim()) return;
        
        const message = input.value.trim();
        input.value = '';
        this.autoResizeInput(input);
        
        // 如果存在原有的aiSend函数，使用它
        if (typeof aiSend === 'function') {
            // 将消息设置到原有的输入框
            const originalInput = document.getElementById('aiInput');
            if (originalInput) {
                originalInput.value = message;
                aiSend();
            }
        } else {
            // 简单的消息显示
            this.addAIMessage('user', message);
            this.addAIMessage('ai', 'AI 助手功能正在初始化中，请稍候...');
        }
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