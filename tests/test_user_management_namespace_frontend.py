import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
USER_MGMT_HTML = (ROOT / 'static' / 'user-management.html').read_text(encoding='utf-8')
USER_MGMT_JS = (ROOT / 'static' / 'js' / 'user-management.js').read_text(encoding='utf-8')


def test_user_management_has_namespace_permission_modal():
    assert 'id="namespaceModal"' in USER_MGMT_HTML
    assert 'namespaceModalUser' in USER_MGMT_HTML
    assert 'namespaceClusterSelect' in USER_MGMT_HTML
    assert 'namespaceInput' in USER_MGMT_HTML
    assert 'assignedNamespaces' in USER_MGMT_HTML


def test_user_table_exposes_namespace_permission_action():
    assert 'showNamespaceModal' in USER_MGMT_JS
    assert '管理namespace' in USER_MGMT_JS


def test_namespace_permission_frontend_calls_backend_routes():
    assert '/user-namespaces/' in USER_MGMT_JS
    assert '/user-namespaces' in USER_MGMT_JS
    assert '/user-namespaces/by-user-cluster-namespace' in USER_MGMT_JS
    assert 'assignNamespace' in USER_MGMT_JS
    assert 'removeNamespacePermission' in USER_MGMT_JS


def test_namespace_permission_frontend_exports_inline_handlers():
    assert 'window.showNamespaceModal = showNamespaceModal;' in USER_MGMT_JS
    assert 'window.assignNamespace = assignNamespace;' in USER_MGMT_JS
    assert 'window.removeNamespacePermission = removeNamespacePermission;' in USER_MGMT_JS
    assert 'window.loadNamespacesForSelectedCluster = loadNamespacesForSelectedCluster;' in USER_MGMT_JS
