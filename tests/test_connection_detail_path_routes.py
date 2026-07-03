#!/usr/bin/env python3
"""连接详情路由应支持包含斜杠的连接 ID。"""
import pathlib


ROOT = pathlib.Path(__file__).resolve().parents[1]


def _read(rel_path):
    return (ROOT / rel_path).read_text(encoding='utf-8')


class TestConnectionDetailPathRoutes:
    """连接 ID 形如 cluster/namespace/pod，路由必须用 path 转换器。"""

    def test_bare_connection_get_route_exists(self):
        """GET /api/connections/{connection_id} 不应落到仅 DELETE 路由导致 405。"""
        src = _read('api/connection_detail.py')

        assert '@connection_detail_bp.route("/<path:connection_id>", methods=["GET"])' in src
        assert 'def get_connection_detail(connection_id: str):' in src

    def test_connection_id_suffix_routes_use_path_converter(self):
        """详情相关子路由应支持连接 ID 中的 /。"""
        src = _read('api/connection_detail.py')

        for suffix, methods in {
            'detail': '["GET"]',
            'health': '["GET"]',
            'ttl': '["GET"]',
            'running-tasks': '["GET"]',
            'switch': '["POST"]',
            'reconnect': '["POST"]',
        }.items():
            assert f'@connection_detail_bp.route("/<path:connection_id>/{suffix}", methods={methods})' in src

        assert '@connection_detail_bp.route("/<path:connection_id>/health", methods=["POST"])' in src
        assert '@connection_detail_bp.route("/<path:connection_id>/ttl", methods=["PUT"])' in src
