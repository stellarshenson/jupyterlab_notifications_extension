import json
import time
from typing import Dict, List
from collections import defaultdict

from jupyter_server.base.handlers import APIHandler
from jupyter_server.utils import url_path_join
import tornado


# In-memory storage for notifications per user
# Structure: {username: [notification1, notification2, ...]}
_notification_store: Dict[str, List[Dict]] = defaultdict(list)


class NotificationIngestHandler(APIHandler):
    """
    POST endpoint for external entities to send notifications.

    Expected payload:
    {
        "message": "Your notification message",
        "type": "info",  // optional: default, info, success, warning, error, in-progress
        "autoClose": 5000,  // optional: milliseconds or false for manual dismiss
        "target_users": ["user1", "user2"],  // optional: specific users, or null for all
        "actions": [  // optional
            {
                "label": "Click here",
                "caption": "Additional info",
                "displayType": "accent"  // optional: default, accent, warn, link
            }
        ]
    }
    """

    @tornado.web.authenticated
    def post(self):
        try:
            payload = json.loads(self.request.body.decode('utf-8'))

            # Validate required fields
            if 'message' not in payload:
                self.set_status(400)
                self.finish(json.dumps({"error": "Missing 'message' field"}))
                return

            # Create notification object
            notification = {
                "id": f"notif_{int(time.time() * 1000)}_{len(_notification_store)}",
                "message": payload['message'],
                "type": payload.get('type', 'info'),
                "autoClose": payload.get('autoClose', 5000),
                "createdAt": int(time.time() * 1000),
                "actions": payload.get('actions', [])
            }

            # Determine target users
            target_users = payload.get('target_users', None)

            if target_users is None:
                # Broadcast to all current users in the store
                # For new users, they won't see this (could be enhanced with persistent storage)
                for username in _notification_store.keys():
                    _notification_store[username].append(notification.copy())

                # If no users in store yet, store for the next user who connects
                if not _notification_store:
                    _notification_store['__broadcast__'].append(notification.copy())
            else:
                # Send to specific users
                for username in target_users:
                    _notification_store[username].append(notification.copy())

            self.finish(json.dumps({
                "success": True,
                "notification_id": notification['id'],
                "target_users": target_users if target_users else "all"
            }))

        except json.JSONDecodeError:
            self.set_status(400)
            self.finish(json.dumps({"error": "Invalid JSON payload"}))
        except Exception as e:
            self.set_status(500)
            self.finish(json.dumps({"error": str(e)}))


class NotificationFetchHandler(APIHandler):
    """
    GET endpoint for frontend to fetch pending notifications.
    Returns all pending notifications for the current user and clears them.
    """

    @tornado.web.authenticated
    def get(self):
        username = self.current_user['name']

        # Get user-specific notifications
        notifications = _notification_store.get(username, []).copy()

        # Get broadcast notifications (for first-time users)
        broadcast_notifications = _notification_store.get('__broadcast__', []).copy()
        notifications.extend(broadcast_notifications)

        # Clear fetched notifications
        _notification_store[username] = []

        # Clear broadcast after first fetch (assumes at least one user has connected)
        if '__broadcast__' in _notification_store:
            del _notification_store['__broadcast__']

        self.finish(json.dumps({"notifications": notifications}))


class HelloRouteHandler(APIHandler):
    # The following decorator should be present on all verb methods (head, get, post,
    # patch, put, delete, options) to ensure only authorized user can request the
    # Jupyter server
    @tornado.web.authenticated
    def get(self):
        self.finish(json.dumps({
            "data": (
                "Hello, world!"
                " This is the '/jupyterlab-notifications-extension/hello' endpoint."
                " Try visiting me in your browser!"
            ),
        }))


def setup_route_handlers(web_app):
    host_pattern = ".*$"
    base_url = web_app.settings["base_url"]

    hello_route_pattern = url_path_join(base_url, "jupyterlab-notifications-extension", "hello")
    ingest_route_pattern = url_path_join(base_url, "jupyterlab-notifications-extension", "ingest")
    fetch_route_pattern = url_path_join(base_url, "jupyterlab-notifications-extension", "notifications")

    handlers = [
        (hello_route_pattern, HelloRouteHandler),
        (ingest_route_pattern, NotificationIngestHandler),
        (fetch_route_pattern, NotificationFetchHandler),
    ]

    web_app.add_handlers(host_pattern, handlers)
