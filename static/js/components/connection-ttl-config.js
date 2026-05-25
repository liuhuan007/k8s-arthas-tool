/**
 * ConnectionTTLConfig - 连接 TTL 配置组件
 *
 * 提供连接有效期（TTL）的可视化设置界面。
 * 支持预设选项和自定义输入，通过 API 持久化配置。
 *
 * @example
 * const ttlConfig = new ConnectionTTLConfig(
 *     document.getElementById('ttl-container'),
 *     'conn-123',
 *     8,  // 当前 TTL
 *     [...]  // 预设选项
 * );
 * ttlConfig.render();
 * ttlConfig.onSave = (newTTL) => { console.log('TTL 已更新:', newTTL); };
 */
class ConnectionTTLConfig {
    /**
     * 创建 TTL 配置组件
     * @param {HTMLElement} container - 渲染容器
     * @param {string} connectionId - 连接 ID
     * @param {number} currentTTL - 当前 TTL 小时数
     * @param {Array} presetOptions - 预设选项列表 [{hours, label, description}]
     */
    constructor(container, connectionId, currentTTL = 0, presetOptions = []) {
        /** @type {HTMLElement} 渲染容器 */
        this._container = container;

        /** @type {string} 连接 ID */
        this._connectionId = connectionId;

        /** @type {number} 当前选中的 TTL 值 */
        this._selectedTTL = currentTTL;

        /** @type {number} 原始 TTL 值（用于检测变更） */
        this._originalTTL = currentTTL;

        /** @type {Array} 预设选项 */
        this._presets = presetOptions.length > 0 ? presetOptions : [
            { hours: 0, label: '不过期', description: '连接不会自动过期' },
            { hours: 1, label: '1 小时', description: '适合临时调试' },
            { hours: 2, label: '2 小时', description: '适合短时诊断' },
            { hours: 4, label: '4 小时', description: '适合较长时间排查' },
            { hours: 8, label: '8 小时', description: '适合一个工作时段' },
            { hours: 24, label: '24 小时', description: '适合跨天监控' },
            { hours: 72, label: '3 天', description: '适合长时间运行' },
        ];

        /** @type {boolean} 是否正在保存 */
        this._saving = false;

        /** @type {Function|null} 保存成功回调 */
        this.onSave = null;

        /** @type {Function|null} 保存失败回调 */
        this.onError = null;
    }

    // ── 渲染 ──────────────────────────────────────────────────────────────

    /** 渲染组件到容器 */
    render() {
        if (!this._container) return;

        const currentLabel = this._getLabelForTTL(this._selectedTTL);

        let html = `
            <div class="ttl-current">
                <span>当前设置：</span>
                <span class="ttl-value" id="ttl-current-value">${currentLabel}</span>
            </div>
            <div class="ttl-options" id="ttl-options">
        `;

        for (const preset of this._presets) {
            const isActive = this._selectedTTL === preset.hours;
            html += `
                <div class="ttl-option ${isActive ? 'active' : ''}"
                     data-ttl-hours="${preset.hours}"
                     onclick="ConnectionTTLConfig._handleOptionClick(this, ${preset.hours})">
                    <div>${preset.label}</div>
                    <div class="ttl-option-desc">${preset.description || ''}</div>
                </div>
            `;
        }

        html += `</div>`;

        // 保存按钮
        html += `
            <div class="ttl-save-bar" style="margin-top:12px;display:flex;align-items:center;gap:10px;">
                <button class="btn btn-primary btn-sm" id="ttl-save-btn"
                        onclick="ConnectionTTLConfig._handleSave('${this._connectionId}')"
                        disabled>
                    保存
                </button>
                <span id="ttl-save-status" class="ttl-note"></span>
            </div>
        `;

        this._container.innerHTML = html;

        // 保存组件引用到 DOM（用于内联事件处理）
        this._container._ttlConfigInstance = this;
    }

    // ── 事件处理 ──────────────────────────────────────────────────────────

    /**
     * 处理选项点击（静态方法，绑定到 DOM）
     * @param {HTMLElement} el 被点击的选项元素
     * @param {number} hours TTL 小时数
     */
    static _handleOptionClick(el, hours) {
        const container = el.closest('.ttl-content') || el.parentElement.parentElement;
        const instance = container._ttlConfigInstance;
        if (!instance) return;

        instance._selectedTTL = hours;

        // 更新选中状态
        const options = container.querySelectorAll('.ttl-option');
        options.forEach(opt => {
            opt.classList.toggle('active', parseInt(opt.dataset.ttlHours) === hours);
        });

        // 更新当前值显示
        const valueEl = container.querySelector('#ttl-current-value');
        if (valueEl) {
            valueEl.textContent = instance._getLabelForTTL(hours);
        }

        // 启用/禁用保存按钮
        const saveBtn = container.querySelector('#ttl-save-btn');
        if (saveBtn) {
            saveBtn.disabled = hours === instance._originalTTL;
        }

        // 清除状态消息
        const statusEl = container.querySelector('#ttl-save-status');
        if (statusEl) statusEl.textContent = '';
    }

    /**
     * 处理保存按钮点击（静态方法，绑定到 DOM）
     * @param {string} connectionId 连接 ID
     */
    static async _handleSave(connectionId) {
        // 找到实例
        const container = document.querySelector(`[data-connection-id="${connectionId}"]`) ||
                          document.getElementById('ttl-content');
        if (!container || !container._ttlConfigInstance) return;

        const instance = container._ttlConfigInstance;
        await instance._save();
    }

    /** 保存 TTL 配置到后端 */
    async _save() {
        if (this._saving) return;
        this._saving = true;

        const statusEl = this._container.querySelector('#ttl-save-status');
        const saveBtn = this._container.querySelector('#ttl-save-btn');

        try {
            if (statusEl) statusEl.textContent = '保存中...';
            if (saveBtn) saveBtn.disabled = true;

            const resp = await fetch(
                `/api/connections/${encodeURIComponent(this._connectionId)}/ttl`,
                {
                    method: 'PUT',
                    credentials: 'include',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ ttl_hours: this._selectedTTL }),
                }
            );

            const json = await resp.json();

            if (json.code === 200 && json.data && json.data.ok) {
                this._originalTTL = this._selectedTTL;
                if (statusEl) {
                    statusEl.textContent = '✓ 保存成功';
                    statusEl.style.color = 'var(--a3)';
                }
                if (saveBtn) saveBtn.disabled = true;

                // 触发回调
                if (typeof this.onSave === 'function') {
                    this.onSave(this._selectedTTL);
                }

                // 广播状态更新
                if (typeof BroadcastChannelManager !== 'undefined') {
                    const bcm = getBroadcastChannelManager();
                    bcm.send('connection_status_update', {
                        connection_id: this._connectionId,
                        status: 'ttl_updated',
                        ttl_hours: this._selectedTTL,
                        timestamp: new Date().toISOString(),
                    });
                }
            } else {
                const errMsg = json.message || '保存失败';
                if (statusEl) {
                    statusEl.textContent = '✗ ' + errMsg;
                    statusEl.style.color = 'var(--a5)';
                }
                if (saveBtn) saveBtn.disabled = false;

                if (typeof this.onError === 'function') {
                    this.onError(errMsg);
                }
            }
        } catch (err) {
            console.error('[ConnectionTTLConfig] 保存失败:', err);
            if (statusEl) {
                statusEl.textContent = '✗ 网络错误';
                statusEl.style.color = 'var(--a5)';
            }
            if (saveBtn) saveBtn.disabled = false;

            if (typeof this.onError === 'function') {
                this.onError(err.message || '网络错误');
            }
        } finally {
            this._saving = false;
        }
    }

    // ── 工具方法 ──────────────────────────────────────────────────────────

    /**
     * 获取 TTL 值对应的显示标签
     * @param {number} hours
     * @returns {string}
     */
    _getLabelForTTL(hours) {
        if (hours === 0) return '不过期';
        const preset = this._presets.find(p => p.hours === hours);
        if (preset) return preset.label;
        return `${hours} 小时`;
    }

    /**
     * 获取当前选中的 TTL 值
     * @returns {number}
     */
    getSelectedTTL() {
        return this._selectedTTL;
    }

    /**
     * 检查是否有未保存的变更
     * @returns {boolean}
     */
    hasChanges() {
        return this._selectedTTL !== this._originalTTL;
    }
}
