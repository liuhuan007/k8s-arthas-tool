#!/usr/bin/env python3
"""授权服务：集群与 namespace 级访问控制。"""
from typing import Any, Iterable, List
import json
from pathlib import Path

from models.db import db


_NAMESPACE_DENIED = '无权访问该 namespace'
_CLUSTER_DENIED = '无权访问此集群'


class AuthorizationService:
    """统一授权服务。

    规则：
    - admin 默认拥有所有集群和 namespace。
    - 普通用户保留 user_clusters 作为集群可见性授权。
    - 普通用户必须在 user_namespaces 中有 cluster_id + namespace 或 namespace='*' 授权，才能操作该 namespace。
    """

    @staticmethod
    def _is_admin(user: Any) -> bool:
        return bool(getattr(user, 'is_admin', False))

    @staticmethod
    def _cluster_keys(cluster_id_or_name: str) -> List[str]:
        """返回可能用于授权匹配的集群 key（兼容 id 和 name）。"""
        keys = []
        raw = (cluster_id_or_name or '').strip()
        if raw:
            keys.append(raw)
        try:
            from backend.config import Config
            p = Path(Config.CLUSTERS_FILE)
            if p.exists():
                clusters = json.loads(p.read_text(encoding='utf-8'))
                for c in clusters:
                    cid = c.get('id') or ''
                    name = c.get('name') or ''
                    if raw and raw in (cid, name):
                        for key in (cid, name):
                            if key and key not in keys:
                                keys.append(key)
        except Exception:
            pass
        return keys

    @staticmethod
    def can_access_cluster(user: Any, cluster_id: str) -> bool:
        if AuthorizationService._is_admin(user):
            return True
        if not user or not cluster_id:
            return False
        user_id = getattr(user, 'id', None)
        for key in AuthorizationService._cluster_keys(cluster_id):
            if db.exists(
                'user_clusters',
                'user_id = ? AND cluster_id = ?',
                (user_id, key),
            ):
                return True
        return False

    @staticmethod
    def can_access_namespace(user: Any, cluster_id: str, namespace: str) -> bool:
        if AuthorizationService._is_admin(user):
            return True
        if not user or not cluster_id or not namespace:
            return False
        user_id = getattr(user, 'id', None)
        for key in AuthorizationService._cluster_keys(cluster_id):
            if db.exists(
                'user_namespaces',
                'user_id = ? AND cluster_id = ? AND (namespace = ? OR namespace = ?)',
                (user_id, key, namespace, '*'),
            ):
                return True
        return False

    @staticmethod
    def filter_namespaces(user: Any, cluster_id: str, namespaces: Iterable[str]) -> List[str]:
        ns_list = list(namespaces or [])
        if AuthorizationService._is_admin(user):
            return ns_list
        if not user or not cluster_id:
            return []
        namespace_rows = []
        for key in AuthorizationService._cluster_keys(cluster_id):
            namespace_rows.extend(db.fetch_all(
                'SELECT namespace FROM user_namespaces WHERE user_id = ? AND cluster_id = ?',
                (getattr(user, 'id', None), key),
            ))
        allowed = {r['namespace'] for r in namespace_rows}
        if '*' in allowed:
            return ns_list
        return [ns for ns in ns_list if ns in allowed]

    @staticmethod
    def require_cluster_access(user: Any, cluster_id: str):
        if not AuthorizationService.can_access_cluster(user, cluster_id):
            return {'error': _CLUSTER_DENIED}, 403
        return None, 0

    @staticmethod
    def require_namespace_access(user: Any, cluster_id: str, namespace: str):
        if not AuthorizationService.can_access_namespace(user, cluster_id, namespace):
            return {'error': _NAMESPACE_DENIED}, 403
        return None, 0
