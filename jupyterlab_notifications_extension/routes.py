import json
import time
from typing import Dict, List
from collections import defaultdict

from jupyter_server.base.handlers import APIHandler
from jupyter_server.utils import url_path_join
import tornado


# In-memory storage for notifications (broadcast to all users)
_notification_store: List[Dict] = []


class NotificationIngestHandler(APIHandler):
    """
    POST endpoint for external entities to send notifications.

    Expected payload:
    {
        "message": "Your notification message",
        "type": "info",  // optional: default, info, success, warning, error, in-progress
        "autoClose": 5000,  // optional: milliseconds or false for manual dismiss
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

            # Add to broadcast queue
            _notification_store.append(notification)

            self.finish(json.dumps({
                "success": True,
                "notification_id": notification['id']
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
    Returns all pending notifications and clears them.
    """

    @tornado.web.authenticated
    def get(self):
        global _notification_store

        # Get all pending notifications
        notifications = _notification_store.copy()

        # Clear the queue
        _notification_store = []

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
