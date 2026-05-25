#!/usr/bin/env python3
"""
连接详情 API — Phase 5

提供连接详细信息、健康状态、TTL 配置、运行中任务、
手动健康检查触发、连接删除等接口。
"""
import logging
import time
from datetime import datetime
from typing import Optional

from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user

from models.db import db

log = logging.getLogger(__name__)

connection_detail_bp = Blueprint(
    "connection_detail",
    __name__,
    url_prefix="/api/connections",
)


# ── 辅助函数 ────────────────────────────────────────────────────────────────

def _check_permission(connection_id: str) -> bool:
    """检查当前用户是否有权访问指定连接。"""
    if current_user.is_admin:
        return True
    row = db.fetch_one(
        "SELECT user_id FROM connections WHERE id = ?",
        (connection_id,),
    )
    return row is not None and row.get("user_id") == current_user.id


def _error_response(message: str, code: int = 400):
    """统一错误响应格式。"""
    return jsonify({"code": code, "data": None, "message": message}), code


def _success_response(data, message: str = "success"):
    """统一成功响应格式。"""
    return jsonify({"code": 200, "data": data, "message": message})


# ── 连接详情 ────────────────────────────────────────────────────────────────

@connection_detail_bp.route("/<connection_id>/detail", methods=["GET"])
@login_required
def get_connection_detail(connection_id: str):
    """获取连接的详细信息。

    返回：连接基本信息、健康状态、可用操作列表、诊断能力入口。
    """
    if not _check_permission(connection_id):
        return _error_response("无权访问此连接", 403)

    row = db.fetch_one(
        "SELECT id, cluster_name, namespace, pod_name, container_name, "
        "level, local_port, java_pid, arthas_version, status, "
        "last_ping_at, last_active_at, ttl_hours, health_status, "
        "last_health_check, user_id, created_at, updated_at "
        "FROM connections WHERE id = ?",
        (connection_id,),
    )
    if not row:
        return _error_response("连接不存在", 404)

    # 构建可用诊断能力列表（与 PRD 一致）
    is_active = row.get("status") in ("ready", "connected", "recovered")
    diagnostic_capabilities = []
    if is_active:
        diagnostic_capabilities = [
            {"id": "terminal",    "label": "终端",      "icon": "🖥️", "url": "/terminal"},
            {"id": "monitor",     "label": "监控",      "icon": "📊", "url": "/monitor"},
            {"id": "filebrowser", "label": "文件下载",  "icon": "📂", "url": "/filebrowser"},
            {"id": "diagnose",    "label": "性能诊断",  "icon": "🔬", "url": "/diagnose"},
            {"id": "arthas_cmd",  "label": "Arthas 命令","icon": "⚡", "url": "/terminal"},
            {"id": "profiler",    "label": "采样工具",  "icon": "🔥", "url": "/profiler"},
        ]

    # 构建可用操作按钮（健康检查、重新连接、删除连接）
    operation_actions = [
        {"id": "health_check", "label": "健康检查", "icon": "💓", "enabled": True},
        {"id": "reconnect",    "label": "重新连接", "icon": "🔄", "enabled": is_active},
        {"id": "delete",       "label": "删除连接", "icon": "🗑️", "enabled": True},
    ]

    data = {
        "id": row.get("id", ""),
        "cluster_name": row.get("cluster_name", ""),
        "namespace": row.get("namespace", ""),
        "pod_name": row.get("pod_name", ""),
        "container_name": row.get("container_name", ""),
        "level": row.get("level", "arthas"),
        "local_port": row.get("local_port"),
        "java_pid": row.get("java_pid"),
        "arthas_version": row.get("arthas_version", ""),
        "status": row.get("status", "unknown"),
        "health_status": row.get("health_status", "unknown"),
        "last_ping_at": row.get("last_ping_at"),
        "last_active_at": row.get("last_active_at"),
        "last_health_check": row.get("last_health_check"),
        "ttl_hours": row.get("ttl_hours", 0),
        "user_id": row.get("user_id"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "diagnostic_capabilities": diagnostic_capabilities,
        "operation_actions": operation_actions,
        "is_active": is_active,
    }

    return _success_response(data)


# ── 健康检查状态 ────────────────────────────────────────────────────────────

@connection_detail_bp.route("/<connection_id>/health", methods=["GET"])
@login_required
def get_connection_health(connection_id: str):
    """获取指定连接的健康检查状态。

    返回：健康状态、延迟、最后检查时间。
    """
    if not _check_permission(connection_id):
        return _error_response("无权访问此连接", 403)

    # 先从数据库读取持久化的健康状态
    row = db.fetch_one(
        "SELECT health_status, last_health_check FROM connections WHERE id = ?",
        (connection_id,),
    )
    if not row:
        return _error_response("连接不存在", 404)

    data = {
        "connection_id": connection_id,
        "health_status": row.get("health_status", "unknown"),
        "last_health_check": row.get("last_health_check"),
        "latency_ms": None,
    }

    # 尝试从内存缓存获取更精确的数据
    try:
        from server import _conn_health, _conn_health_lock
        with _conn_health_lock:
            cached = _conn_health.get(connection_id)
            if cached:
                data["health_status"] = cached.get("status", data["health_status"])
                data["last_health_check"] = cached.get(
                    "last_check_at", data["last_health_check"]
                )
                data["latency_ms"] = cached.get("latency_ms")
    except (ImportError, Exception):
        pass

    return _success_response(data)


@connection_detail_bp.route("/<connection_id>/health", methods=["POST"])
@login_required
def trigger_health_check(connection_id: str):
    """手动触发指定连接的健康检查。

    通过 HTTP 探活检测 Arthas 端口可达性，立即返回检查结果。
    """
    if not _check_permission(connection_id):
        return _error_response("无权访问此连接", 403)

    row = db.fetch_one(
        "SELECT id, status, local_port, namespace, pod_name, cluster_name "
        "FROM connections WHERE id = ?",
        (connection_id,),
    )
    if not row:
        return _error_response("连接不存在", 404)

    # 仅对活跃连接执行健康检查
    if row.get("status") not in ("ready", "connected", "recovered"):
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db.update(
            "connections",
            {
                "health_status": "disconnected",
                "last_health_check": now_str,
                "updated_at": now_str,
            },
            "id = ?",
            (connection_id,),
        )
        return _success_response({
            "connection_id": connection_id,
            "health_status": "disconnected",
            "latency_ms": None,
            "last_health_check": now_str,
            "message": "连接状态不活跃，无法执行健康检查",
        })

    import requests as http_requests
    local_port = row.get("local_port")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if not local_port:
        # 没有端口信息，标记为 unknown
        db.update(
            "connections",
            {
                "health_status": "unknown",
                "last_health_check": now_str,
                "updated_at": now_str,
            },
            "id = ?",
            (connection_id,),
        )
        return _success_response({
            "connection_id": connection_id,
            "health_status": "unknown",
            "latency_ms": None,
            "last_health_check": now_str,
            "message": "缺少端口信息，无法执行健康检查",
        })

    # 执行 HTTP 探活
    start_ts = time.time()
    health_status = "healthy"
    error_msg = None

    try:
        url = f"http://127.0.0.1:{local_port}/"
        resp = http_requests.get(url, timeout=5)
        latency_ms = round((time.time() - start_ts) * 1000, 1)
        if resp.status_code >= 400:
            health_status = "unhealthy"
            error_msg = f"HTTP {resp.status_code}"
    except http_requests.exceptions.Timeout:
        latency_ms = round((time.time() - start_ts) * 1000, 1)
        health_status = "unhealthy"
        error_msg = "请求超时"
    except http_requests.exceptions.ConnectionError:
        latency_ms = None
        health_status = "unhealthy"
        error_msg = "连接失败"
    except Exception as e:
        latency_ms = None
        health_status = "unhealthy"
        error_msg = str(e)

    # 更新数据库
    db.update(
        "connections",
        {
            "health_status": health_status,
            "last_health_check": now_str,
            "updated_at": now_str,
        },
        "id = ?",
        (connection_id,),
    )

    # 记录健康检查日志
    try:
        db.insert(
            "health_check_logs",
            {
                "connection_id": connection_id,
                "status": health_status,
                "latency_ms": latency_ms,
                "error_message": error_msg,
                "checked_at": now_str,
            },
        )
    except Exception as e:
        log.warning("[HealthCheck] 记录日志失败: %s", e)

    # 同步更新内存缓存
    try:
        from server import _conn_health, _conn_health_lock
        with _conn_health_lock:
            _conn_health[connection_id] = {
                "status": health_status,
                "latency_ms": latency_ms,
                "last_check_at": now_str,
            }
    except (ImportError, Exception):
        pass

    log.info(
        "[HealthCheck] 手动检查 %s: %s, latency=%sms, error=%s",
        connection_id, health_status, latency_ms, error_msg,
    )

    return _success_response({
        "connection_id": connection_id,
        "health_status": health_status,
        "latency_ms": latency_ms,
        "last_health_check": now_str,
        "error_message": error_msg,
    })


# ── TTL 配置 ────────────────────────────────────────────────────────────────

@connection_detail_bp.route("/<connection_id>/ttl", methods=["PUT"])
@login_required
def update_connection_ttl(connection_id: str):
    """更新指定连接的 TTL 配置。

    请求体: {"ttl_hours": 8}
    返回：更新后的 TTL 配置
    """
    if not _check_permission(connection_id):
        return _error_response("无权访问此连接", 403)

    d = request.json or {}
    ttl_hours = d.get("ttl_hours")

    if ttl_hours is None:
        return _error_response("缺少 ttl_hours 参数")

    try:
        from services.connection_ttl_config import ConnectionTTLConfig
        ttl_svc = ConnectionTTLConfig(db)
        result = ttl_svc.set_connection_ttl(connection_id, ttl_hours)
        if result.get("ok"):
            return _success_response(result)
        else:
            return _error_response(result.get("error", "设置失败"))
    except Exception as e:
        log.error("[ConnectionDetail] 设置 TTL 失败: %s", e, exc_info=True)
        return _error_response(f"设置失败: {str(e)}", 500)


@connection_detail_bp.route("/<connection_id>/ttl", methods=["GET"])
@login_required
def get_connection_ttl(connection_id: str):
    """获取指定连接的当前 TTL 配置及可用预设选项。"""
    if not _check_permission(connection_id):
        return _error_response("无权访问此连接", 403)

    try:
        from services.connection_ttl_config import ConnectionTTLConfig
        ttl_svc = ConnectionTTLConfig(db)
        current_ttl = ttl_svc.get_connection_ttl(connection_id)
        presets = ttl_svc.get_preset_options()

        data = {
            "connection_id": connection_id,
            "ttl_hours": current_ttl,
            "preset_options": presets,
        }
        return _success_response(data)
    except Exception as e:
        log.error("[ConnectionDetail] 获取 TTL 配置失败: %s", e, exc_info=True)
        return _error_response(f"获取失败: {str(e)}", 500)


# ── 运行中的任务 ────────────────────────────────────────────────────────────

@connection_detail_bp.route("/<connection_id>/running-tasks", methods=["GET"])
@login_required
def get_running_tasks(connection_id: str):
    """获取指定连接的运行中诊断任务列表。"""
    if not _check_permission(connection_id):
        return _error_response("无权访问此连接", 403)

    rows = db.fetch_all(
        "SELECT id, type, event, status, progress, created_at, updated_at "
        "FROM profiler_tasks WHERE connection_id = ? AND status IN (?, ?) "
        "ORDER BY created_at DESC",
        (connection_id, "running", "starting"),
    )

    tasks = []
    for row in (rows or []):
        tasks.append({
            "id": row.get("id", ""),
            "type": row.get("type", ""),
            "event": row.get("event", ""),
            "status": row.get("status", ""),
            "progress": row.get("progress", 0),
            "created_at": row.get("created_at", ""),
            "updated_at": row.get("updated_at", ""),
        })

    return _success_response({
        "connection_id": connection_id,
        "tasks": tasks,
        "count": len(tasks),
    })


# ── 连接切换 ────────────────────────────────────────────────────────────────

@connection_detail_bp.route("/<connection_id>/switch", methods=["POST"])
@login_required
def switch_connection(connection_id: str):
    """从当前连接切换到目标连接。

    请求体: {"target_connection_id": "new_conn_id"}
    返回：切换结果

    流程：
    1. 验证权限
    2. 检查目标连接是否存在
    3. 取消当前连接的运行中任务（可选）
    4. 返回切换结果（前端负责实际切换）
    """
    if not _check_permission(connection_id):
        return _error_response("无权访问此连接", 403)

    d = request.json or {}
    target_id = d.get("target_connection_id", "")

    if not target_id:
        return _error_response("缺少 target_connection_id 参数")

    if target_id == connection_id:
        return _error_response("不能切换到同一个连接")

    # 检查目标连接是否存在
    target_row = db.fetch_one(
        "SELECT id, status, health_status FROM connections WHERE id = ?",
        (target_id,),
    )
    if not target_row:
        return _error_response("目标连接不存在", 404)

    # 检查目标连接的用户权限
    if not _check_permission(target_id):
        return _error_response("无权访问目标连接", 403)

    # 获取当前连接运行中的任务
    running_tasks = db.fetch_all(
        "SELECT id FROM profiler_tasks WHERE connection_id = ? AND status IN (?, ?)",
        (connection_id, "running", "starting"),
    )

    cancel_tasks = d.get("cancel_tasks", False)

    cancelled_tasks = []
    if running_tasks and cancel_tasks:
        for task in running_tasks:
            task_id = task.get("id", "")
            if task_id:
                db.update(
                    "profiler_tasks",
                    {
                        "status": "cancelled",
                        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    },
                    "id = ?",
                    (task_id,),
                )
                cancelled_tasks.append(task_id)
        log.info(
            "[ConnectionSwitch] 连接 %s 切换到 %s，取消了 %d 个任务",
            connection_id,
            target_id,
            len(cancelled_tasks),
        )

    data = {
        "ok": True,
        "source_connection_id": connection_id,
        "target_connection_id": target_id,
        "target_status": target_row.get("status", "unknown"),
        "target_health": target_row.get("health_status", "unknown"),
        "had_running_tasks": len(running_tasks) > 0 if running_tasks else False,
        "cancelled_tasks": cancelled_tasks,
        "message": "切换成功" if not cancelled_tasks else f"已取消 {len(cancelled_tasks)} 个任务并切换",
    }

    return _success_response(data)


# ── 删除连接 ────────────────────────────────────────────────────────────────

@connection_detail_bp.route("/<connection_id>", methods=["DELETE"])
@login_required
def delete_connection(connection_id: str):
    """删除指定连接。

    删除前会检查是否有运行中的任务，如有则拒绝删除。
    """
    if not _check_permission(connection_id):
        return _error_response("无权访问此连接", 403)

    row = db.fetch_one(
        "SELECT id, status, cluster_name, pod_name, namespace FROM connections WHERE id = ?",
        (connection_id,),
    )
    if not row:
        return _error_response("连接不存在", 404)

    # 检查是否有运行中的任务
    running_tasks = db.fetch_all(
        "SELECT id, type, event FROM profiler_tasks "
        "WHERE connection_id = ? AND status IN (?, ?)",
        (connection_id, "running", "starting"),
    )
    if running_tasks:
        task_list = [
            {"id": t.get("id"), "type": t.get("type"), "event": t.get("event")}
            for t in running_tasks
        ]
        return _error_response(
            "该连接有运行中的诊断任务，请先停止或等待任务完成后删除",
            409,
        )

    # 执行删除
    try:
        # 尝试断开 Arthas 连接
        try:
            from backend import ArthasConnection
            conn_obj = ArthasConnection.load(connection_id)
            if conn_obj:
                conn_obj.close()
                log.info("[ConnectionDetail] 已关闭 Arthas 连接: %s", connection_id)
        except Exception as e:
            log.debug("[ConnectionDetail] 关闭 Arthas 连接失败 (可忽略): %s", e)

        db.delete("connections", "id = ?", (connection_id,))

        log.info(
            "[ConnectionDetail] 连接已删除: %s (集群=%s, Pod=%s, 命名空间=%s)",
            connection_id,
            row.get("cluster_name", ""),
            row.get("pod_name", ""),
            row.get("namespace", ""),
        )

        # 记录审计日志
        try:
            from services.audit_service import AuditService
            audit = AuditService(db)
            audit.log_action(
                current_user.id,
                "connection_delete",
                f"删除连接 {connection_id} ({row.get('pod_name', '')})",
            )
        except Exception as e:
            log.debug("[ConnectionDetail] 记录审计日志失败: %s", e)

        # 通知内存缓存清理
        try:
            from server import _conn_health, _conn_health_lock
            with _conn_health_lock:
                _conn_health.pop(connection_id, None)
        except (ImportError, Exception):
            pass

        return _success_response({
            "ok": True,
            "deleted_id": connection_id,
            "message": f"连接 {connection_id} 已删除",
        })
    except Exception as e:
        log.error("[ConnectionDetail] 删除连接失败: %s", e, exc_info=True)
        return _error_response(f"删除失败: {str(e)}", 500)


# ── 重新连接 ────────────────────────────────────────────────────────────────

@connection_detail_bp.route("/<connection_id>/reconnect", methods=["POST"])
@login_required
def reconnect_connection(connection_id: str):
    """重新建立与目标连接的 Arthas 代理。

    执行探活验证连接可达性，成功则更新状态，失败则标记异常。
    """
    if not _check_permission(connection_id):
        return _error_response("无权访问此连接", 403)

    row = db.fetch_one(
        "SELECT id, status, local_port, namespace, pod_name, cluster_name "
        "FROM connections WHERE id = ?",
        (connection_id,),
    )
    if not row:
        return _error_response("连接不存在", 404)

    local_port = row.get("local_port")
    if not local_port:
        return _error_response("缺少本地端口信息，无法重新连接")

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    import requests as http_requests

    # 执行 HTTP 探活
    start_ts = time.time()
    try:
        url = f"http://127.0.0.1:{local_port}/"
        resp = http_requests.get(url, timeout=10)
        latency_ms = round((time.time() - start_ts) * 1000, 1)
        if resp.status_code < 400:
            # 探活成功，更新状态
            db.update(
                "connections",
                {
                    "status": "ready",
                    "health_status": "healthy",
                    "last_ping_at": now_str,
                    "last_health_check": now_str,
                    "last_active_at": now_str,
                    "updated_at": now_str,
                },
                "id = ?",
                (connection_id,),
            )
            log.info("[ConnectionDetail] 重新连接成功: %s", connection_id)
            return _success_response({
                "ok": True,
                "status": "ready",
                "health_status": "healthy",
                "latency_ms": latency_ms,
                "message": "重新连接成功",
            })
        else:
            raise Exception(f"HTTP {resp.status_code}")
    except Exception as e:
        latency_ms = round((time.time() - start_ts) * 1000, 1) if time.time() - start_ts < 10 else None
        db.update(
            "connections",
            {
                "status": "disconnected",
                "health_status": "unhealthy",
                "last_health_check": now_str,
                "updated_at": now_str,
            },
            "id = ?",
            (connection_id,),
        )
        log.warning("[ConnectionDetail] 重新连接失败: %s, error=%s", connection_id, e)
        return _error_response(f"重新连接失败: {str(e)}")
