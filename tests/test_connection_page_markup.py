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