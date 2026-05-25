/**
 * ConnectionSwitchConfirm - 连接切换确认组件
 *
 * 在用户切换连接前检测目标连接是否有运行中任务，
 * 如有则显示确认弹窗，用户确认后取消任务并执行切换。
 *
 * 流程：
 * 1. 用户触发连接切换
 * 2. 检查目标连接是否有运行中任务
 * 3. 有任务 → 显示确认弹窗（列出运行中的任务）
 * 4. 用户点击「确认切换」→ 调用 API 取消任务并切换
 * 5. 无任务 → 直接切换
 * 6. 切换成功后通过 BroadcastChannel 通知其他标签页
 *
 * @example
 * const confirm = new ConnectionSwitchConfirm();
 *
 * // 触发切换
 * confirm.switch('current_conn_id', 'target_conn_id');
 *
 * // 自定义回调
 * confirm.onSwitchComplete = (result) => {
 *     console.log('切换完成:', result);
 * };
 */
class ConnectionSwitchConfirm {
    constructor() {
        /** @type {Function|null} 切换完成回调 */
        this.onSwitchComplete = null;

        /** @type {Function|null} 切换失败回调 */
        this.onSwitchError = null;

        /** @type {boolean} 是否正在切换 */
        this._switching = false;
    }

    // ── 公共接口 ──────────────────────────────────────────────────────────

    /**
     * 执行连接切换（带任务检测和确认弹窗）
     * @param {string} sourceConnId - 当前连接 ID
     * @param {string} targetConnId - 目标连接 ID
     */
    async switch(sourceConnId, targetConnId) {
        if (this._switching) return;
        if (!sourceConnId || !targetConnId) {
            console.error('[ConnectionSwitchConfirm] 连接 ID 不能为空');
            return;
        }
        if (sourceConnId === targetConnId) {
            console.warn('[ConnectionSwitchConfirm] 不能切换到同一个连接');
            return;
        }

        this._switching = true;

        try {
            // 1. 检查目标连接是否有运行中任务
            const tasks = await this._checkRunningTasks(sourceConnId);

            if (tasks && tasks.length > 0) {
                // 2. 显示确认弹窗
                const confirmed = await this._showConfirmDialog(sourceConnId, targetConnId, tasks);

                if (!confirmed) {
                    this._switching = false;
                    return;
                }

                // 3. 执行切换（带取消任务）
                await this._executeSwitch(sourceConnId, targetConnId, true);
            } else {
                // 无任务，直接切换
                await this._executeSwitch(sourceConnId, targetConnId, false);
            }
        } catch (err) {
            console.error('[ConnectionSwitchConfirm] 切换失败:', err);
            this._showToast('连接切换失败: ' + (err.message || '未知错误'), 'error');
            if (typeof this.onSwitchError === 'function') {
                this.onSwitchError(err);
            }
        } finally {
            this._switching = false;
        }
    }

    // ── 任务检测 ──────────────────────────────────────────────────────────

    /**
     * 检查指定连接的运行中任务
     * @param {string} connectionId
     * @returns {Promise<Array>}
     */
    async _checkRunningTasks(connectionId) {
        try {
            const resp = await fetch(
                `/api/connections/${encodeURIComponent(connectionId)}/running-tasks`,
                { credentials: 'include' }
            );

            if (resp.status === 401) {
                window.location.replace('/login.html');
                return [];
            }

            const json = await resp.json();
            if (json.code === 200 && json.data) {
                return json.data.tasks || [];
            }
            return [];
        } catch (err) {
            console.error('[ConnectionSwitchConfirm] 检查运行中任务失败:', err);
            return [];
        }
    }

    // ── 确认弹窗 ──────────────────────────────────────────────────────────

    /**
     * 显示确认弹窗
     * @param {string} sourceConnId
     * @param {string} targetConnId
     * @param {Array} tasks 运行中的任务列表
     * @returns {Promise<boolean>} 用户是否确认切换
     */
    _showConfirmDialog(sourceConnId, targetConnId, tasks) {
        return new Promise((resolve) => {
            // 创建弹窗 DOM
            const overlay = document.createElement('div');
            overlay.className = 'switch-confirm-overlay';

            const taskListHTML = tasks.map(t => `
                <div class="task-item" style="padding:4px 0;">
                    <span class="task-type">${t.type || '—'}</span>
                    <span class="task-event">${t.event || '—'}</span>
                    <span class="task-status running">${t.status}</span>
                </div>
            `).join('');

            overlay.innerHTML = `
                <div class="switch-confirm-dialog">
                    <div class="switch-confirm-title">⚠️ 确认切换连接</div>
                    <div class="switch-confirm-body">
                        <p>当前连接有 <strong>${tasks.length}</strong> 个运行中的任务：</p>
                        <div class="switch-confirm-tasks">
                            ${taskListHTML}
                        </div>
                        <p>切换连接后，这些任务将被自动取消。确定要继续吗？</p>
                    </div>
                    <div class="switch-confirm-actions">
                        <button class="btn btn-secondary" id="switch-cancel-btn">取消</button>
                        <button class="btn btn-primary" id="switch-confirm-btn">确认切换</button>
                    </div>
                </div>
            `;

            document.body.appendChild(overlay);

            // 绑定事件
            let resolved = false;

            const cleanup = (result) => {
                if (resolved) return;
                resolved = true;
                overlay.remove();
                resolve(result);
            };

            overlay.querySelector('#switch-cancel-btn').addEventListener('click', () => {
                cleanup(false);
            });

            overlay.querySelector('#switch-confirm-btn').addEventListener('click', () => {
                cleanup(true);
            });

            // 点击遮罩关闭
            overlay.addEventListener('click', (e) => {
                if (e.target === overlay) {
                    cleanup(false);
                }
            });

            // ESC 键关闭
            const onKeydown = (e) => {
                if (e.key === 'Escape') {
                    document.removeEventListener('keydown', onKeydown);
                    cleanup(false);
                }
            };
            document.addEventListener('keydown', onKeydown);
        });
    }

    // ── 执行切换 ──────────────────────────────────────────────────────────

    /**
     * 执行连接切换 API 调用
     * @param {string} sourceConnId
     * @param {string} targetConnId
     * @param {boolean} cancelTasks 是否取消运行中任务
     */
    async _executeSwitch(sourceConnId, targetConnId, cancelTasks) {
        this._showToast('正在切换连接...', 'info');

        const resp = await fetch(
            `/api/connections/${encodeURIComponent(sourceConnId)}/switch`,
            {
                method: 'POST',
                credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    target_connection_id: targetConnId,
                    cancel_tasks: cancelTasks,
                }),
            }
        );

        if (resp.status === 401) {
            window.location.replace('/login.html');
            return;
        }

        const json = await resp.json();

        if (json.code === 200 && json.data && json.data.ok) {
            const result = json.data;

            // 通过 BroadcastChannel 通知其他标签页
            this._broadcastSwitch(sourceConnId, targetConnId);

            // 显示成功提示
            const msg = result.message || '切换成功';
            this._showToast('✓ ' + msg, 'success');

            // 触发回调
            if (typeof this.onSwitchComplete === 'function') {
                this.onSwitchComplete(result);
            }

            // 跳转到目标连接详情页
            setTimeout(() => {
                window.location.href = `/connection-detail?conn=${encodeURIComponent(targetConnId)}`;
            }, 800);
        } else {
            const errMsg = json.message || '切换失败';
            this._showToast('✗ ' + errMsg, 'error');
            if (typeof this.onSwitchError === 'function') {
                this.onSwitchError(new Error(errMsg));
            }
        }
    }

    // ── 多标签页同步 ──────────────────────────────────────────────────────

    /**
     * 通过 BroadcastChannel 广播连接切换事件
     * @param {string} oldConnId
     * @param {string} newConnId
     */
    _broadcastSwitch(oldConnId, newConnId) {
        if (typeof BroadcastChannelManager !== 'undefined') {
            const bcm = getBroadcastChannelManager();
            bcm.send('connection_switch', {
                old_connection_id: oldConnId,
                new_connection_id: newConnId,
                timestamp: new Date().toISOString(),
            });
        }
    }

    // ── UI 辅助 ───────────────────────────────────────────────────────────

    /**
     * 显示 Toast 提示
     * @param {string} message
     * @param {string} type - 'info' | 'success' | 'error'
     */
    _showToast(message, type = 'info') {
        const toast = document.createElement('div');
        toast.className = 'detail-notice';

        const colors = {
            info: 'var(--a)',
            success: 'var(--a3)',
            error: 'var(--a5)',
        };

        toast.style.borderColor = colors[type] || colors.info;
        toast.style.color = colors[type] || colors.info;
        toast.textContent = message;

        document.body.appendChild(toast);
        setTimeout(() => toast.remove(), 3000);
    }
}
