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


async def test_ingest_applies_the_documented_auto_close_default(jp_fetch):
    """A REST caller that omits autoClose gets the value README documents.

    The frontend always sends one, so this default reaches only a raw REST
    caller - which is exactly why nothing pinned it and the value could be
    changed without a test noticing.
    """
    await jp_fetch(
        "jupyterlab-notifications-extension", "ingest",
        method="POST",
        body=json.dumps({"message": "No autoClose given"}),
    )

    response = await jp_fetch("jupyterlab-notifications-extension", "notifications")
    notification = json.loads(response.body.decode())["notifications"][0]

    assert notification["autoClose"] == routes.DEFAULT_AUTO_CLOSE_MS
    assert notification["autoClose"] == 5000


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


async def test_notification_ids_unique_across_drains(jp_fetch, monkeypatch):
    """Ids stay unique across a drain because the suffix is a counter, not len().

    The clock is pinned so the millisecond prefix is identical in both ids. That
    is what makes the assertion bite: with a real clock the prefixes differ on
    their own and the test passes even when the suffix resets.
    """
    monkeypatch.setattr(routes.time, "time", lambda: 1_000_000.0)

    r1 = await jp_fetch(
        "jupyterlab-notifications-extension", "ingest",
        method="POST", body=json.dumps({"message": "A"})
    )
    # Drain the store, which resets len() to 0
    await jp_fetch("jupyterlab-notifications-extension", "notifications")
    r2 = await jp_fetch(
        "jupyterlab-notifications-extension", "ingest",
        method="POST", body=json.dumps({"message": "B"})
    )
    id1 = json.loads(r1.body)["notification_id"]
    id2 = json.loads(r2.body)["notification_id"]

    prefix1, suffix1 = id1.rsplit("_", 1)
    prefix2, suffix2 = id2.rsplit("_", 1)
    assert prefix1 == prefix2, "clock not pinned; the test would pass on the prefix alone"
    assert suffix1 != suffix2
    assert id1 != id2


class _FakeListener:
    """Stands in for a connected NotificationStreamHandler."""

    def __init__(self, raises=None):
        self.messages = []
        self._raises = raises

    def write_message(self, message):
        if self._raises is not None:
            raise self._raises
        self.messages.append(message)


class _FakeLog:
    """Captures the warnings _push_immediate routes through the app logger."""

    def __init__(self):
        self.warnings = []

    def warning(self, *args, **kwargs):
        self.warnings.append(args)


@pytest.fixture(autouse=True)
def clear_stream_listeners():
    """Drop any listener a previous test registered"""
    routes._stream_listeners.clear()
    yield
    routes._stream_listeners.clear()


def test_push_immediate_writes_to_every_listener():
    """An immediate notification reaches all connected sockets, not just one"""
    first, second = _FakeListener(), _FakeListener()
    routes._stream_listeners.update({first, second})

    routes._push_immediate({"id": "notif_1_1", "message": "hello"}, _FakeLog())

    for listener in (first, second):
        assert len(listener.messages) == 1
        payload = json.loads(listener.messages[0])
        assert payload["notifications"][0]["id"] == "notif_1_1"


def test_push_immediate_discards_a_closed_listener():
    """A genuinely closed socket is dropped from the listener set"""
    from tornado.websocket import WebSocketClosedError

    closed = _FakeListener(raises=WebSocketClosedError())
    routes._stream_listeners.add(closed)

    routes._push_immediate({"id": "notif_1_2", "message": "x"}, _FakeLog())

    assert closed not in routes._stream_listeners


def test_push_immediate_keeps_a_listener_that_errors_otherwise():
    """A transient write error is logged, and the listener is kept"""
    flaky = _FakeListener(raises=RuntimeError("transient"))
    routes._stream_listeners.add(flaky)
    log = _FakeLog()

    routes._push_immediate({"id": "notif_1_3", "message": "x"}, log)

    assert flaky in routes._stream_listeners
    assert len(log.warnings) == 1


def test_push_immediate_with_no_listeners_is_a_noop():
    """No sockets connected is not an error; the poll still delivers"""
    log = _FakeLog()

    routes._push_immediate({"id": "notif_1_4", "message": "x"}, log)

    # The fixture already emptied the set, so only the warning can fail here.
    assert log.warnings == []


async def test_immediate_ingest_pushes_to_listeners(jp_fetch):
    """POSTing immediate true pushes over the stream as well as queueing"""
    listener = _FakeListener()
    routes._stream_listeners.add(listener)

    await jp_fetch(
        "jupyterlab-notifications-extension",
        "ingest",
        method="POST",
        body=json.dumps({"message": "Now", "immediate": True}),
    )

    assert len(listener.messages) == 1
    assert json.loads(listener.messages[0])["notifications"][0]["message"] == "Now"
    assert len(routes._notification_store) == 1


async def test_non_immediate_ingest_does_not_push(jp_fetch):
    """Without the flag the notification waits for the poll"""
    listener = _FakeListener()
    routes._stream_listeners.add(listener)

    await jp_fetch(
        "jupyterlab-notifications-extension",
        "ingest",
        method="POST",
        body=json.dumps({"message": "Later"}),
    )

    assert listener.messages == []
    assert len(routes._notification_store) == 1


def test_all_three_routes_are_registered():
    """ACC-IMMED-5: ingest, notifications and the stream are all mounted."""
    registered = []

    class _FakeWebApp:
        settings = {"base_url": "/"}

        def add_handlers(self, host_pattern, handlers):
            registered.extend(pattern for pattern, _ in handlers)

    routes.setup_route_handlers(_FakeWebApp())

    assert any(p.endswith("/ingest") for p in registered)
    assert any(p.endswith("/notifications") for p in registered)
    assert any(p.endswith("/stream") for p in registered)
    assert all(routes.API_NAMESPACE in p for p in registered)


def test_stream_route_maps_to_the_authenticated_handler():
    """ACC-IMMED-5 / ACC-IMMED-6: the stream is the ws-authenticated handler."""
    mapping = {}

    class _FakeWebApp:
        settings = {"base_url": "/"}

        def add_handlers(self, host_pattern, handlers):
            mapping.update(dict(handlers))

    routes.setup_route_handlers(_FakeWebApp())
    stream = next(h for p, h in mapping.items() if p.endswith("/stream"))

    # Which handler serves the route is what this can prove. That the handler
    # actually authenticates is proved by .github/scripts/check_auth.py, which
    # fails when @ws_authenticated is removed; a decorator-shape assertion here
    # passed against a no-op wrapper, so it is not kept.
    assert stream is routes.NotificationStreamHandler


async def test_ingest_500_body_is_generic(jp_fetch, monkeypatch):
    """ACC-IMMED-28: an unexpected failure must not leak internals."""
    def boom(notification, log):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(routes, "_push_immediate", boom)

    with pytest.raises(Exception) as excinfo:
        await jp_fetch(
            "jupyterlab-notifications-extension",
            "ingest",
            method="POST",
            body=json.dumps({"message": "x", "immediate": True}),
        )

    response = excinfo.value.response
    assert response.code == 500
    body = json.loads(response.body)
    assert body == {"error": "Internal server error"}
    assert "secret internal detail" not in response.body.decode()


# --- ingest rejects payloads that would break the display loop ---------------

@pytest.mark.parametrize(
    "body,reason",
    [
        ('{"message": 42}', "numeric message"),
        ('{"message": {"a": 1}}', "object message"),
        ('{"message": ["a", "b"]}', "list message"),
        ('{"message": null}', "null message"),
        ('{"message": ""}', "empty message"),
        ('{"message": "   "}', "whitespace-only message"),
        ('{"message": "ok", "actions": "Retry"}', "string actions"),
        ('{"message": "ok", "actions": [null]}', "null action element"),
        ('{"message": "ok", "actions": ["Retry"]}', "string action element"),
        ('{"message": "ok", "actions": [{}]}', "action with no label"),
        ('{"message": "ok", "actions": [{"label": {"x": 1}}]}', "object label"),
        ('{"message": "ok", "actions": [{"label": 7}]}', "numeric label"),
        ('5', "scalar body"),
        ('null', "null body"),
        # json.dumps emits these for any non-finite float, so a script building
        # --data from computed metrics produces one without trying. Each makes the
        # server re-emit invalid JSON: --now shows no toast while the CLI exits 0,
        # and a poll clears the store before serialising, so every other sender's
        # notification in that batch is destroyed.
        ('{"message": "ok", "data": {"loss": NaN}}', "NaN in data"),
        ('{"message": "ok", "data": {"loss": Infinity}}', "Infinity in data"),
        ('{"message": "ok", "data": {"loss": -Infinity}}', "-Infinity in data"),
        ('{"message": "ok", "data": {"loss": 1e400}}', "overflowing literal"),
        ('{"message": "ok", "autoClose": NaN}', "NaN autoClose"),
    ],
)
async def test_ingest_rejects_unusable_payloads(jp_fetch, body, reason):
    """A payload that throws browser-side would discard the whole drained batch."""
    with pytest.raises(Exception) as excinfo:
        await jp_fetch(
            "jupyterlab-notifications-extension",
            "ingest",
            method="POST",
            body=body,
        )

    assert excinfo.value.response.code == 400, reason
    assert routes._notification_store == [], "a rejected payload must not queue"


async def test_ingest_drops_the_oldest_past_the_queue_bound(jp_fetch, monkeypatch):
    """Nothing drains the queue while every lab tab is closed, so it must self-bound."""
    monkeypatch.setattr(routes, "MAX_QUEUED_NOTIFICATIONS", 3)

    for i in range(5):
        await jp_fetch(
            "jupyterlab-notifications-extension",
            "ingest",
            method="POST",
            body=json.dumps({"message": f"m{i}"}),
        )

    assert len(routes._notification_store) == 3
    # The newest survive: the oldest are the ones a reader has least use for.
    assert [n["message"] for n in routes._notification_store] == ["m2", "m3", "m4"]


def test_stream_handler_does_not_opt_out_of_authentication():
    """The stream must not be marked as allowing unauthenticated access.

    check_auth.py only reports a handler carrying no auth decorator at all, so
    swapping @ws_authenticated for @allow_unauthenticated passes that gate.
    jupyter_server marks the two apart on the wrapper: ws_authenticated sets
    __allow_unauthenticated False, allow_unauthenticated sets it True, and an
    undecorated method has neither.
    """
    marker = getattr(routes.NotificationStreamHandler.get,
                     "__allow_unauthenticated", None)

    assert marker is False, (
        "the stream is either undecorated or explicitly public; "
        f"__allow_unauthenticated is {marker!r}"
    )


def test_http_handlers_do_not_opt_out_of_authentication():
    """Ingest and fetch must not be marked public either.

    check_auth.py reports only a handler with no decorator, so swapping either
    for @allow_unauthenticated leaves the whole gate green while any local
    process could post to every open tab of this server.
    """
    for handler, verb in (
        (routes.NotificationIngestHandler.post, "ingest POST"),
        (routes.NotificationFetchHandler.get, "fetch GET"),
    ):
        marker = getattr(handler, "__allow_unauthenticated", False)
        assert marker is not True, f"{verb} is marked as allowing unauthenticated access"


async def test_a_non_utf8_body_is_a_bad_payload(jp_fetch):
    """Every other malformed body answers 400; this one answered 500.

    UnicodeDecodeError is a ValueError but not a JSONDecodeError, so it missed the
    400 arm and each attempt wrote a traceback into the server log.
    """
    with pytest.raises(Exception) as excinfo:
        await jp_fetch(
            "jupyterlab-notifications-extension",
            "ingest",
            method="POST",
            body='{"message": "caf\u00e9"}'.encode("latin-1"),
        )

    assert excinfo.value.response.code == 400
    assert routes._notification_store == []


async def test_a_finite_number_in_data_is_still_accepted(jp_fetch):
    """The control for the non-finite cases above.

    Without it a guard that refused every payload carrying a number would pass.
    """
    response = await jp_fetch(
        "jupyterlab-notifications-extension",
        "ingest",
        method="POST",
        body='{"message": "ok", "data": {"loss": 0.25}, "autoClose": 5000}',
    )

    assert response.code == 200


@pytest.mark.parametrize(
    "body,reason",
    [
        ("[" * 20000 + "]" * 20000, "nesting past the recursion limit"),
        ('{"message": "ok", "data": {"n": ' + "1" * 5000 + "}}",
         "an integer past the 4300-digit limit"),
    ],
)
async def test_a_body_json_cannot_parse_is_a_bad_payload(jp_fetch, body, reason):
    """Neither of these raises JSONDecodeError, so both answered 500.

    RecursionError is not a ValueError at all, and the digit limit raises a plain
    ValueError; every sibling malformed shape answers 400, and each 500 wrote a
    traceback into the administrator's log.
    """
    with pytest.raises(Exception) as excinfo:
        await jp_fetch(
            "jupyterlab-notifications-extension",
            "ingest",
            method="POST",
            body=body,
        )

    assert excinfo.value.response.code == 400, reason
    assert routes._notification_store == []
