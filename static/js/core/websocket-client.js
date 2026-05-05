/**
 * WebSocket Real-time Push - WebSocket 实时推送
 * 
 * 功能:
 * - 连接状态变更推送
 * - 任务进度推送
 * - 错误通知推送
 * - 断线重连 (5次指数退避)
 * - 消息分片 (64KB 限制)
 */

(function() {
  'use strict';
  
  // ✅ 临时禁用 WebSocket (保留代码,不执行连接)
  const WS_ENABLED = false;
  if (!WS_ENABLED) {
    console.log('[WebSocket] 功能已禁用');
    window.WebSocketClient = {
      connect: () => {},
      disconnect: () => {},
      send: () => {},
      on: () => {},
      isConnected: () => false,
    };
    return;
  }
  
  const WS_URL = window.WS_URL || `ws://${window.location.host}/ws`;
  let ws = null;
  let reconnectAttempts = 0;
  const MAX_RECONNECT = 5;
  const BASE_RECONNECT_DELAY = 1000; // 1秒
  let heartbeatInterval = null;
  let messageBuffer = [];
  
  // 事件监听器
  const listeners = {
    connection_state: [],
    task_progress: [],
    error_notification: [],
    system_notification: [],
  };
  
  /**
   * 连接 WebSocket
   */
  function connect() {
    if (ws && ws.readyState === WebSocket.OPEN) {
      console.log('[WebSocket] Already connected');
      return;
    }
    
    console.log('[WebSocket] Connecting to', WS_URL);
    
    ws = new WebSocket(WS_URL);
    
    ws.onopen = function() {
      console.log('[WebSocket] Connected');
      reconnectAttempts = 0;
      
      // 启动心跳
      startHeartbeat();
      
      // 发送认证消息 (可选)
      sendAuth();
    };
    
    ws.onmessage = function(event) {
      handleMessage(event.data);
    };
    
    ws.onerror = function(error) {
      console.error('[WebSocket] Error:', error);
    };
    
    ws.onclose = function(event) {
      console.log('[WebSocket] Closed:', event.code, event.reason);
      stopHeartbeat();
      
      // 尝试重连
      if (reconnectAttempts < MAX_RECONNECT) {
        const delay = BASE_RECONNECT_DELAY * Math.pow(2, reconnectAttempts);
        console.log(`[WebSocket] Reconnecting in ${delay}ms (attempt ${reconnectAttempts + 1}/${MAX_RECONNECT})`);
        
        setTimeout(() => {
          reconnectAttempts++;
          connect();
        }, delay);
      } else {
        console.error('[WebSocket] Max reconnect attempts reached');
        notifyError('WebSocket 连接失败', '请刷新页面重试');
      }
    };
  }
  
  /**
   * 处理消息
   */
  function handleMessage(data) {
    try {
      const message = JSON.parse(data);
      const type = message.type;
      
      console.log('[WebSocket] Received:', type, message);
      
      switch (type) {
        case 'connection_state':
          notifyListeners('connection_state', message);
          break;
        
        case 'task_progress':
          notifyListeners('task_progress', message);
          break;
        
        case 'error_notification':
          notifyListeners('error_notification', message);
          showNotification(message);
          break;
        
        case 'system_notification':
          notifyListeners('system_notification', message);
          break;
        
        default:
          console.warn('[WebSocket] Unknown message type:', type);
      }
      
    } catch (e) {
      console.error('[WebSocket] Parse error:', e, data);
    }
  }
  
  /**
   * 发送消息
   */
  function send(type, data) {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      console.warn('[WebSocket] Not connected, buffering message');
      messageBuffer.push({ type, data });
      return;
    }
    
    const message = JSON.stringify({ type, ...data });
    
    // 检查消息大小 (64KB 限制)
    if (message.length > 65536) {
      console.warn('[WebSocket] Message too large, splitting');
      splitAndSend(message);
      return;
    }
    
    ws.send(message);
  }
  
  /**
   * 分片发送大消息
   */
  function splitAndSend(message) {
    const chunkSize = 60000; // 60KB
    const chunks = [];
    
    for (let i = 0; i < message.length; i += chunkSize) {
      chunks.push(message.slice(i, i + chunkSize));
    }
    
    chunks.forEach((chunk, index) => {
      ws.send(JSON.stringify({
        type: 'chunk',
        chunk_index: index,
        total_chunks: chunks.length,
        data: chunk
      }));
    });
  }
  
  /**
   * 发送认证
   */
  function sendAuth() {
    // 从 cookie 或 localStorage 获取 token
    const token = getAuthToken();
    if (token) {
      send('auth', { token });
    }
  }
  
  /**
   * 获取认证 token
   */
  function getAuthToken() {
    // 从 cookie 获取 session
    const cookies = document.cookie.split(';');
    for (let cookie of cookies) {
      const [name, value] = cookie.trim().split('=');
      if (name === 'session') {
        return value;
      }
    }
    return null;
  }
  
  /**
   * 心跳
   */
  function startHeartbeat() {
    stopHeartbeat();
    
    heartbeatInterval = setInterval(() => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'ping' }));
      }
    }, 30000); // 30秒
  }
  
  function stopHeartbeat() {
    if (heartbeatInterval) {
      clearInterval(heartbeatInterval);
      heartbeatInterval = null;
    }
  }
  
  /**
   * 事件监听
   */
  function on(eventType, callback) {
    if (!listeners[eventType]) {
      listeners[eventType] = [];
    }
    listeners[eventType].push(callback);
    
    // 返回取消订阅函数
    return () => {
      listeners[eventType] = listeners[eventType].filter(cb => cb !== callback);
    };
  }
  
  /**
   * 通知监听器
   */
  function notifyListeners(eventType, message) {
    const callbacks = listeners[eventType] || [];
    callbacks.forEach(cb => {
      try {
        cb(message);
      } catch (e) {
        console.error(`[WebSocket] Listener error (${eventType}):`, e);
      }
    });
  }
  
  /**
   * 显示通知
   */
  function showNotification(message) {
    // 使用现有的 toast 或通知组件
    if (typeof window.toast === 'function') {
      window.toast(message.message || '未知错误', message.level || 'error');
    }
    
    // 也可以显示自定义通知
    if (typeof window.showErrorNotification === 'function') {
      window.showErrorNotification({
        title: message.title || '通知',
        message: message.message || '',
        suggestion: message.suggestion || ''
      });
    }
  }
  
  /**
   * 断开连接
   */
  function disconnect() {
    if (ws) {
      ws.close();
      ws = null;
    }
    stopHeartbeat();
  }
  
  /**
   * 获取连接状态
   */
  function isConnected() {
    return ws && ws.readyState === WebSocket.OPEN;
  }
  
  // 导出 API
  window.WebSocketClient = {
    connect,
    disconnect,
    send,
    on,
    isConnected,
  };
  
  // DOM Ready 时连接
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', connect);
  } else {
    connect();
  }
  
  // 页面卸载时断开
  window.addEventListener('beforeunload', disconnect);
  
})();
