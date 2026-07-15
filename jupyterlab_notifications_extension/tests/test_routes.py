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


async def test_notification_ids_unique_across_drains(jp_fetch):
    """DEF-2: ids stay unique even after the store is drained (counter, not len)."""
    r1 = await jp_fetch(
        "jupyterlab-notifications-extension", "ingest",
        method="POST", body=json.dumps({"message": "A"})
    )
    # Drain the store, resetting len() to 0
    await jp_fetch("jupyterlab-notifications-extension", "notifications")
    r2 = await jp_fetch(
        "jupyterlab-notifications-extension", "ingest",
        method="POST", body=json.dumps({"message": "B"})
    )
    id1 = json.loads(r1.body)["notification_id"]
    id2 = json.loads(r2.body)["notification_id"]
    assert id1 != id2


async def test_localhost_bypass_is_opt_in(jp_serverapp):
    """DEF-6: localhost auth bypass is off by default, on only when enabled."""
    from unittest.mock import patch, MagicMock
    from jupyterlab_notifications_extension.routes import (
        NotificationIngestHandler,
        ALLOW_UNAUTH_LOCALHOST_SETTING,
    )

    handler = NotificationIngestHandler(jp_serverapp.web_app, MagicMock())

    # Default (setting absent/off): localhost does NOT bypass -> parent auth
    jp_serverapp.web_app.settings.pop(ALLOW_UNAUTH_LOCALHOST_SETTING, None)
    with patch.object(handler, '_is_localhost', return_value=True):
        with patch('jupyter_server.base.handlers.APIHandler.get_current_user', return_value=None):
            assert handler.get_current_user() is None

    # Opt-in enabled: genuine localhost bypasses with a dummy user
    jp_serverapp.web_app.settings[ALLOW_UNAUTH_LOCALHOST_SETTING] = True
    with patch.object(handler, '_is_localhost', return_value=True):
        assert handler.get_current_user() == {"name": "localhost"}


async def test_remote_ip_requires_auth(jp_serverapp):
    """Remote IPs always go through parent auth, even with the opt-in enabled."""
    from unittest.mock import patch, MagicMock
    from jupyterlab_notifications_extension.routes import (
        NotificationIngestHandler,
        ALLOW_UNAUTH_LOCALHOST_SETTING,
    )

    handler = NotificationIngestHandler(jp_serverapp.web_app, MagicMock())
    # Even with the localhost opt-in on, a remote IP must authenticate
    jp_serverapp.web_app.settings[ALLOW_UNAUTH_LOCALHOST_SETTING] = True

    # Remote IP with valid auth returns user from parent
    with patch.object(handler, '_is_localhost', return_value=False):
        with patch('jupyter_server.base.handlers.APIHandler.get_current_user', return_value={"name": "testuser"}):
            assert handler.get_current_user() == {"name": "testuser"}

    # Remote IP without valid auth returns None from parent
    with patch.object(handler, '_is_localhost', return_value=False):
        with patch('jupyter_server.base.handlers.APIHandler.get_current_user', return_value=None):
            assert handler.get_current_user() is None
