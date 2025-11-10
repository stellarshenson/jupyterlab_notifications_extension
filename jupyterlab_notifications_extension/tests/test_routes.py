import json
import pytest
from jupyterlab_notifications_extension import routes


@pytest.fixture(autouse=True)
def clear_notification_store():
    """Clear notification store before each test"""
    routes._notification_store.clear()
    yield


async def test_notification_ingest(jp_fetch):
    """Test notification object creation"""
    response = await jp_fetch(
        "jupyterlab-notifications-extension",
        "ingest",
        method="POST",
        body=json.dumps({"message": "Test", "type": "info", "autoClose": 5000})
    )

    assert response.code == 200
    payload = json.loads(response.body)
    assert payload["success"] is True
    assert payload["notification_id"].startswith("notif_")


async def test_notification_fetch(jp_fetch):
    """Test notification fetching"""
    await jp_fetch(
        "jupyterlab-notifications-extension",
        "ingest",
        method="POST",
        body=json.dumps({"message": "Test", "type": "success"})
    )

    response = await jp_fetch("jupyterlab-notifications-extension", "notifications")

    assert response.code == 200
    payload = json.loads(response.body)
    assert len(payload["notifications"]) == 1
    assert payload["notifications"][0]["message"] == "Test"


async def test_notification_fetch_clears_queue(jp_fetch):
    """Test queue clearing after fetch"""
    await jp_fetch(
        "jupyterlab-notifications-extension",
        "ingest",
        method="POST",
        body=json.dumps({"message": "Test"})
    )

    response1 = await jp_fetch("jupyterlab-notifications-extension", "notifications")
    response2 = await jp_fetch("jupyterlab-notifications-extension", "notifications")

    assert len(json.loads(response1.body)["notifications"]) == 1
    assert len(json.loads(response2.body)["notifications"]) == 0


async def test_notification_with_actions(jp_fetch):
    """Test action buttons and autoClose"""
    response = await jp_fetch(
        "jupyterlab-notifications-extension",
        "ingest",
        method="POST",
        body=json.dumps({
            "message": "Test",
            "autoClose": False,
            "actions": [{"label": "Retry", "displayType": "accent"}]
        })
    )

    assert response.code == 200
    fetch_response = await jp_fetch("jupyterlab-notifications-extension", "notifications")
    notification = json.loads(fetch_response.body)["notifications"][0]
    assert notification["autoClose"] is False
    assert len(notification["actions"]) == 1
    assert notification["actions"][0]["label"] == "Retry"


async def test_localhost_no_auth_required(jp_fetch):
    """Test that localhost requests work without authentication"""
    # jp_fetch uses localhost by default, so we'll make a request without auth headers
    # The handler should detect localhost and skip authentication
    response = await jp_fetch(
        "jupyterlab-notifications-extension",
        "ingest",
        method="POST",
        body=json.dumps({"message": "Localhost test", "type": "info"})
    )

    assert response.code == 200
    payload = json.loads(response.body)
    assert payload["success"] is True


async def test_remote_ip_requires_auth(jp_fetch, jp_serverapp):
    """Test that get_current_user returns None for remote IPs without valid auth"""
    from unittest.mock import patch, MagicMock
    from jupyterlab_notifications_extension.routes import NotificationIngestHandler

    # Create a mock handler instance to test the get_current_user logic
    handler = NotificationIngestHandler(jp_serverapp.web_app, MagicMock())

    # Test 1: localhost returns dummy user (bypasses auth)
    with patch.object(handler, '_is_localhost', return_value=True):
        user = handler.get_current_user()
        assert user == {"name": "localhost"}

    # Test 2: remote IP with valid auth returns user from parent
    with patch.object(handler, '_is_localhost', return_value=False):
        # Mock parent's get_current_user to return a valid user
        with patch('jupyter_server.base.handlers.APIHandler.get_current_user', return_value={"name": "testuser"}):
            user = handler.get_current_user()
            assert user == {"name": "testuser"}

    # Test 3: remote IP without valid auth returns None from parent
    with patch.object(handler, '_is_localhost', return_value=False):
        # Mock parent's get_current_user to return None (no auth)
        with patch('jupyter_server.base.handlers.APIHandler.get_current_user', return_value=None):
            user = handler.get_current_user()
            assert user is None
