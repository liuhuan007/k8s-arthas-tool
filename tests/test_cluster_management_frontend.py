import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
INDEX = (ROOT / 'static' / 'index.html').read_text(encoding='utf-8')
APP_UI = (ROOT / 'static' / 'js' / 'app-ui.js').read_text(encoding='utf-8')
LAYOUT = (ROOT / 'static' / 'js' / 'layout-loader.js').read_text(encoding='utf-8')
CLUSTER_HTML = ROOT / 'static' / 'cluster-management.html'
CLUSTER_JS = ROOT / 'static' / 'js' / 'cluster-management.js'


def test_cluster_management_is_available_from_system_menu():
    assert "data-nav-tab=\"cluster-management\"" in INDEX
    assert "navigateTo('cluster-management')" in INDEX
    assert "panel-cluster-management" in INDEX
    assert "cluster-management.html?embed=1" in INDEX
    assert "'cluster-management': '/cluster-management.html'" in APP_UI
    assert "'cluster-management': '/cluster-management.html'" in LAYOUT
    assert "cluster-management" in APP_UI and "loadAdminFrameIfNeeded" in APP_UI
    assert "'cluster-management': { required: 'none', showConnBar: false }" in APP_UI
    assert "if (window.__hideConnStatusBar) return;" in APP_UI


def test_cluster_management_page_supports_crud_and_test():
    assert CLUSTER_HTML.exists()
    assert CLUSTER_JS.exists()
    html = CLUSTER_HTML.read_text(encoding='utf-8')
    js = CLUSTER_JS.read_text(encoding='utf-8')
    assert '集群管理' in html
    assert 'clusterTableBody' in html
    assert 'openClusterModal' in js
    assert 'saveClusterConfig' in js
    assert "method: 'DELETE'" in js
    assert "'/test'" in js
    assert 'renderClusterTable' in js

def test_connection_builder_guides_cluster_creation_to_management_page():
    assert 'title="前往集群管理创建集群"' in INDEX
    assert "navigateTo('cluster-management')" in INDEX
    assert 'onclick="openAddCluster()" title="新建集群"' not in INDEX
    assert 'onclick="openAddCluster()" title="添加集群"' not in INDEX
    assert '暂无集群<br>请到系统管理 → 集群管理创建' in APP_UI


def test_save_cluster_button_shows_saving_and_testing_feedback():
    assert "const saveBtn = document.getElementById('mSaveBtn');" in APP_UI
    assert "saveBtn.textContent = '保存中...'" in APP_UI
    assert "toast('集群已保存，正在后台测试连接...'" in APP_UI
    assert "toast(`集群连接测试${d.ok ? '成功' : '失败'}" in APP_UI
    assert 'id="mSaveBtn"' in INDEX
