import json
import pytest
from jupyterlab_notifications_extension import routes


@pytest.fixture(autouse=True)
def clear_notification_store():
    """Clear notification store before each test"""
    routes._notification_store.clear()
    yield


async def test_hello(jp_fetch):
    # When
    response = await jp_fetch("jupyterlab-notifications-extension", "hello")

    # Then
    assert response.code == 200
    payload = json.loads(response.body)
    assert payload == {
            "data": (
                "Hello, world!"
                " This is the '/jupyterlab-notifications-extension/hello' endpoint."
                " Try visiting me in your browser!"
            ),
        }


async def test_notification_ingest(jp_fetch):
    """Test that notifications can be ingested and notification objects are created"""
    # Given
    notification_payload = {
        "message": "Test notification message",
        "type": "info",
        "autoClose": 5000
    }

    # When - Send notification to ingest endpoint
    response = await jp_fetch(
        "jupyterlab-notifications-extension",
        "ingest",
        method="POST",
        body=json.dumps(notification_payload)
    )

    # Then - Verify response
    assert response.code == 200
    payload = json.loads(response.body)
    assert payload["success"] is True
    assert "notification_id" in payload
    assert payload["notification_id"].startswith("notif_")


async def test_notification_fetch(jp_fetch):
    """Test that notifications can be fetched after ingestion"""
    # Given - Send a notification first
    notification_payload = {
        "message": "Fetch test notification",
        "type": "success",
        "autoClose": 3000
    }

    await jp_fetch(
        "jupyterlab-notifications-extension",
        "ingest",
        method="POST",
        body=json.dumps(notification_payload)
    )

    # When - Fetch notifications
    response = await jp_fetch("jupyterlab-notifications-extension", "notifications")

    # Then - Verify notification was returned
    assert response.code == 200
    payload = json.loads(response.body)
    assert "notifications" in payload
    assert len(payload["notifications"]) == 1
    notification = payload["notifications"][0]
    assert notification["message"] == "Fetch test notification"
    assert notification["type"] == "success"
    assert notification["autoClose"] == 3000


async def test_notification_fetch_clears_queue(jp_fetch):
    """Test that fetching notifications clears the queue"""
    # Given - Send a notification
    notification_payload = {
        "message": "Clear test notification",
        "type": "warning"
    }

    await jp_fetch(
        "jupyterlab-notifications-extension",
        "ingest",
        method="POST",
        body=json.dumps(notification_payload)
    )

    # When - Fetch notifications twice
    response1 = await jp_fetch("jupyterlab-notifications-extension", "notifications")
    response2 = await jp_fetch("jupyterlab-notifications-extension", "notifications")

    # Then - First fetch has notification, second is empty
    payload1 = json.loads(response1.body)
    payload2 = json.loads(response2.body)
    assert len(payload1["notifications"]) == 1
    assert len(payload2["notifications"]) == 0


async def test_notification_with_actions(jp_fetch):
    """Test notifications with action buttons"""
    # Given
    notification_payload = {
        "message": "Action test notification",
        "type": "error",
        "autoClose": False,
        "actions": [
            {
                "label": "Retry",
                "caption": "Retry the operation",
                "displayType": "accent"
            },
            {
                "label": "Cancel",
                "caption": "Cancel the operation",
                "displayType": "default"
            }
        ]
    }

    # When
    response = await jp_fetch(
        "jupyterlab-notifications-extension",
        "ingest",
        method="POST",
        body=json.dumps(notification_payload)
    )

    # Then
    assert response.code == 200
    fetch_response = await jp_fetch("jupyterlab-notifications-extension", "notifications")
    payload = json.loads(fetch_response.body)
    notification = payload["notifications"][0]
    assert len(notification["actions"]) == 2
    assert notification["actions"][0]["label"] == "Retry"
    assert notification["actions"][0]["displayType"] == "accent"
    assert notification["autoClose"] is False
