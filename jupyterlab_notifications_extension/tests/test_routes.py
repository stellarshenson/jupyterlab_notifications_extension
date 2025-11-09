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
