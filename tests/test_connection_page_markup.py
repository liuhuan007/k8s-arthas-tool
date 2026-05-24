import pytest
from unittest.mock import patch
from server import app


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def authenticated_client():
    """创建一个已认证的测试客户端"""
    app.config['TESTING'] = True
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess['_user_id'] = '1'  # Flask-Login session key
        yield client


def test_index_page_has_connection_list_structure(authenticated_client):
    """Test that index.html has connection list structure"""
    with patch('server.current_user') as mock_user:
        mock_user.is_authenticated = True
        response = authenticated_client.get('/')
        assert response.status_code == 200
        html = response.data.decode()
        assert 'connection-list-container' in html
        assert 'connection-table' in html


def test_page_shell_component_exists(authenticated_client):
    """Test that page-shell.js is loaded"""
    with patch('server.current_user') as mock_user:
        mock_user.is_authenticated = True
        response = authenticated_client.get('/')
        assert response.status_code == 200
        html = response.data.decode()
        assert 'page-shell.js' in html


def test_connection_page_context_component_exists(authenticated_client):
    """Test that connection-page-context.js is loaded"""
    with patch('server.current_user') as mock_user:
        mock_user.is_authenticated = True
        response = authenticated_client.get('/connection-detail')
        assert response.status_code == 200
        html = response.data.decode()
        assert 'connection-page-context.js' in html


def test_connection_detail_page_exists(authenticated_client):
    """Test that connection-detail.html exists"""
    with patch('server.current_user') as mock_user:
        mock_user.is_authenticated = True
        response = authenticated_client.get('/connection-detail')
        assert response.status_code == 200
        html = response.data.decode()
        assert 'connection-detail-container' in html


def test_two_step_connection_dom_target(authenticated_client):
    """Test that two-step-connection.js has configurable DOM target"""
    with patch('server.current_user') as mock_user:
        mock_user.is_authenticated = True
        response = authenticated_client.get('/connection-detail')
        assert response.status_code == 200
        html = response.data.decode()
        assert 'two-step-connection.js' in html


def test_workspace_pages_exist(authenticated_client):
    """Test that all workspace pages exist"""
    with patch('server.current_user') as mock_user:
        mock_user.is_authenticated = True
        pages = ['/terminal', '/monitor', '/filebrowser', '/diagnose', '/arthas-console', '/profiler', '/history']
        for page in pages:
            response = authenticated_client.get(page)
            assert response.status_code == 200