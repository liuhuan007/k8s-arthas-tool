#!/usr/bin/env python3
"""
K8s Arthas Tool — Flask API Server
REST endpoints:
  /api/health
  /api/clusters          CRUD + test + namespaces/pods/contexts
  /api/check             Pod liveness + Java PID detection
  /api/arthas/*          Connect / disconnect / exec / session
  /api/profile/*         JProfiler async task management
  /api/monitor/*         Pod snapshot / metrics polling / logs / events
  /api/pod/files/*       Pod file browser + download
  /api/files/*           Local output file download
"""
import json, os, threading, uuid, time, tempfile, shutil, shlex, sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

from profiler_backend import (
    ClusterConfig, PodTarget, KubectlExecutor,
    ArthasAgentManager, ArthasConnection, ProfilerWorkflow,
    ARTHAS_DEFAULT_JAR,
)
from pod_monitor import (
    KubectlRunner, collect_pod_snapshot,
    get_metrics_history, start_metrics_polling, stop_metrics_polling,
)

# ─────────────────────────────────────────────────────────────────────────────
SERVER_VERSION = "2026.03.23"  # 部署版本标识

app = Flask(__name__,
    static_folder='static',
    static_url_path='/static',
)
CORS(app)

@app.errorhandler(Exception)
def handle_exception(e):
    """全局异常处理 - 确保任何未捕获异常都返回 JSON 而不是关闭连接"""
    import traceback
    traceback.print_exc()
    return jsonify({"error": str(e), "type": type(e).__name__}), 500

# ── 路径初始化（基于 server.py 文件位置，不依赖启动时工作目录）─────────────────
_BASE_DIR     = Path(__file__).parent
OUTPUT_DIR    = _BASE_DIR / "profiler_output"
CLUSTERS_FILE = _BASE_DIR / "clusters.json"
DB_FILE       = _BASE_DIR / "arthas.db"
OUTPUT_DIR.mkdir(exist_ok=True)

# ── 前端静态文件服务（K8s / Docker 部署时通过 HTTP 访问）──────────────────────
@app.get('/')
@app.get('/index.html')
def serve_index():
    return send_file(str(_BASE_DIR / 'index.html'))

@app.get('/login.html')
def serve_login():
    return send_file(str(_BASE_DIR / 'login.html'))

# ── In-memory state ───────────────────────────────────────────────────────────
_clusters:    dict[str, ClusterConfig]  = {}
_connections: dict[str, ArthasConnection] = {}   # "{cluster}/{ns}/{pod}" → conn
_tasks:       dict[str, dict]           = {}     # task_id → task dict
_lock = threading.Lock()


# ═════════════════════════════════════════════════════════════════════════════
# Database - SQLite
# ═════════════════════════════════════════════════════════════════════════════

def _init_db():
    """初始化 SQLite 数据库"""
    conn = sqlite3.connect(str(DB_FILE))
    cursor = conn.cursor()

    # 连接记录表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS connections (
            id TEXT PRIMARY KEY,
            cluster_name TEXT NOT NULL,
            namespace TEXT NOT NULL,
            pod_name TEXT NOT NULL,
            local_port INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Arthas 命令历史表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS arthas_commands (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            connection_id TEXT NOT NULL,
            command TEXT NOT NULL,
            output TEXT,
            error TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (connection_id) REFERENCES connections(id) ON DELETE CASCADE
        )
    ''')

    # 采样任务历史表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS profiler_tasks (
            id TEXT PRIMARY KEY,
            connection_id TEXT NOT NULL,
            mode TEXT NOT NULL,
            event TEXT,
            duration INTEGER,
            status TEXT,
            output_path TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (connection_id) REFERENCES connections(id) ON DELETE CASCADE
        )
    ''')

    # 采样日志表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS profiler_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            connection_id TEXT NOT NULL,
            message TEXT NOT NULL,
            level TEXT DEFAULT 'info',
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (connection_id) REFERENCES connections(id) ON DELETE CASCADE
        )
    ''')

    conn.commit()
    conn.close()

def _get_db():
    """获取数据库连接"""
    conn = sqlite3.connect(str(DB_FILE), timeout=10)
    conn.row_factory = sqlite3.Row  # 返回字典格式
    return conn

def _save_connection(conn_id: str, cluster_name: str, namespace: str, pod_name: str, local_port: int):
    """保存或更新连接记录"""
    conn = _get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO connections (id, cluster_name, namespace, pod_name, local_port, updated_at)
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    ''', (conn_id, cluster_name, namespace, pod_name, local_port))
    conn.commit()
    conn.close()

def _get_connection(conn_id: str) -> Optional[dict]:
    """获取连接信息"""
    conn = _get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM connections WHERE id = ?', (conn_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def _save_arthas_command(conn_id: str, command: str, output: str = None, error: str = None):
    """保存 Arthas 命令历史"""
    conn = _get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO arthas_commands (connection_id, command, output, error)
        VALUES (?, ?, ?, ?)
    ''', (conn_id, command, output, error))
    conn.commit()
    conn.close()

def _get_arthas_commands(conn_id: str, limit: int = 100) -> List[dict]:
    """获取连接的命令历史"""
    conn = _get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT command, output, error, timestamp
        FROM arthas_commands
        WHERE connection_id = ?
        ORDER BY timestamp DESC
        LIMIT ?
    ''', (conn_id, limit))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def _save_profiler_log(conn_id: str, message: str, level: str = 'info'):
    """保存采样日志"""
    conn = _get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO profiler_logs (connection_id, message, level)
        VALUES (?, ?, ?)
    ''', (conn_id, message, level))
    conn.commit()
    conn.close()

def _get_profiler_logs(conn_id: str, limit: int = 1000) -> List[dict]:
    """获取连接的采样日志"""
    conn = _get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, message, level, timestamp
        FROM profiler_logs
        WHERE connection_id = ?
        ORDER BY timestamp ASC
        LIMIT ?
    ''', (conn_id, limit))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def _clear_profiler_logs(conn_id: str):
    """清空连接的采样日志"""
    conn = _get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM profiler_logs WHERE connection_id = ?', (conn_id,))
    conn.commit()
    conn.close()

# ═════════════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════════════

def _conn_key(cluster: str, ns: str, pod: str) -> str:
    return f"{cluster}/{ns}/{pod}"

def _load_clusters():
    if CLUSTERS_FILE.exists():
        try:
            for item in json.loads(CLUSTERS_FILE.read_text(encoding='utf-8')):
                c = ClusterConfig(**item)
                # 清理旧版本遗留的 __tmp__ 临时集群记录
                if c.name == '__tmp__':
                    continue
                _clusters[c.name] = c
        except Exception:
            pass

def _save_clusters():
    """Save clusters config - atomic write to avoid corruption on Linux."""
    data = [{"name": c.name, "kubeconfig": c.kubeconfig, "context": c.context}
            for c in _clusters.values()]
    content_str = json.dumps(data, ensure_ascii=False, indent=2)
    # Atomic write: write to temp file then rename (safe on Linux)
    tmp = CLUSTERS_FILE.with_suffix('.tmp')
    tmp.write_text(content_str, encoding='utf-8')
    tmp.replace(CLUSTERS_FILE)

def _make_executor(cluster_name: str):
    """Return (KubectlExecutor, error_str)"""
    c = _clusters.get(cluster_name)
    if not c:
        return None, f"集群 '{cluster_name}' 不存在"
    return KubectlExecutor(c.kubeconfig, c.context), ""

def _make_runner(cluster_name: str):
    """Return (KubectlRunner, error_str) — used by pod_monitor"""
    c = _clusters.get(cluster_name)
    if not c:
        return None, f"集群 '{cluster_name}' 不存在"
    return KubectlRunner(c.kubeconfig, c.context), ""

def _get_or_create_connection(d: dict):
    """Parse request body → return (ArthasConnection, error_str)"""
    cluster_name = d.get("cluster_name", "")
    c = _clusters.get(cluster_name)
    if not c:
        return None, f"集群 '{cluster_name}' 不存在"
    ns  = d.get("namespace", "default")
    pod = d.get("pod_name", "")
    if not pod:
        return None, "pod_name 必填"

    key = _conn_key(cluster_name, ns, pod)
    with _lock:
        if key not in _connections:
            target = PodTarget(
                cluster_name = cluster_name,
                namespace    = ns,
                pod_name     = pod,
                container    = d.get("container", ""),
                arthas_jar   = d.get("arthas_jar", ARTHAS_DEFAULT_JAR),
                arthas_http_port   = int(d.get("arthas_http_port", 8563)),
                arthas_telnet_port = int(d.get("arthas_telnet_port", 3658)),
            )
            executor = KubectlExecutor(c.kubeconfig, c.context)
            _connections[key] = ArthasConnection(executor, target)
    return _connections[key], ""

_load_clusters()


# ═════════════════════════════════════════════════════════════════════════════
# Health
# ═════════════════════════════════════════════════════════════════════════════

@app.get("/api/health")
def health():
    return jsonify({
        "ok": True,
        "version": globals().get("SERVER_VERSION", "unknown"),
        "time": datetime.now().isoformat(),
        "clusters": list(_clusters.keys()),
        "clusters_file": str(CLUSTERS_FILE),
    })

@app.post("/api/debug/put_test")
def debug_put_test():
    """调试接口：测试 PUT 请求体解析，帮助排查 ERR_EMPTY_RESPONSE"""
    try:
        raw = request.get_data(as_text=False)
        d = json.loads(raw.decode("utf-8")) if raw else {}
        return jsonify({"ok": True, "received": d, "raw_len": len(raw)})
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ═════════════════════════════════════════════════════════════════════════════
# Cluster management
# ═════════════════════════════════════════════════════════════════════════════

@app.get("/api/clusters")
def list_clusters():
    return jsonify([
        {"name": c.name, "kubeconfig": c.kubeconfig, "context": c.context}
        for c in _clusters.values()
    ])

@app.post("/api/clusters")
def add_cluster():
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        # 优先使用 request.get_json()，它不会消费请求流
        d = {}
        try:
            d = request.get_json(force=True, silent=True) or {}
            logger.info(f"[add_cluster] parsed JSON: {d}")
        except Exception as e:
            logger.error(f"[add_cluster] JSON parse error: {e}")
            raw = request.get_data(as_text=False)
            if raw:
                d = json.loads(raw.decode("utf-8"))
        
        name = str(d.get("name", "")).strip()
        kc   = str(d.get("kubeconfig", "")).strip()
        ctx  = str(d.get("context", "")).strip()
        logger.info(f"[add_cluster] name={name}, kc={kc}, ctx={ctx}")
        if not name or not kc:
            return jsonify({"error": "name 和 kubeconfig 必填"}), 400
        if not os.path.exists(kc):
            # 提供更详细的错误信息
            import platform
            system = platform.system()
            hint = ""
            if system == "Linux" and (kc.startswith("C:") or kc.startswith("D:") or "\\" in kc):
                hint = " (看起来是 Windows 路径，请使用 Linux 路径如 /root/.kube/config)"
            elif system == "Windows" and kc.startswith("/"):
                hint = " (看起来是 Linux 路径，请使用 Windows 路径如 C:\\Users\\...)"
            return jsonify({"error": f"kubeconfig 文件不存在: {kc}{hint}"}), 400
        _clusters[name] = ClusterConfig(name=name, kubeconfig=kc, context=ctx)
        if name != '__tmp__':
            _save_clusters()
        return jsonify({"ok": True})
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": f"添加失败: {str(e)}"}), 500

@app.get("/api/clusters/<path:name>")
def get_cluster(name: str):
    """获取单个集群详情"""
    # Flask 3.x 会自动解码 path 参数，不需要再调用 unquote
    c = _clusters.get(name)
    if not c:
        return jsonify({"error": f"集群 '{name}' 不存在"}), 404
    return jsonify({"name": c.name, "kubeconfig": c.kubeconfig, "context": c.context})

@app.route("/api/clusters/<path:name>", methods=["PUT", "POST"])
def update_cluster(name: str):
    """Update cluster config (context switch, rename, etc.)
    同时支持 PUT 和 POST，避免某些代理/防火墙拦截 PUT 请求
    """
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(f"[update_cluster] method={request.method}, URL name={name}, repr={repr(name)}")
    logger.info(f"[update_cluster] _clusters keys={[repr(k) for k in _clusters.keys()]}")
    logger.info(f"[update_cluster] request headers: {dict(request.headers)}")
    
    try:
        # 解析请求体
        d = request.get_json(force=True, silent=True) or {}
        logger.info(f"[update_cluster] request JSON: {d}")
        
        if not d:
            return jsonify({"error": "请求体为空"}), 400

        # 查找集群 - 尝试多种匹配方式
        old = _clusters.get(name)
        
        # 如果没找到，尝试其他方式匹配
        if not old:
            for key in _clusters.keys():
                if key.strip() == name.strip():
                    old = _clusters[key]
                    logger.info(f"[update_cluster] matched by strip: '{key}'")
                    break
        
        if not old:
            logger.error(f"[update_cluster] Cluster '{name}' not found")
            return jsonify({"error": f"集群 '{name}' 不存在", "available": list(_clusters.keys())}), 404

        new_name = str(d.get("name", old.name)).strip()
        new_kc   = str(d.get("kubeconfig", old.kubeconfig)).strip()
        new_ctx  = str(d.get("context",   old.context)).strip()

        if not new_name or not new_kc:
            return jsonify({"error": "名称和 kubeconfig 路径不能为空"}), 400

        # 检查 kubeconfig 文件是否存在（始终检查，避免 Windows 路径在 Linux 上导致问题）
        if not os.path.exists(new_kc):
            # 提供更详细的错误信息
            import platform
            system = platform.system()
            hint = ""
            if system == "Linux" and (new_kc.startswith("C:") or new_kc.startswith("D:") or "\\" in new_kc):
                hint = " (看起来是 Windows 路径，请使用 Linux 路径如 /root/.kube/config)"
            elif system == "Windows" and new_kc.startswith("/"):
                hint = " (看起来是 Linux 路径，请使用 Windows 路径如 C:\\Users\\...)"
            return jsonify({"error": f"kubeconfig 文件不存在: {new_kc}{hint}"}), 400

        if new_name != name:
            _clusters.pop(name, None)
        _clusters[new_name] = ClusterConfig(name=new_name, kubeconfig=new_kc, context=new_ctx)
        _save_clusters()
        return jsonify({"ok": True, "name": new_name})
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": f"保存失败: {str(e)}"}), 500

@app.route("/api/clusters/<path:name>", methods=["DELETE"])
def del_cluster(name: str):
    # Flask 3.x 会自动解码 path 参数
    try:
        _clusters.pop(name, None)
        _save_clusters()
        return jsonify({"ok": True})
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.post("/api/clusters/<path:name>/test")
def test_cluster(name: str):
    # Flask 3.x 会自动解码 path 参数
    try:
        ex, err = _make_executor(name)
        if not ex:
            return jsonify({"ok": False, "error": err}), 404
        ok, info    = ex.cluster_info()
        contexts    = ex.get_contexts()
        current_ctx = ex.get_current_context()
        return jsonify({
            "ok": ok, "info": info,
            "contexts": contexts,
            "current_context": current_ctx,
        })
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)}), 500

@app.get("/api/clusters/<path:name>/namespaces")
def get_namespaces(name: str):
    # Flask 3.x 会自动解码 path 参数
    ex, err = _make_executor(name)
    if not ex:
        return jsonify({"namespaces": [], "error": err})
    return jsonify({"namespaces": ex.get_namespaces()})

@app.get("/api/clusters/<path:name>/pods")
def get_pods(name: str):
    # Flask 3.x 会自动解码 path 参数
    ex, err = _make_executor(name)
    ns = request.args.get("namespace", "default")
    if not ex:
        return jsonify({"pods": [], "error": err})
    return jsonify({"pods": ex.get_pods(ns)})

@app.get("/api/clusters/<path:name>/contexts")
def get_contexts_api(name: str):
    # Flask 3.x 会自动解码 path 参数
    ex, err = _make_executor(name)
    if not ex:
        return jsonify({"contexts": [], "current": "", "error": err})
    return jsonify({
        "contexts": ex.get_contexts(),
        "current":  ex.get_current_context(),
    })

@app.post("/api/contexts")
def get_contexts_by_kubeconfig():
    """
    根据 kubeconfig 路径直接返回 contexts，不创建/保存任何集群配置。
    替代旧的 __tmp__ 临时集群方案，避免 ERR_EMPTY_RESPONSE。
    """
    d  = request.json or {}
    kc = d.get("kubeconfig", "").strip()
    if not kc:
        return jsonify({"error": "kubeconfig 必填"}), 400
    if not os.path.exists(kc):
        return jsonify({"error": f"kubeconfig 文件不存在: {kc}"}), 400
    try:
        ex = KubectlExecutor(kc, "")
        return jsonify({
            "contexts": ex.get_contexts(),
            "current":  ex.get_current_context(),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ═════════════════════════════════════════════════════════════════════════════
# Pod quick-check (no Arthas needed)
# ═════════════════════════════════════════════════════════════════════════════

@app.post("/api/check")
def check_pod():
    d   = request.json
    ex, err = _make_executor(d.get("cluster_name", ""))
    if not ex:
        return jsonify({"ok": False, "error": err}), 400

    ns  = d.get("namespace", "default")
    pod = d.get("pod_name", "")
    phase = ex.get_pod_phase(ns, pod)
    ok    = phase == "Running"

    # Also find Java PID without starting Arthas
    java_pid = None
    if ok:
        mgr = ArthasAgentManager(ex, PodTarget(
            cluster_name = d.get("cluster_name", ""),
            namespace    = ns,
            pod_name     = pod,
            container    = d.get("container", ""),
            arthas_jar   = d.get("arthas_jar", ARTHAS_DEFAULT_JAR),
        ))
        java_pid = mgr.find_java_pid()

    return jsonify({
        "ok":      ok,
        "phase":   phase or "Unknown",
        "java_pid": java_pid,
        "message": f"Pod {phase or 'Unknown'}" + (f"  Java PID={java_pid}" if java_pid else "  未找到 Java 进程"),
    })

# needed by ArthasAgentManager in /api/check
from profiler_backend import ArthasAgentManager


# ═════════════════════════════════════════════════════════════════════════════
# Arthas connection
# ═════════════════════════════════════════════════════════════════════════════

@app.post("/api/arthas/connect")
def arthas_connect():
    d    = request.json
    conn, err = _get_or_create_connection(d)
    if not conn:
        return jsonify({"ok": False, "error": err}), 400

    # Update target fields in case caller passes new values
    conn.target.container  = d.get("container",  conn.target.container)
    conn.target.arthas_jar = d.get("arthas_jar", conn.target.arthas_jar)

    # Already alive?
    if conn.is_alive():
        # 保存连接信息到数据库
        conn_id = d.get("connection_id", str(int(time.time() * 1000)))
        _save_connection(conn_id, d["cluster_name"], d["namespace"], d["pod_name"], conn.local_port)
        return jsonify({
            "ok": True,
            "message": "已连接",
            "local_port": conn.local_port,
            "connection_id": conn_id
        })

    ok, msg = conn.connect()
    if ok:
        # 保存连接信息到数据库
        conn_id = d.get("connection_id", str(int(time.time() * 1000)))
        _save_connection(conn_id, d["cluster_name"], d["namespace"], d["pod_name"], conn.local_port)
        return jsonify({
            "ok": True, "message": msg,
            "local_port": conn.local_port,
            "connection_id": conn_id
        })
    return jsonify({
        "ok": False, "message": msg,
        "local_port": 0,
    })

@app.post("/api/arthas/disconnect")
def arthas_disconnect():
    d = request.json
    key = _conn_key(d.get("cluster_name",""), d.get("namespace","default"), d.get("pod_name",""))
    with _lock:
        conn = _connections.pop(key, None)
    if conn:
        conn.disconnect()
    return jsonify({"ok": True})

@app.post("/api/arthas/status")
def arthas_status():
    d   = request.json
    key = _conn_key(d.get("cluster_name",""), d.get("namespace","default"), d.get("pod_name",""))
    with _lock:
        conn = _connections.get(key)
    if not conn:
        return jsonify({"connected": False})
    return jsonify({
        "connected":  conn.is_alive(),
        "local_port": conn.local_port,
        "java_pid":   conn.java_pid,
    })

# ── One-shot command ──────────────────────────────────────────────────────────

@app.post("/api/arthas/exec")
def arthas_exec():
    d    = request.json
    conn, err = _get_or_create_connection(d)
    if not conn:
        return jsonify({"state": "FAILED", "message": err}), 400
    if not conn.client:
        return jsonify({"state": "FAILED", "message": "未连接，请先调用 /api/arthas/connect"}), 400

    conn_id = d.get("connection_id", "")
    command = d.get("command", "")

    try:
        resp = conn.client.exec_once(command, int(d.get("timeout_ms", 30000)))

        # 保存命令历史到数据库
        if conn_id and command:
            output = resp.get("response", "")
            error = resp.get("message", "") if resp.get("state") == "FAILED" else None
            _save_arthas_command(conn_id, command, output, error)

        return jsonify(resp)
    except Exception as e:
        if conn_id and command:
            _save_arthas_command(conn_id, command, None, str(e))
        return jsonify({"state": "FAILED", "message": str(e)}), 500

# ── Session commands ──────────────────────────────────────────────────────────

@app.post("/api/arthas/session/create")
def session_create():
    d = request.json
    conn, err = _get_or_create_connection(d)
    if not conn:
        return jsonify({"state": "FAILED", "message": err}), 400
    if not conn.client:
        return jsonify({"state": "FAILED", "message": "未连接"}), 400
    try:
        return jsonify(conn.client.init_session())
    except Exception as e:
        return jsonify({"state": "FAILED", "message": str(e)}), 500

@app.post("/api/arthas/session/exec")
def session_exec():
    d = request.json
    conn, err = _get_or_create_connection(d)
    if not conn or not conn.client:
        return jsonify({"state": "FAILED", "message": err or "未连接"}), 400
    try:
        return jsonify(conn.client.exec_async(d.get("session_id",""), d.get("command","")))
    except Exception as e:
        return jsonify({"state": "FAILED", "message": str(e)}), 500

@app.post("/api/arthas/session/pull")
def session_pull():
    d = request.json
    conn, err = _get_or_create_connection(d)
    if not conn or not conn.client:
        return jsonify({"state": "FAILED", "message": err or "未连接"}), 400
    try:
        return jsonify(conn.client.pull_results(d.get("session_id",""), d.get("consumer_id","")))
    except Exception as e:
        return jsonify({"state": "FAILED", "message": str(e)}), 500

@app.post("/api/arthas/session/interrupt")
def session_interrupt():
    d = request.json
    conn, err = _get_or_create_connection(d)
    if not conn or not conn.client:
        return jsonify({"state": "FAILED", "message": err or "未连接"}), 400
    try:
        return jsonify(conn.client.interrupt_job(d.get("session_id","")))
    except Exception as e:
        return jsonify({"state": "FAILED", "message": str(e)}), 500

@app.post("/api/arthas/session/close")
def session_close():
    d = request.json
    conn, err = _get_or_create_connection(d)
    if not conn or not conn.client:
        return jsonify({"state": "FAILED", "message": err or "未连接"}), 400
    try:
        return jsonify(conn.client.close_session(d.get("session_id","")))
    except Exception as e:
        return jsonify({"state": "FAILED", "message": str(e)}), 500


# ═════════════════════════════════════════════════════════════════════════════
# JProfiler async tasks
# ═════════════════════════════════════════════════════════════════════════════

@app.post("/api/profile/start")
def profile_start():
    d    = request.json
    import logging as _lg
    _lg.getLogger(__name__).info(
        "profile/start: mode=%s event=%s fmt=%s dur=%s jfr_name=%s",
        d.get("mode"), d.get("event"), d.get("format"),
        d.get("duration"), d.get("jfr_name"),
    )

    conn, err = _get_or_create_connection(d)
    if not conn:
        return jsonify({"error": err}), 400

    mode     = (d.get("mode") or "profiler").strip()
    event    = (d.get("event") or "cpu").strip()
    fmt      = (d.get("format") or "html").strip()
    duration = int(d.get("duration") or 60)

    task_id = f"task_{datetime.now().strftime('%H%M%S')}_{uuid.uuid4().hex[:6]}"
    wf      = ProfilerWorkflow(conn)

    with _lock:
        _tasks[task_id] = {
            "id":         task_id,
            "wf":         wf,
            "status":     "starting",
            "created_at": datetime.now().isoformat(),
            "config": {
                "cluster":   d.get("cluster_name"),
                "pod":       d.get("pod_name"),
                "namespace": d.get("namespace", "default"),
                "duration":  duration,
                "format":    fmt,
                "mode":      mode,
                "event":     event,
            },
        }

    def _run():
        result = wf.run(
            duration     = duration,
            fmt          = fmt,
            output_dir   = str(OUTPUT_DIR),
            mode         = mode,
            event        = event,
            jfr_name     = d.get("jfr_name", "arthas-jfr"),
            jfr_settings = d.get("jfr_settings", "default"),
            jfr_file     = d.get("jfr_file", ""),
            heap_file    = d.get("heap_file", "/tmp/heap.hprof"),
            heap_live    = d.get("heap_live", True),
        )
        with _lock:
            _tasks[task_id]["status"] = result.get("status", "failed")

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"task_id": task_id})

@app.get("/api/arthas/commands")
def get_arthas_commands():
    """获取连接的 Arthas 命令历史"""
    conn_id = request.args.get("connection_id")
    limit = int(request.args.get("limit", 100))
    if not conn_id:
        return jsonify({"error": "Missing connection_id"}), 400
    try:
        commands = _get_arthas_commands(conn_id, limit)
        return jsonify({"ok": True, "commands": commands})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.get("/api/profile")
def list_profiles():
    with _lock:
        tasks = list(_tasks.values())
    return jsonify([{
        "id":         t["id"],
        "config":     t["config"],
        "status":     t["wf"].result.get("status", "?"),
        "created_at": t["created_at"],
        "has_file":   bool(t["wf"].result.get("local_file")),
        "file_name":  os.path.basename(t["wf"].result.get("local_file", "")) if t["wf"].result.get("local_file") else None,
    } for t in reversed(tasks)])

@app.get("/api/profile/<task_id>")
def profile_status(task_id: str):
    with _lock:
        t = _tasks.get(task_id)
    if not t:
        return jsonify({"error": "不存在"}), 404
    return jsonify({"id": task_id, "config": t["config"],
                    "created_at": t["created_at"], **t["wf"].snapshot()})

@app.post("/api/profile/<task_id>/cancel")
def profile_cancel(task_id: str):
    with _lock:
        t = _tasks.get(task_id)
    if t:
        t["wf"].cancel()
    return jsonify({"ok": True})

@app.get("/api/profile/<task_id>/download")
def profile_download(task_id: str):
    with _lock:
        t = _tasks.get(task_id)
    if not t:
        return jsonify({"error": "不存在"}), 404
    lf = t["wf"].result.get("local_file", "")
    if not lf or not os.path.exists(lf):
        return jsonify({"error": "文件不存在"}), 404
    return send_file(lf, as_attachment=True, download_name=os.path.basename(lf))

# ── 采样日志 API ────────────────────────────────────────────────────────────────
@app.post("/api/profile/logs")
def save_profiler_log():
    """保存采样日志"""
    data = request.json
    conn_id = data.get("connection_id")
    message = data.get("message")
    level = data.get("level", "info")
    if not conn_id or not message:
        return jsonify({"error": "connection_id 和 message 必填"}), 400
    _save_profiler_log(conn_id, message, level)
    return jsonify({"ok": True})

@app.get("/api/profile/logs/<conn_id>")
def get_profiler_logs(conn_id: str):
    """获取连接的采样日志"""
    logs = _get_profiler_logs(conn_id)
    return jsonify({"logs": logs})

@app.delete("/api/profile/logs/<conn_id>")
def clear_profiler_logs(conn_id: str):
    """清空连接的采样日志"""
    _clear_profiler_logs(conn_id)
    return jsonify({"ok": True})



# ═════════════════════════════════════════════════════════════════════════════
# GC Log — 获取 GC 日志路径及内容
# ═════════════════════════════════════════════════════════════════════════════

@app.post("/api/gc/info")
def gc_info():
    """
    探测 JVM GC 日志配置。
    只需 kubectl exec，不需要 Arthas 连接。
    通过读取 /proc/PID/cmdline 获取完整 JVM 启动参数并解析 GC 日志配置。
    """
    d = request.json
    runner, err = _make_runner(d.get("cluster_name", ""))
    if not runner:
        return jsonify({"error": err}), 400

    ns  = d.get("namespace", "default")
    pod = d.get("pod_name", "")
    ctr = d.get("container", "")

    if not pod:
        return jsonify({"error": "pod_name 必填"}), 400

    # ── 1. 找 Java PID ────────────────────────────────────────────────────────
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
        return jsonify({"error": "未找到 Java 进程", "gc_flags": [], "log_path": ""}), 400

    # ── 2. 读取 /proc/PID/cmdline ─────────────────────────────────────────────
    _, cmdline, _ = runner.exec_pod(ns, pod, ctr,
        f"cat /proc/{pid}/cmdline 2>/dev/null | tr '\\0' ' '",
        timeout=5)

    # ── 3. 解析 GC 日志参数 ───────────────────────────────────────────────────
    import re as _re
    gc_flags  = []
    log_paths = []
    stdout_gc = False

    patterns = [
        (r'(-Xloggc:(\S+))',              2),   # JDK 8: path in group 2
        (r'(-Xlog:[^:]*:file=([^:,\s]+))', 2),   # JDK 9+: path in group 2
        (r'(-Xlog:[^:]*:(stdout|stderr))', 2),   # stdout/stderr
        (r'(-XX:\+Print\w*GC\w*)',         None), # PrintGCDetails etc
        (r'(-verbose:gc)',                 None), # verbose gc
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

    # ── 4. 扫描常见路径 ───────────────────────────────────────────────────────
    if not log_paths and not stdout_gc:
        scan_patterns = [
            '/app/logs/gc*.log', '/app/logs/gc.log',
            '/logs/gc*.log',     '/var/log/gc.log',
            '/tmp/gc*.log',      '/home/admin/logs/gc.log',
        ]
        for p in scan_patterns:
            rc2, out2, _ = runner.exec_pod(ns, pod, ctr,
                f"ls {p} 2>/dev/null | head -3", timeout=5)
            if rc2 == 0 and out2.strip():
                log_paths.extend(out2.strip().splitlines())
                break

    # ── 5. 读取日志内容 ───────────────────────────────────────────────────────
    log_content   = ""
    log_path_used = ""

    if stdout_gc:
        log_content   = "GC 输出到 stdout，请使用「Pod 监控 → 日志」标签查看容器日志"
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
        "pid":           pid,
        "gc_flags":      gc_flags,
        "log_paths":     log_paths,
        "log_path_used": log_path_used,
        "stdout_gc":     stdout_gc,
        "gc_enabled":    gc_enabled,
        "log_content":   log_content,
        "cmdline_snippet": cmdline.strip()[:500],
        "hint": "" if gc_enabled else (
            "未检测到 GC 日志配置。\n"
            "JDK 8  启用: -Xloggc:/app/logs/gc.log -XX:+PrintGCDetails -XX:+PrintGCDateStamps\n"
            "JDK 9+ 启用: -Xlog:gc*:file=/app/logs/gc.log:time,tags"
        ),
    })


@app.post("/api/gc/download")
def gc_download():
    """下载 GC 日志文件到本地。"""
    d = request.json
    runner, err = _make_runner(d.get("cluster_name", ""))
    if not runner:
        return jsonify({"error": err}), 400

    log_path  = d.get("log_path", "")
    if not log_path:
        return jsonify({"error": "log_path 必填"}), 400

    filename   = os.path.basename(log_path)
    ts         = datetime.now().strftime("%Y%m%d%H%M%S")
    # 命名规则: gc-{podName}-{ts}.log
    pod_name   = d.get("pod_name", "pod")[:40]
    local_name = f"gc-{pod_name}-{ts}{Path(filename).suffix or '.log'}"
    tmp_dir    = Path(tempfile.mkdtemp(prefix="gc_dl_"))
    local_path = str(tmp_dir / local_name)

    rc, out, err2 = runner.cp_from_pod(
        d.get("namespace","default"), d.get("pod_name",""), d.get("container",""),
        log_path, local_path,
    )
    if rc != 0 or not os.path.exists(local_path):
        shutil.rmtree(str(tmp_dir), ignore_errors=True)
        return jsonify({"error": f"下载失败: {err2 or out}"}), 500

    resp = send_file(local_path, as_attachment=True, download_name=local_name,
                     mimetype="text/plain; charset=utf-8")
    resp.call_on_close(lambda: shutil.rmtree(str(tmp_dir), ignore_errors=True))
    return resp
# ═════════════════════════════════════════════════════════════════════════════

@app.post("/api/monitor/snapshot")
def monitor_snapshot():
    d = request.json
    runner, err = _make_runner(d.get("cluster_name", ""))
    if not runner:
        return jsonify({"error": err}), 400
    pod = d.get("pod_name", "")
    if not pod:
        return jsonify({"error": "pod_name 必填"}), 400
    snap = collect_pod_snapshot(runner, d.get("namespace","default"), pod, d.get("container",""))
    return jsonify(snap)

@app.post("/api/monitor/start-polling")
def monitor_start_polling():
    d = request.json
    runner, err = _make_runner(d.get("cluster_name", ""))
    if not runner:
        return jsonify({"error": err}), 400
    start_metrics_polling(runner, d.get("cluster_name",""),
                          d.get("namespace","default"), d.get("pod_name",""), d.get("container",""))
    return jsonify({"ok": True})

@app.post("/api/monitor/stop-polling")
def monitor_stop_polling():
    d = request.json
    stop_metrics_polling(d.get("cluster_name",""), d.get("namespace","default"), d.get("pod_name",""))
    return jsonify({"ok": True})

@app.post("/api/monitor/history")
def monitor_history():
    d = request.json
    return jsonify(get_metrics_history(
        d.get("cluster_name",""), d.get("namespace","default"), d.get("pod_name","")))

@app.post("/api/monitor/logs")
def monitor_logs():
    d = request.json
    runner, err = _make_runner(d.get("cluster_name", ""))
    if not runner:
        return jsonify({"error": err}), 400
    logs = runner.get_logs(
        ns        = d.get("namespace", "default"),
        pod       = d.get("pod_name", ""),
        container = d.get("container", ""),
        tail      = int(d.get("tail", 200)),
        since     = d.get("since", ""),
    )
    return jsonify({"logs": logs})

@app.post("/api/monitor/logs/download")
def download_logs():
    d = request.json
    runner, err = _make_runner(d.get("cluster_name", ""))
    if not runner:
        return jsonify({"error": err}), 400
    ns        = d.get("namespace", "default")
    pod       = d.get("pod_name", "")
    container = d.get("container", "")
    tail      = int(d.get("tail", 5000))
    since     = d.get("since", "")
    logs      = runner.get_logs(ns=ns, pod=pod, container=container, tail=tail, since=since)
    ts    = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"logs_{pod}_{container or 'default'}_{ts}.log"
    tmp   = Path(tempfile.mkdtemp()) / fname
    tmp.write_text(logs, encoding="utf-8")
    return send_file(str(tmp), as_attachment=True, download_name=fname,
                     mimetype="text/plain; charset=utf-8")

@app.post("/api/monitor/events")
def monitor_events():
    d = request.json
    runner, err = _make_runner(d.get("cluster_name", ""))
    if not runner:
        return jsonify({"error": err}), 400
    events = runner.get_pod_events(d.get("namespace","default"), d.get("pod_name",""))
    return jsonify({"events": events})


# ═════════════════════════════════════════════════════════════════════════════
# Pod File Browser
# ═════════════════════════════════════════════════════════════════════════════

@app.post("/api/pod/files/list")
def pod_files_list():
    d = request.json
    runner, err = _make_runner(d.get("cluster_name", ""))
    if not runner:
        return jsonify({"error": err, "files": []}), 400

    path = (d.get("path", "/tmp") or "/tmp").rstrip("/") or "/"
    ns        = d.get("namespace", "default")
    pod       = d.get("pod_name", "")
    container = d.get("container", "")

    # ── 兼容 BusyBox ls（不支持 --time-style / --full-time）──────────────────
    # 策略：先尝试 GNU ls（支持 --full-time），失败则 fallback 到 BusyBox ls -l
    # 再用 stat 补充精确时间（BusyBox stat 格式不同，做双重 fallback）
    ls_cmd = (
        # 优先：GNU coreutils ls（glibc 镜像）
        f'ls -lAh --full-time "{path}" 2>/dev/null'
        # 次选：BusyBox ls，时间列只有 Mon DD HH:MM 或 Mon DD  YYYY 格式
        f' || ls -lA "{path}" 2>&1'
    )
    rc, out, err2 = runner.exec_pod(ns, pod, container, ls_cmd, timeout=10)
    if rc != 0 or (not out.strip() and err2):
        return jsonify({"error": f"ls 失败: {out or err2}", "files": []})

    # ── 用 stat 批量获取精确 mtime（BusyBox stat: %y = modification time）──
    # 格式: filename|||2024-01-15 10:30:45.000000000
    stat_map: dict[str, str] = {}
    stat_cmd = (
        # GNU stat
        f'stat -c "%n|||%y" "{path}"/* 2>/dev/null'
        f' || stat -c "%n|||%y" "{path}"/.[!.]* 2>/dev/null'
        f' || for f in "{path}"/*; do stat "$f" 2>/dev/null | '
        f'awk -v n="$f" \'/Modify:/ {{print n"|||"$2" "$3}}\'; done'
    )
    rc_s, stat_out, _ = runner.exec_pod(ns, pod, container, stat_cmd, timeout=10)
    if rc_s == 0 and stat_out.strip():
        for sline in stat_out.strip().splitlines():
            if "|||" in sline:
                fname_full, mtime = sline.split("|||", 1)
                fname = os.path.basename(fname_full.strip())
                # 截取 "YYYY-MM-DD HH:MM:SS" 前19字符
                stat_map[fname] = mtime.strip()[:19]

    # ── 解析 ls 输出 ─────────────────────────────────────────────────────────
    files = []
    for line in out.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("total"):
            continue

        parts = line.split()
        if len(parts) < 5:
            continue

        perm = parts[0]
        if not perm[0] in ("-", "d", "l", "p", "s", "c", "b"):
            continue

        # 文件大小
        size = ""
        name = ""

        # GNU --full-time 格式:
        # -rw-r--r-- 1 root root 1234 2024-01-15 10:30:45.123 filename
        # BusyBox 格式:
        # -rw-r--r-- 1 root root 1234 Jan 15 10:30 filename
        # -rw-r--r-- 1 root root 1234 Jan 15  2024 filename
        if len(parts) >= 9 and parts[5].count("-") == 2 and parts[5][4] == "-":
            # GNU full-time: perm links user group size YYYY-MM-DD HH:MM:SS.ns name...
            size = parts[4]
            name = " ".join(parts[8:])
        elif len(parts) >= 9:
            # BusyBox: perm links user group size Mon DD HH:MM name...
            size = parts[4]
            name = " ".join(parts[8:])
        elif len(parts) >= 5:
            # 最简 fallback
            size = parts[4] if parts[4].isdigit() or parts[4][-1] in "KMGkmbg" else ""
            name = parts[-1]

        if not name or name in (".", ".."):
            continue

        # 处理软链接 "name -> target"
        real_name = name.split(" -> ")[0].strip() if " -> " in name else name.strip()
        link_target = name.split(" -> ")[1].strip() if " -> " in name else ""

        # 时间：优先 stat_map，其次从 ls 行提取
        mtime = stat_map.get(real_name, "")
        if not mtime:
            # 从 ls 行尝试提取
            if len(parts) >= 8 and parts[5].count("-") == 2:
                mtime = f"{parts[5]} {parts[6][:8]}"  # YYYY-MM-DD HH:MM:SS
            elif len(parts) >= 8:
                mtime = f"{parts[5]} {parts[6]} {parts[7]}"  # Mon DD HH:MM/YYYY

        full_path = f"{path}/{real_name}".replace("//", "/")
        files.append({
            "name":        real_name,
            "perm":        perm,
            "user":        parts[2] if len(parts) > 2 else "",
            "size":        size,
            "modified":    mtime,
            "is_dir":      perm.startswith("d"),
            "is_link":     perm.startswith("l"),
            "link_target": link_target,
            "path":        full_path,
        })

    files.sort(key=lambda f: (not f["is_dir"], f["name"].lower()))
    return jsonify({"path": path, "files": files})

@app.post("/api/pod/files/download")
def pod_files_download():
    d = request.json
    import logging as _logging_mod
    _log = _logging_mod.getLogger(__name__)

    cluster_name = d.get("cluster_name", "")
    namespace    = d.get("namespace", "default")
    pod_name     = d.get("pod_name", "")
    container    = d.get("container", "")
    pod_path     = d.get("path", "")

    _log.info("download request: cluster=%s ns=%s pod=%s container=%s path=%s",
              cluster_name, namespace, pod_name, container, pod_path)

    runner, err = _make_runner(cluster_name)
    if not runner:
        return jsonify({"error": err}), 400

    if not pod_name:
        return jsonify({"error": "pod_name 为空，请在左侧边栏填写 Pod 名称"}), 400
    if not pod_path:
        return jsonify({"error": "path 必填"}), 400

    filename   = os.path.basename(pod_path)
    tmp_dir    = tempfile.mkdtemp(prefix="pod_dl_")
    local_path = os.path.join(tmp_dir, filename)

    _log.info("cp_from_pod: ns=%s pod=%s container=%s src=%s dst=%s",
              namespace, pod_name, container, pod_path, local_path)
    try:
        rc, stdout, err2 = runner.cp_from_pod(
            namespace, pod_name, container, pod_path, local_path,
        )
        if rc != 0 or not os.path.exists(local_path):
            shutil.rmtree(tmp_dir, ignore_errors=True)
            detail = err2 or stdout or "（无详细信息）"
            _log.error("cp_from_pod failed rc=%s err=%s", rc, detail)
            return jsonify({
                "error": detail,
                "debug": {
                    "cluster": cluster_name, "namespace": namespace,
                    "pod": pod_name, "container": container, "pod_path": pod_path,
                }
            }), 500
        import mimetypes
        mime, _ = mimetypes.guess_type(filename)
        resp = send_file(local_path, as_attachment=True, download_name=filename,
                         mimetype=mime or "application/octet-stream")
        resp.call_on_close(lambda: shutil.rmtree(tmp_dir, ignore_errors=True))
        return resp
    except Exception as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        _log.exception("download exception")
        return jsonify({"error": str(e)}), 500

@app.post("/api/pod/files/tail")
def pod_files_tail():
    d = request.json
    runner, err = _make_runner(d.get("cluster_name", ""))
    if not runner:
        return jsonify({"error": err, "content": ""}), 400
    lines = int(d.get("lines", 200))
    rc, out, err2 = runner.exec_pod(
        d.get("namespace","default"), d.get("pod_name",""), d.get("container",""),
        f"tail -n {lines} \"{d.get('path','')}\" 2>&1", timeout=10,
    )
    if rc != 0:
        return jsonify({"error": out or err2, "content": ""})
    return jsonify({"content": out, "path": d.get("path","")})


# ═════════════════════════════════════════════════════════════════════════════
# Pod Terminal exec
# ═════════════════════════════════════════════════════════════════════════════

@app.post("/api/pod/exec")
def pod_exec():
    """
    在 Pod 内执行 shell 命令，返回 stdout + stderr + exit code。
    支持带工作目录（cd + command 拼接）。
    timeout 最长 60s，超时返回已有输出。
    """
    d         = request.json
    runner, err = _make_runner(d.get("cluster_name", ""))
    if not runner:
        return jsonify({"error": err, "stdout": "", "stderr": "", "rc": -1}), 400

    ns        = d.get("namespace", "default")
    pod       = d.get("pod_name", "")
    container = d.get("container", "")
    command   = d.get("command", "").strip()
    cwd       = d.get("cwd", "").strip()       # 当前工作目录
    timeout   = min(int(d.get("timeout", 30)), 60)

    if not pod:
        return jsonify({"error": "pod_name 必填", "stdout": "", "stderr": "", "rc": -1}), 400
    if not command:
        return jsonify({"error": "command 必填", "stdout": "", "stderr": "", "rc": -1}), 400

    # 构建 shell 命令：先 cd 到工作目录，再执行用户命令
    # 用 { } 包裹保证 cd 失败时提前报错
    if cwd and cwd != "/":
        shell_cmd = f'cd {shlex.quote(cwd)} && ( {command} ); echo "__RC__=$?"'
    else:
        shell_cmd = f'( {command} ); echo "__RC__=$?"'

    rc_exec, raw_out, raw_err = runner.exec_pod(
        ns, pod, container, shell_cmd, timeout=timeout
    )

    # 解析 __RC__ 标记
    rc_actual = rc_exec
    out_clean = raw_out
    if "__RC__=" in raw_out:
        lines     = raw_out.rsplit("__RC__=", 1)
        out_clean = lines[0]
        try:
            rc_actual = int(lines[1].strip().splitlines()[0])
        except (ValueError, IndexError):
            pass

    return jsonify({
        "stdout": out_clean,
        "stderr": raw_err,
        "rc":     rc_actual,
        "cwd":    cwd,
    })


@app.post("/api/pod/exec/cwd")
def pod_exec_cwd():
    """获取 Pod 内当前工作目录、hostname、用户名（用于终端初始化）。"""
    d         = request.json
    runner, err = _make_runner(d.get("cluster_name", ""))
    if not runner:
        return jsonify({"cwd": "/", "hostname": "", "user": "root"}), 400
    ns, pod, ctr = (d.get("namespace","default"), d.get("pod_name",""), d.get("container",""))
    _, cwd,  _ = runner.exec_pod(ns, pod, ctr, "pwd 2>/dev/null || echo /",          timeout=5)
    _, host, _ = runner.exec_pod(ns, pod, ctr, "hostname 2>/dev/null || echo pod",    timeout=5)
    _, user, _ = runner.exec_pod(ns, pod, ctr, "whoami 2>/dev/null || echo root",     timeout=5)
    return jsonify({
        "cwd":      cwd.strip()  or "/",
        "hostname": host.strip() or pod,
        "user":     user.strip() or "root",
    })


# ═════════════════════════════════════════════════════════════════════════════
# Local output files
# ═════════════════════════════════════════════════════════════════════════════

@app.get("/api/files")
def list_local_files():
    files = []
    for f in sorted(OUTPUT_DIR.glob("*"), key=lambda x: x.stat().st_mtime, reverse=True):
        if f.is_file():
            files.append({
                "name":     f.name,
                "size":     f.stat().st_size,
                "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
            })
    return jsonify(files)

@app.get("/api/files/<path:filename>")
def download_local_file(filename: str):
    p = OUTPUT_DIR / filename
    if not p.exists():
        return jsonify({"error": "不存在"}), 404
    return send_file(str(p), as_attachment=True, download_name=filename)


# ═════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="K8s Arthas Tool Server")
    parser.add_argument("--port", type=int, default=5001)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    # 初始化数据库
    _init_db()
    _load_clusters()

    print(f"🚀  K8s Arthas Tool  →  http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=False, threaded=True)
