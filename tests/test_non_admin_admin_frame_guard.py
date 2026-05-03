import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
INDEX = (ROOT / 'static' / 'index.html').read_text(encoding='utf-8')
USER_MGMT_HTML = (ROOT / 'static' / 'user-management.html').read_text(encoding='utf-8')
AUDIT_HTML = (ROOT / 'static' / 'audit-logs.html').read_text(encoding='utf-8')


def test_admin_iframes_are_lazy_loaded_to_avoid_non_admin_alert_loop():
    assert '<iframe class="admin-frame" src="user-management.html?embed=1"' not in INDEX
    assert '<iframe class="admin-frame" src="audit-logs.html?embed=1"' not in INDEX
    assert 'data-src="user-management.html?embed=1"' in INDEX
    assert 'data-src="audit-logs.html?embed=1"' in INDEX
    assert 'loadAdminFrameIfNeeded' in INDEX or 'loadAdminFrameIfNeeded' in (ROOT / 'static' / 'js' / 'app-ui.js').read_text(encoding='utf-8')


def test_embedded_admin_pages_do_not_alert_and_redirect_parent_for_non_admin():
    assert "alert('只有管理员可以访问此页面')" not in USER_MGMT_HTML
    assert "alert('只有管理员可以查看审计日志')" not in AUDIT_HTML
    assert 'window.parent' in USER_MGMT_HTML
    assert 'window.parent' in AUDIT_HTML
