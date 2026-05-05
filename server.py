#!/usr/bin/env python3
"""
K8s Arthas Tool — Flask API Server (重构后)
REST endpoints:
  /api/auth/*        - 认证 (login/logout/current/change-password)
  /api/users/*       - 用户管理 (CRUD, 集群分配)
  /api/clusters/*   - 集群管理 (CRUD, test, namespaces, pods)
  /api/audit-logs   - 审计日志查询
  /api/health       - 健康检查
  /api/check        - Pod 检测 + Java PID
  /api/arthas/*     - Arthas 连接/执行/会话
  /api/profile/*    - 性能分析任务
  /api/monitor/*    - Pod 监控/指标
  /api/pod/files/*  - Pod 文件浏览
  /api/files/*      - 本地文件下载
"""
import os
import json
import re
import uuid
import time
import tempfile
import shutil
import shlex
import threading
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict

log = logging.getLogger(__name__)

from flask import Flask, request, jsonify, send_file, redirect
from flask_cors import CORS
from flask_login import LoginManager, login_required, current_user

# 导入配置和模型
from backend import Config
from models import db, User
from services.authorization_service import AuthorizationService
from api import register_blueprints

# 导入后端模块
from backend import (
    ClusterConfig, PodTarget, KubectlExecutor,
    ArthasAgentManager, ArthasConnection, ProfilerWorkflow,
    PodConnection, RuntimeInfo,
    ARTHAS_DEFAULT_JAR,
    collect_pod_snapshot,
    get_metrics_history, start_metrics_polling, stop_metrics_polling,
)

# ═══════════════════════════════════════════════════════════════════════════════
# 应用初始化
# ═══════════════════════════════════════════════════════════════════════════════

app = Flask(__name__,
    static_folder=Config.STATIC_FOLDER,
    static_url_path=Config.STATIC_URL_PATH,
)
app.secret_key = Config.SECRET_KEY

# ✅ 新增: 初始化 WebSocket
from backend.websocket_server import init_websocket
init_websocket(app)

# ✅ 新增: 注册全局异常处理器
from backend.exceptions import register_error_handlers
register_error_handlers(app)

# ✅ 新增: 提供 external_links.json 配置
@app.route('/external_links.json')
def serve_external_links():
    """提供外部链接配置"""
    try:
        import json
        with open(Config.EXTERNAL_LINKS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data, 200, {'Content-Type': 'application/json'}
    except FileNotFoundError:
        return {'links': [], 'categories': {}}, 200, {'Content-Type': 'application/json'}
    except Exception as e:
        return {'error': str(e)}, 500, {'Content-Type': 'application/json'}

CORS(app, supports_credentials=True, resources={
    r"/api/*": {
        "origins": os.environ.get('CORS_ORIGINS', 'http://127.0.0.1:5001,http://localhost:5001').split(','),
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    },
    r"/mcp/*": {
        "origins": "*",  # AI 客户端来自任意来源
        "methods": ["GET", "POST", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization", "Accept"],
    },
})

# 配置 logging — 紧凑格式：时间|级别|线程|消息
import logging as _logging

class _CompactFormatter(_logging.Formatter):
    _LEVEL_MAP = {'WARNING': 'WARN', 'CRITICAL': 'CRIT'}
    def format(self, record):
        record.levelname = self._LEVEL_MAP.get(record.levelname, record.levelname)
        tname = record.threadName or '-'
        if '(' in tname:
            tname = tname[:tname.index('(')].rstrip()
        record.threadName = tname[:14]
        return super().format(record)

_h = _logging.StreamHandler()
_h.setFormatter(_CompactFormatter('%(asctime)s|%(levelname)-4s|%(threadName)-14s|%(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
_logging.basicConfig(level=_logging.INFO, handlers=[_h])

# 自定义 werkzeug RequestHandler，在原生日志中追加耗时
import time as _time
from werkzeug.serving import WSGIRequestHandler as _BaseHandler

class _TimedRequestHandler(_BaseHandler):
    def handle_one_request(self):
        self._req_start = _time.time()
        super().handle_one_request()

    def log_request(self, code='-', size='-'):
        if self.path.startswith('/static/') or self.path.startswith('/css/') or self.path.startswith('/js/'):
            return
        elapsed = (_time.time() - getattr(self, '_req_start', _time.time())) * 1000
        _logging.getLogger('werkzeug').info(
            '%s|%s|%s|%s|%4.0fms',
            self.client_address[0], self.command, self.path, code, elapsed)

    def log(self, type, message, *args):
        getattr(_logging.getLogger('werkzeug'), type)(message, *args)

# Flask-Login 配置
login_manager = LoginManager(app)
login_manager.login_view = 'login_page'


@login_manager.unauthorized_handler
def unauthorized():
    """未登录时：API 请求返回 JSON 401，页面请求重定向到登录页"""
    if request.path.startswith('/api/'):
        return jsonify({"error": "未登录或会话已过期，请重新登录"}), 401
    return redirect('/login.html')


@login_manager.user_loader
def load_user(user_id: int):
    """Flask-Login user_loader 回调函数"""
    return User.get_by_id(user_id)


# 注册 API 蓝图
register_blueprints(app)

# ✅ 关键修复: 首先初始化主数据库表 (users, clusters, connections 等)
try:
    db.initialize()
    print("✓ 数据库初始化成功")
except Exception as e:
    print(f"✗ 数据库初始化失败: {e}")
    raise

# 初始化 MCP 数据库表
from api.mcp_proxy import init_mcp_tables
init_mcp_tables()

# 初始化 AI 数据库表
from api.ai_chat import init_ai_tables
init_ai_tables()

# 初始化任务中心数据库表
from api.task_center import init_task_tables, start_task_scheduler
init_task_tables()
start_task_scheduler()

# 启动 task_logs 定时清理服务
def _start_cleanup_scheduler():
    """启动 task_logs 清理定时任务"""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from services.task_logs_cleanup_service import TaskLogsCleanupService, get_cleanup_config
        
        scheduler = BackgroundScheduler()
        cleanup_service = TaskLogsCleanupService()
        
        # 读取清理配置
        cleanup_cron = get_cleanup_config('task_logs.cleanup_cron', '0 3 * * *')
        archive_cleanup_cron = get_cleanup_config('task_logs_archive.cleanup_cron', '0 4 1 * *')
        
        # 解析 cron 表达式 (格式: minute hour day month day_of_week)
        parts = cleanup_cron.split()
        if len(parts) == 5:
            scheduler.add_job(
                lambda: asyncio.run(cleanup_service.cleanup_expired_logs()),
                'cron',
                minute=parts[0],
                hour=parts[1],
                day=parts[2],
                month=parts[3],
                day_of_week=parts[4],
                id='cleanup_task_logs',
                replace_existing=True,
            )
            log.info("task_logs 清理定时任务已注册: %s", cleanup_cron)
        
        parts = archive_cleanup_cron.split()
        if len(parts) == 5:
            scheduler.add_job(
                lambda: asyncio.run(cleanup_service.cleanup_old_archives()),
                'cron',
                minute=parts[0],
                hour=parts[1],
                day=parts[2],
                month=parts[3],
                day_of_week=parts[4],
                id='cleanup_task_logs_archive',
                replace_existing=True,
            )
            log.info("task_logs_archive 清理定时任务已注册: %s", archive_cleanup_cron)
        
        scheduler.start()
        log.info("APScheduler 定时清理服务已启动")
        
    except ImportError:
        log.warning("APScheduler 未安装，task_logs 清理服务未启动。请运行: pip install apscheduler")
    except Exception as e:
        log.error("启动清理调度器失败: %s", e, exc_info=True)

_start_cleanup_scheduler()

# ═══════════════════════════════════════════════════════════════════════════════
# 辅助函数

# ═══════════════════════════════════════════════════════════════════════════════

OUTPUT_DIR = Path(Config.OUTPUT_DIR)
OUTPUT_DIR.mkdir(exist_ok=True)


def _load_clusters() -> List[Dict]:
    """加载集群配置（委托给 api/clusters.py 统一实现）"""
    from api.clusters import _load_clusters as _load
    return _load()


def _sync_clusters_to_db():
    """启动时将 clusters.json 中的集群同步到数据库（仅补充缺失的记录）"""
    try:
        clusters = _load_clusters()
        for c in clusters:
            if not db.exists('clusters', 'id = ?', (c.get('id', ''),)):
                db.insert('clusters', {
                    'id': c.get('id', ''),
                    'name': c.get('name', ''),
                    'kubeconfig': c.get('kubeconfig', ''),
                    'context': c.get('context', ''),
                })
    except Exception as e:
        log.warning("同步 clusters 到数据库失败: %s", e)


def _make_runner(cluster_name: str) -> tuple:
    """创建 KubectlExecutor"""
    clusters = _load_clusters()
    cluster = next((c for c in clusters if c.get('name') == cluster_name), None)
    if not cluster:
        return None, "集群不存在"
    
    # 非 admin 检查集群访问权限
    if not current_user.is_admin:
        user_clusters = db.fetch_all(
            'SELECT cluster_id FROM user_clusters WHERE user_id = ?',
            (current_user.id,)
        )
        allowed = {r['cluster_id'] for r in user_clusters}
        if cluster.get('id') not in allowed:
            return None, "无权访问此集群"
    
    kubeconfig = cluster.get('kubeconfig', '')
    context = cluster.get('context', '')
    return KubectlExecutor(kubeconfig=kubeconfig, context=context), None


# ═══════════════════════════════════════════════════════════════════════════════
# 页面路由
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/')
@app.route('/index.html')
@app.route('/index')
def index():
    """根路径 - 未登录重定向到登录页"""
    if not current_user.is_authenticated:
        return redirect('/login.html')
    return app.send_static_file('index.html')


@app.route('/login.html')
@app.route('/login')
def login_page():
    """登录页面"""
    return app.send_static_file('login.html')


@app.route('/user-management.html')
@login_required
def user_management_page():
    """用户管理页面（仅管理员）"""
    return app.send_static_file('user-management.html')


@app.route('/audit-logs.html')
@login_required
def audit_logs_page():
    """审计日志页面（仅管理员）"""
    return app.send_static_file('audit-logs.html')


@app.route('/mcp-config.html')
@login_required
def mcp_config_page():
    """MCP 接入配置页面"""
    return app.send_static_file('mcp-config.html')


# ═══════════════════════════════════════════════════════════════════════════════
# 保留的后端 API (待迁移的部分)
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/api/health', methods=['GET'])
def health():
    """健康检查"""
    return jsonify({"ok": True, "version": "2026.03.23"})


@app.route('/api/contexts', methods=['POST'])
@login_required
def get_kube_contexts():
    """获取 kubeconfig 中的 contexts"""
    from backend.core.kubectl import KubectlExecutor
    
    d = request.json or {}
    kubeconfig = d.get('kubeconfig', '')
    
    if not kubeconfig:
        return jsonify({"error": "请提供 kubeconfig 路径"}), 400
    
    try:
        runner = KubectlExecutor(kubeconfig=kubeconfig)
        contexts = runner.get_contexts()
        current = runner.get_current_context()
        return jsonify({"contexts": contexts, "current": current})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ═══════════════════════════════════════════════════════════════════════════════
# 集群管理 API
# ═══════════════════════════════════════════════════════════════════════════════

# 集群管理端点已移至 api/clusters.py 蓝图


@app.route('/api/check', methods=['POST'])
@login_required
def check_pod():
    """检测 Pod 内 Java 进程，返回详细列表供用户选择"""
    d = request.json or {}
    runner, err = _make_runner(d.get('cluster_name', ''))
    if err:
        return jsonify({"error": err, "java_pid": None}), 400
    
    ns = d.get('namespace', 'default')
    pod = d.get('pod_name', '')
    container = d.get('container', '')
    
    # 检测 Java 进程 (使用 jps -l 获取进程名)
    rc, out, _ = runner.exec_pod(ns, pod, container, 
        "jps -l 2>/dev/null || ps -ef 2>/dev/null | grep java | grep -v grep", timeout=10)
    
    java_processes = []
    arthas_keywords = ['arthas', 'arthas-boot', 'as-boot', 'arthas.jar', 'jps', 'sun.tools.jps']
    
    for line in out.strip().splitlines():
        line_lower = line.lower()
        # 过滤 arthas/jps 相关进程
        if any(kw in line_lower for kw in arthas_keywords):
            continue
        parts = line.strip().split(None, 1)
        if parts and parts[0].isdigit():
            pid = parts[0]
            desc = parts[1] if len(parts) > 1 else "java"
            java_processes.append({
                "pid": pid,
                "description": desc.strip()
            })
    
    # 默认选择第一个进程
    default_pid = java_processes[0]["pid"] if java_processes else None
    
    return jsonify({
        "cluster_name": d.get('cluster_name'),
        "namespace": ns,
        "pod_name": pod,
        "container": container,
        "java_pid": default_pid,
        "java_pids": [p["pid"] for p in java_processes],
        "java_processes": java_processes,  # 新增：完整进程列表
        "has_multiple_jvms": len(java_processes) > 1,  # 新增：是否有多个 JVM
    })


# ═══════════════════════════════════════════════════════════════════════════════
# Arthas 连接管理
# ═══════════════════════════════════════════════════════════════════════════════

# 连接状态缓存 (待迁移到数据库)
# 格式: {conn_id: {"conn": ArthasConnection, "user_id": int}}
_connections: Dict[str, dict] = {}
_connections_lock = threading.Lock()

# ✅ 关键修复: 初始化 ConnectionStateManager
from backend.core.connection_state import ConnectionStateManager
_state_manager = ConnectionStateManager(db)
# 启动 TTL 清理 (每 30 分钟)
_state_manager.schedule_ttl_cleanup(interval_seconds=1800)
log.info("ConnectionStateManager initialized with TTL cleanup (30min interval)")


# 注册 Pod 连接 API（轻量级，无需 Arthas）
from api.pod_apis import register_pod_apis
register_pod_apis(app, db, _make_runner, _connections_lock, _connections)


def _check_conn_owner(conn_id: str) -> bool:
    """检查当前用户是否是连接的拥有者（admin 拥有所有权限）"""
    if current_user.is_admin:
        return True
    entry = _connections.get(conn_id)
    return entry and entry.get('user_id') == current_user.id


def _get_conn(conn_id: str):
    """获取连接对象(带权限检查)"""
    entry = _connections.get(conn_id)
    if not entry:
        return None
    
    # 权限检查: 非 admin 只能访问自己的连接
    if not current_user.is_admin and entry.get('user_id') != current_user.id:
        return None
    
    return entry.get('conn')


@app.route('/api/arthas/connect', methods=['POST'])
@login_required
def arthas_connect():
    """创建 Arthas 连接，支持指定 Java PID"""
    d = request.json or {}
    cluster_name = d.get('cluster_name', '')
    namespace = d.get('namespace', 'default')
    pod = d.get('pod_name', '')
    container = d.get('container', '')
    java_pid = d.get('java_pid')  # 新增：用户指定的 Java PID（可选）
    
    runner, err = _make_runner(cluster_name)
    if err:
        return jsonify({"error": err}), 400
    auth_err, auth_code = AuthorizationService.require_namespace_access(current_user, cluster_name, namespace)
    if auth_err:
        return jsonify(auth_err), auth_code
    
    conn_id = f"{cluster_name}/{namespace}/{pod}"
    # 非 admin 的连接 ID 带上 user_id，避免与 admin 或其他用户的连接冲突
    if not current_user.is_admin:
        conn_id = f"{cluster_name}/{namespace}/{pod}@u{current_user.id}"
    
    # 创建连接
    target = PodTarget(cluster_name=cluster_name, namespace=namespace, pod_name=pod, container=container)
    conn = ArthasConnection(runner, target, state_manager=_state_manager)
    conn.connection_id = conn_id  # ✅ 设置 connection_id 用于状态管理
    
    # 如果用户指定了 PID，设置到 agent manager 中
    if java_pid:
        conn.agent_mgr._pid = int(java_pid)
    
    try:
        ok, msg = conn.connect()
        if not ok:
            if isinstance(msg, dict):
                return jsonify({"ok": False, **msg}), 400
            return jsonify({"ok": False, "error": msg}), 400
        
        # 检测 MCP 端点是否可用
        mcp_available = conn.agent_mgr._check_mcp_available(conn.target.arthas_http_port)
        
        with _connections_lock:
            _connections[conn_id] = {"conn": conn, "user_id": current_user.id, "mcp_available": mcp_available}
        
        # 持久化连接到数据库（UPSERT）
        now_ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        if db.exists('connections', 'id = ?', (conn_id,)):
            db.update('connections', {
                'level': 'arthas',
                'local_port': conn.local_port,
                'java_pid': conn.java_pid,
                'arthas_version': conn.arthas_version,
                'status': 'ready',
                'last_ping_at': now_ts,
                'user_id': current_user.id,
                'updated_at': now_ts,
            }, 'id = ?', (conn_id,))
        else:
            db.insert('connections', {
                'id': conn_id,
                'cluster_name': cluster_name,
                'namespace': namespace,
                'pod_name': pod,
                'container_name': '',
                'level': 'arthas',
                'local_port': conn.local_port,
                'java_pid': conn.java_pid,
                'arthas_version': conn.arthas_version,
                'status': 'ready',
                'last_ping_at': now_ts,
                'user_id': current_user.id,
                'updated_at': now_ts,
            })
        
        from services.audit_service import AuditService
        AuditService.log_connection_created(current_user.id, conn_id, pod, namespace)
        
        return jsonify({
            "ok": True,
            "conn_id": conn_id,  # DEPRECATED: use connection_id instead (remove in v2.0)
            "connection_id": conn_id,
            "local_port": conn.local_port,
            "java_pid": conn.java_pid,  # 返回实际连接的 PID
            "http_url": f"http://localhost:{conn.local_port}",
            "arthas_version": conn.arthas_version,  # Arthas 版本号
            "arthas_address": conn.arthas_address,   # Arthas HTTP 地址
            "mcp_available": mcp_available,  # MCP 端点是否可用
            "message": msg
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/arthas/disconnect', methods=['POST'])
@login_required
def arthas_disconnect():
    """断开 Arthas 连接"""
    d = request.json or {}
    conn_id = d.get('conn_id', '')
    
    if conn_id in _connections:
        if not _check_conn_owner(conn_id):
            return jsonify({"state": "FAILED", "message": "无权操作此连接"}), 403
        with _connections_lock:
            entry = _connections.pop(conn_id, None)
        conn = entry.get('conn') if entry else None
        if conn:
            conn.disconnect()
        
        # 从数据库删除连接记录
        db.delete('connections', 'id = ?', (conn_id,))
        
        # 解析 conn_id
        parts = conn_id.split('/')
        if len(parts) >= 3:
            pod = parts[2]
            namespace = parts[1]
            from services.audit_service import AuditService
            AuditService.log_connection_deleted(current_user.id, conn_id, pod, namespace)
        
        return jsonify({"ok": True})
    
    return jsonify({"error": "连接不存在"}), 404


def _ensure_connection(conn_id: str, d: dict):
    """确保连接存在，若内存中不存在则自动重建（线程安全）"""
    with _connections_lock:
        if conn_id and conn_id in _connections:
            # 检查连接所有者
            if not _check_conn_owner(conn_id):
                return None, "无权操作此连接"
            return _connections[conn_id].get('conn'), None

    # 从请求参数中提取连接信息并自动重建
    cluster_name = d.get('cluster_name', '')
    namespace = d.get('namespace', 'default')
    pod = d.get('pod_name', '')
    container = d.get('container', '')

    if not conn_id:
        conn_id = f"{cluster_name}/{namespace}/{pod}"
        # 非 admin 的连接 ID 带上 user_id，避免与 admin 或其他用户的连接冲突
        if not current_user.is_admin:
            conn_id = f"{cluster_name}/{namespace}/{pod}@u{current_user.id}"

    if not cluster_name or not pod:
        return None, "连接不存在且缺少连接参数，请重新连接"

    # 检查用户是否有权访问该集群（非 admin 只能连接分配给自己的集群）
    if not current_user.is_admin:
        user_clusters = db.fetch_all(
            'SELECT cluster_id FROM user_clusters WHERE user_id = ?',
            (current_user.id,)
        )
        allowed_cluster_ids = {r['cluster_id'] for r in user_clusters}
        clusters = _load_clusters()
        target_cluster = next((c for c in clusters if c.get('name') == cluster_name), None)
        if not target_cluster or target_cluster.get('id') not in allowed_cluster_ids:
            return None, "无权访问此集群"

    # 尝试自动重建连接
    runner, err = _make_runner(cluster_name)
    if err:
        return None, f"连接已丢失，自动重连失败: {err}"

    target = PodTarget(cluster_name=cluster_name, namespace=namespace, pod_name=pod, container=container)
    conn = ArthasConnection(runner, target, state_manager=_state_manager)
    conn.connection_id = conn_id  # ✅ 设置 connection_id 用于状态管理
    
    log.info("[_ensure_connection] 开始建立连接, conn_id=%s", conn_id)
    
    # ✅ 关键修复: 先建立 Pod 连接
    try:
        ok, msg = conn.pod_conn.connect()
        log.info("[_ensure_connection] Pod 连接结果: ok=%s, msg=%s", ok, msg)
    except Exception as e:
        log.error("[_ensure_connection] Pod 连接异常: %s", e, exc_info=True)
        return None, f"连接已丢失，自动重连失败: {str(e)}"
    
    if not ok:
        # msg 可能是字符串或字典
        err_str = msg.get("message", str(msg)) if isinstance(msg, dict) else msg
        return None, f"连接已丢失，自动重连失败: {err_str}"
    
    # ✅ 同步 Pod 连接状态到 ArthasConnection
    conn._pod_connected = True
    conn._healthy = True
    conn._runtime_info = conn.pod_conn._runtime_info
    conn._pod_phase = conn.pod_conn._pod_phase
    
    # ✅ 关键修复: 再建立 Arthas 连接
    log.info("[_ensure_connection] 开始建立 Arthas 连接...")
    ok2, msg2 = conn.connect_arthas(timeout=30)
    log.info("[_ensure_connection] 第一次 Arthas 连接结果: ok=%s, msg=%s, msg_type=%s", ok2, msg2, type(msg2).__name__)
    if not ok2:
        # ✅ 如果是 REINSTALL_NEEDED,关闭端口转发,清理残留进程,重试
        is_reinstall = (msg2 == "REINSTALL_NEEDED") or (isinstance(msg2, dict) and msg2.get('message') == 'REINSTALL_NEEDED')
        log.info("[_ensure_connection] is_reinstall=%s, msg2=%s", is_reinstall, msg2)
        if is_reinstall:
            log.warning("[_ensure_connection] 检测到 REINSTALL_NEEDED,清理后重试")
            conn._stop_port_forward()
            conn._arthas_ready = False
            conn.client = None
            conn._pf_proc = None
            conn.local_port = 0
            # 重试一次
            log.info("[_ensure_connection] 开始第二次 Arthas 连接...")
            ok2, msg2 = conn.connect_arthas(timeout=30)
            log.info("[_ensure_connection] 第二次 Arthas 连接结果: ok=%s, msg=%s", ok2, msg2)
        
        if not ok2:
            err_str = msg2.get("message", str(msg2)) if isinstance(msg2, dict) else msg2
            return None, f"连接已丢失，自动重连失败: {err_str}"

    # ✅ Arthas 连接成功,更新数据库中的元数据
    with _connections_lock:
        now_ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        if db.exists('connections', 'id = ?', (conn_id,)):
            db.update('connections', {
                'level': 'arthas',
                'local_port': conn.local_port,
                'java_pid': conn.java_pid,
                'arthas_version': conn.arthas_version,
                'status': 'ready',
                'last_ping_at': now_ts,
                'user_id': current_user.id,
                'updated_at': now_ts,
            }, 'id = ?', (conn_id,))
        else:
            db.insert('connections', {
                'id': conn_id,
                'cluster_name': cluster_name,
                'namespace': namespace,
                'pod_name': pod,
                'container_name': '',
                'level': 'arthas',
                'local_port': conn.local_port,
                'java_pid': conn.java_pid,
                'arthas_version': conn.arthas_version,
                'status': 'ready',
                'last_ping_at': now_ts,
                'user_id': current_user.id,
                'updated_at': now_ts,
            })
        
        if conn_id not in _connections:
            _connections[conn_id] = {"conn": conn, "user_id": current_user.id}
    log.info("Auto-reconnected: %s", conn_id)
    return conn, None


@app.route('/api/arthas/exec', methods=['POST'])
@login_required
def arthas_exec():
    """执行 Arthas 命令"""
    d = request.json or {}
    # DEPRECATED: conn_id parameter support (remove in v2.0)
    conn_id = d.get('conn_id') or d.get('connection_id') or ''
    command = d.get('command', '').strip()

    conn, err = _ensure_connection(conn_id, d)
    if err:
        return jsonify({"state": "FAILED", "message": err}), 404

    try:
        from backend.core.arthas_executor import ArthasCommandExecutor
        result = ArthasCommandExecutor.execute(
            conn,
            command,
            skip_audit=False,
            skip_history=False,
        )
        
        # 保存命令历史
        _save_arthas_command(conn_id, command, json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result), '')
        
        # 直接透传 Arthas HTTP API 原始响应，前端 renderRes 依赖 state/body 结构
        return jsonify(result)
    except Exception as e:
        return jsonify({"state": "FAILED", "message": str(e)}), 500


def _save_arthas_command(conn_id: str, command: str, output: str = None, error: str = None):
    """保存 Arthas 命令历史"""
    user_id = current_user.id if current_user.is_authenticated else None
    db.insert('arthas_command_logs', {
        'connection_id': conn_id,
        'user_id': user_id,
        'command': command,
        'output': output,
        'error': error
    })


@app.route('/api/arthas/status', methods=['POST'])
@login_required
def arthas_status():
    """获取 Arthas 连接状态"""
    d = request.json or {}
    conn_id = d.get('conn_id') or d.get('connection_id') or ''
    
    conn = _get_conn(conn_id)
    if not conn:
        return jsonify({"connected": False})
    
    if not _check_conn_owner(conn_id):
        return jsonify({"connected": False, "message": "无权访问此连接"})
    
    return jsonify({
        "connected": conn.is_alive() if hasattr(conn, 'is_alive') else True,
        "local_port": conn.local_port if hasattr(conn, 'local_port') else 0,
        "java_pid": conn.java_pid if hasattr(conn, 'java_pid') else None,
    })


@app.route('/api/arthas/connections/cleanup-stale', methods=['POST'])
@login_required
def cleanup_stale_connections():
    """真正清理失效连接：断开内存连接、删除 Pod/Arthas 状态和数据库记录。"""
    d = request.json or {}
    conn_ids = d.get('connection_ids') or d.get('conn_ids') or []
    if not isinstance(conn_ids, list):
        return jsonify({'error': 'connection_ids 必须是数组'}), 400

    cleaned = []
    denied = []
    for conn_id in conn_ids:
        if not conn_id:
            continue

        row = db.fetch_one('SELECT user_id FROM connections WHERE id = ?', (conn_id,))
        if row and not current_user.is_admin and row.get('user_id') != current_user.id:
            denied.append(conn_id)
            continue
        if conn_id in _connections and not _check_conn_owner(conn_id):
            denied.append(conn_id)
            continue

        entry = None
        with _connections_lock:
            entry = _connections.pop(conn_id, None)
        
        # 安全获取 conn 对象
        conn = entry.get('conn') if entry else None
        if conn:
            try:
                conn.disconnect()
            except Exception as e:
                log.warning(f"断开连接 {conn_id} 失败: {e}")

        cleanup_pod = getattr(app, 'cleanup_pod_connection_by_id', None)
        if cleanup_pod:
            cleanup_pod(conn_id)

        db.delete('connections', 'id = ?', (conn_id,))
        cleaned.append(conn_id)

    return jsonify({'ok': True, 'cleaned': cleaned, 'denied': denied, 'count': len(cleaned)})


@app.route('/api/arthas/connections/check', methods=['POST'])
@login_required
def check_connections_health():
    """批量检查连接列表的健康状态，检测 Pod 是否存在、Arthas 是否存活"""
    d = request.json or {}
    conn_list = d.get('connections', [])  # [{id, cluster_name, namespace, pod_name}, ...]
    
    results = {}
    for c in conn_list:
        conn_id = c.get('id', '')
        cluster_name = c.get('cluster_name', '')
        namespace = c.get('namespace', '')
        pod_name = c.get('pod_name', '')
        
        status = {'alive': False, 'pod_exists': None, 'reason': ''}
        
        # 1. 检查后端内存中的连接是否存活
        conn = _get_conn(conn_id)
        if conn:
            try:
                status['alive'] = conn.is_alive() if hasattr(conn, 'is_alive') else True
            except Exception:
                status['alive'] = False
            if not status['alive']:
                status['reason'] = 'arthas_unreachable'
        
        # 2. 检查 Pod 是否存在（kubectl get pod）
        if cluster_name and namespace and pod_name:
            try:
                runner, err = _make_runner(cluster_name)
                if not err:
                    rc, out, _ = runner._run(
                        ["get", "pod", pod_name, "-n", namespace,
                         "-o", "jsonpath={.status.phase}"],
                        timeout=8
                    )
                    if rc == 0 and out.strip():
                        phase = out.strip()
                        status['pod_exists'] = True
                        status['pod_phase'] = phase
                        if phase not in ('Running',):
                            status['reason'] = f'pod_{phase.lower()}'
                    else:
                        status['pod_exists'] = False
                        status['reason'] = 'pod_not_found'
                else:
                    status['pod_exists'] = None
                    status['reason'] = 'cluster_unavailable'
            except Exception as e:
                status['pod_exists'] = None
                status['reason'] = f'check_error: {str(e)[:80]}'
        
        results[conn_id] = status
    
    return jsonify({'results': results})


@app.route('/api/arthas/commands', methods=['GET'])
@login_required
def get_arthas_commands():
    """获取 Arthas 命令历史"""
    conn_id = request.args.get('connection_id', '')
    limit = int(request.args.get('limit', 100))
    
    if not conn_id:
        return jsonify({"error": "connection_id 必填"}), 400
    
    # 非 admin 只能查看自己的命令历史
    if current_user.is_admin:
        commands = db.fetch_all(
            'SELECT command, output, error, timestamp FROM arthas_command_logs WHERE connection_id = ? ORDER BY timestamp DESC LIMIT ?',
            (conn_id, limit)
        )
    else:
        commands = db.fetch_all(
            'SELECT command, output, error, timestamp FROM arthas_command_logs WHERE connection_id = ? AND user_id = ? ORDER BY timestamp DESC LIMIT ?',
            (conn_id, current_user.id, limit)
        )
    return jsonify({"ok": True, "commands": [dict(c) for c in (commands or [])]})


# ── Arthas Session 命令 ─────────────────────────────────────────────────────────

@app.route('/api/arthas/session/create', methods=['POST'])
@login_required
def arthas_session_create():
    """创建 Arthas 会话"""
    d = request.json or {}
    conn_id = d.get('conn_id') or d.get('connection_id') or ''
    
    conn, err = _ensure_connection(conn_id, d)
    if err:
        return jsonify({"state": "FAILED", "message": err}), 400
    
    if not conn or not hasattr(conn, 'http_client') or not conn.http_client:
        return jsonify({"state": "FAILED", "message": "未连接"}), 400
    
    try:
        result = conn.http_client.init_session() if hasattr(conn.http_client, 'init_session') else {"state": "FAILED", "message": "不支持会话模式"}
        return jsonify(result)
    except Exception as e:
        return jsonify({"state": "FAILED", "message": str(e)}), 500


@app.route('/api/arthas/session/exec', methods=['POST'])
@login_required
def arthas_session_exec():
    """在会话中执行命令"""
    d = request.json or {}
    conn_id = d.get('conn_id') or d.get('connection_id') or ''
    session_id = d.get('session_id', '')
    command = d.get('command', '')
    
    conn, err = _ensure_connection(conn_id, d)
    if err or not conn or not hasattr(conn, 'http_client'):
        return jsonify({"state": "FAILED", "message": err or "未连接"}), 400
    
    try:
        result = conn.http_client.exec_async(session_id, command) if hasattr(conn.http_client, 'exec_async') else {"state": "FAILED", "message": "不支持会话模式"}
        return jsonify(result)
    except Exception as e:
        return jsonify({"state": "FAILED", "message": str(e)}), 500


@app.route('/api/arthas/session/pull', methods=['POST'])
@login_required
def arthas_session_pull():
    """拉取会话输出"""
    d = request.json or {}
    conn_id = d.get('conn_id') or d.get('connection_id') or ''
    session_id = d.get('session_id', '')
    consumer_id = d.get('consumer_id', '')
    
    conn, err = _ensure_connection(conn_id, d)
    if err or not conn or not hasattr(conn, 'http_client'):
        return jsonify({"state": "FAILED", "message": err or "未连接"}), 400
    
    try:
        result = conn.http_client.pull_results(session_id, consumer_id) if hasattr(conn.http_client, 'pull_results') else {"state": "FAILED", "message": "不支持会话模式"}
        return jsonify(result)
    except Exception as e:
        return jsonify({"state": "FAILED", "message": str(e)}), 500


@app.route('/api/arthas/session/interrupt', methods=['POST'])
@login_required
def arthas_session_interrupt():
    """中断会话命令"""
    d = request.json or {}
    conn_id = d.get('conn_id') or d.get('connection_id') or ''
    session_id = d.get('session_id', '')
    
    conn, err = _ensure_connection(conn_id, d)
    if err or not conn or not hasattr(conn, 'http_client'):
        return jsonify({"state": "FAILED", "message": err or "未连接"}), 400
    
    try:
        result = conn.http_client.interrupt_job(session_id) if hasattr(conn.http_client, 'interrupt_job') else {"state": "FAILED", "message": "不支持会话模式"}
        return jsonify(result)
    except Exception as e:
        return jsonify({"state": "FAILED", "message": str(e)}), 500


@app.route('/api/arthas/session/close', methods=['POST'])
@login_required
def arthas_session_close():
    """关闭会话"""
    d = request.json or {}
    conn_id = d.get('conn_id') or d.get('connection_id') or ''
    session_id = d.get('session_id', '')
    
    conn, err = _ensure_connection(conn_id, d)
    if err or not conn or not hasattr(conn, 'http_client'):
        return jsonify({"state": "FAILED", "message": err or "未连接"}), 400
    
    try:
        result = conn.http_client.close_session(session_id) if hasattr(conn.http_client, 'close_session') else {"state": "FAILED", "message": "不支持会话模式"}
        return jsonify(result)
    except Exception as e:
        return jsonify({"state": "FAILED", "message": str(e)}), 500


# ═══════════════════════════════════════════════════════════════════════════════
# 性能分析任务
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/api/profile/start', methods=['POST'])
@login_required
def start_profiler():
    """启动性能分析任务"""
    d = request.json or {}
    # DEPRECATED: conn_id parameter support (remove in v2.0)
    conn_id = d.get('conn_id') or d.get('connection_id') or ''
    # 优先使用 mode，兼容旧版 type 参数
    task_type = d.get('mode') or d.get('type', 'profiler')  # profiler/jfr/threaddump/heapdump
    duration = int(d.get('duration', 60))
    fmt = d.get('format', 'html')  # html/collapsed/jfr
    # 根据任务类型设置默认事件
    mode = task_type
    if mode == 'jfr':
        event = d.get('event', d.get('jfr_settings', 'default'))
    elif mode in ('threaddump', 'heapdump'):
        event = d.get('event', mode)  # dump 类型事件=类型名
    else:
        event = d.get('event', 'cpu')  # profiler 默认 cpu
    
    conn, err = _ensure_connection(conn_id, d)
    if err:
        return jsonify({"state": "FAILED", "message": err}), 404

    conn_id = conn_id or f"{d.get('cluster_name','')}/{d.get('namespace','default')}/{d.get('pod_name','')}"
    
    # 检查同一连接是否已有运行中的任务（防止重复提交）
    running_task = db.fetch_one(
        'SELECT id, type, event, created_at FROM profiler_tasks WHERE connection_id = ? AND status IN (?, ?) LIMIT 1',
        (conn_id, 'running', 'starting')
    )
    if running_task:
        return jsonify({
            "state": "FAILED", 
            "message": f"该连接已有运行中的任务 (ID: {running_task['id']}, 类型: {running_task['type']}/{running_task['event']}, 启动于: {running_task['created_at']})，请等待完成后再试"
        }), 409
    
    task_id = str(uuid.uuid4())[:8]
    
    # 保存任务到数据库
    user_id = current_user.id if current_user.is_authenticated else None
    now_ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    db.insert('profiler_tasks', {
        'id': task_id,
        'connection_id': conn_id,
        'user_id': user_id,
        'type': task_type,
        'status': 'running',
        'cluster_name': d.get('cluster_name', ''),
        'namespace': d.get('namespace', 'default'),
        'pod_name': d.get('pod_name', ''),
        'mode': task_type,
        'event': event,
        'duration': duration,
        'format': fmt,
        'progress': 0,
        'created_at': now_ts,
        'updated_at': now_ts,
    })
    
    from services.audit_service import AuditService
    AuditService.log_task_created(user_id, task_id, task_type)
    
    # 后台执行任务
    def run_task():
        import logging
        logger = logging.getLogger(__name__)
        workflow = ProfilerWorkflow(conn)
        try:
            result = workflow.run(duration=duration, fmt=fmt, mode=task_type, event=event,
                                   output_dir=str(OUTPUT_DIR))
            output_path = (result.get('local_file', '') or result.get('output_path', '')) if isinstance(result, dict) else ''
            message = result.get('message', '') if isinstance(result, dict) else ''
            logger.info(f"[Profiler] Task {task_id} completed: {output_path}")
            db.update('profiler_tasks', {
                'status': 'completed',
                'progress': 100,
                'output_path': output_path,
                'message': message,
                'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }, 'id = ?', (task_id,))
        except Exception as e:
            logger.error(f"[Profiler] Task {task_id} failed: {e}", exc_info=True)
            db.update('profiler_tasks', {
                'status': 'failed',
                'message': str(e),
                'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }, 'id = ?', (task_id,))
    
    import threading
    threading.Thread(target=run_task, daemon=True).start()
    
    return jsonify({"ok": True, "task_id": task_id})


# ── 任务状态轮询（前端 pfPoll 使用）───
@app.route('/api/profile/<task_id>', methods=['GET'])
@login_required
def get_profile_status(task_id: str):
    """获取任务状态 + 关联日志（供前端轮询使用）"""
    task = db.fetch_one('SELECT * FROM profiler_tasks WHERE id = ?', (task_id,))
    if not task:
        return jsonify({"error": "任务不存在", "status": "failed"}), 404
    
    # 直接从 task 获取消息，不再使用 profiler_logs 表
    logs = []
    if task.get('message'):
        logs = [{"message": task['message'], "timestamp": task['updated_at']}]
    
    # 提取输出文件名（从 output_path 中获取文件名）
    output_file = None
    if task.get('output_path'):
        output_file = Path(task['output_path']).name or task['output_path']
    
    return jsonify({
        "status": task['status'],
        "type": task['type'],
        "event": task.get('event', ''),
        "duration": task.get('duration', 60),
        "progress": task.get('progress', _calc_progress(task)),
        "output_file": output_file,
        "logs": logs,
        "created_at": task.get('created_at', ''),  # 添加创建时间，供前端恢复进度计算
    })


# ── 任务状态查询（profiler.js 组件兼容）───
@app.route('/api/profile/status', methods=['POST'])
@login_required
def profile_status():
    """查询采样任务状态（profiler.js 组件使用）"""
    d = request.json or {}
    task_id = d.get('task_id', '')
    
    task = db.fetch_one('SELECT * FROM profiler_tasks WHERE id = ?', (task_id,))
    if not task:
        return jsonify({"status": "not_found", "error": "任务不存在"}), 404
    
    # 直接从 task 获取消息
    logs = []
    if task.get('message'):
        logs = [task['message']]
    
    return jsonify({
        "status": task['status'],
        "logs": logs,
        "progress": task.get('progress', _calc_progress(task)),
    })


# ── 停止任务（profiler.js 组件使用）───
@app.route('/api/profile/stop', methods=['POST'])
@login_required
def stop_profiler():
    """停止正在运行的采样任务"""
    d = request.json or {}
    task_id = d.get('task_id', '')
    
    task = db.fetch_one('SELECT * FROM profiler_tasks WHERE id = ?', (task_id,))
    if not task:
        return jsonify({"error": "任务不存在"}), 404
    
    if task['status'] not in ('running', 'pending'):
        return jsonify({"ok": False, "msg": f"当前状态 {task['status']}，无法停止"})
    
    db.update('profiler_tasks', {'status': 'stopped', 'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')},
             'id = ?', (task_id,))
    return jsonify({"ok": True, "status": "stopped"})


# ── 采样日志 CRUD ──
@app.route('/api/profile/logs', methods=['POST'])
@login_required
def save_profiler_log():
    """更新任务进度消息"""
    d = request.json or {}
    task_id = d.get('task_id', '') or d.get('connection_id', '')
    message = d.get('message', '')
    progress = d.get('progress')  # 可选
    
    if not task_id:
        return jsonify({"error": "task_id 必填"}), 400
    
    update_data = {'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    if message:
        update_data['message'] = message
    if progress is not None:
        update_data['progress'] = int(progress)
    
    db.update('profiler_tasks', update_data, 'id = ?', (task_id,))
    return jsonify({"ok": True})


@app.route('/api/profile/logs/<path:connection_id>', methods=['GET'])
@login_required
def get_profiler_logs(connection_id):
    """获取连接的采样任务日志"""
    # 获取该连接的所有任务
    tasks = db.fetch_all(
        'SELECT id, status, message, progress, created_at, updated_at FROM profiler_tasks WHERE connection_id = ? ORDER BY created_at DESC LIMIT 20',
        (connection_id,)
    )
    return jsonify({
        "tasks": tasks or [],
        "count": len(tasks) if tasks else 0,
    })


@app.route('/api/profile/logs/<path:connection_id>', methods=['DELETE'])
@login_required
def clear_profiler_logs(connection_id):
    """清除连接的采样日志记录（保留任务记录）"""
    try:
        # 只删除日志，保留任务记录（profiler_tasks）以便历史查询
        db.delete('profiler_logs', 'task_id IN (SELECT id FROM profiler_tasks WHERE connection_id = ?)', (connection_id,))
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _calc_progress(task):
    """根据任务状态和时间估算进度百分比"""
    if task['status'] == 'completed':
        return 100
    if task['status'] in ('failed', 'stopped'):
        return 0
    created = task.get('created_at', '')
    if not created:
        return 10
    try:
        t = datetime.strptime(created[:19], '%Y-%m-%d %H:%M:%S')
        elapsed = (datetime.now() - t).total_seconds()
        return min(90, max(5, int(elapsed / 2)))
    except:
        return 50


@app.route('/api/profile/tasks', methods=['GET'])
@login_required
def list_profiler_tasks():
    """获取性能分析任务列表"""
    conn_id = request.args.get('conn_id', '')
    
    # 尝试从数据库获取，表不存在时返回空列表
    try:
        sql = '''SELECT pt.*, u.username 
                 FROM profiler_tasks pt 
                 LEFT JOIN users u ON pt.user_id = u.id 
                 WHERE 1=1'''
        params = []
        
        if conn_id:
            sql += ' AND pt.connection_id = ?'
            params.append(conn_id)
        
        # 非管理员只看到自己的任务
        if current_user.is_authenticated and not current_user.is_admin:
            sql += ' AND pt.user_id = ?'
            params.append(current_user.id)
        
        sql += ' ORDER BY pt.created_at DESC LIMIT 50'
        
        raw_tasks = db.fetch_all(sql, tuple(params))
    except Exception:
        raw_tasks = []
    
    # 格式化输出，兼容前端期望的格式
    tasks = []
    for t in (raw_tasks or []):
        # 检查是否有输出文件
        output_path = t.get('output_path', '')
        has_file = bool(output_path) and Path(output_path).exists() if output_path else False
        file_name = Path(output_path).name if has_file else ''
        
        tasks.append({
            'id': t.get('id', ''),
            'status': t.get('status', 'pending'),
            'progress': t.get('progress', 0),
            'message': t.get('message', ''),
            'created_at': t.get('created_at', ''),
            'updated_at': t.get('updated_at', ''),
            'has_file': has_file,
            'file_name': file_name,
            'username': t.get('username', '-'),
            # 兼容前端 config 格式
            'config': {
                'cluster': t.get('cluster_name', ''),
                'namespace': t.get('namespace', ''),
                'pod': t.get('pod_name', ''),
                'mode': t.get('mode', t.get('type', 'profiler')),
                'type': t.get('type', 'profiler'),
                'event': t.get('event', ''),
                'duration': t.get('duration', 60),
                'format': t.get('format', 'html'),
            }
        })
    
    return jsonify(tasks)


@app.route('/api/profile/tasks/<task_id>', methods=['GET'])
@login_required
def get_profiler_task(task_id: str):
    """获取任务详情"""
    task = db.fetch_one('SELECT * FROM profiler_tasks WHERE id = ?', (task_id,))
    if not task:
        return jsonify({"error": "任务不存在"}), 404
    
    # 检查权限
    if not current_user.is_admin and task.get('user_id') != current_user.id:
        return jsonify({"error": "无权限"}), 403
    
    # 格式化输出
    result = dict(task)
    result['config'] = {
        'cluster': task.get('cluster_name', ''),
        'namespace': task.get('namespace', ''),
        'pod': task.get('pod_name', ''),
        'mode': task.get('mode', task.get('type', 'profiler')),
        'type': task.get('type', 'profiler'),
        'event': task.get('event', ''),
        'duration': task.get('duration', 60),
        'format': task.get('format', 'html'),
    }
    
    return jsonify({"task": result})


@app.route('/api/profile', methods=['GET'])
@login_required
def list_profiles():
    """获取采样任务列表（兼容旧接口）"""
    return list_profiler_tasks()


@app.route('/api/profile/<task_id>/cancel', methods=['POST'])
@login_required
def cancel_profiler_task(task_id: str):
    """取消采样任务"""
    task = db.fetch_one('SELECT * FROM profiler_tasks WHERE id = ?', (task_id,))
    if not task:
        return jsonify({"error": "任务不存在"}), 404
    
    if task['status'] not in ('running', 'pending'):
        return jsonify({"ok": False, "msg": f"当前状态 {task['status']}，无法取消"})
    
    db.update('profiler_tasks', {'status': 'cancelled', 'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')},
             'id = ?', (task_id,))
    return jsonify({"ok": True, "status": "cancelled"})


@app.route('/api/profile/<task_id>/download', methods=['GET'])
@login_required
def download_profiler_result(task_id: str):
    """下载采样结果文件"""
    task = db.fetch_one('SELECT * FROM profiler_tasks WHERE id = ?', (task_id,))
    if not task:
        return jsonify({"error": "任务不存在"}), 404
    
    # 非管理员检查任务归属
    if not current_user.is_admin and task.get('user_id') != current_user.id:
        return jsonify({"error": "无权限"}), 403
    
    if task['status'] != 'completed':
        return jsonify({"error": "任务未完成"}), 400
    
    # 从 output_path 字段获取文件路径
    output_path = task.get('output_path', '')
    if output_path and Path(output_path).exists():
        return send_file(str(output_path), as_attachment=True, download_name=Path(output_path).name)
    
    # output_path 为空或文件不存在，尝试多种方式查找
    # 1. 按 task_id 匹配文件名
    for f in OUTPUT_DIR.glob(f"*{task_id}*"):
        if f.is_file():
            return send_file(str(f), as_attachment=True, download_name=f.name)
    
    # 2. 按 pod_name + mode + 创建时间匹配
    pod_name = task.get('pod_name', '')
    mode = task.get('mode', 'profiler')
    created_at = task.get('created_at', '')
    
    if pod_name and created_at:
        # 根据 mode 确定扩展名
        ext_map = {'jfr': 'jfr', 'heapdump': 'hprof', 'threaddump': 'html'}
        ext = ext_map.get(mode, 'html')
        
        # 从创建时间提取时间段（前后 5 分钟）
        try:
            task_time = datetime.strptime(created_at[:19], '%Y-%m-%d %H:%M:%S')
            from datetime import timedelta
            time_min = task_time - timedelta(minutes=5)
            time_max = task_time + timedelta(minutes=10)
        except Exception:
            time_min = time_max = None
        
        candidates = []
        for f in OUTPUT_DIR.glob(f"*.{ext}"):
            if f.is_file() and pod_name in f.name:
                if time_min and time_max:
                    mtime = datetime.fromtimestamp(f.stat().st_mtime)
                    if time_min <= mtime <= time_max:
                        candidates.append(f)
                else:
                    candidates.append(f)
        
        # 选最新的候选文件
        if candidates:
            candidates.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            best = candidates[0]
            # 更新数据库中的 output_path
            db.update('profiler_tasks', {'output_path': str(best)}, 'id = ?', (task_id,))
            return send_file(str(best), as_attachment=True, download_name=best.name)
    
    return jsonify({"error": "采样结果文件不存在，可能文件已被清理或下载失败"}), 404


# ═══════════════════════════════════════════════════════════════════════════════
# Pod 监控
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/api/monitor/snapshot', methods=['POST'])
@login_required
def pod_snapshot():
    """获取 Pod 快照"""
    d = request.json or {}
    runner, err = _make_runner(d.get('cluster_name', ''))
    if err:
        return jsonify({"error": err}), 400
    
    ns = d.get('namespace', 'default')
    pod = d.get('pod_name', '')
    container = d.get('container', '')
    
    try:
        result = collect_pod_snapshot(runner, ns, pod, container)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Pod 指标采集（monitor.js 组件使用）───
@app.route('/api/monitor/pod', methods=['POST'])
@login_required
def monitor_pod():
    """获取 Pod 实时指标（CPU/内存/网络/进程列表）"""
    d = request.json or {}
    cluster = d.get('cluster', '')
    ns = d.get('namespace', 'default')
    pod = d.get('pod', '')
    
    if not cluster or not pod:
        return jsonify({"error": "参数不全"}), 400
    
    # 使用已有的快照接口逻辑
    runner, err = _make_runner(cluster)
    if err:
        return jsonify({"error": err}), 400
    auth_err, auth_code = AuthorizationService.require_namespace_access(current_user, cluster, ns)
    if auth_err:
        return jsonify(auth_err), auth_code
    
    container = d.get('container', '')
    try:
        result = collect_pod_snapshot(runner, ns, pod, container)
        return jsonify({"metrics": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/monitor/logs', methods=['POST'])
@login_required
def get_pod_logs():
    """获取容器日志（kubectl logs）"""
    d = request.json or {}
    cluster_name = d.get('cluster_name', '')
    namespace = d.get('namespace', 'default')
    pod_name = d.get('pod_name', '')
    container = d.get('container', '')
    tail = int(d.get('tail', 100))
    since = d.get('since', '')
    
    runner, err = _make_runner(cluster_name)
    if err:
        return jsonify({"error": err}), 400
    auth_err, auth_code = AuthorizationService.require_namespace_access(current_user, cluster_name, namespace)
    if auth_err:
        return jsonify(auth_err), auth_code
    
    try:
        logs_text = runner.get_logs(namespace, pod_name, tail=tail, container=container, since=since)
        
        # 返回原始字符串，前端负责渲染
        return jsonify({
            "logs": logs_text or '',
            "count": len(logs_text.strip().split('\n')) if logs_text else 0,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/monitor/metrics', methods=['GET'])
@login_required
def get_metrics():
    """获取实时指标"""
    cluster = request.args.get('cluster', '')
    ns = request.args.get('namespace', '')
    pod = request.args.get('pod', '')
    
    if not all([cluster, ns, pod]):
        return jsonify({"error": "参数不全"}), 400
    
    history = get_metrics_history(cluster, ns, pod)
    return jsonify({"metrics": history})


@app.route('/api/monitor/start-polling', methods=['POST'])
@login_required
def start_polling():
    """启动指标轮询"""
    d = request.json or {}
    runner, err = _make_runner(d.get('cluster_name', ''))
    if err:
        return jsonify({"error": err}), 400
    
    ns = d.get('namespace', 'default')
    pod = d.get('pod_name', '')
    container = d.get('container', '')
    
    start_metrics_polling(runner, d.get('cluster_name', ''), ns, pod, container)
    return jsonify({"ok": True})


@app.route('/api/monitor/stop-polling', methods=['POST'])
@login_required
def stop_polling():
    """停止指标轮询"""
    d = request.json or {}
    stop_metrics_polling(d.get('cluster', ''), d.get('namespace', ''), d.get('pod', ''))
    return jsonify({"ok": True})


@app.route('/api/monitor/history', methods=['POST'])
@login_required
def monitor_history():
    """获取指标历史"""
    d = request.json or {}
    cluster = d.get('cluster_name', '')
    ns = d.get('namespace', 'default')
    pod = d.get('pod_name', '')
    
    if not all([cluster, ns, pod]):
        return jsonify({"error": "参数不全"}), 400
    
    history = get_metrics_history(cluster, ns, pod)
    return jsonify(history or {})


@app.route('/api/monitor/logs/download', methods=['POST'])
@login_required
def download_container_logs():
    """下载容器日志文件"""
    d = request.json or {}
    cluster_name = d.get('cluster_name', '')
    namespace = d.get('namespace', 'default')
    pod_name = d.get('pod_name', '')
    container = d.get('container', '')
    tail = int(d.get('tail', 5000))
    since = d.get('since', '')
    
    runner, err = _make_runner(cluster_name)
    if err:
        return jsonify({"error": err}), 400
    
    try:
        logs_text = runner.get_logs(namespace, pod_name, tail=tail, container=container, since=since)
        
        # 创建临时文件
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"logs_{pod_name}_{container or 'default'}_{ts}.log"
        tmp = Path(tempfile.mkdtemp()) / fname
        tmp.write_text(logs_text or '', encoding='utf-8')
        
        return send_file(str(tmp), as_attachment=True, download_name=fname,
                        mimetype="text/plain; charset=utf-8")
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/monitor/events', methods=['POST'])
@login_required
def monitor_events():
    """获取 Pod 事件"""
    d = request.json or {}
    cluster_name = d.get('cluster_name', '')
    namespace = d.get('namespace', 'default')
    pod_name = d.get('pod_name', '')
    
    runner, err = _make_runner(cluster_name)
    if err:
        return jsonify({"error": err}), 400
    
    try:
        events = runner.get_events(namespace, pod_name)
        return jsonify({"events": events})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ═══════════════════════════════════════════════════════════════════════════════
# GC 日志
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/api/gc/info', methods=['POST'])
@login_required
def gc_info():
    """探测 JVM GC 日志配置"""
    d = request.json or {}
    runner, err = _make_runner(d.get('cluster_name', ''))
    if err:
        return jsonify({"error": err}), 400
    
    ns = d.get('namespace', 'default')
    pod = d.get('pod_name', '')
    ctr = d.get('container', '')
    
    if not pod:
        return jsonify({"error": "pod_name 必填"}), 400
    
    # 找 Java PID
    rc, jps_out, _ = runner.exec_pod(ns, pod, ctr,
        "jps -l 2>/dev/null || ps -ef 2>/dev/null | grep java | grep -v grep",
        timeout=8)
    
    pid = None
    skip = {"arthas", "jps", "sun.tools.jps"}
    if rc == 0:
        for line in jps_out.strip().splitlines():
            parts = line.strip().split(None, 1)
            if len(parts) >= 1 and parts[0].isdigit():
                desc = (parts[1] if len(parts) > 1 else "").lower()
                if not any(k in desc for k in skip):
                    pid = parts[0]
                    break
    
    if not pid:
        return jsonify({"error": "未找到 Java 进程", "gc_flags": [], "log_paths": []}), 400
    
    # 读取 /proc/PID/cmdline
    _, cmdline, _ = runner.exec_pod(ns, pod, ctr,
        f"cat /proc/{pid}/cmdline 2>/dev/null | tr '\\0' ' '",
        timeout=5)
    
    # 解析 GC 日志参数
    import re as _re
    gc_flags = []
    log_paths = []
    stdout_gc = False
    
    patterns = [
        (r'(-Xloggc:(\S+))', 2),
        (r'(-Xlog:[^:]*:file=([^:,\s]+))', 2),
        (r'(-Xlog:[^:]*:(stdout|stderr))', 2),
        (r'(-XX:\+Print\w*GC\w*)', None),
        (r'(-verbose:gc)', None),
    ]
    
    for pattern, path_grp in patterns:
        for m in _re.finditer(pattern, cmdline):
            gc_flags.append(m.group(1).strip())
            if path_grp:
                val = m.group(path_grp)
                if val in ('stdout', 'stderr'):
                    stdout_gc = True
                elif '/' in val:
                    log_paths.append(val.strip())
    
    # 扫描常见路径
    if not log_paths and not stdout_gc:
        scan_patterns = [
            '/app/logs/gc*.log', '/app/logs/gc.log',
            '/logs/gc*.log', '/var/log/gc.log',
            '/tmp/gc*.log', '/home/admin/logs/gc.log',
        ]
        for p in scan_patterns:
            rc2, out2, _ = runner.exec_pod(ns, pod, ctr,
                f"ls {p} 2>/dev/null | head -3", timeout=5)
            if rc2 == 0 and out2.strip():
                log_paths.extend(out2.strip().splitlines())
                break
    
    # 读取日志内容
    log_content = ""
    log_path_used = ""
    
    if stdout_gc:
        log_content = "GC 输出到 stdout，请使用「Pod 监控 → 日志」标签查看容器日志"
        log_path_used = "stdout"
    elif log_paths:
        log_path_used = log_paths[0]
        rc3, content_out, _ = runner.exec_pod(ns, pod, ctr,
            f"tail -500 '{log_path_used}' 2>/dev/null || echo '__FILE_NOT_FOUND__'",
            timeout=15)
        if rc3 == 0 and "__FILE_NOT_FOUND__" not in content_out:
            log_content = content_out
        else:
            log_content = f"文件不可读: {log_path_used}"
    
    gc_enabled = bool(gc_flags or log_paths or stdout_gc)
    
    return jsonify({
        "pid": pid,
        "gc_flags": gc_flags,
        "log_paths": log_paths,
        "log_path_used": log_path_used,
        "stdout_gc": stdout_gc,
        "gc_enabled": gc_enabled,
        "log_content": log_content,
        "cmdline_snippet": cmdline.strip()[:500],
        "hint": "" if gc_enabled else (
            "未检测到 GC 日志配置。\n"
            "JDK 8  启用: -Xloggc:/app/logs/gc.log -XX:+PrintGCDetails -XX:+PrintGCDateStamps\n"
            "JDK 9+ 启用: -Xlog:gc*:file=/app/logs/gc.log:time,tags"
        ),
    })


@app.route('/api/gc/download', methods=['POST'])
@login_required
def gc_download():
    """下载 GC 日志文件"""
    d = request.json or {}
    runner, err = _make_runner(d.get('cluster_name', ''))
    if err:
        return jsonify({"error": err}), 400
    
    log_path = d.get('log_path', '')
    if not log_path:
        return jsonify({"error": "log_path 必填"}), 400
    
    namespace = d.get('namespace', 'default')
    pod_name = d.get('pod_name', '')
    container = d.get('container', '')
    
    filename = os.path.basename(log_path)
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    pod_name_safe = pod_name[:40] if pod_name else "pod"
    local_name = f"gc-{pod_name_safe}-{ts}{Path(filename).suffix or '.log'}"
    tmp_dir = Path(tempfile.mkdtemp(prefix="gc_dl_"))
    local_path = str(tmp_dir / local_name)
    
    rc, out, err2 = runner.cp_from_pod(namespace, pod_name, container, log_path, local_path)
    if rc != 0 or not os.path.exists(local_path):
        shutil.rmtree(str(tmp_dir), ignore_errors=True)
        return jsonify({"error": f"下载失败: {err2 or out}"}), 500
    
    resp = send_file(local_path, as_attachment=True, download_name=local_name,
                    mimetype="text/plain; charset=utf-8")
    resp.call_on_close(lambda: shutil.rmtree(str(tmp_dir), ignore_errors=True))
    return resp


# ═══════════════════════════════════════════════════════════════════════════════
# Pod 文件操作
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/api/pod/files', methods=['POST'])
@login_required
def list_pod_files():
    """列出 Pod 内文件"""
    d = request.json or {}
    runner, err = _make_runner(d.get('cluster_name', ''))
    if err:
        return jsonify({"error": err}), 400
    
    ns = d.get('namespace', 'default')
    pod = d.get('pod_name', '')
    container = d.get('container', '')
    path = d.get('path', '/')
    
    rc, out, err = runner.exec_pod(ns, pod, container, f"ls -la {shlex.quote(path)} 2>/dev/null", timeout=10)
    
    if rc != 0:
        return jsonify({"error": err or "无法列出文件"}), 400
    
    files = []
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 9:
            name = parts[-1]
            mode = parts[0]
            is_dir = mode.startswith('d')
            files.append({
                "name": name,
                "path": f"{path.rstrip('/')}/{name}",
                "is_dir": is_dir,
                "mode": mode,
                "size": parts[4],
                "modified": " ".join(parts[5:8])
            })
    
    return jsonify({"files": files, "path": path})


@app.route('/api/pod/files/read', methods=['POST'])
@login_required
def read_pod_file():
    """读取 Pod 内文件内容"""
    d = request.json or {}
    runner, err = _make_runner(d.get('cluster_name', ''))
    if err:
        return jsonify({"error": err}), 400
    
    ns = d.get('namespace', 'default')
    pod = d.get('pod_name', '')
    container = d.get('container', '')
    path = d.get('path', '')
    
    if not path:
        return jsonify({"error": "path 必填"}), 400
    
    rc, out, err = runner.exec_pod(ns, pod, container, f"cat {shlex.quote(path)}", timeout=30)
    
    if rc != 0:
        return jsonify({"error": err or "读取失败"}), 400
    
    return jsonify({"content": out})


@app.route('/api/pod/files/download', methods=['POST'])
@login_required
def download_pod_file():
    """从 Pod 下载文件"""
    d = request.json or {}
    runner, err = _make_runner(d.get('cluster_name', ''))
    if err:
        return jsonify({"error": err}), 400
    
    ns = d.get('namespace', 'default')
    pod = d.get('pod_name', '')
    container = d.get('container', '')
    path = d.get('path', '')
    
    if not path:
        return jsonify({"error": "path 必填"}), 400
    
    # 复制到临时目录
    temp_dir = tempfile.mkdtemp()
    local_path = os.path.join(temp_dir, os.path.basename(path))
    
    try:
        rc, out, err = runner.cp_from_pod(ns, pod, container, path, local_path)
        
        if rc != 0:
            return jsonify({"error": err or "下载失败"}), 400
        
        # 记录审计日志
        from services.audit_service import AuditService
        AuditService.log_file_downloaded(current_user.id, os.path.basename(path))
        
        return send_file(local_path, as_attachment=True)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.route('/api/pod/files/tail', methods=['POST'])
@login_required
def tail_pod_file():
    """Tail Pod 内文件"""
    d = request.json or {}
    runner, err = _make_runner(d.get('cluster_name', ''))
    if err:
        return jsonify({"error": err, "content": ""}), 400
    
    ns = d.get('namespace', 'default')
    pod = d.get('pod_name', '')
    container = d.get('container', '')
    path = d.get('path', '')
    lines = int(d.get('lines', 200))
    
    if not path:
        return jsonify({"error": "path 必填", "content": ""}), 400
    
    rc, out, err2 = runner.exec_pod(
        ns, pod, container,
        f"tail -n {lines} {shlex.quote(path)} 2>&1", timeout=10
    )
    
    if rc != 0:
        return jsonify({"error": out or err2, "content": ""})
    
    return jsonify({"content": out, "path": path})


# ═══════════════════════════════════════════════════════════════════════════════
# Pod 命令执行
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/api/pod/exec', methods=['POST'])
@login_required
def pod_exec():
    """在 Pod 内执行命令"""
    d = request.json or {}
    runner, err = _make_runner(d.get('cluster_name', ''))
    if err:
        return jsonify({"error": err, "stdout": "", "stderr": "", "rc": -1}), 400
    
    ns = d.get('namespace', 'default')
    pod = d.get('pod_name', '')
    container = d.get('container', '')
    command = d.get('command', '').strip()
    cwd = d.get('cwd', '').strip()
    timeout = min(int(d.get('timeout', 30)), 60)
    
    if not pod or not command:
        return jsonify({"error": "pod_name 和 command 必填", "stdout": "", "stderr": "", "rc": -1}), 400
    
    # 危险命令检测：阻止明显的破坏性操作
    _DANGEROUS_PATTERNS = re.compile(
        r'(?:;\s*(?:rm\s|mkfs\b|dd\s+if=|chmod\s|chown\s|shutdown\b|reboot\b|init\s+[06])'
        r'|`[^`]*`|\$\([^)]*\)|\|\s*(?:rm\s|mkfs\b|dd\s+if=|shutdown\b|reboot\b)'
        r'|&&\s*(?:rm\s|mkfs\b|dd\s+if=|chmod\s|chown\s|shutdown\b|reboot\b))',
        re.IGNORECASE
    )
    if _DANGEROUS_PATTERNS.search(command):
        return jsonify({"error": "命令包含不允许的危险操作", "stdout": "", "stderr": "", "rc": -1}), 400

    if cwd and cwd != "/":
        shell_cmd = f'cd {shlex.quote(cwd)} && ( {command} ); echo "__RC__=$?"'
    else:
        shell_cmd = f'( {command} ); echo "__RC__=$?"'
    
    rc_exec, raw_out, raw_err = runner.exec_pod(ns, pod, container, shell_cmd, timeout=timeout)
    
    rc_actual = rc_exec
    out_clean = raw_out
    if "__RC__=" in raw_out:
        lines = raw_out.rsplit("__RC__=", 1)
        out_clean = lines[0]
        try:
            rc_actual = int(lines[1].strip().splitlines()[0])
        except (ValueError, IndexError):
            pass
    
    return jsonify({
        "stdout": out_clean,
        "stderr": raw_err,
        "rc": rc_actual,
        "cwd": cwd,
    })


@app.route('/api/pod/exec/cwd', methods=['POST'])
@login_required
def pod_exec_cwd():
    """获取 Pod 内当前工作目录"""
    d = request.json
    runner, err = _make_runner(d.get('cluster_name', ''))
    if not runner:
        return jsonify({"cwd": "/", "hostname": "", "user": "root"}), 400
    
    ns, pod, ctr = d.get('namespace', 'default'), d.get('pod_name', ''), d.get('container', '')
    
    _, cwd, _ = runner.exec_pod(ns, pod, ctr, "pwd 2>/dev/null || echo /", timeout=5)
    _, host, _ = runner.exec_pod(ns, pod, ctr, "hostname 2>/dev/null || echo pod", timeout=5)
    _, user, _ = runner.exec_pod(ns, pod, ctr, "whoami 2>/dev/null || echo root", timeout=5)
    
    return jsonify({
        "cwd": cwd.strip() or "/",
        "hostname": host.strip() or pod,
        "user": user.strip() or "root",
    })


# ═══════════════════════════════════════════════════════════════════════════════
# 本地文件下载
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/api/files', methods=['GET'])
@login_required
def list_local_files():
    """列出本地输出文件（按用户隔离）"""
    # 获取当前用户有权限的任务输出文件，关联用户信息
    if current_user.is_admin:
        # 管理员看所有，并显示用户名
        task_files = db.fetch_all(
            '''SELECT pt.output_path, u.username 
               FROM profiler_tasks pt 
               LEFT JOIN users u ON pt.user_id = u.id 
               WHERE pt.output_path IS NOT NULL AND pt.output_path != ""'''
        )
    else:
        # 普通用户只看自己的
        task_files = db.fetch_all(
            '''SELECT pt.output_path, u.username 
               FROM profiler_tasks pt 
               LEFT JOIN users u ON pt.user_id = u.id 
               WHERE pt.user_id = ? AND pt.output_path IS NOT NULL AND pt.output_path != ""''',
            (current_user.id,)
        )
    
    # 构建文件名 -> 用户名 映射
    file_users = {}
    allowed_files = set()
    for t in (task_files or []):
        op = t.get('output_path', '')
        if op:
            fname = Path(op).name
            allowed_files.add(fname)
            file_users[fname] = t.get('username', '-')
    
    files = []
    for f in sorted(OUTPUT_DIR.glob("*"), key=lambda x: x.stat().st_mtime, reverse=True):
        if f.is_file() and f.name in allowed_files:
            files.append({
                "name": f.name,
                "size": f.stat().st_size,
                "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                "username": file_users.get(f.name, '-'),  # 添加用户名
            })
    return jsonify(files)


@app.route('/api/files/<path:filename>', methods=['GET'])
@login_required
def download_local_file(filename: str):
    """下载本地输出文件（按用户隔离）"""
    p = OUTPUT_DIR / filename
    if not p.exists():
        return jsonify({"error": "不存在"}), 404
    
    # 非管理员检查文件归属
    if not current_user.is_admin:
        task = db.fetch_one(
            'SELECT id FROM profiler_tasks WHERE user_id = ? AND output_path LIKE ? LIMIT 1',
            (current_user.id, f'%{filename}')
        )
        if not task:
            return jsonify({"error": "无权限"}), 403
    
    # 记录审计日志
    from services.audit_service import AuditService
    AuditService.log_file_downloaded(current_user.id, filename)
    
    return send_file(str(p), as_attachment=True, download_name=filename)


# ═══════════════════════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="K8s Arthas Tool Server")
    parser.add_argument("--port", type=int, default=Config.DEFAULT_PORT)
    parser.add_argument("--host", default=Config.DEFAULT_HOST)
    args = parser.parse_args()
    
    # 初始化数据库
    db.initialize()
    # 从 clusters.json 同步到数据库（仅补充缺失的记录）
    _sync_clusters_to_db()
    # 校验生产环境安全配置
    Config.validate_production()
    print(f"🚀  K8s Arthas Tool v2026.03.23  →  http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=True, request_handler=_TimedRequestHandler)