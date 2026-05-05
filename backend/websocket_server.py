"""
WebSocket Server - WebSocket 实时推送服务端

功能:
- 连接状态变更推送
- 任务进度推送
- 错误通知推送
- 心跳保活
"""

from flask import request
from flask_sock import Sock
import json
import time
from backend.core.connection_state import ConnectionState

# 全局 WebSocket 管理器
_ws_clients = {}  # {user_id: [ws_connections]}
_ws_lock = None

def init_websocket(app):
    """初始化 WebSocket"""
    global _ws_lock
    import threading
    _ws_lock = threading.Lock()
    
    sock = Sock(app)
    
    @sock.route('/ws')
    def ws_handler(ws):
        """WebSocket 连接处理"""
        user_id = None
        try:
            # ✅ 修复: 缩短认证超时到 3s,避免阻塞
            import logging
            log = logging.getLogger(__name__)
            log.info("[WebSocket] 等待认证...")
            
            data = ws.receive(timeout=3)
            if not data:
                log.warning("[WebSocket] 认证超时,关闭连接")
                ws.close()
                return
            
            msg = json.loads(data)
            if msg.get('type') == 'auth':
                # 从 session 获取 user_id
                from flask import session
                user_id = session.get('user_id')
                if not user_id:
                    ws.send(json.dumps({
                        'type': 'error',
                        'message': '未认证'
                    }))
                    ws.close()
                    return
                
                # 注册客户端
                with _ws_lock:
                    if user_id not in _ws_clients:
                        _ws_clients[user_id] = []
                    _ws_clients[user_id].append(ws)
                
                log.info(f"[WebSocket] User {user_id} connected")
                
                # 发送欢迎消息
                ws.send(json.dumps({
                    'type': 'system_notification',
                    'message': 'WebSocket 连接成功',
                    'level': 'success'
                }))
                
                # 心跳处理
                while True:
                    data = ws.receive(timeout=60)
                    if not data:
                        break
                    
                    msg = json.loads(data)
                    if msg.get('type') == 'ping':
                        ws.send(json.dumps({
                            'type': 'pong',
                            'timestamp': int(time.time())
                        }))
            
        except Exception as e:
            print(f"[WebSocket] Error: {e}")
        finally:
            # 清理客户端
            if user_id:
                with _ws_lock:
                    if user_id in _ws_clients:
                        _ws_clients[user_id].remove(ws)
                        if not _ws_clients[user_id]:
                            del _ws_clients[user_id]
                print(f"[WebSocket] User {user_id} disconnected")


def broadcast_to_user(user_id, message):
    """向指定用户广播消息"""
    with _ws_lock:
        clients = _ws_clients.get(user_id, [])
    
    dead_clients = []
    for ws in clients:
        try:
            ws.send(json.dumps(message))
        except Exception as e:
            print(f"[WebSocket] Send error to user {user_id}: {e}")
            dead_clients.append(ws)
    
    # 清理失效连接
    if dead_clients:
        with _ws_lock:
            for ws in dead_clients:
                if ws in _ws_clients.get(user_id, []):
                    _ws_clients[user_id].remove(ws)


def broadcast_to_all(message):
    """向所有用户广播消息"""
    with _ws_lock:
        all_clients = []
        for user_clients in _ws_clients.values():
            all_clients.extend(user_clients)
    
    for ws in all_clients:
        try:
            ws.send(json.dumps(message))
        except Exception as e:
            print(f"[WebSocket] Broadcast error: {e}")


def notify_connection_state(user_id, connection_id, state, message=""):
    """推送连接状态变更"""
    broadcast_to_user(user_id, {
        'type': 'connection_state',
        'connection_id': connection_id,
        'state': state.value if hasattr(state, 'value') else state,
        'message': message,
        'timestamp': int(time.time())
    })


def notify_task_progress(user_id, task_id, progress, status="running"):
    """推送任务进度"""
    broadcast_to_user(user_id, {
        'type': 'task_progress',
        'task_id': task_id,
        'progress': progress,
        'status': status,
        'timestamp': int(time.time())
    })


def notify_error(user_id, title, message, suggestion="", level="error"):
    """推送错误通知"""
    broadcast_to_user(user_id, {
        'type': 'error_notification',
        'title': title,
        'message': message,
        'suggestion': suggestion,
        'level': level,
        'timestamp': int(time.time())
    })
