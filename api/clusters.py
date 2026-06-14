#!/usr/bin/env python3
"""集群管理 API"""
import json
import threading
from flask import Blueprint, request, jsonify
from flask_login import current_user, login_required
from functools import wraps
from pathlib import Path

from models.db import db
from services.authorization_service import AuthorizationService
from services.cache_service import query_cache, invalidate_cluster_cache

# 集群配置文件读写锁
_clusters_lock = threading.Lock()


def admin_required(f):
    """Admin 权限装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            return jsonify({'error': '需要管理员权限'}), 403
        return f(*args, **kwargs)
    return decorated_function


# 加载集群配置的辅助函数
def _load_clusters() -> list:
    """加载集群配置"""
    from backend.config import Config
    p = Path(Config.CLUSTERS_FILE)
    if p.exists():
        with open(p, encoding='utf-8') as f:
            return json.load(f)
    return []


def _save_clusters(clusters: list):
    """保存集群配置（线程安全）"""
    from backend.config import Config
    with _clusters_lock:
        with open(Config.CLUSTERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(clusters, f, indent=2, ensure_ascii=False)


clusters_bp = Blueprint('clusters', __name__, url_prefix='/api')


def _check_cluster_access(cluster_id: str):
    """检查当前用户是否有权访问指定集群，返回集群配置或错误"""
    clusters = _load_clusters()
    # 优先用 id 查找，没有则用 name 查找
    cluster = next((c for c in clusters if c.get('id') == cluster_id or c.get('name') == cluster_id), None)
    
    if not cluster:
        return None, {'error': '集群不存在'}, 404
    
    # 非 admin 检查是否有权访问
    if not current_user.is_admin:
        user_clusters = db.fetch_all(
            'SELECT cluster_id FROM user_clusters WHERE user_id = ?',
            (current_user.id,)
        )
        allowed = {r['cluster_id'] for r in user_clusters}
        if cluster.get('id') not in allowed:
            return None, {'error': '无权访问此集群'}, 403
    
    return cluster, None, 0


@clusters_bp.route('/clusters', methods=['GET'])
@login_required
def list_clusters():
    """获取集群列表"""
    # Build a user-scoped cache key
    cache_key = f"list_clusters:admin={current_user.is_admin}:uid={current_user.id}"
    cached_result = query_cache.get(cache_key)
    if cached_result is not None:
        return jsonify(cached_result)

    clusters = _load_clusters()

    # 非管理员只返回分配的集群
    if not current_user.is_admin:
        user_clusters = db.fetch_all(
            'SELECT cluster_id FROM user_clusters WHERE user_id = ?',
            (current_user.id,)
        )
        allowed = {r['cluster_id'] for r in user_clusters}
        clusters = [c for c in clusters if c.get('id') in allowed]

    result = {'clusters': clusters}
    query_cache.set(cache_key, result, ttl=300)
    return jsonify(result)


@clusters_bp.route('/clusters', methods=['POST'])
@login_required
@admin_required
def create_cluster():
    """创建集群（仅 admin）"""
    data = request.json or {}
    name = data.get('name', '').strip()
    kubeconfig = data.get('kubeconfig', '').strip()
    context = data.get('context', '').strip()
    
    if not name:
        return jsonify({'error': '集群名称必填'}), 400
    
    clusters = _load_clusters()
    
    # 检查是否已存在
    if any(c.get('name') == name for c in clusters):
        return jsonify({'error': '集群名称已存在'}), 400
    
    # 生成 ID
    import uuid
    cluster_id = str(uuid.uuid4())[:8]
    
    clusters.append({
        'id': cluster_id,
        'name': name,
        'kubeconfig': kubeconfig,
        'context': context
    })
    
    _save_clusters(clusters)

    # 同步到数据库
    db.insert('clusters', {
        'id': cluster_id,
        'name': name,
        'kubeconfig': kubeconfig,
        'context': context,
    })

    invalidate_cluster_cache()
    return jsonify({'ok': True, 'id': cluster_id}), 201


@clusters_bp.route('/clusters/<cluster_id>', methods=['PUT', 'POST'])
@login_required
@admin_required
def update_cluster(cluster_id: str):
    """更新集群（仅 admin）"""
    data = request.json or {}
    name = data.get('name', '').strip()
    kubeconfig = data.get('kubeconfig', '').strip()
    context = data.get('context', '').strip()
    
    clusters = _load_clusters()
    
    # 优先用 id 查找，没有则用 name 查找
    target = next((c for c in clusters if c.get('id') == cluster_id or c.get('name') == cluster_id), None)
    
    if not target:
        return jsonify({'error': '集群不存在'}), 404
    
    if name:
        target['name'] = name
    if kubeconfig is not None:
        target['kubeconfig'] = kubeconfig
    if context is not None:
        target['context'] = context
    
    _save_clusters(clusters)
    
    # 同步到数据库
    update_data = {}
    if name:
        update_data['name'] = name
    if kubeconfig is not None:
        update_data['kubeconfig'] = kubeconfig
    if context is not None:
        update_data['context'] = context
    if update_data:
        db.update('clusters', update_data, 'id = ?', (target.get('id', cluster_id),))

    invalidate_cluster_cache()
    return jsonify({'ok': True})


@clusters_bp.route('/clusters/<cluster_id>', methods=['DELETE'])
@login_required
@admin_required
def delete_cluster(cluster_id: str):
    """删除集群（仅 admin）"""
    clusters = _load_clusters()
    
    # 优先用 id 查找，没有则用 name 查找
    clusters = [c for c in clusters if c.get('id') != cluster_id and c.get('name') != cluster_id]
    
    _save_clusters(clusters)
    
    # 删除相关的用户分配
    db.delete('user_clusters', 'cluster_id = ?', (cluster_id,))
    
    # 从数据库删除集群
    db.delete('clusters', 'id = ? OR name = ?', (cluster_id, cluster_id))

    invalidate_cluster_cache()
    return jsonify({'ok': True})


@clusters_bp.route('/clusters/<cluster_id>/test', methods=['POST'])
@login_required
def test_cluster(cluster_id: str):
    """测试集群连接"""
    from backend.core.kubectl import KubectlExecutor
    
    cluster, err, code = _check_cluster_access(cluster_id)
    if err:
        return jsonify(err), code
    
    runner = KubectlExecutor(
        kubeconfig=cluster.get('kubeconfig', ''),
        context=cluster.get('context', ''),
    )
    
    try:
        ok, msg = runner.cluster_info()
        if ok:
            return jsonify({'ok': True, 'message': '连接成功'})
        else:
            return jsonify({'ok': False, 'error': _parse_kubectl_error(msg) or msg or '连接失败'}), 400
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400


def _parse_kubectl_error(stderr: str) -> str:
    """解析 kubectl stderr，返回用户友好的错误信息"""
    if 'the server has asked for the client to provide credentials' in stderr:
        return 'kubectl 认证失败：kubeconfig 中的凭据无效或已过期，请更新 kubeconfig 配置'
    if 'Unable to connect to the server' in stderr:
        return 'kubectl 无法连接到集群，请检查网络和 kubeconfig 配置'
    if 'No resources found' in stderr:
        return ''
    # 从多行 stderr 中提取关键错误信息（跳过 memcache.go 等库内部日志）
    lines = stderr.strip().splitlines()
    meaningful = [l for l in lines if 'memcache.go' not in l and 'Unhandled Error' not in l]
    return meaningful[-1].strip() if meaningful else stderr.strip()[:200]


@clusters_bp.route('/clusters/<cluster_id>/namespaces', methods=['GET'])
@login_required
def list_namespaces(cluster_id: str):
    """获取命名空间列表"""
    from backend.core.kubectl import KubectlExecutor
    
    cluster, err, code = _check_cluster_access(cluster_id)
    if err:
        return jsonify(err), code
    
    runner = KubectlExecutor(
        kubeconfig=cluster.get('kubeconfig', ''),
        context=cluster.get('context', ''),
    )
    
    try:
        rc, out, stderr = runner._run(["get", "ns", "-o", "json"], timeout=10)
        if rc == 0:
            data = json.loads(out)
            ns_list = [item['metadata']['name'] for item in data.get('items', [])]
            ns_list = AuthorizationService.filter_namespaces(current_user, cluster.get('id') or cluster_id, ns_list)
            return jsonify({'namespaces': ns_list})
        else:
            return jsonify({'error': _parse_kubectl_error(stderr) or '获取命名空间列表失败'}), 400
    except json.JSONDecodeError:
        return jsonify({'error': '解析失败'}), 400


@clusters_bp.route('/clusters/<cluster_id>/pods', methods=['GET'])
@login_required
def list_pods(cluster_id: str):
    """获取 Pod 列表"""
    from backend.core.kubectl import KubectlExecutor
    
    cluster, err, code = _check_cluster_access(cluster_id)
    if err:
        return jsonify(err), code
    
    namespace = request.args.get('namespace', 'default')
    if not AuthorizationService.can_access_namespace(current_user, cluster.get('id') or cluster_id, namespace):
        return jsonify({'error': '无权访问该 namespace'}), 403
    
    runner = KubectlExecutor(
        kubeconfig=cluster.get('kubeconfig', ''),
        context=cluster.get('context', ''),
    )
    
    try:
        rc, out, stderr = runner._run(["-n", namespace, "get", "pods", "-o", "json"], timeout=15)
        if rc == 0:
            data = json.loads(out)
            pods = []
            for item in data.get('items', []):
                pods.append({
                    'name': item['metadata']['name'],
                    'phase': item['status']['phase'],
                    'containers': [c['name'] for c in item['spec']['containers']],
                    'ip': item['status'].get('podIP', ''),
                    'node': item['spec'].get('nodeName', '')
                })
            return jsonify({'pods': pods})
        else:
            return jsonify({'error': _parse_kubectl_error(stderr) or '获取 Pod 列表失败'}), 400
    except json.JSONDecodeError:
        return jsonify({'error': '解析失败'}), 400


@clusters_bp.route('/clusters/<cluster_id>/contexts', methods=['GET'])
@login_required
def list_contexts(cluster_id: str):
    """获取可用上下文列表"""
    from backend.core.kubectl import KubectlExecutor
    
    cluster, err, code = _check_cluster_access(cluster_id)
    if err:
        return jsonify(err), code
    
    if not cluster.get('kubeconfig'):
        return jsonify({'error': '未配置 kubeconfig'}), 400
    
    runner = KubectlExecutor(
        kubeconfig=cluster.get('kubeconfig', ''),
        context=cluster.get('context', ''),
    )
    
    try:
        rc, out, stderr = runner._run(["config", "get-contexts", "-o", "json"], timeout=10)
        if rc == 0:
            data = json.loads(out)
            contexts = [c['name'] for c in data.get('clusters', [])]
            return jsonify({'contexts': contexts})
        else:
            return jsonify({'error': _parse_kubectl_error(stderr) or '获取上下文列表失败'}), 400
    except json.JSONDecodeError:
        return jsonify({'error': '解析失败'}), 400