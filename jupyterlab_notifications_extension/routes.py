import itertools
import json
import time
from typing import Dict, List, Set

from jupyter_server.base.handlers import APIHandler, JupyterHandler
from jupyter_server.base.websocket import WebSocketMixin
from jupyter_server.auth.decorator import ws_authenticated
from jupyter_server.utils import url_path_join
from tornado.websocket import WebSocketHandler, WebSocketClosedError
import tornado


# Single source for the extension's URL namespace (see also request.ts)
API_NAMESPACE = "jupyterlab-notifications-extension"

# web_app.settings key gating the localhost auth bypass (opt-in, default off)
ALLOW_UNAUTH_LOCALHOST_SETTING = "jupyterlab_notifications_allow_unauthenticated_localhost"

# Process-lifetime monotonic counter for notification ids. Guarantees a
# unique id even across store drains (unlike len(_notification_store),
# which resets to 0 on every fetch and could collide).
_id_counter = itertools.count(1)

# In-memory storage for notifications (broadcast to all users)
_notification_store: List[Dict] = []

# Live WebSocket listeners for immediate ("--now") push delivery
_stream_listeners: Set["NotificationStreamHandler"] = set()


def _push_immediate(notification: Dict, log) -> None:
    """Push a single notification to all connected WebSocket listeners."""
    message = json.dumps({"notifications": [notification]})
    for listener in list(_stream_listeners):
        try:
            listener.write_message(message)
        except WebSocketClosedError:
            # Socket genuinely closed - drop it. A transient write error of
            # another kind is logged but the listener is kept (it may recover).
            _stream_listeners.discard(listener)
        except Exception:
            log.warning(
                "Failed to push notification to a stream listener", exc_info=True
            )


class NotificationIngestHandler(APIHandler):
    """
    POST endpoint for external entities to send notifications.

    Expected payload:
    {
        "message": "Your notification message",
        "type": "info",  // optional: default, info, success, warning, error, in-progress
        "autoClose": 5000,  // optional: milliseconds or false for manual dismiss
        "immediate": true,  // optional: push instantly to connected clients via WebSocket
        "actions": [  // optional
            {
                "label": "Click here",
                "caption": "Additional info",
                "displayType": "accent"  // optional: default, accent, warn, link
            }
        ]
    }
    """

    def _is_localhost(self):
        """Check if request is from a genuine loopback peer."""
        return self.request.remote_ip in ('127.0.0.1', '::1')

    def _allow_unauthenticated_localhost(self):
        """Whether the operator opted in to token-free localhost ingest."""
        return bool(self.settings.get(ALLOW_UNAUTH_LOCALHOST_SETTING, False))

    def get_current_user(self):
        """Override to optionally allow localhost without authentication.

        Opt-in and secure by default: the bypass fires only when the server
        operator explicitly enables it. Inferring trust from remote_ip alone
        is unsafe behind a same-host reverse proxy, where every external
        client's remote_ip is 127.0.0.1.
        """
        if self._allow_unauthenticated_localhost() and self._is_localhost():
            # Return a dummy user for localhost to bypass authentication
            return {"name": "localhost"}
        # Otherwise use parent's authentication
        return super().get_current_user()

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
                "id": f"notif_{int(time.time() * 1000)}_{next(_id_counter)}",
                "message": payload['message'],
                "type": payload.get('type', 'info'),
                "autoClose": payload.get('autoClose', 5000),
                "createdAt": int(time.time() * 1000),
                "actions": payload.get('actions', []),
                "data": payload.get('data')
            }

            # Add to the broadcast queue. NOTE: the poll fetch is a
            # destructive, single-consumer drain - the first client to poll
            # empties the queue for all clients - so queue delivery is
            # best-effort, not a per-client guarantee. Immediate ("--now")
            # notifications are additionally pushed to every currently
            # connected socket below for instant, all-tabs delivery.
            _notification_store.append(notification)

            if payload.get('immediate'):
                _push_immediate(notification, self.log)

            self.finish(json.dumps({
                "success": True,
                "notification_id": notification['id']
            }))

        except json.JSONDecodeError:
            self.set_status(400)
            self.finish(json.dumps({"error": "Invalid JSON payload"}))
        except Exception:
            # Log the detail server-side; do not leak internals to the client
            self.log.exception("Failed to ingest notification")
            self.set_status(500)
            self.finish(json.dumps({"error": "Internal server error"}))


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


class NotificationStreamHandler(WebSocketMixin, WebSocketHandler, JupyterHandler):
    """
    WebSocket endpoint for immediate notification delivery.

    The frontend keeps this socket open. The ingest handler pushes
    notifications flagged 'immediate' to every connected listener for
    instant display. The 30-second frontend poll remains the baseline.

    Inherits WebSocketMixin for ping/pong keepalive (survives proxy
    idle timeouts) and JupyterHandler for authentication.
    """

    def set_default_headers(self):
        """Undo JupyterHandler default headers (meaningless for websockets)."""

    def open(self):
        # super().open() starts the ping/pong keepalive loop
        super().open()
        _stream_listeners.add(self)
        self.log.debug(
            "Notification stream connected (%d listener(s))", len(_stream_listeners)
        )

    def on_message(self, message):
        """No inbound messages expected; the stream is push-only."""

    def on_close(self):
        _stream_listeners.discard(self)
        self.log.debug(
            "Notification stream disconnected (%d listener(s))", len(_stream_listeners)
        )

    @ws_authenticated
    async def get(self, *args, **kwargs):
        await super().get(*args, **kwargs)


def setup_route_handlers(web_app):
    host_pattern = ".*$"
    base_url = web_app.settings["base_url"]

    ingest_route_pattern = url_path_join(base_url, API_NAMESPACE, "ingest")
    fetch_route_pattern = url_path_join(base_url, API_NAMESPACE, "notifications")
    stream_route_pattern = url_path_join(base_url, API_NAMESPACE, "stream")

    handlers = [
        (ingest_route_pattern, NotificationIngestHandler),
        (fetch_route_pattern, NotificationFetchHandler),
        (stream_route_pattern, NotificationStreamHandler),
    ]

    web_app.add_handlers(host_pattern, handlers)
