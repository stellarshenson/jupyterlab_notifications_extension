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


# The URL namespace. Three copies exist on purpose: here, src/request.ts, and
# a third copy in cli.py, which must not import tornado to send one POST.
# The path is a published contract, so the duplication is stable.
API_NAMESPACE = "jupyterlab-notifications-extension"

# Process-lifetime monotonic counter for notification ids. Guarantees a
# unique id even across store drains (unlike len(_notification_store),
# which resets to 0 on every fetch and could collide).
_id_counter = itertools.count(1)

# In-memory storage for pending notifications. Drained destructively by the
# first client to poll - see NotificationFetchHandler - so this is a queue,
# not a per-client mailbox.
_notification_store: List[Dict] = []

# The queue only drains when a client polls, so a server whose lab tabs are all
# closed grows it without limit. Past this many, the oldest is dropped: the
# frontend bounds its own two tracking structures for the same reason.
MAX_QUEUED_NOTIFICATIONS = 500

# How long a notification stays on screen when the caller does not say. The
# frontend's send dialog and the CLI both default to the same number.
DEFAULT_AUTO_CLOSE_MS = 5000

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
        "data": {},  // optional: arbitrary JSON; every number in it must be finite
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

            # Validate types, not just presence. The poll fetch is a destructive
            # drain and the frontend displays a whole batch in one loop, so a
            # payload that throws browser-side takes every notification behind
            # it with it - and those are then gone for good.
            if not isinstance(payload, dict):
                self.set_status(400)
                self.finish(json.dumps({"error": "Body must be a JSON object"}))
                return

            message = payload.get('message')
            if not isinstance(message, str) or not message.strip():
                self.set_status(400)
                self.finish(json.dumps(
                    {"error": "'message' must be a non-empty string"}
                ))
                return

            # Element types matter as much as the container's: the frontend reads
            # action.label off every element, and a non-string label makes
            # JupyterLab's own renderer throw, which kills the tab's whole toast
            # surface until it is reloaded.
            actions = payload.get('actions', [])
            if not isinstance(actions, list) or not all(
                isinstance(action, dict) and isinstance(action.get('label'), str)
                for action in actions
            ):
                self.set_status(400)
                self.finish(json.dumps(
                    {"error": "'actions' must be a list of objects, each with "
                              "a string 'label'"}
                ))
                return

            # Serialised here to fail the sender rather than the reader: the
            # store is drained before it is serialised, so one non-finite number
            # reaching the frontend makes JSON.parse reject the whole batch and
            # every other sender's notification in it is lost.
            try:
                json.dumps(payload, allow_nan=False)
            except ValueError:
                self.set_status(400)
                self.finish(json.dumps(
                    {"error": "numbers must be finite; NaN and Infinity "
                              "are not JSON"}
                ))
                return

            # Create notification object
            notification = {
                "id": f"notif_{int(time.time() * 1000)}_{next(_id_counter)}",
                "message": message,
                "type": payload.get('type', 'info'),
                "autoClose": payload.get('autoClose', DEFAULT_AUTO_CLOSE_MS),
                "createdAt": int(time.time() * 1000),
                "actions": actions,
                "data": payload.get('data')
            }

            # Add to the poll queue. NOTE: the poll fetch is a
            # destructive, single-consumer drain - the first client to poll
            # empties the queue for all clients - so queue delivery is
            # best-effort, not a per-client guarantee. Immediate ("--now")
            # notifications are additionally pushed to every currently
            # connected socket below for instant, all-tabs delivery.
            _notification_store.append(notification)
            if len(_notification_store) > MAX_QUEUED_NOTIFICATIONS:
                del _notification_store[:-MAX_QUEUED_NOTIFICATIONS]

            if payload.get('immediate'):
                _push_immediate(notification, self.log)

            self.finish(json.dumps({
                "success": True,
                "notification_id": notification['id']
            }))

        except (UnicodeDecodeError, json.JSONDecodeError, RecursionError,
                ValueError):
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
        # Get all pending notifications
        notifications = _notification_store.copy()

        # Cleared in place: everything else mutates this list in place, and
        # rebinding the global would strand any reference taken across a drain.
        _notification_store.clear()

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
