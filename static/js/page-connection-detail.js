/**
 * ConnectionDetailPage - 连接详情页面 (Phase 5 增强版)
 *
 * 功能：
 * 1. 显示连接详细信息（基本信息、健康状态、TTL 配置）
 * 2. 提供可用操作入口（终端、采样、监控等）
 * 3. 显示运行中的诊断任务
 * 4. 集成多标签页同步
 * 5. 集成连接切换确认
 */
class ConnectionDetailPage {
    constructor() {
        /** @type {string|null} 连接 ID */
        this.connectionId = null;
        /** @type {object|null} 连接详细数据 */
        this.connectionData = null;
        /** @type {object|null} 健康状态数据 */
        this.healthData = null;
        /** @type {object|null} TTL 配置数据 */
        this.ttlData = null;
        /** @type {object|null} 运行中任务数据 */
        this.runningTasks = null;
        /** @type {number|null} 健康状态轮询定时器 ID */
        this._healthPollTimer = null;
        /** @type {ConnectionSwitchConfirm|null} 连接切换确认组件 */
        this._switchConfirm = null;

        this.init();
    }

    /** 页面初始化入口 */
    init() {
        this.parseQueryString();
        this.bindEvents();
        this.loadConnectionDetail();

        // 初始化多标签页同步
        this._initBroadcastChannel();

        // 初始化连接切换确认组件
        this._initSwitchConfirm();
    }

    // ── URL 参数解析 ──────────────────────────────────────────────────────

    parseQueryString() {
        const params = new URLSearchParams(window.location.search);
        this.connectionId = params.get('conn');
    }

    // ── 事件绑定 ──────────────────────────────────────────────────────────

    bindEvents() {
        // 返回按钮
        const backBtn = document.getElementById('back-btn');
        if (backBtn) {
            backBtn.addEventListener('click', () => {
                window.location.href = '/';
            });
        }

        // 健康状态刷新按钮
        const healthRefreshBtn = document.getElementById('health-refresh-btn');
        if (healthRefreshBtn) {
            healthRefreshBtn.addEventListener('click', () => {
                this.loadHealthStatus();
            });
        }
    }

    // ── 数据加载 ──────────────────────────────────────────────────────────

    /** 加载连接详细信息 */
    loadConnectionDetail() {
        if (!this.connectionId) {
            this._showNotFound('未指定连接 ID');
            return;
        }

        this._fetchJSON(`/api/connections/${encodeURIComponent(this.connectionId)}/detail`)
            .then(data => {
                if (!data) return;
                this.connectionData = data;
                this.renderConnectionInfo();
                this.renderAvailableActions(data.available_actions || []);

                // 并行加载子数据
                this.loadHealthStatus();
                this.loadTTLConfig();
                this.loadRunningTasks();

                // 启动健康状态轮询
                this._startHealthPolling();

                // 更新页面标题
                this._updateTitle(data);
            })
            .catch(err => {
                console.error('加载连接详情失败:', err);
                this._showNotFound('加载连接详情失败: ' + (err.message || '未知错误'));
            });
    }

    /** 加载健康检查状态 */
    loadHealthStatus() {
        if (!this.connectionId) return;

        const refreshBtn = document.getElementById('health-refresh-btn');
        if (refreshBtn) refreshBtn.disabled = true;

        this._fetchJSON(`/api/connections/${encodeURIComponent(this.connectionId)}/health`)
            .then(data => {
                if (!data) return;
                this.healthData = data;
                this.renderHealthPanel(data);
            })
            .catch(err => {
                console.error('加载健康状态失败:', err);
            })
            .finally(() => {
                if (refreshBtn) refreshBtn.disabled = false;
            });
    }

    /** 加载 TTL 配置 */
    loadTTLConfig() {
        if (!this.connectionId) return;

        this._fetchJSON(`/api/connections/${encodeURIComponent(this.connectionId)}/ttl`)
            .then(data => {
                if (!data) return;
                this.ttlData = data;
                this.renderTTLPanel(data);
            })
            .catch(err => {
                console.error('加载 TTL 配置失败:', err);
            });
    }

    /** 加载运行中任务 */
    loadRunningTasks() {
        if (!this.connectionId) return;

        this._fetchJSON(`/api/connections/${encodeURIComponent(this.connectionId)}/running-tasks`)
            .then(data => {
                if (!data) return;
                this.runningTasks = data;
                this.renderRunningTasks(data);
            })
            .catch(err => {
                console.error('加载运行中任务失败:', err);
            });
    }

    // ── 渲染方法 ──────────────────────────────────────────────────────────

    /** 渲染连接基本信息 */
    renderConnectionInfo() {
        const container = document.getElementById('connection-info');
        if (!container || !this.connectionData) return;

        const d = this.connectionData;
        const statusClass = this._getStatusClass(d.status);
        const healthClass = this._getStatusClass(d.health_status);

        container.innerHTML = `
            <div class="connection-info-card">
                <div class="conn-info-top">
                    <div class="conn-info-badge ${statusClass}">${this._statusLabel(d.status)}</div>
                    <div class="conn-info-badge ${healthClass}">健康: ${this._statusLabel(d.health_status)}</div>
                    ${d.ttl_hours > 0 ? `<div class="conn-info-badge info">TTL: ${d.ttl_hours}h</div>` : ''}
                </div>
                <div class="info-grid">
                    <div class="info-item">
                        <label>连接 ID</label>
                        <span class="info-mono">${d.id || '—'}</span>
                    </div>
                    <div class="info-item">
                        <label>集群</label>
                        <span>${d.cluster_name || '未知'}</span>
                    </div>
                    <div class="info-item">
                        <label>命名空间</label>
                        <span>${d.namespace || '未知'}</span>
                    </div>
                    <div class="info-item">
                        <label>Pod</label>
                        <span>${d.pod_name || '未知'}</span>
                    </div>
                    <div class="info-item">
                        <label>Java PID</label>
                        <span class="info-mono">${d.java_pid || '—'}</span>
                    </div>
                    <div class="info-item">
                        <label>Arthas 版本</label>
                        <span>${d.arthas_version || '—'}</span>
                    </div>
                    <div class="info-item">
                        <label>本地端口</label>
                        <span class="info-mono">${d.local_port || '—'}</span>
                    </div>
                    <div class="info-item">
                        <label>最后活跃</label>
                        <span>${d.last_active_at || '—'}</span>
                    </div>
                    <div class="info-item">
                        <label>更新时间</label>
                        <span>${d.updated_at || '—'}</span>
                    </div>
                </div>
            </div>
        `;
    }

    /** 渲染健康状态面板 */
    renderHealthPanel(data) {
        const panel = document.getElementById('health-panel');
        const content = document.getElementById('health-content');
        if (!panel || !content) return;

        panel.style.display = 'block';

        const status = data.health_status || 'unknown';
        const statusClass = this._getStatusClass(status);
        const latency = data.latency_ms != null ? `${data.latency_ms}ms` : '—';
        const lastCheck = data.last_health_check || '—';

        content.innerHTML = `
            <div class="health-grid">
                <div class="health-item">
                    <span class="health-label">状态</span>
                    <span class="health-value ${statusClass}">${this._statusLabel(status)}</span>
                </div>
                <div class="health-item">
                    <span class="health-label">延迟</span>
                    <span class="health-value">${latency}</span>
                </div>
                <div class="health-item">
                    <span class="health-label">最后检查</span>
                    <span class="health-value">${lastCheck}</span>
                </div>
            </div>
        `;
    }

    /** 渲染 TTL 配置面板 */
    renderTTLPanel(data) {
        const panel = document.getElementById('ttl-panel');
        const content = document.getElementById('ttl-content');
        if (!panel || !content) return;

        panel.style.display = 'block';

        const currentTTL = data.ttl_hours || 0;
        const presets = data.preset_options || [];

        // 使用 ConnectionTTLConfig 组件渲染
        if (typeof ConnectionTTLConfig !== 'undefined') {
            const ttlConfig = new ConnectionTTLConfig(
                content,
                this.connectionId,
                currentTTL,
                presets
            );
            ttlConfig.render();
            ttlConfig.onSave = (newTTL) => {
                this._onTTLUpdated(newTTL);
            };
            this._ttlConfig = ttlConfig;
        } else {
            // 降级：简单渲染
            content.innerHTML = `
                <div class="ttl-current">
                    <span>当前 TTL: </span>
                    <span class="ttl-value">${currentTTL > 0 ? currentTTL + ' 小时' : '不过期'}</span>
                </div>
                <div class="ttl-note">TTL 配置组件未加载，请刷新页面重试。</div>
            `;
        }
    }

    /** 渲染可用操作入口 */
    renderAvailableActions(actions) {
        const panel = document.getElementById('actions-panel');
        const grid = document.getElementById('actions-grid');
        if (!panel || !grid) return;

        if (!actions || actions.length === 0) {
            panel.style.display = 'none';
            return;
        }

        panel.style.display = 'block';

        grid.innerHTML = actions.map(action => `
            <a href="${action.url}?conn=${encodeURIComponent(this.connectionId)}"
               class="action-card" title="${action.label}">
                <span class="action-icon">${action.icon}</span>
                <span class="action-label">${action.label}</span>
            </a>
        `).join('');
    }

    /** 渲染运行中任务 */
    renderRunningTasks(data) {
        const panel = document.getElementById('tasks-panel');
        const content = document.getElementById('tasks-content');
        const countEl = document.getElementById('tasks-count');
        if (!panel || !content) return;

        const tasks = data.tasks || [];
        if (tasks.length === 0) {
            panel.style.display = 'none';
            return;
        }

        panel.style.display = 'block';
        if (countEl) countEl.textContent = `${tasks.length} 个`;

        content.innerHTML = tasks.map(task => `
            <div class="task-item">
                <span class="task-type">${task.type || '—'}</span>
                <span class="task-event">${task.event || '—'}</span>
                <span class="task-status running">${task.status}</span>
                <span class="task-progress">${task.progress || 0}%</span>
                <span class="task-time">${task.created_at || '—'}</span>
            </div>
        `).join('');
    }

    // ── TTL 更新回调 ──────────────────────────────────────────────────────

    _onTTLUpdated(newTTL) {
        // 更新本地数据
        if (this.connectionData) {
            this.connectionData.ttl_hours = newTTL;
        }
        // 重新渲染连接信息
        this.renderConnectionInfo();

        // 广播连接状态更新
        this._broadcastStatusUpdate();
    }

    // ── 连接切换确认 ──────────────────────────────────────────────────────

    /** 初始化连接切换确认组件 */
    _initSwitchConfirm() {
        if (typeof ConnectionSwitchConfirm !== 'undefined') {
            this._switchConfirm = new ConnectionSwitchConfirm();

            this._switchConfirm.onSwitchComplete = (result) => {
                console.log('[ConnectionDetail] 连接切换完成:', result);
            };

            this._switchConfirm.onSwitchError = (err) => {
                console.error('[ConnectionDetail] 连接切换失败:', err);
            };
        }
    }

    /**
     * 触发连接切换（带确认弹窗）
     * @param {string} targetConnId 目标连接 ID
     */
    switchConnection(targetConnId) {
        if (!this._switchConfirm) {
            this._showNotice('连接切换组件未加载');
            return;
        }
        if (!this.connectionId) {
            this._showNotice('当前没有活跃连接');
            return;
        }
        this._switchConfirm.switch(this.connectionId, targetConnId);
    }

    // ── 多标签页同步 ──────────────────────────────────────────────────────

    _initBroadcastChannel() {
        if (typeof BroadcastChannelManager !== 'undefined') {
            this._bcm = new BroadcastChannelManager('k8s-arthas');

            // 监听连接切换消息
            this._bcm.onMessage('connection_switch', (data) => {
                if (data.new_connection_id === this.connectionId) {
                    // 被切换到了当前连接，刷新数据
                    this.loadConnectionDetail();
                } else if (data.old_connection_id === this.connectionId) {
                    // 当前连接被切换走了，提示用户
                    this._showNotice(`连接已切换到 ${data.new_connection_id}，页面将刷新。`);
                    setTimeout(() => {
                        window.location.href = `/connection-detail?conn=${encodeURIComponent(data.new_connection_id)}`;
                    }, 2000);
                }
            });

            // 监听连接状态更新
            this._bcm.onMessage('connection_status_update', (data) => {
                if (data.connection_id === this.connectionId) {
                    this.loadHealthStatus();
                }
            });
        }
    }

    _broadcastStatusUpdate() {
        if (this._bcm && this.connectionId) {
            this._bcm.send('connection_status_update', {
                connection_id: this.connectionId,
                status: this.connectionData ? this.connectionData.status : 'unknown',
                timestamp: new Date().toISOString(),
            });
        }
    }

    // ── 健康状态轮询 ──────────────────────────────────────────────────────

    _startHealthPolling() {
        this._stopHealthPolling();
        // 每 30 秒刷新一次健康状态
        this._healthPollTimer = setInterval(() => {
            if (document.visibilityState === 'visible') {
                this.loadHealthStatus();
            }
        }, 30000);
    }

    _stopHealthPolling() {
        if (this._healthPollTimer) {
            clearInterval(this._healthPollTimer);
            this._healthPollTimer = null;
        }
    }

    // ── 工具方法 ──────────────────────────────────────────────────────────

    /**
     * 发起 JSON 请求并返回解析后的数据
     * @param {string} url 请求地址
     * @returns {Promise<object|null>}
     */
    async _fetchJSON(url) {
        try {
            const resp = await fetch(url, { credentials: 'include' });
            if (resp.status === 401) {
                window.location.replace('/login.html');
                return null;
            }
            const json = await resp.json();
            if (json.code === 200) {
                return json.data;
            } else {
                console.warn('[ConnectionDetail] API 错误:', json.message);
                return null;
            }
        } catch (err) {
            throw err;
        }
    }

    /** 获取状态对应的 CSS 类名 */
    _getStatusClass(status) {
        switch (status) {
            case 'healthy': case 'ready': case 'connected': case 'recovered':
                return 'status-ok';
            case 'unhealthy': case 'failed': case 'disconnected': case 'stale':
                return 'status-error';
            case 'starting': case 'pod_selected': case 'pod_checked':
                return 'status-pending';
            default:
                return 'status-unknown';
        }
    }

    /** 状态中文标签 */
    _statusLabel(status) {
        const labels = {
            'healthy': '健康', 'unhealthy': '异常', 'unknown': '未知',
            'ready': '已就绪', 'connected': '已连接', 'disconnected': '已断开',
            'failed': '失败', 'recovered': '已恢复', 'stale': '已过期',
            'starting': '启动中', 'pod_selected': 'Pod 已选',
            'pod_checked': 'Pod 已检',
        };
        return labels[status] || status || '未知';
    }

    /** 更新页面标题 */
    _updateTitle(data) {
        const titleEl = document.getElementById('detail-title');
        if (titleEl) {
            titleEl.textContent = `${data.pod_name} — ${data.namespace} — ${data.cluster_name}`;
        }
        document.title = `连接详情 - ${data.pod_name} - K8s Arthas Tool`;
    }

    /** 显示未找到页面提示 */
    _showNotFound(message) {
        const container = document.getElementById('connection-info');
        if (container) {
            container.innerHTML = `
                <div class="connection-empty">
                    <div class="empty-icon">🔌</div>
                    <div class="empty-message">${message}</div>
                    <button class="btn btn-primary" onclick="window.location.href='/'">返回首页</button>
                </div>
            `;
        }
    }

    /** 显示通知提示 */
    _showNotice(message) {
        const notice = document.createElement('div');
        notice.className = 'detail-notice';
        notice.textContent = message;
        document.body.appendChild(notice);
        setTimeout(() => notice.remove(), 5000);
    }

    // ── 公共接口 ──────────────────────────────────────────────────────────

    getConnection() { return this.connectionData; }
    getConnectionId() { return this.connectionId; }
    hasConnection() { return this.connectionId !== null && this.connectionData !== null; }

    /** 销毁页面（清理定时器） */
    destroy() {
        this._stopHealthPolling();
        if (this._bcm) {
            this._bcm.destroy();
        }
    }
}

// ── 页面加载初始化 ────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function () {
    if (typeof ConnectionDetailPage !== 'undefined') {
        window.connectionDetailPage = new ConnectionDetailPage();
    }
});

// 页面卸载前清理
window.addEventListener('beforeunload', function () {
    if (window.connectionDetailPage) {
        window.connectionDetailPage.destroy();
    }
});
