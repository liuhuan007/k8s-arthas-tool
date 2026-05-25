/**
 * BroadcastChannelManager - 多标签页状态同步管理器
 *
 * 基于浏览器原生 BroadcastChannel API 实现跨标签页通信，
 * 配合 sessionStorage 实现标签页隔离的持久化状态。
 *
 * 使用场景：
 * 1. 连接切换时通知其他标签页刷新状态
 * 2. 连接健康状态变化时同步更新
 * 3. 任意自定义事件的跨标签页广播
 *
 * @example
 * const bcm = new BroadcastChannelManager('k8s-arthas');
 *
 * // 监听消息
 * bcm.onMessage('connection_switch', (data) => {
 *     console.log('收到连接切换消息:', data);
 * });
 *
 * // 发送消息
 * bcm.send('connection_switch', {
 *     old_connection_id: 'old_conn',
 *     new_connection_id: 'new_conn',
 *     timestamp: new Date().toISOString()
 * });
 *
 * // 清理
 * bcm.destroy();
 */
class BroadcastChannelManager {
    /**
     * 创建 BroadcastChannelManager 实例
     * @param {string} channelName - 频道名称，同一应用的不同实例应使用相同名称
     */
    constructor(channelName = 'k8s-arthas') {
        /** @type {string} 频道名称 */
        this._channelName = channelName;

        /** @type {BroadcastChannel|null} 底层 BroadcastChannel 实例 */
        this._channel = null;

        /** @type {Map<string, Set<Function>>} 事件监听器映射 */
        this._listeners = new Map();

        /** @type {string} 当前标签页唯一 ID */
        this._pageId = this._generatePageId();

        /** @type {boolean} 是否已销毁 */
        this._destroyed = false;

        // 初始化
        this._init();
    }

    // ── 公共接口 ──────────────────────────────────────────────────────────

    /**
     * 注册消息监听器
     * @param {string} eventType - 事件类型
     * @param {Function} callback - 回调函数，接收 (data, senderPageId)
     * @returns {Function} 取消监听的函数
     */
    onMessage(eventType, callback) {
        if (this._destroyed) {
            console.warn('[BroadcastChannelManager] 已销毁，无法注册监听器');
            return () => {};
        }

        if (!this._listeners.has(eventType)) {
            this._listeners.set(eventType, new Set());
        }
        this._listeners.get(eventType).add(callback);

        // 返回取消监听函数
        return () => {
            const set = this._listeners.get(eventType);
            if (set) {
                set.delete(callback);
                if (set.size === 0) {
                    this._listeners.delete(eventType);
                }
            }
        };
    }

    /**
     * 移除指定事件的所有监听器
     * @param {string} eventType - 事件类型
     */
    offMessage(eventType) {
        this._listeners.delete(eventType);
    }

    /**
     * 发送消息到其他标签页
     * @param {string} eventType - 事件类型
     * @param {object} data - 消息数据
     */
    send(eventType, data) {
        if (this._destroyed) {
            console.warn('[BroadcastChannelManager] 已销毁，无法发送消息');
            return;
        }

        if (!this._channel) {
            console.warn('[BroadcastChannelManager] BroadcastChannel 不可用');
            return;
        }

        const message = {
            type: eventType,
            data: data,
            senderPageId: this._pageId,
            timestamp: new Date().toISOString(),
        };

        try {
            this._channel.postMessage(message);
        } catch (err) {
            console.error('[BroadcastChannelManager] 发送消息失败:', err);
        }
    }

    /**
     * 设置 sessionStorage 值
     * @param {string} key - 键名
     * @param {*} value - 值（会被 JSON 序列化）
     */
    setSession(key, value) {
        try {
            const namespacedKey = `${this._channelName}:${key}`;
            sessionStorage.setItem(namespacedKey, JSON.stringify(value));
        } catch (err) {
            console.error('[BroadcastChannelManager] 设置 sessionStorage 失败:', err);
        }
    }

    /**
     * 获取 sessionStorage 值
     * @param {string} key - 键名
     * @param {*} defaultValue - 默认值
     * @returns {*}
     */
    getSession(key, defaultValue = null) {
        try {
            const namespacedKey = `${this._channelName}:${key}`;
            const raw = sessionStorage.getItem(namespacedKey);
            return raw !== null ? JSON.parse(raw) : defaultValue;
        } catch (err) {
            console.error('[BroadcastChannelManager] 读取 sessionStorage 失败:', err);
            return defaultValue;
        }
    }

    /**
     * 删除 sessionStorage 值
     * @param {string} key - 键名
     */
    removeSession(key) {
        try {
            const namespacedKey = `${this._channelName}:${key}`;
            sessionStorage.removeItem(namespacedKey);
        } catch (err) {
            console.error('[BroadcastChannelManager] 删除 sessionStorage 失败:', err);
        }
    }

    /**
     * 获取当前标签页 ID
     * @returns {string}
     */
    getPageId() {
        return this._pageId;
    }

    /**
     * 销毁管理器，释放资源
     */
    destroy() {
        if (this._destroyed) return;
        this._destroyed = true;

        if (this._channel) {
            this._channel.onmessage = null;
            this._channel.close();
            this._channel = null;
        }

        this._listeners.clear();
    }

    // ── 内部方法 ──────────────────────────────────────────────────────────

    /** 初始化 BroadcastChannel */
    _init() {
        if (typeof BroadcastChannel === 'undefined') {
            console.warn(
                '[BroadcastChannelManager] 当前浏览器不支持 BroadcastChannel API，多标签页同步功能不可用'
            );
            return;
        }

        try {
            this._channel = new BroadcastChannel(this._channelName);
            this._channel.onmessage = (event) => {
                this._handleMessage(event.data);
            };
        } catch (err) {
            console.error('[BroadcastChannelManager] 创建 BroadcastChannel 失败:', err);
        }
    }

    /**
     * 处理收到的消息
     * @param {object} message - 完整消息对象 {type, data, senderPageId, timestamp}
     */
    _handleMessage(message) {
        if (!message || !message.type) return;

        // 忽略自己发送的消息
        if (message.senderPageId === this._pageId) return;

        const eventType = message.type;
        const listeners = this._listeners.get(eventType);

        if (listeners && listeners.size > 0) {
            for (const callback of listeners) {
                try {
                    callback(message.data, message.senderPageId);
                } catch (err) {
                    console.error(
                        `[BroadcastChannelManager] 监听器回调错误 (${eventType}):`,
                        err
                    );
                }
            }
        }
    }

    /**
     * 生成当前标签页唯一 ID
     * @returns {string} 格式: tab_{timestamp}_{random}
     */
    _generatePageId() {
        return `tab_${Date.now()}_${Math.random().toString(36).substring(2, 8)}`;
    }
}

// ── 全局单例（可选） ──────────────────────────────────────────────────────

/**
 * 获取全局 BroadcastChannelManager 单例
 * @returns {BroadcastChannelManager}
 */
function getBroadcastChannelManager() {
    if (!window._globalBCM) {
        window._globalBCM = new BroadcastChannelManager('k8s-arthas');
    }
    return window._globalBCM;
}
