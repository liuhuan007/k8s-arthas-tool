/**
 * HistoryPage - 历史记录页面
 * 显示全局历史记录
 */
class HistoryPage {
    constructor() {
        this.init();
    }
    
    init() {
        this.loadHistory();
        this.bindEvents();
    }
    
    loadHistory() {
        // 加载历史记录
        console.log('HistoryPage.loadHistory() - 加载历史记录');
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
}

// 页面加载后初始化
document.addEventListener('DOMContentLoaded', function() {
    if (typeof HistoryPage !== 'undefined') {
        window.historyPage = new HistoryPage();
    }
});