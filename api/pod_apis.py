"""
Pod 连接相关 API 端点

包含：
- /api/pod/connect - 建立轻量级 Pod 连接
- /api/pod/disconnect - 断开 Pod 连接  
- /api/pod/connections - 列出所有 Pod 连接
- /api/pod/upgrade-to-arthas - 升级为 Arthas 连接
- /api/pod/diagnose - Pod 级系统诊断（无需 Arthas）
"""

import logging
import re
from datetime import datetime
from typing import Dict
from flask import request, jsonify
from flask_login import login_required, current_user
from services.authorization_service import AuthorizationService
from services.cache_service import query_cache, invalidate_connection_cache

log = logging.getLogger(__name__)


def register_pod_apis(app, db, _make_runner, _connections_lock, _connections):
    """注册 Pod 连接相关的 API 端点"""
    
    # ✅ 修复: 单一连接池,通过 level 字段区分 Pod/Arthas 连接
    # 移除 _pod_connections,统一使用 _connections
    _pod_connections_lock = __import__('threading').Lock()  # 保留用于向后兼容
    
    def _make_pod_conn_id(cluster_name: str, namespace: str, pod_name: str) -> str:
        """生成 Pod 连接 ID"""
        conn_id = f"{cluster_name}/{namespace}/{pod_name}"
        if not current_user.is_admin:
            conn_id = f"{conn_id}@u{current_user.id}"
        return conn_id
    
    def _get_connection_entry(conn_id: str):
        """获取连接对象 (从统一连接池)"""
        with _connections_lock:
            return _connections.get(conn_id)
    
    def _check_conn_owner(conn_id: str) -> bool:
        """检查当前用户是否是连接的拥有者"""
        if current_user.is_admin:
            return True
        entry = _get_connection_entry(conn_id)
        return entry and entry.get('user_id') == current_user.id
    
    @app.route('/api/pod/connect', methods=['POST'])
    @login_required
    def pod_connect():
        """建立轻量级 Pod 连接（不启动 Arthas）"""
        from backend import PodTarget, PodConnection
        from services.audit_service import AuditService
        
        d = request.json or {}
        cluster_name = d.get('cluster_name', '')
        namespace = d.get('namespace', 'default')
        pod_name = d.get('pod_name', '')
        container = d.get('container', '')
        
        if not cluster_name or not pod_name:
            return jsonify({"error": "cluster_name 和 pod_name 必填"}), 400
        
        runner, err = _make_runner(cluster_name)
        if err:
            return jsonify({"error": err}), 400
        auth_err, auth_code = AuthorizationService.require_namespace_access(current_user, cluster_name, namespace)
        if auth_err:
            return jsonify(auth_err), auth_code
        
        conn_id = _make_pod_conn_id(cluster_name, namespace, pod_name)
        
        # ✅ 修复: 从统一连接池检查是否已有连接
        with _connections_lock:
            if conn_id in _connections:
                entry = _connections[conn_id]
                conn = entry.get('conn')
                # 检查连接是否存活且是 Pod 级别
                if conn and hasattr(conn, '_healthy') and conn._healthy:
                    from dataclasses import asdict
                    
                    runtime_data = asdict(conn.runtime_info) if hasattr(conn, 'runtime_info') and conn.runtime_info else None
                    log.info("[Pod Connect Reuse] conn_id=%s, runtime_info=%s", conn_id, runtime_data)
                    
                    # 如果 runtime_info 缺失,重新检测
                    if not runtime_data or not runtime_data.get('runtime_type'):
                        log.warning("[Pod Connect Reuse] runtime_info 缺失,重新检测")
                        if hasattr(conn, '_detect_runtime'):
                            conn._runtime_info = conn._detect_runtime(timeout=10)
                            runtime_data = asdict(conn.runtime_info) if conn.runtime_info else None
                    
                    return jsonify({
                        "ok": True,
                        "connection_id": conn_id,
                        "message": "Pod 连接已存在，复用",
                        "pod_phase": getattr(conn, 'pod_phase', 'Running'),
                        "runtime": runtime_data,
                        "reused": True
                    })
                else:
                    # 连接失效,移除
                    _connections.pop(conn_id, None)
        
        # 创建新连接
        target = PodTarget(
            cluster_name=cluster_name,
            namespace=namespace,
            pod_name=pod_name,
            container=container
        )
        conn = PodConnection(runner, target)
        
        try:
            ok, msg = conn.connect(timeout=10)
            if not ok:
                if isinstance(msg, dict):
                    return jsonify({"ok": False, **msg}), 400
                return jsonify({"ok": False, "error": msg}), 400
            
            with _connections_lock:
                _connections[conn_id] = {
                    "conn": conn,
                    "user_id": current_user.id,
                    "level": "pod",  # ✅ 标记为 Pod 连接
                    "created_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
            
            # 持久化到数据库（保存完整上下文）
            now_ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            conn_data = {
                'cluster_name': cluster_name,
                'namespace': namespace,
                'pod_name': pod_name,
                'container_name': container or '',
                'level': 'pod',
                'local_port': None,
                'java_pid': None,
                'arthas_version': None,
                'last_ping_at': now_ts,
                'user_id': current_user.id,
                'status': 'pod_connected',
                'updated_at': now_ts,
            }
            if db.exists('connections', 'id = ?', (conn_id,)):
                db.update('connections', conn_data, 'id = ?', (conn_id,))
            else:
                conn_data['id'] = conn_id
                db.insert('connections', conn_data)
            
            AuditService.log_connection_created(current_user.id, conn_id, pod_name, namespace)
            
            # ✅ 修复: 使用 asdict 转换 dataclass
            from dataclasses import asdict
            runtime_data = asdict(conn.runtime_info) if conn.runtime_info else None
            log.info("[Pod Connect] runtime_info: %s", runtime_data)
            
            return jsonify({
                "ok": True,
                "connection_id": conn_id,
                "pod_phase": conn.pod_phase,
                "runtime": runtime_data,
                "message": msg,
                "reused": False
            })
            
        except Exception as e:
            log.error("Pod connect failed: %s", e, exc_info=True)
            return jsonify({"error": str(e)}), 500
    
    def cleanup_pod_connection_by_id(conn_id: str) -> bool:
        """按连接 ID 清理 Pod 连接,供全局失效连接清理复用。"""
        entry = None
        with _connections_lock:
            entry = _connections.pop(conn_id, None)
        if entry:
            conn = entry.get('conn')
            if conn:
                try:
                    conn.disconnect()
                except Exception:
                    pass
            return True
        return False

    # 将清理函数挂到 Flask app，避免跨闭包直接访问 _pod_connections
    app.cleanup_pod_connection_by_id = cleanup_pod_connection_by_id

    @app.route('/api/pod/disconnect', methods=['POST'])
    @login_required
    def pod_disconnect():
        """断开 Pod 连接（同时释放 Arthas 层资源）"""
        from services.audit_service import AuditService
        d = request.json or {}
        conn_id = d.get('connection_id', '')
        
        if not conn_id:
            return jsonify({"error": "connection_id 必填"}), 400
        
        # ✅ 修复: 从统一连接池检查
        entry = _get_connection_entry(conn_id)
        
        if entry and not _check_conn_owner(conn_id):
            return jsonify({"error": "无权操作此连接"}), 403
        
        # ✅ 如果连接不存在,直接返回成功（幂等性）
        if not entry:
            log.info("[断开] 连接不存在（可能已断开）: %s", conn_id)
            return jsonify({"ok": True, "message": "连接已断开"})

        # 释放连接资源 (Pod 或 Arthas)
        with _connections_lock:
            removed_entry = _connections.pop(conn_id, None)
        
        # 释放连接资源
        if removed_entry:
            conn = removed_entry.get('conn')
            if conn:
                try:
                    conn.disconnect()
                except Exception:
                    pass

        # 3. 更新数据库状态为 disconnected（而非删除）
        now_ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        db.update('connections', {
            'status': 'disconnected',
            'updated_at': now_ts,
        }, 'id = ?', (conn_id,))

        # ✅ 缓存失效：断开连接后清除相关缓存
        invalidate_connection_cache(conn_id)

        # 4. 审计日志
        parts = conn_id.split('/')
        pod = parts[2] if len(parts) >= 3 else conn_id
        namespace = parts[1] if len(parts) >= 3 else ''
        AuditService.log_connection_deleted(current_user.id, conn_id, pod, namespace)

        return jsonify({"ok": True, "message": "Pod 连接已断开"})
    
    @app.route('/api/pod/connections', methods=['GET'])
    @login_required
    def list_pod_connections():
        """列出当前用户的所有连接 (Pod + Arthas)"""
        # ✅ Cache: user-scoped key
        cache_key = f"list_pod_connections:uid={current_user.id}:admin={current_user.is_admin}"
        cached_result = query_cache.get(cache_key)
        if cached_result is not None:
            return jsonify(cached_result)

        # ✅ 修复: 从数据库获取历史连接,不仅返回内存中的活跃连接
        if current_user.is_admin:
            rows = db.fetch_all(
                "SELECT * FROM connections ORDER BY last_ping_at DESC LIMIT 50"
            )
        else:
            rows = db.fetch_all(
                "SELECT * FROM connections WHERE user_id = ? ORDER BY last_ping_at DESC LIMIT 50",
                (current_user.id,)
            )

        connections = []
        for row in rows:
            conn_id = row['id']

            # 检查内存中是否有活跃连接
            with _connections_lock:
                entry = _connections.get(conn_id)

            conn = entry.get('conn') if entry else None

            connections.append({
                "id": conn_id,
                "connection_id": conn_id,
                "cluster_name": row['cluster_name'],
                "namespace": row['namespace'],
                "pod_name": row['pod_name'],
                "container": row.get('container_name', ''),
                "pod_phase": 'Running',  # 默认值,健康检查会更新
                "level": row.get('level', 'pod'),
                "runtime": None,  # 从内存连接获取
                "runtime_version": None,
                "alive": conn is not None and (hasattr(conn, '_healthy') and conn._healthy),
                "created_at": row.get('created_at', ''),
                "last_ping_at": row.get('last_ping_at', ''),
                # Arthas 层元数据
                "local_port": row.get('local_port'),
                "java_pid": row.get('java_pid'),
                "arthas_version": row.get('arthas_version'),
                "arthas_address": row.get('arthas_address'),
                "mcp_available": row.get('mcp_available', False) or (entry.get('mcp_available', False) if entry else False),
                "status": row.get('status', 'disconnected'),
            })

            # 如果有活跃连接,补充运行时信息
            if conn and hasattr(conn, 'runtime_info') and conn.runtime_info:
                connections[-1]['runtime'] = conn.runtime_info.runtime_type
                connections[-1]['runtime_version'] = conn.runtime_info.version
                connections[-1]['pod_phase'] = getattr(conn, 'pod_phase', 'Running')

        result = {"ok": True, "connections": connections, "count": len(connections)}
        query_cache.set(cache_key, result, ttl=30)  # Short TTL -- connection state changes frequently
        return jsonify(result)
    
    @app.route('/api/pod/upgrade-to-arthas', methods=['POST'])
    @login_required
    def upgrade_to_arthas():
        """将 Pod 连接升级为 Arthas 连接"""
        from backend import ArthasConnection
        from services.audit_service import AuditService
        
        d = request.json or {}
        pod_conn_id = d.get('connection_id', '')
        java_pid = d.get('java_pid')
        force = d.get('force', False)  # 前端恢复连接时可强制升级（跳过 is_java 检查）
        
        if not pod_conn_id:
            return jsonify({"error": "connection_id 必填"}), 400
        
        # ✅ 修复: 从统一连接池获取 Pod 连接
        entry = _get_connection_entry(pod_conn_id)
        
        if not entry:
            return jsonify({"error": "Pod 连接不存在"}), 404
        
        if not _check_conn_owner(pod_conn_id):
            return jsonify({"error": "无权操作此连接"}), 403
        
        pod_conn = entry.get('conn')

        if not pod_conn:
            return jsonify({"error": "Pod 连接已失效，请重新连接"}), 400

        # ✅ 修复: 主动检查 Pod 连接健康状态，不健康的连接直接拒绝
        if hasattr(pod_conn, '_healthy') and not pod_conn._healthy:
            log.warning("[Upgrade Arthas] Pod 连接不健康，清理后要求重连: %s", pod_conn_id)
            with _connections_lock:
                _connections.pop(pod_conn_id, None)
            return jsonify({"error": "Pod 连接已失效，请重新连接"}), 400

        # ✅ 修复: 检查 port-forward 进程是否存活
        if hasattr(pod_conn, '_pf_proc') and pod_conn._pf_proc is not None:
            if pod_conn._pf_proc.poll() is not None:
                log.warning("[Upgrade Arthas] port-forward 进程已退出，清理连接: %s", pod_conn_id)
                with _connections_lock:
                    _connections.pop(pod_conn_id, None)
                return jsonify({"error": "port-forward 已断开，请重新连接 Pod"}), 400
        auth_err, auth_code = AuthorizationService.require_namespace_access(
            current_user, pod_conn.target.cluster_name, pod_conn.target.namespace)
        if auth_err:
            return jsonify(auth_err), auth_code
        
        if not pod_conn.is_java and not force:
            return jsonify({
                "error": "非 Java 应用，无法启动 Arthas",
                "runtime": pod_conn.runtime_info.runtime_type if pod_conn.runtime_info else "unknown"
            }), 400
        
        if force and not pod_conn.is_java:
            log.warning("[Upgrade Arthas] force=True, 跳过 is_java 检查 (runtime=%s)",
                       pod_conn.runtime_info.runtime_type if pod_conn.runtime_info else "unknown")
        
        arthas_conn = ArthasConnection(pod_conn.executor, pod_conn.target)
        
        # Pod 已连接，直接标记状态（不再调 connect_pod 避免重复检测）
        arthas_conn._pod_connected = True
        arthas_conn.pod_conn = pod_conn  # 复用已有 Pod 连接实例
        
        if java_pid:
            arthas_conn.agent_mgr._pid = int(java_pid)
        
        try:
            log.info("[Upgrade Arthas] 开始连接...")
            # connect_arthas 内部已处理 REINSTALL_NEEDED 重试（最多 1 次），无需外层重复
            ok, msg = arthas_conn.connect_arthas(timeout=30)
            log.info("[Upgrade Arthas] 连接结果: ok=%s, msg=%s", ok, msg)
            
            if not ok:
                log.error("[Upgrade Arthas] 连接失败: %s", msg)
                if isinstance(msg, dict):
                    return jsonify({"ok": False, **msg}), 400
                return jsonify({"ok": False, "error": msg}), 400
            
            is_reused = '复用' in msg or '已在运行' in msg
            mcp_available = arthas_conn.agent_mgr._check_mcp_available(arthas_conn.target.arthas_http_port)
            
            with _connections_lock:
                _connections[pod_conn_id] = {
                    "conn": arthas_conn,
                    "user_id": current_user.id,
                    "level": "arthas",  # ✅ 升级为 Arthas 连接
                    "mcp_available": mcp_available
                }
            
            now_ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            upgrade_data = {
                'cluster_name': pod_conn.target.cluster_name,
                'namespace': pod_conn.target.namespace,
                'pod_name': pod_conn.target.pod_name,
                'container_name': pod_conn.target.container or '',
                'level': 'arthas',
                'local_port': arthas_conn.local_port,
                'java_pid': arthas_conn.java_pid,
                'arthas_version': arthas_conn.arthas_version,
                'last_ping_at': now_ts,
                'user_id': current_user.id,
                'status': 'ready',
                'updated_at': now_ts,
            }
            if db.exists('connections', 'id = ?', (pod_conn_id,)):
                db.update('connections', upgrade_data, 'id = ?', (pod_conn_id,))
            else:
                upgrade_data['id'] = pod_conn_id
                db.insert('connections', upgrade_data)
            
            AuditService.log_connection_created(
                current_user.id, pod_conn_id, pod_conn.target.pod_name, pod_conn.target.namespace
            )
            
            return jsonify({
                "ok": True,
                "connection_id": pod_conn_id,
                "local_port": arthas_conn.local_port,
                "java_pid": arthas_conn.java_pid,
                "http_url": f"http://localhost:{arthas_conn.local_port}",
                "arthas_version": arthas_conn.arthas_version,
                "arthas_address": arthas_conn.arthas_address,
                "mcp_available": mcp_available,
                "reused": is_reused,
                "message": msg
            })
            
        except Exception as e:
            log.error("Upgrade to Arthas failed: %s", e, exc_info=True)
            return jsonify({"error": str(e)}), 500

    # ═══════════════════════════════════════════════════════════════════════════════
    # Connection health & listing APIs
    # ═══════════════════════════════════════════════════════════════════════════════

    @app.route('/api/arthas/connections/<id>/ping', methods=['POST'])
    @login_required
    def arthas_connection_ping(id: str):
        """主动健康检查：刷新 last_ping_at 并返回当前状态"""
        now_ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        db.update('connections', {
            'last_ping_at': now_ts,
            'updated_at': now_ts,
        }, 'id = ?', (id,))
        row = db.fetch_one(
            "SELECT status, last_ping_at FROM connections WHERE id = ?",
            (id,),
        )
        if not row:
            return jsonify({"ok": False, "error": "连接不存在"}), 404
        return jsonify({
            "ok": True,
            "status": row.get('status', 'unknown'),
            "last_ping_at": row.get('last_ping_at', ''),
        })

    @app.route('/api/arthas/connections', methods=['GET'])
    @login_required
    def list_arthas_connections():
        """列出连接（含完整上下文字段）"""
        try:
            if current_user.is_admin:
                rows = db.fetch_all(
                    'SELECT id, cluster_name, namespace, pod_name, container_name, '
                    'level, java_pid, arthas_version, local_port, last_ping_at, '
                    'user_id, status, updated_at '
                    'FROM connections ORDER BY updated_at DESC'
                )
            else:
                # 非 admin 只能看到自己的连接
                rows = db.fetch_all(
                    'SELECT id, cluster_name, namespace, pod_name, container_name, '
                    'level, java_pid, arthas_version, local_port, last_ping_at, '
                    'user_id, status, updated_at '
                    'FROM connections WHERE user_id = ? ORDER BY updated_at DESC',
                    (current_user.id,)
                )
            connections = [dict(r) for r in (rows or [])]
            return jsonify({"ok": True, "connections": connections, "count": len(connections)})
        except Exception as e:
            log.exception('获取连接列表失败')
            return jsonify({"ok": False, "error": str(e)}), 500

    # ═══════════════════════════════════════════════════════════════════════════════
    # Pod 级系统诊断（无需 Arthas）
    # ═══════════════════════════════════════════════════════════════════════════════

    @app.route('/api/pod/diagnose', methods=['POST'])
    @login_required
    def pod_diagnose():
        """
        Pod 级系统诊断 — 通过 kubectl exec 在容器内采集系统指标，无需 Arthas。

        POST /api/pod/diagnose
        {
            "connection_id": "cluster/ns/pod",
            "tool": "sys_cpu" | "sys_mem" | "sys_disk" | "sys_net" | "sys_proc" | "system_overview"
        }
        """
        d = request.json or {}
        conn_id = d.get('connection_id', '')
        tool = d.get('tool', '')

        if not conn_id:
            return jsonify({"error": "connection_id 必填"}), 400
        if not tool:
            return jsonify({"error": "tool 必填"}), 400

        # ✅ 修复: 从统一连接池查找
        entry = _get_connection_entry(conn_id)

        if not entry:
            return jsonify({"error": "连接不存在，请先建立连接"}), 404

        if not _check_conn_owner(conn_id):
            return jsonify({"error": "无权操作此连接"}), 403

        conn = entry.get('conn')
        if not conn or (hasattr(conn, '_healthy') and not conn._healthy):
            return jsonify({"error": "连接已失效，请重新连接"}), 400
        auth_err, auth_code = AuthorizationService.require_namespace_access(
            current_user, conn.target.cluster_name, conn.target.namespace)
        if auth_err:
            return jsonify(auth_err), auth_code

        # 执行采集
        valid_tools = ('sys_cpu', 'sys_mem', 'sys_disk', 'sys_net', 'sys_proc', 'system_overview')
        if tool not in valid_tools:
            return jsonify({"error": f"未知工具: {tool}，支持: {', '.join(valid_tools)}"}), 400

        try:
            if tool == 'system_overview':
                data = _collect_system_overview(conn)
                data['timestamp'] = datetime.now().isoformat()
                return jsonify({"ok": True, "data": data})
            else:
                collector = {
                    'sys_cpu': _collect_cpu,
                    'sys_mem': _collect_mem,
                    'sys_disk': _collect_disk,
                    'sys_net': _collect_net,
                    'sys_proc': _collect_proc,
                }[tool]
                result = collector(conn)
                return jsonify({"ok": True, "data": result})

        except Exception as e:
            log.error("pod_diagnose failed: tool=%s conn=%s err=%s", tool, conn_id, e, exc_info=True)
            return jsonify({"error": f"采集失败: {str(e)}"}), 500

    # ── 采集函数 ────────────────────────────────────────────────────────────────

    def _exec_pod_cmd(conn, cmd: str, timeout: int = 10) -> str:
        """在 Pod 内执行命令，返回 stdout"""
        rc, out, err = conn.exec_command(cmd, timeout=timeout)
        if rc != 0:
            raise RuntimeError(err or out or f"命令执行失败 (rc={rc})")
        return out

    def _collect_cpu(conn) -> dict:
        """采集 CPU 指标"""
        # 尝试 cgroup v2 → cgroup v1 → /proc/stat
        out = _exec_pod_cmd(conn,
            "echo '===CGROUP2==='; "
            "cat /sys/fs/cgroup/cpu.stat 2>/dev/null | head -5 || true; "
            "echo '===CGROUP1==='; "
            "cat /sys/fs/cgroup/cpu/cpu.stat 2>/dev/null | head -5 || true; "
            "echo '===LOAD==='; "
            "cat /proc/loadavg 2>/dev/null || true; "
            "echo '===NPROC==='; "
            "nproc 2>/dev/null || grep -c ^processor /proc/cpuinfo 2>/dev/null || echo 1",
            timeout=10
        )

        result = {'cpu_percent': 0, 'cpu_count': 1, 'load_avg': ''}

        # 解析负载
        load_match = re.search(r'===LOAD===\s*\n(.+)', out)
        if load_match:
            load_line = load_match.group(1).strip().split()
            if len(load_line) >= 3:
                result['load_avg'] = f"{load_line[0]} {load_line[1]} {load_line[2]}"

        # 解析 CPU 核数
        nproc_match = re.search(r'===NPROC===\s*\n(\d+)', out)
        if nproc_match:
            result['cpu_count'] = int(nproc_match.group(1))

        # 解析 CPU 使用率 — cgroup v2 优先
        cgroup2_match = re.search(r'===CGROUP2===\s*\n(.*?)(?====CGROUP1===)', out, re.DOTALL)
        if cgroup2_match:
            usage_usec = None
            total_usec = None
            for line in cgroup2_match.group(1).strip().splitlines():
                parts = line.split()
                if len(parts) == 2:
                    if parts[0] == 'usage_usec':
                        usage_usec = int(parts[1])
                    elif parts[0] == 'user_usec' or parts[0] == 'system_usec':
                        total_usec = (total_usec or 0) + int(parts[1])
            if usage_usec and total_usec:
                result['cpu_percent'] = min(usage_usec / total_usec * 100, 100)

        # cgroup v1
        if result['cpu_percent'] == 0:
            cgroup1_match = re.search(r'===CGROUP1===\s*\n(.*?)(?====LOAD===)', out, re.DOTALL)
            if cgroup1_match:
                for line in cgroup1_match.group(1).strip().splitlines():
                    if line.startswith('nr_periods'):
                        pass  # 需要两次采样才能算，这里用 top 快速估算

        # 如果 cgroup 采集失败，用 top 一次性采样
        if result['cpu_percent'] == 0:
            try:
                top_out = _exec_pod_cmd(conn,
                    "top -bn1 2>/dev/null | head -5 || true",
                    timeout=8
                )
                # %Cpu(s):  1.2 us,  0.3 sy,  0.0 ni, 98.5 id
                idle_match = re.search(r'(\d+\.?\d*)\s*id', top_out)
                if idle_match:
                    result['cpu_percent'] = round(100 - float(idle_match.group(1)), 1)
            except Exception:
                pass

        return result

    def _collect_mem(conn) -> dict:
        """采集内存指标"""
        out = _exec_pod_cmd(conn,
            "echo '===CGROUP2==='; "
            "cat /sys/fs/cgroup/memory.current 2>/dev/null || true; "
            "echo '===CGROUP2MAX==='; "
            "cat /sys/fs/cgroup/memory.max 2>/dev/null || true; "
            "echo '===CGROUP1==='; "
            "cat /sys/fs/cgroup/memory/memory.usage_in_bytes 2>/dev/null || true; "
            "echo '===CGROUP1LIMIT==='; "
            "cat /sys/fs/cgroup/memory/memory.limit_in_bytes 2>/dev/null || true; "
            "echo '===MEMINFO==='; "
            "head -5 /proc/meminfo 2>/dev/null || true",
            timeout=10
        )

        result = {'total': 0, 'used': 0, 'available': 0, 'percent': 0}

        # 尝试 cgroup v2
        cg2_usage_match = re.search(r'===CGROUP2===\s*\n(\d+)', out)
        cg2_max_match = re.search(r'===CGROUP2MAX===\s*\n(\S+)', out)

        usage = None
        limit = None

        if cg2_usage_match:
            usage = int(cg2_usage_match.group(1))
        if cg2_max_match:
            max_val = cg2_max_match.group(1).strip()
            limit = int(max_val) if max_val != 'max' else None

        # 尝试 cgroup v1
        if usage is None:
            cg1_usage_match = re.search(r'===CGROUP1===\s*\n(\d+)', out)
            if cg1_usage_match:
                usage = int(cg1_usage_match.group(1))

        if limit is None:
            cg1_limit_match = re.search(r'===CGROUP1LIMIT===\s*\n(\d+)', out)
            if cg1_limit_match:
                lim = int(cg1_limit_match.group(1))
                if lim < 2**60:  # 排除 unlimited
                    limit = lim

        # 回退到 /proc/meminfo
        if usage is None or limit is None:
            meminfo_match = re.search(r'===MEMINFO===\s*\n(.+?)(?=\n\n|\Z)', out, re.DOTALL)
            if meminfo_match:
                mem_total = None
                mem_available = None
                for line in meminfo_match.group(1).strip().splitlines():
                    parts = line.split()
                    if len(parts) >= 2:
                        key = parts[0].rstrip(':')
                        val = int(parts[1]) * 1024  # kB → bytes
                        if key == 'MemTotal':
                            mem_total = val
                        elif key == 'MemAvailable':
                            mem_available = val
                        elif key == 'MemFree' and mem_available is None:
                            mem_available = val

                if mem_total:
                    result['total'] = mem_total
                    result['used'] = mem_total - (mem_available or 0)
                    result['available'] = mem_available or 0
                    if mem_total > 0:
                        result['percent'] = round(result['used'] / mem_total * 100, 1)
                    return result

        if usage is not None and limit is not None and limit > 0:
            result['total'] = limit
            result['used'] = usage
            result['available'] = limit - usage
            result['percent'] = round(usage / limit * 100, 1)
        elif usage is not None:
            result['used'] = usage

        return result

    def _collect_disk(conn) -> dict:
        """采集磁盘指标"""
        out = _exec_pod_cmd(conn,
            "df -hP 2>/dev/null | grep -v '^Filesystem'",
            timeout=10
        )

        partitions = []
        for line in out.strip().splitlines():
            parts = line.split()
            if len(parts) >= 6:
                try:
                    mount = parts[-1]
                    pct_str = parts[-2].replace('%', '')
                    pct = float(pct_str)
                    # 解析大小
                    total = _parse_size(parts[-5])
                    used = _parse_size(parts[-4])
                    avail = _parse_size(parts[-3])
                    filesystem = ' '.join(parts[:-5])

                    partitions.append({
                        'device': filesystem,
                        'mount': mount,
                        'total': total,
                        'used': used,
                        'avail': avail,
                        'percent': pct,
                        'use_percent': pct,
                    })
                except (ValueError, IndexError):
                    continue

        return {'partitions': partitions}

    def _collect_net(conn) -> dict:
        """采集网络接口指标"""
        out = _exec_pod_cmd(conn,
            "cat /proc/net/dev 2>/dev/null",
            timeout=10
        )

        interfaces = []
        for line in out.strip().splitlines()[2:]:
            line = line.strip()
            if not line or ': lo:' in line or line.startswith('lo:'):
                continue
            parts = line.split()
            if len(parts) >= 11:
                iface = parts[0].rstrip(':')
                try:
                    interfaces.append({
                        'name': iface,
                        'bytes_recv': int(parts[1]),
                        'packets_recv': int(parts[2]),
                        'bytes_sent': int(parts[9]),
                        'packets_sent': int(parts[10]),
                    })
                except (ValueError, IndexError):
                    continue

        return {'interfaces': interfaces}

    def _collect_proc(conn) -> dict:
        """采集进程列表"""
        out = _exec_pod_cmd(conn,
            "ps aux 2>/dev/null || ps -ef 2>/dev/null",
            timeout=10
        )

        processes = []
        lines = out.strip().splitlines()
        if not lines:
            return {'processes': []}

        header = lines[0]
        is_aux = 'STAT' in header or 'VSZ' in header

        for line in lines[1:52]:  # skip header, max 50
            parts = line.split(None, 10)
            if len(parts) < 3:
                continue

            try:
                if is_aux and len(parts) >= 11:
                    # ps aux: USER PID %CPU %MEM VSZ RSS TTY STAT START TIME COMMAND
                    processes.append({
                        'pid': parts[1],
                        'name': parts[10][:60],
                        'cpu_percent': float(parts[2]),
                        'mem_percent': float(parts[3]),
                        'status': parts[7],
                    })
                elif len(parts) >= 5:
                    # ps -ef: UID PID PPID C STIME TTY TIME CMD
                    processes.append({
                        'pid': parts[1],
                        'name': parts[-1][:60] if parts[-1] else '?',
                        'cpu_percent': float(parts[3]) if parts[3].replace('.', '').isdigit() else 0,
                        'mem_percent': 0,
                        'status': '?',
                    })
            except (ValueError, IndexError):
                continue

        # 按 CPU 排序
        try:
            processes.sort(key=lambda p: p.get('cpu_percent', 0), reverse=True)
        except Exception:
            pass

        return {'processes': processes}

    def _collect_system_overview(conn) -> dict:
        """综合采集：CPU + 内存 + 磁盘 + 网络 + 进程"""
        import concurrent.futures

        result = {}

        def _safe_collect(fn, key):
            try:
                result[key] = fn(conn)
            except Exception as e:
                log.warning("_collect_system_overview: %s failed: %s", key, e)
                result[key] = {}

        # 并发采集（4 个维度），进程串行避免竞争
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = {
                executor.submit(_safe_collect, _collect_cpu, 'cpu'): 'cpu',
                executor.submit(_safe_collect, _collect_mem, 'memory'): 'memory',
                executor.submit(_safe_collect, _collect_disk, 'disk'): 'disk',
                executor.submit(_safe_collect, _collect_net, 'network'): 'network',
            }
            for f in concurrent.futures.as_completed(futures):
                f.result()  # 传播异常

        # 进程列表（TOP10）
        _safe_collect(_collect_proc, 'processes')

        return result

    def _parse_size(s: str) -> int:
        """解析 df -h 输出的大小字符串为字节数"""
        s = s.strip()
        if not s:
            return 0

        units = {
            'K': 1024, 'k': 1024,
            'M': 1024**2, 'm': 1024**2,
            'G': 1024**3, 'g': 1024**3,
            'T': 1024**4, 't': 1024**4,
            'Ki': 1024, 'ki': 1024,
            'Mi': 1024**2, 'mi': 1024**2,
            'Gi': 1024**3, 'gi': 1024**3,
        }

        for suffix, multiplier in units.items():
            if s.endswith(suffix):
                try:
                    return int(float(s[:-len(suffix)]) * multiplier)
                except ValueError:
                    return 0

        try:
            return int(s)
        except ValueError:
            return 0
