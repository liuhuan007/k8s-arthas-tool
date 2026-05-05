#!/usr/bin/env python3
"""热更新 API — jad → 编辑/上传 → mc → redefine → 验证"""
import logging
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user

from services.hotfix_service import HotfixService
from services.audit_service import AuditService
from services.authorization_service import AuthorizationService
from backend.core.connection import ArthasConnection

log = logging.getLogger(__name__)

hotfix_bp = Blueprint('hotfix', __name__, url_prefix='/api/hotfix')

# 全局服务实例
_hotfix_service = HotfixService()


def _get_connection(conn_id: str):
    """从全局连接池获取连接,支持自动重建"""
    try:
        from server import _connections, _connections_lock, _ensure_connection
    except ImportError:
        return None, "服务未初始化"
    
    # ✅ 第一步: 尝试从内存获取
    with _connections_lock:
        available = list(_connections.keys())
        log.info(f"[_get_connection] 查找 conn_id={conn_id}, 可用连接: {available}")
        
        if conn_id in _connections:
            entry = _connections[conn_id]
            log.info(f"[_get_connection] 内存中找到连接, entry.user_id={entry.get('user_id')}, current_user.id={current_user.id}")
            
            # 检查权限
            if entry.get('user_id') != current_user.id and not current_user.is_admin:
                log.warning(f"[权限拒绝] conn_id={conn_id}, entry.user_id={entry.get('user_id')}, current_user.id={current_user.id}")
                return None, "无权操作此连接"
            
            conn = entry.get('conn')
            if not conn:
                return None, "连接对象为空"
            
            # ✅ 关键修复: 验证 Arthas 连接是否完整
            if not hasattr(conn, 'http_client') or conn.http_client is None:
                log.warning(f"[_get_connection] 连接不完整, http_client=None, 删除并重建 conn_id={conn_id}")
                # 删除不完整的连接
                with _connections_lock:
                    if conn_id in _connections:
                        del _connections[conn_id]
                # 继续执行后续的重建逻辑
            else:
                return conn, None
    
    # ✅ 第二步: 内存中不存在,尝试自动重建
    log.info(f"[_get_connection] 内存中未找到,尝试自动重建 conn_id={conn_id}")
    
    # 从 conn_id 解析连接信息
    parts = conn_id.split('/')
    if len(parts) < 3:
        return None, f"连接不存在 (conn_id={conn_id})"
    
    cluster_name = parts[0]
    namespace = parts[1]
    pod_name = parts[2]
    
    # 调用 _ensure_connection 自动重建
    d = {
        'cluster_name': cluster_name,
        'namespace': namespace,
        'pod_name': pod_name,
        'container': ''
    }
    
    try:
        conn, err = _ensure_connection(conn_id, d)
        if err:
            log.warning(f"[_get_connection] 自动重建失败: {err}")
            return None, f"连接已丢失，请重新建立连接: {err}"
        
        log.info(f"[_get_connection] 自动重建成功 conn_id={conn_id}")
        return conn, None
    except Exception as e:
        log.exception(f"[_get_connection] 自动重建异常: {e}")
        return None, f"连接已丢失，请重新建立连接: {str(e)}"


# ── jad: 一键查看源码 ──────────────────────────────────────────────────────

@hotfix_bp.route('/jad', methods=['POST'])
@login_required
def hotfix_jad():
    """一键查看目标类源码"""
    d = request.json or {}
    conn_id = d.get('connection_id', '')
    class_name = d.get('class_name', '')

    log.info(f"[Hotfix jad] 收到请求: conn_id={conn_id}, class_name={class_name}, user_id={current_user.id}")

    if not conn_id or not class_name:
        return jsonify({"error": "connection_id 和 class_name 为必填项"}), 400

    conn, err = _get_connection(conn_id)
    if err:
        log.warning(f"[Hotfix jad] 连接获取失败: {err}")
        return jsonify({"error": err}), 400

    log.info(f"[Hotfix jad] 连接获取成功, 开始执行 jad")

    # 执行 jad
    result = _hotfix_service.execute_jad(
        connection=conn,
        class_name=class_name,
        connection_id=conn_id,
        user_id=current_user.id
    )

    # 记录审计
    if result.get('ok'):
        AuditService.log_event(
            user_id=current_user.id,
            action='hotfix_jad',
            resource_type='hotfix',
            resource_id=conn_id,
            details=f'jad 查看源码: {class_name}'
        )
        return jsonify(result), 200
    else:
        return jsonify(result), 400


# ── upload: 上传文件 ───────────────────────────────────────────────────────

@hotfix_bp.route('/upload', methods=['POST'])
@login_required
def hotfix_upload():
    """上传 .java 或 .class 文件到受控目录"""
    conn_id = request.form.get('connection_id', '')
    
    if not conn_id:
        return jsonify({"error": "connection_id 为必填项"}), 400

    if 'file' not in request.files:
        return jsonify({"error": "未找到上传文件"}), 400

    file = request.files['file']
    if not file or not file.filename:
        return jsonify({"error": "文件名为空"}), 400

    # 验证文件类型
    if not file.filename.endswith(('.java', '.class')):
        return jsonify({"error": "仅支持 .java 或 .class 文件"}), 400

    # 读取文件内容
    file_content = file.read()

    # 上传文件
    result = _hotfix_service.upload_file(
        connection_id=conn_id,
        file_content=file_content,
        filename=file.filename,
        user_id=current_user.id
    )

    # 记录审计
    if result.get('ok'):
        AuditService.log_event(
            user_id=current_user.id,
            action='hotfix_upload',
            resource_type='hotfix',
            resource_id=conn_id,
            details=f'上传文件: {file.filename} (sha256: {result.get("sha256", "")[:16]}...)'
        )
        return jsonify(result), 200
    else:
        return jsonify(result), 400


# ── save-edit: 保存在线编辑内容 ───────────────────────────────────────────

@hotfix_bp.route('/save-edit', methods=['POST'])
@login_required
def hotfix_save_edit():
    """保存在线编辑的 Java 源码到文件"""
    conn_id = request.form.get('connection_id', '')
    file_path = request.form.get('file_path', '')
    content = request.form.get('content', '')

    if not conn_id or not file_path or not content:
        return jsonify({"error": "connection_id, file_path 和 content 为必填项"}), 400

    conn, err = _get_connection(conn_id)
    if err:
        return jsonify({"error": err}), 400

    # 保存编辑内容
    result = _hotfix_service.save_edit_content(
        connection=conn,
        file_path=file_path,
        content=content,
        connection_id=conn_id,
        user_id=current_user.id
    )

    # 记录审计
    if result.get('ok'):
        AuditService.log_event(
            user_id=current_user.id,
            action='hotfix_save_edit',
            resource_type='hotfix',
            resource_id=conn_id,
            details=f'保存编辑内容: {file_path} ({len(content)} bytes)'
        )
        return jsonify(result), 200
    else:
        return jsonify(result), 400


# ── compile: mc 编译 ───────────────────────────────────────────────────────

@hotfix_bp.route('/compile', methods=['POST'])
@login_required
def hotfix_compile():
    """对 .java 执行 Arthas mc 编译"""
    d = request.json or {}
    conn_id = d.get('connection_id', '')
    java_file_path = d.get('java_file_path', '')

    if not conn_id or not java_file_path:
        return jsonify({"error": "connection_id 和 java_file_path 为必填项"}), 400

    conn, err = _get_connection(conn_id)
    if err:
        return jsonify({"error": err}), 400

    # 执行 mc
    result = _hotfix_service.execute_mc(
        connection=conn,
        java_file_path=java_file_path,
        connection_id=conn_id,
        user_id=current_user.id
    )

    # 记录审计
    if result.get('ok'):
        AuditService.log_event(
            user_id=current_user.id,
            action='hotfix_compile',
            resource_type='hotfix',
            resource_id=conn_id,
            details=f'mc 编译: {java_file_path}'
        )
        return jsonify(result), 200
    else:
        return jsonify(result), 400


# ── redefine: 热更新 ───────────────────────────────────────────────────────

@hotfix_bp.route('/redefine', methods=['POST'])
@login_required
def hotfix_redefine():
    """对 .class 执行 Arthas redefine"""
    d = request.json or {}
    conn_id = d.get('connection_id', '')
    # ✅ 兼容前端 class_file 参数
    class_file_path = d.get('class_file_path', '') or d.get('class_file', '')
    # ✅ 去掉 confirm 验证,直接执行
    confirmed = True  # 默认已确认

    conn, err = _get_connection(conn_id)
    if err:
        return jsonify({"error": err}), 400

    # 执行 redefine
    result = _hotfix_service.execute_redefine(
        connection=conn,
        class_file_path=class_file_path,
        connection_id=conn_id,
        user_id=current_user.id
    )

    # 记录审计
    if result.get('ok'):
        AuditService.log_event(
            user_id=current_user.id,
            action='hotfix_redefine',
            resource_type='hotfix',
            resource_id=conn_id,
            details=f'redefine: {class_file_path} (sha256: {result.get("sha256", "")[:16]}...)'
        )
        return jsonify(result), 200
    else:
        return jsonify(result), 400


# ── artifacts: 查询产物 ────────────────────────────────────────────────────

@hotfix_bp.route('/artifacts', methods=['GET'])
@login_required
def hotfix_artifacts():
    """查看当前连接最近的源码、class、编译输出和 redefine 输出文件"""
    conn_id = request.args.get('connection_id', '')
    limit = int(request.args.get('limit', '20'))

    if not conn_id:
        return jsonify({"error": "connection_id 为必填项"}), 400

    # 验证连接归属
    _, err = _get_connection(conn_id)
    if err:
        return jsonify({"error": err}), 400

    # 查询产物
    result = _hotfix_service.list_artifacts(
        connection_id=conn_id,
        limit=limit
    )

    return jsonify(result), 200


# ── limitations: 获取 redefine 限制 ────────────────────────────────────────

@hotfix_bp.route('/limitations', methods=['GET'])
@login_required
def hotfix_limitations():
    """获取 redefine 8 项技术限制"""
    limitations = _hotfix_service.get_redefine_limitations()
    return jsonify({
        "ok": True,
        "limitations": limitations
    }), 200


# ── verification: 生成验证报告 ─────────────────────────────────────────────

@hotfix_bp.route('/verification', methods=['POST'])
@login_required
def hotfix_verification():
    """生成验证报告"""
    d = request.json or {}
    conn_id = d.get('connection_id', '')
    timestamp = d.get('timestamp', '')
    class_name = d.get('class_name', '')
    old_source = d.get('old_source', '')
    new_source = d.get('new_source', '')
    redefine_output = d.get('redefine_output', '')

    if not conn_id or not timestamp or not class_name:
        return jsonify({"error": "connection_id、timestamp 和 class_name 为必填项"}), 400

    # 验证连接归属
    _, err = _get_connection(conn_id)
    if err:
        return jsonify({"error": err}), 400

    # 生成验证报告
    result = _hotfix_service.generate_verification_report(
        connection_id=conn_id,
        timestamp=timestamp,
        class_name=class_name,
        old_source=old_source,
        new_source=new_source,
        redefine_output=redefine_output
    )

    # 记录审计
    if result.get('ok'):
        AuditService.log_event(
            user_id=current_user.id,
            action='hotfix_verification',
            resource_type='hotfix',
            resource_id=conn_id,
            details=f'生成验证报告: {class_name}'
        )
        return jsonify(result), 200
    else:
        return jsonify(result), 400
