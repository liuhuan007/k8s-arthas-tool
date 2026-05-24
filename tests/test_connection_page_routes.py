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


def test_connection_detail_route_exists(authenticated_client):
    """Test that /connection-detail route exists"""
    with patch('server.current_user') as mock_user:
        mock_user.is_authenticated = True
        response = authenticated_client.get('/connection-detail')
        assert response.status_code == 200


def test_terminal_route_exists(authenticated_client):
    """Test that /terminal route exists"""
    with patch('server.current_user') as mock_user:
        mock_user.is_authenticated = True
        response = authenticated_client.get('/terminal')
        assert response.status_code == 200


def test_monitor_route_exists(authenticated_client):
    """Test that /monitor route exists"""
    with patch('server.current_user') as mock_user:
        mock_user.is_authenticated = True
        response = authenticated_client.get('/monitor')
        assert response.status_code == 200