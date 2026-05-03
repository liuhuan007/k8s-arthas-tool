import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
DB = (ROOT / 'models' / 'db.py').read_text(encoding='utf-8')
USERS = (ROOT / 'api' / 'users.py').read_text(encoding='utf-8')
CLUSTERS = (ROOT / 'api' / 'clusters.py').read_text(encoding='utf-8')
POD_APIS = (ROOT / 'api' / 'pod_apis.py').read_text(encoding='utf-8')
TASK_CENTER = (ROOT / 'api' / 'task_center.py').read_text(encoding='utf-8')
SERVER = (ROOT / 'server.py').read_text(encoding='utf-8')
AUTHZ_PATH = ROOT / 'services' / 'authorization_service.py'


def test_user_namespace_permissions_table_exists():
    assert 'user_namespaces' in DB
    assert 'user_id INTEGER NOT NULL' in DB
    assert 'cluster_id TEXT NOT NULL' in DB
    assert 'namespace TEXT NOT NULL' in DB
    assert 'UNIQUE(user_id, cluster_id, namespace)' in DB


def test_user_namespace_api_routes_exist():
    assert "/user-namespaces/<int:user_id>" in USERS
    assert "/user-namespaces" in USERS
    assert "assign_namespace" in USERS
    assert "remove_namespace" in USERS
    assert "remove_namespace_by_user_cluster_namespace" in USERS


def test_authorization_service_contract_exists():
    source = AUTHZ_PATH.read_text(encoding='utf-8')
    assert 'class AuthorizationService' in source
    assert 'can_access_cluster' in source
    assert 'can_access_namespace' in source
    assert 'filter_namespaces' in source
    assert 'require_namespace_access' in source


def test_namespace_authorization_is_integrated_with_cluster_and_pod_entrypoints():
    assert 'AuthorizationService.filter_namespaces' in CLUSTERS
    assert 'AuthorizationService.can_access_namespace' in CLUSTERS
    assert 'AuthorizationService.require_namespace_access' in POD_APIS
    assert 'AuthorizationService.require_namespace_access' in TASK_CENTER
    assert 'AuthorizationService.require_namespace_access' in SERVER


def test_namespace_permission_error_message_is_consistent():
    combined = '\n'.join([CLUSTERS, POD_APIS, TASK_CENTER, SERVER])
    assert '无权访问该 namespace' in combined
