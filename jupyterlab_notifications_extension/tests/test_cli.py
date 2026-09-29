"""Tests for the jupyterlab-notify CLI, covering how it scopes the auth token.

The CLI auto-detects the local server's token when none is given. That token
must never reach a host the user pointed it at explicitly, and must never
travel in the URL where it would land in the server's access log.
"""
import io
import json
import urllib.error
from urllib.parse import urlparse
import ssl
from http.client import BadStatusLine, IncompleteRead, RemoteDisconnected

import pytest

from jupyterlab_notifications_extension import cli

SENTINEL_TOKEN = "sentinel-local-token"

# The captured_request fixture stubs detect_token. A test that needs the real
# precedence must put it back, so keep a reference from before any stubbing.
_REAL_DETECT_TOKEN = cli.detect_token


@pytest.fixture
def captured_request(monkeypatch):
    """Capture the urllib Request the CLI builds, without any network call."""
    captured = {}

    def fake_urlopen(req, *args, **kwargs):
        captured["request"] = req
        # io.BytesIO is already a context manager, which is all the CLI uses.
        return io.BytesIO(json.dumps({"notification_id": "notif_1_1"}).encode())

    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(cli, "detect_token", lambda: SENTINEL_TOKEN)
    # The developer's own shell must not decide the result: this variable
    # legitimately outranks detect_token, so leaving it set fails the suite.
    monkeypatch.delenv("JUPYTERLAB_NOTIFY_TOKEN", raising=False)
    return captured


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8888",
        "http://127.0.0.1:8888/jupyterhub/user/konrad",
        "http://localhost:8888",
        "http://[::1]:8888/lab",
    ],
)
def test_is_loopback_url_accepts_loopback(url):
    assert cli._is_loopback_url(url) is True


@pytest.mark.parametrize(
    "url",
    [
        "http://remote-host:8888",
        "http://192.168.1.50:8888",
        # the host is evil.com; 127.0.0.1 is only userinfo
        "http://127.0.0.1@evil.com/",
        "http://localhost.evil.com/",
        "http://127.0.0.1.evil.com/",
        "https://evil.com/?x=127.0.0.1",
    ],
)
def test_is_loopback_url_rejects_remote_and_spoofs(url):
    assert cli._is_loopback_url(url) is False


def test_tool_token_variable_reaches_a_remote_host(captured_request, monkeypatch):
    """JUPYTERLAB_NOTIFY_TOKEN is aimed by the user, so it may go anywhere.

    It exists so a remote send does not have to put the secret in argv, where
    every local account can read /proc/<pid>/cmdline.
    """
    monkeypatch.setenv("JUPYTERLAB_NOTIFY_TOKEN", "aimed-token")
    cli.send_notification_api(base_url="http://remote-host:8888", message="x")

    req = captured_request["request"]
    assert req.headers.get("Authorization") == "token aimed-token"


def test_ambient_jupyter_token_does_not_reach_a_remote_host(
    captured_request, monkeypatch
):
    """The server's own token stays loopback-only, even via the environment.

    The real detect_token is restored, or the fixture's stub would mean the
    variable this test sets is never read and the name describes a path the
    test does not take.
    """
    monkeypatch.setattr(cli, "detect_token", _REAL_DETECT_TOKEN)
    monkeypatch.delenv("JUPYTERLAB_NOTIFY_TOKEN", raising=False)
    monkeypatch.setenv("JUPYTER_TOKEN", "ambient-local-token")
    cli.send_notification_api(base_url="http://remote-host:8888", message="x")

    req = captured_request["request"]
    assert "Authorization" not in req.headers


def test_remote_url_gets_no_auto_token(captured_request, monkeypatch):
    """A host the user named explicitly never receives the detected token."""
    monkeypatch.delenv("JUPYTERLAB_NOTIFY_TOKEN", raising=False)
    cli.send_notification_api(base_url="http://remote-host:8888", message="x")

    req = captured_request["request"]
    assert "Authorization" not in req.headers
    assert "authorization" not in {k.lower() for k in req.headers}
    assert SENTINEL_TOKEN not in req.full_url


def test_loopback_url_gets_auto_token(captured_request):
    """A loopback target is safe, so the detected token is attached."""
    cli.send_notification_api(base_url="http://127.0.0.1:8888", message="x")

    req = captured_request["request"]
    assert req.headers.get("Authorization") == f"token {SENTINEL_TOKEN}"


def test_explicit_token_reaches_a_remote_host(captured_request):
    """An explicitly passed token is the user's own choice of target."""
    cli.send_notification_api(
        base_url="http://remote-host:8888", message="x", token="user-supplied"
    )

    req = captured_request["request"]
    assert req.headers.get("Authorization") == "token user-supplied"


def test_token_never_travels_in_the_url(captured_request):
    """The token goes in the header only, so it stays out of access logs."""
    cli.send_notification_api(base_url="http://127.0.0.1:8888", message="x")

    assert "token=" not in captured_request["request"].full_url


def test_immediate_flag_sets_payload_field(captured_request):
    """--now maps to the immediate field the server pushes on."""
    cli.send_notification_api(
        base_url="http://127.0.0.1:8888", message="x", immediate=True
    )

    payload = json.loads(captured_request["request"].data.decode())
    assert payload["immediate"] is True


def test_immediate_absent_by_default(captured_request):
    """Without --now the field is absent, so the server takes the poll path."""
    cli.send_notification_api(base_url="http://127.0.0.1:8888", message="x")

    payload = json.loads(captured_request["request"].data.decode())
    assert "immediate" not in payload


# --- the failure report carries a reason, never a markup page ----------------

class _FakeHTTPError(urllib.error.HTTPError):
    """An HTTPError whose body is whatever the test hands it."""

    def __init__(self, body, code=502, reason="Bad Gateway"):
        super().__init__("http://127.0.0.1:8888", code, reason, {},
                         io.BytesIO(body))


class _TruncatedHTTPError(urllib.error.HTTPError):
    """An HTTPError whose body stops mid-read, as a dropped connection does.

    IncompleteRead is an HTTPException, not an OSError, so it escaped the
    original guard and replaced the whole failure report with a read error.
    """

    def __init__(self, code=502, reason="Bad Gateway"):
        super().__init__("http://127.0.0.1:8888", code, reason, {}, None)

    def read(self, *args, **kwargs):
        raise IncompleteRead(b'{"error": "par', 4986)


@pytest.mark.parametrize(
    "body,expected",
    [
        (b'{"error": "no message"}', ": no message"),
        (b'{"message": "Forbidden"}', ": Forbidden"),
        # A proxy answers a restart with its own page, and a --url ending in
        # /lab answers 405 with the whole lab document. Neither belongs in a
        # one-line report, and the status already says what happened.
        (b'<html><head><title>504</title></head><body>' + b'x' * 3000, ""),
        (b'{"detail": "upstream closed"}', ""),
        (b'', ""),
        (b'{}', ""),
        (b'[]', ""),
        (b'null', ""),
        (b'{"error": ""}', ""),
        (b'{"error": {"nested": 1}}', ""),
        (b'\xff\xfe not utf-8 \x80', ""),
    ],
)
def test_readable_reason_takes_only_a_usable_string(body, expected):
    assert cli._readable_reason(_FakeHTTPError(body)) == expected


@pytest.mark.parametrize(
    "make_error,expected",
    [
        (lambda: _FakeHTTPError(b'<html>' + b'y' * 4000, code=405,
                                reason="Method Not Allowed"),
         "HTTP 405 Method Not Allowed from http://remote-host:8888"),
        (lambda: _TruncatedHTTPError(),
         "HTTP 502 Bad Gateway from http://remote-host:8888"),
        # A reason the status line does not already carry must survive, or
        # deleting _readable_reason from the report would pass every test.
        (lambda: _FakeHTTPError(b'{"message": "Token is invalid"}', code=403,
                                reason="Forbidden"),
         "HTTP 403 Forbidden from http://remote-host:8888: Token is invalid"),
        # jupyter_server sets 'message' to the status phrase when the error
        # carries no log message, which printed the phrase twice.
        (lambda: _FakeHTTPError(b'{"message": "Forbidden"}', code=403,
                                reason="Forbidden"),
         "HTTP 403 Forbidden from http://remote-host:8888"),
    ],
)
def test_failure_report_is_one_status_line(make_error, expected, monkeypatch):
    """The operator must not have to scroll a proxy page to find the status.

    Asserts on what send_notification_api raises. The test this replaced
    rebuilt the format string itself, so it passed with the markup body
    interpolated back into the report and never ran the reporting code.
    """
    def fake_urlopen(req, *args, **kwargs):
        raise make_error()

    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)
    # A remote target takes no auto-detected token, so nothing reads the
    # developer's own running servers; the variable must not decide the result.
    monkeypatch.delenv("JUPYTERLAB_NOTIFY_TOKEN", raising=False)

    with pytest.raises(RuntimeError) as raised:
        cli.send_notification_api(base_url="http://remote-host:8888", message="x")

    line = str(raised.value)
    assert line == expected
    assert len(line.splitlines()) == 1


def test_unreachable_server_names_the_url_and_what_to_check(monkeypatch):
    """A server that is not running is the common failure, so the line says so."""
    def fake_urlopen(req, *args, **kwargs):
        raise urllib.error.URLError("Connection refused")

    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.delenv("JUPYTERLAB_NOTIFY_TOKEN", raising=False)

    with pytest.raises(RuntimeError) as raised:
        cli.send_notification_api(base_url="http://remote-host:8888", message="x")

    assert str(raised.value) == (
        "cannot reach http://remote-host:8888: Connection refused; "
        "is JupyterLab running there?"
    )


def test_main_reports_one_failure_line_on_stderr_and_exits_1(monkeypatch, capsys):
    """stdout carries the sent id and nothing else, so a failure leaves it empty.

    Covers main's own report, which no test reached: a script parsing stdout
    must not receive a failure line, and the operator must get exactly one.
    """
    def fake_urlopen(req, *args, **kwargs):
        raise _FakeHTTPError(b'<html>' + b'y' * 4000, code=405,
                             reason="Method Not Allowed")

    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.delenv("JUPYTERLAB_NOTIFY_TOKEN", raising=False)
    # main reads the server list before the loopback rule rejects the host, so
    # without this the test spawns the developer's own `jupyter server list`.
    monkeypatch.setattr(cli, "_list_running_servers", lambda: [])
    monkeypatch.setattr("sys.argv",
                        ["jupyterlab-notify", "--url",
                         "http://remote-host:8888", "-m", "x"])

    assert cli.main() == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.splitlines() == [
        "URL: http://remote-host:8888 (no listed server matched) | Type: info",
        "Sending without an authentication token",
        "Failed to send notification: "
        "HTTP 405 Method Not Allowed from http://remote-host:8888",
    ]


def test_a_server_that_never_answers_does_not_block_for_ever(monkeypatch):
    """An unattended script is the usual sender, so the call must be bounded."""
    def fake_urlopen(req, *args, **kwargs):
        assert kwargs.get("timeout") == cli.REQUEST_TIMEOUT_S
        raise TimeoutError("timed out")

    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.delenv("JUPYTERLAB_NOTIFY_TOKEN", raising=False)

    with pytest.raises(RuntimeError) as raised:
        cli.send_notification_api(base_url="http://remote-host:8888", message="x")

    assert str(raised.value) == (
        "no answer from http://remote-host:8888 within 10s; "
        "is that server responding?"
    )


@pytest.mark.parametrize(
    "body",
    [
        # A 2xx from something that is not this endpoint. Reporting the read
        # error named neither the status nor the URL.
        b"<html><body>hello</body></html>",
        # A 2xx whose JSON has no id printed "Notification sent: None" and
        # exited 0, so a script's exit-code check passed for nothing sent.
        b'{"ok": true}',
    ],
)
def test_a_success_that_is_not_one_is_reported_as_a_failure(body, monkeypatch):
    """Exit 0 must mean the notification was ingested."""
    monkeypatch.setattr(cli.urllib.request, "urlopen",
                        lambda req, *a, **k: io.BytesIO(body))
    monkeypatch.delenv("JUPYTERLAB_NOTIFY_TOKEN", raising=False)

    with pytest.raises(RuntimeError) as raised:
        cli.send_notification_api(base_url="http://remote-host:8888", message="x")

    assert str(raised.value) == (
        "unreadable answer from http://remote-host:8888; only this extension's "
        "ingest endpoint answers here"
    )


@pytest.mark.parametrize(
    "error",
    [
        # All three are HTTPException and none is an OSError, so all three
        # escaped every arm and reported a bare read error naming no URL.
        IncompleteRead(b"partial", 182),
        RemoteDisconnected("Remote end closed connection without response"),
        # A reply in another protocol. Its message carries the peer's own
        # bytes, so a raw CRLF in them made the report two lines.
        BadStatusLine("SSH-2.0-OpenSSH_9.6\r\n"),
        # A reset as the response is read. urllib wraps only h.request in
        # URLError, so this arrives bare and matched no arm: the report lost
        # the URL and the warning that the notification may already exist.
        ConnectionResetError(104, "Connection reset by peer"),
        # TLS state lost after the POST was read. An OSError, so it escaped
        # every arm and the report lost the URL and the double-send warning.
        ssl.SSLError("[SSL] record layer failure (_ssl.c:2660)"),
    ],
)
def test_a_transport_that_fails_mid_answer_still_names_the_url(
    error, monkeypatch
):
    """And says the notification may exist, because a retry would double-send."""
    def fake_urlopen(req, *args, **kwargs):
        raise error

    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.delenv("JUPYTERLAB_NOTIFY_TOKEN", raising=False)

    with pytest.raises(RuntimeError) as raised:
        cli.send_notification_api(base_url="http://remote-host:8888", message="x")

    line = str(raised.value)
    assert "failed before a usable answer arrived" in line
    assert "http://remote-host:8888" in line
    # Conditional, because for a reply in another protocol nothing was ingested.
    assert "if that was this server's ingest endpoint" in line
    assert len(line.splitlines()) == 1


def test_a_port_that_is_not_a_number_matches_no_listed_server():
    """Reading it raised before any reporting ran, printing a urllib traceback."""
    assert cli._match_listed_server("http://127.0.0.1:888o/", [SERVER_A]) is None


def test_a_mistyped_port_reports_one_line_instead_of_a_traceback(
    monkeypatch, capsys
):
    """The documented exit codes promise a report, not an interpreter error."""
    monkeypatch.delenv("JUPYTERLAB_NOTIFY_TOKEN", raising=False)
    monkeypatch.setattr(cli, "_list_running_servers", lambda: [])
    monkeypatch.setattr("sys.argv",
                        ["jupyterlab-notify", "--url",
                         "http://127.0.0.1:888o", "-m", "x"])

    assert cli.main() == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    failure = [
        line for line in captured.err.splitlines()
        if line.startswith("Failed to send notification:")
    ]
    assert failure == [
        "Failed to send notification: bad URL http://127.0.0.1:888o: "
        "the port must be a number from 0 to 65535 "
        "(Port could not be cast to integer value as '888o')"
    ]


@pytest.mark.parametrize(
    "base_url",
    [
        "http://127.0.0.1:8888",
        # `jupyter server list` prints this form and a hub address bar ends
        # /user/<name>/, so it is the likeliest thing an operator pastes.
        "http://127.0.0.1:8888/",
        "http://127.0.0.1:8888/user/alice",
        "http://127.0.0.1:8888/user/alice/",
    ],
)
def test_the_endpoint_path_never_doubles_its_slash(
    base_url, captured_request
):
    """A doubled slash made the server answer 404 for a deliverable send."""
    cli.send_notification_api(base_url=base_url, message="x")

    full_url = captured_request["request"].full_url
    assert full_url.startswith(base_url.rstrip("/") + "/")
    assert "//jupyterlab-notifications-extension" not in full_url
    assert full_url.endswith("/jupyterlab-notifications-extension/ingest")


# A record for a server bound to one specific non-loopback address. 127.0.0.1
# does not reach it, so addressing it as loopback posted its token elsewhere.
LAN_SERVER = {
    "port": 8792, "base_url": "/", "token": "lan-token",
    "hostname": "172.24.0.3",
}
# What a server started with the default bind records, which loopback does reach.
ANY_SERVER = {
    "port": 8792, "base_url": "/", "token": "any-token", "hostname": "0.0.0.0",
}


def test_a_loopback_url_does_not_match_a_server_bound_elsewhere():
    """Its token would go to whatever local process holds that port."""
    assert cli._match_listed_server("http://127.0.0.1:8792/", [LAN_SERVER]) is None


def test_a_loopback_url_still_matches_a_server_bound_to_all_addresses():
    """Positive control: refusing every record would be just as wrong."""
    assert cli._match_listed_server("http://127.0.0.1:8792/", [ANY_SERVER]) \
        is ANY_SERVER


def test_the_url_for_a_server_bound_elsewhere_names_its_own_host():
    assert cli._server_url(LAN_SERVER) == "http://172.24.0.3:8792"
    assert cli._server_url(ANY_SERVER) == "http://127.0.0.1:8792"


# jupyter_server records ServerApp.ip verbatim, and tornado binds an AF_INET6
# socket with IPV6_V6ONLY set, so 127.0.0.1 reaches neither of these.
V6_LOOPBACK_SERVER = {
    "port": 8912, "base_url": "/", "token": "v6-token", "hostname": "::1",
}
V6_WILDCARD_SERVER = {
    "port": 8912, "base_url": "/", "token": "v6-token", "hostname": "::",
}


def test_a_both_family_bind_matches_either_url_family():
    """localhost reaches either family, so it must match a URL of either.

    Collapsing the entry to a single literal left the whole suite green.
    """
    record = {"port": 8792, "base_url": "/", "token": "t",
              "hostname": "localhost"}
    assert cli._match_listed_server("http://[::1]:8792/", [record]) is record
    assert cli._match_listed_server("http://127.0.0.1:8792/", [record]) is record


@pytest.mark.parametrize("url", ["http://127.0.0.1:8792/", "http://[::1]:8792/",
                                 "http://localhost:8792/"])
def test_a_record_with_no_bind_address_matches_nothing(url):
    """Fails closed on a record shape jupyter_server cannot produce.

    ServerApp.server_info always writes hostname, so an absent one is a record
    this CLI did not read from a runtime file. Treating it as a bare bind -
    which is what the table did - made it reach both loopback families, so
    anything that could put a hostname-less record in front of the matcher got
    the token of whatever was on that port.
    """
    assert cli._match_listed_server(url, [{"port": 8792, "base_url": "/",
                                           "token": "t"}]) is None


@pytest.mark.parametrize("hostname", ["0.0.0.0", "127.0.0.1"])
def test_an_ipv4_only_bind_refuses_an_ipv6_url(hostname):
    """Widening either to both families reopens the leak on the other axis."""
    record = {"port": 8792, "base_url": "/", "token": "t", "hostname": hostname}
    assert cli._match_listed_server("http://[::1]:8792/", [record]) is None


@pytest.mark.parametrize(
    "hostname,expected",
    [
        # localhost resolves to ::1 first under RFC 6724, so a localhost URL
        # matching an IPv4-only record used to send its token to whatever held
        # the IPv6 port. It must match, and be addressed by the record's host.
        ("0.0.0.0", "http://127.0.0.1:8792"),
        ("127.0.0.1", "http://127.0.0.1:8792"),
        ("::1", "http://[::1]:8792"),
        ("::", "http://[::1]:8792"),
    ],
)
def test_a_localhost_url_matches_either_family_and_is_readdressed(
    hostname, expected
):
    record = {"port": 8792, "base_url": "/", "token": "t", "hostname": hostname}
    assert cli._match_listed_server("http://localhost:8792/", [record]) is record
    assert cli._server_url(record) == expected


def test_main_addresses_the_matched_record_not_the_typed_host(
    captured_request, monkeypatch
):
    """The spelling the operator typed is not where the server is listening."""
    record = {"port": 8792, "base_url": "/", "token": "rec-token",
              "hostname": "0.0.0.0"}
    monkeypatch.setattr(cli, "detect_token", _REAL_DETECT_TOKEN)
    monkeypatch.delenv("JUPYTERLAB_NOTIFY_TOKEN", raising=False)
    monkeypatch.setattr(cli, "_list_running_servers", lambda: [record])
    monkeypatch.setattr("sys.argv",
                        ["jupyterlab-notify", "--url",
                         "http://localhost:8792/", "-m", "x"])

    assert cli.main() == 0

    request = captured_request["request"]
    assert request.full_url.startswith("http://127.0.0.1:8792/")
    assert request.headers.get("Authorization") == "token rec-token"


@pytest.mark.parametrize("record", [V6_LOOPBACK_SERVER, V6_WILDCARD_SERVER])
def test_an_ipv6_bound_server_is_addressed_over_ipv6(record):
    """Addressing it as 127.0.0.1 both failed to deliver and freed that port."""
    assert cli._server_url(record) == "http://[::1]:8912"
    # Reachable at [::1], and deliberately not at 127.0.0.1: tornado binds
    # AF_INET6 with IPV6_V6ONLY, so that port is free for anyone to take.
    assert cli._match_listed_server("http://[::1]:8912/", [record]) is record
    assert cli._match_listed_server("http://127.0.0.1:8912/", [record]) is None


def test_an_ipv6_host_that_is_not_loopback_is_bracketed():
    """Unbracketed, urlparse reads the port as part of the address and raises."""
    record = {"port": 8912, "base_url": "/", "token": "t", "hostname": "fd12::3"}
    url = cli._server_url(record)
    assert url == "http://[fd12::3]:8912"
    assert urlparse(url).hostname == "fd12::3"
    assert urlparse(url).port == 8912


def test_a_records_own_token_reaches_the_address_that_record_names(
    captured_request, monkeypatch
):
    """The record names this host and port, so its token belongs to this target.

    Honouring the record's host without this made a server bound with
    --ip=<an address> reachable and then refused, every time.
    """
    monkeypatch.delenv("JUPYTERLAB_NOTIFY_TOKEN", raising=False)
    lan = {"port": 8795, "base_url": "/", "token": "lan-token",
           "hostname": "172.24.0.3"}

    cli.send_notification_api(base_url=cli._server_url(lan), message="x",
                              server=lan)

    request = captured_request["request"]
    assert request.full_url.startswith("http://172.24.0.3:8795/")
    assert request.headers.get("Authorization") == "token lan-token"


def test_an_empty_url_is_not_treated_as_no_url(monkeypatch, capsys):
    """An unset shell variable must not silently deliver somewhere else.

    `--url "$LAB_URL"` with LAB_URL unset gives argparse an empty string, which
    is falsy; the branch fell through to auto-detection and reported success.
    """
    monkeypatch.delenv("JUPYTERLAB_NOTIFY_TOKEN", raising=False)
    monkeypatch.delenv("JUPYTERHUB_SERVICE_PREFIX", raising=False)
    monkeypatch.setattr(cli, "_list_running_servers", lambda: [SERVER_A])
    sent = []
    monkeypatch.setattr(cli.urllib.request, "urlopen",
                        lambda req, *a, **k: sent.append(req) or io.BytesIO(
                            b'{"notification_id": "x"}'))
    monkeypatch.setattr("sys.argv",
                        ["jupyterlab-notify", "--url", "", "-m", "x"])

    assert cli.main() == 1
    assert sent == [], "nothing may be sent for an empty --url"
    assert capsys.readouterr().out == ""


# --- choosing which running server to talk to -------------------------------

SERVER_A = {"port": 8888, "base_url": "/user/alice/", "token": "tok-a",
            "hostname": "localhost"}
SERVER_B = {"port": 8999, "base_url": "/", "token": "tok-b", "secure": True,
            "hostname": "localhost"}


def test_select_server_returns_the_only_one(monkeypatch):
    # Its three siblings control this and it did not: with the variable set to
    # SERVER_A's own base_url, the prefix branch returns the record and a
    # mutant that deletes the single-server rule below still passes.
    monkeypatch.delenv("JUPYTERHUB_SERVICE_PREFIX", raising=False)
    assert cli._select_server([SERVER_A]) is SERVER_A


def test_select_server_refuses_to_guess_between_several(monkeypatch):
    """An unordered list is not a choice, so no server is better than a wrong one."""
    # SERVER_A's base_url would otherwise resolve the ambiguity on a hub box.
    monkeypatch.delenv("JUPYTERHUB_SERVICE_PREFIX", raising=False)
    assert cli._select_server([SERVER_A, SERVER_B]) is None


def test_select_server_prefers_the_hub_prefix(monkeypatch):
    monkeypatch.setenv("JUPYTERHUB_SERVICE_PREFIX", "/user/alice")
    assert cli._select_server([SERVER_B, SERVER_A]) is SERVER_A


def test_select_server_ignores_a_prefix_that_matches_nothing(monkeypatch):
    monkeypatch.setenv("JUPYTERHUB_SERVICE_PREFIX", "/user/nobody")
    assert cli._select_server([SERVER_A, SERVER_B]) is None


def test_server_url_honours_the_secure_flag():
    assert cli._server_url(SERVER_B).startswith("https://")
    assert cli._server_url(SERVER_A).startswith("http://")


def test_main_exits_2_when_several_servers_are_running(monkeypatch, capsys):
    """Rather than post to whichever server os.listdir happened to yield first."""
    monkeypatch.delenv("JUPYTERHUB_SERVICE_PREFIX", raising=False)
    monkeypatch.setattr(cli, "_list_running_servers", lambda: [SERVER_A, SERVER_B])
    monkeypatch.setattr("sys.argv", ["jupyterlab-notify", "-m", "x"])

    assert cli.main() == 2
    # stderr: a script redirecting stdout to /dev/null must still see the reason.
    err = capsys.readouterr().err
    assert "--url" in err
    assert "8888" in err and "8999" in err


# --- an explicit --url still gets the right server's token -------------------

def test_match_listed_server_finds_the_named_target():
    """--url names the target, so ambiguity between servers must not deny it a token."""
    assert cli._match_listed_server("http://127.0.0.1:8888/user/alice",
                                    [SERVER_B, SERVER_A]) is SERVER_A


def test_match_listed_server_accepts_localhost_for_the_same_server():
    """The same server is reachable as localhost and as 127.0.0.1."""
    assert cli._match_listed_server("http://localhost:8888/user/alice",
                                    [SERVER_A]) is SERVER_A


def test_match_listed_server_ignores_a_remote_url():
    """A remote host must never be matched to a local record's token."""
    assert cli._match_listed_server("http://remote-host:8888/user/alice",
                                    [SERVER_A]) is None


def test_match_listed_server_returns_none_when_nothing_matches():
    assert cli._match_listed_server("http://127.0.0.1:9999/", [SERVER_A]) is None


def test_an_unmatched_loopback_url_gets_no_server_token(
    captured_request, monkeypatch
):
    """A mistyped port must not receive the token of some other listed server.

    Asserted on the wire rather than on detect_token, which no longer knows
    what a record is: the guarantee now belongs to send_notification_api,
    which attaches a record's token only when main resolved that record.
    """
    monkeypatch.setattr(cli, "detect_token", _REAL_DETECT_TOKEN)
    monkeypatch.delenv("JUPYTERLAB_NOTIFY_TOKEN", raising=False)
    for var in ("JUPYTERHUB_API_TOKEN", "JPY_API_TOKEN", "JUPYTER_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    # Stubbed, so the assertion cannot read whatever this machine is running.
    monkeypatch.setattr(cli, "_list_running_servers", lambda: [SERVER_A])

    # The port matches no listed record, so main would pass server=None.
    assert cli._match_listed_server("http://127.0.0.1:9999/", [SERVER_A]) is None
    cli.send_notification_api(base_url="http://127.0.0.1:9999", message="x",
                              server=None)

    assert captured_request["request"].headers.get("Authorization") is None


# A plaintext record at the default port and the root path: the one a URL with
# no usable port or a different scheme would wrongly fall back onto.
ROOT_SERVER = {"port": 8888, "base_url": "/", "token": "tok-root",
               "hostname": "localhost"}


def test_the_default_port_still_matches_the_root_server():
    """Positive control. Without it the three cases below pass vacuously."""
    assert cli._match_listed_server("http://127.0.0.1:8888/", [ROOT_SERVER]) \
        is ROOT_SERVER


@pytest.mark.parametrize(
    "url,why",
    [
        # parsed.port is 0 here and None below; `or` treated both as absent and
        # fell back to 8888, so each took the plaintext server's token.
        ("http://127.0.0.1:0/", "port 0 is not an absent port"),
        # A portless URL takes the scheme's default port, not this project's.
        # urlopen addresses 80 and 443 for these, so matching the 8888 record
        # sent its token to whatever else answers there.
        ("http://127.0.0.1/", "a portless http URL addresses port 80"),
        ("https://127.0.0.1/", "a portless https URL addresses port 443"),
        # Ports agree, scheme does not.
        ("https://127.0.0.1:8888/", "a record carries its own scheme"),
    ],
)
def test_a_url_that_only_looks_like_the_root_server_does_not_match(url, why):
    assert cli._match_listed_server(url, [ROOT_SERVER]) is None, why


def test_port_zero_falls_back_to_no_port_at_all():
    """Against a record on the scheme default, where the weakened test cannot see it.

    ROOT_SERVER is on 8888, so with a falsy-port mutant the URL resolves to 80
    and misses it for the wrong reason. A record on 80 is what exposes the rule.
    """
    port80 = {"port": 80, "base_url": "/", "token": "t", "hostname": "127.0.0.1"}
    assert cli._match_listed_server("http://127.0.0.1:0/", [port80]) is None


@pytest.mark.parametrize(
    "url,record",
    [
        ("http://127.0.0.1/",
         {"port": 80, "base_url": "/", "token": "t", "hostname": "127.0.0.1"}),
        ("https://127.0.0.1/",
         {"port": 443, "base_url": "/", "token": "t", "secure": True,
          "hostname": "127.0.0.1"}),
    ],
)
def test_a_portless_url_matches_the_server_on_that_scheme_default(url, record):
    """The other half: refusing every portless URL would be just as wrong."""
    assert cli._match_listed_server(url, [record]) is record


def test_explicit_loopback_url_is_authenticated_despite_ambiguity(captured_request,
                                                                  monkeypatch):
    """Two servers listed must not stop an explicit loopback --url getting a token.

    The fixture's detect_token stub is put back to the real function here. A stub
    of it once encoded the precedence the real function did not implement, which
    is exactly what hid the defect the two tests below now cover.
    """
    monkeypatch.setattr(cli, "detect_token", _REAL_DETECT_TOKEN)
    monkeypatch.delenv("JUPYTERHUB_SERVICE_PREFIX", raising=False)
    for var in ("JUPYTERHUB_API_TOKEN", "JPY_API_TOKEN", "JUPYTER_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(cli, "_list_running_servers", lambda: [SERVER_A, SERVER_B])
    monkeypatch.setattr("sys.argv",
                        ["jupyterlab-notify", "--url",
                         "http://127.0.0.1:8888/user/alice", "-m", "x"])

    assert cli.main() == 0
    assert captured_request["request"].headers.get("Authorization") == "token tok-a"


# --- the addressed server's token outranks an ambient one --------------------

@pytest.mark.parametrize(
    "ambient", ["JUPYTERHUB_API_TOKEN", "JPY_API_TOKEN", "JUPYTER_TOKEN"]
)
def test_server_token_beats_an_ambient_token(
    captured_request, monkeypatch, ambient
):
    """Reading the environment first sent the hub's credential to another server.

    Every JupyterHub single-user container has one of these set, so the ambient
    value used to win for every target: the addressed server answered 403, and
    the live hub token was handed to whichever loopback server was addressed.

    Asserted through send_notification_api, which is where the precedence now
    lives. Asserting it on detect_token held a branch alive that the send path
    can no longer reach, so the order itself had become unobservable.
    """
    monkeypatch.setattr(cli, "detect_token", _REAL_DETECT_TOKEN)
    monkeypatch.delenv("JUPYTERLAB_NOTIFY_TOKEN", raising=False)
    for var in ("JUPYTERHUB_API_TOKEN", "JPY_API_TOKEN", "JUPYTER_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv(ambient, "ambient-hub-token")

    cli.send_notification_api(base_url="http://127.0.0.1:8888/user/alice",
                              message="x", server=SERVER_A)

    assert captured_request["request"].headers.get("Authorization") == \
        "token tok-a"


@pytest.mark.parametrize(
    "ambient", ["JUPYTERHUB_API_TOKEN", "JPY_API_TOKEN", "JUPYTER_TOKEN"]
)
def test_ambient_token_is_used_when_the_server_has_none(
    captured_request, monkeypatch, ambient
):
    """A record with no token of its own falls through to the variables.

    Not the JupyterHub case: a hub-spawned server's record carries a token, and
    it is JUPYTERHUB_API_TOKEN itself, so the precedence cannot change what a
    hub sends. This covers a genuinely token-less record.

    Asserted through send_notification_api. Asserting it on detect_token could
    not observe the fall-through at all, because that function never sees a
    record: narrowing the gate to `server is None` left the whole suite green.
    """
    monkeypatch.setattr(cli, "detect_token", _REAL_DETECT_TOKEN)
    monkeypatch.delenv("JUPYTERLAB_NOTIFY_TOKEN", raising=False)
    for var in ("JUPYTERHUB_API_TOKEN", "JPY_API_TOKEN", "JUPYTER_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv(ambient, "ambient-hub-token")

    cli.send_notification_api(base_url="http://127.0.0.1:8888/user/alice",
                              message="x",
                              server={"port": 8888, "base_url": "/user/alice",
                                      "hostname": "localhost"})

    assert captured_request["request"].headers.get("Authorization") == \
        "token ambient-hub-token"


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8912/?token=SECRET",
        "http://127.0.0.1:8912/#token=SECRET",
        "http://127.0.0.1:8912/user/bob/?token=SECRET",
    ],
)
def test_a_url_query_or_fragment_never_reaches_the_request(captured_request, url):
    """The token must not enter the request line, where every access log keeps it.

    An operator pasting the URL out of the browser address bar brings the
    browser's own ?token= with it. Concatenating the endpoint onto that text
    produced the path /?token=SECRET/<namespace>/ingest, so the credential the
    CLI says twice it only ever puts in a header was in the path instead.
    """
    cli.send_notification_api(base_url=url, message="x")

    sent = captured_request["request"].full_url
    assert "SECRET" not in sent
    assert sent.endswith(f"/{cli.API_NAMESPACE}/ingest")


def test_the_progress_line_says_the_address_came_from_a_listed_server(
    captured_request, monkeypatch, capsys
):
    """The same line on a matched server must not read like the unmatched one.

    Its sibling covers the unmatched wording. Without both, a mutant that
    prints one label for every state passes: the operator then cannot tell a
    403 caused by a wrong --url from one caused by the server.
    """
    monkeypatch.setattr(cli, "_list_running_servers", lambda: [ROOT_SERVER])
    monkeypatch.setattr("sys.argv",
                        ["jupyterlab-notify", "--url", "http://localhost:8888",
                         "-m", "x"])

    assert cli.main() == 0

    assert capsys.readouterr().err.splitlines()[0] == \
        "URL: http://127.0.0.1:8888 (listed server) | Type: info"


def test_a_pasted_token_never_reaches_stderr(monkeypatch, capsys):
    """The other sink of the same paste: the progress line and the failure line.

    The first fix scrubbed the query inside send_notification_api only, so main
    had already printed the raw text and still held it for the error report -
    two copies of the credential in what is a log file for an unattended
    sender. Asserted on the whole stream, not on one line, because either sink
    alone defeats the guarantee.
    """
    def fake_urlopen(req, *args, **kwargs):
        raise ConnectionRefusedError(111, "Connection refused")

    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.delenv("JUPYTERLAB_NOTIFY_TOKEN", raising=False)
    monkeypatch.setattr(cli, "_list_running_servers", lambda: [])
    monkeypatch.setattr("sys.argv",
                        ["jupyterlab-notify", "--url",
                         "http://127.0.0.1:8941/user/alice/?token=SECRET",
                         "-m", "x"])

    assert cli.main() == 1

    captured = capsys.readouterr()
    assert "SECRET" not in captured.err
    assert "SECRET" not in captured.out
    assert "URL: http://127.0.0.1:8941/user/alice/ (no listed server matched)" \
        in captured.err


def test_the_progress_line_says_the_address_is_the_default(monkeypatch, capsys):
    """The third state: no --url, nothing listed, so the address was invented.

    Its two siblings cover a matched record and a --url that matched nothing.
    Without this one the label read "no listed server matched" for a run that
    compared nothing, and a script whose HOME hides the runtime directory was
    told a comparison had failed.
    """
    def fake_urlopen(req, *args, **kwargs):
        raise ConnectionRefusedError(111, "Connection refused")

    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.delenv("JUPYTERLAB_NOTIFY_TOKEN", raising=False)
    monkeypatch.delenv("JUPYTERHUB_SERVICE_PREFIX", raising=False)
    monkeypatch.delenv("JUPYTER_PORT", raising=False)
    monkeypatch.setattr(cli, "_list_running_servers", lambda: [])
    monkeypatch.setattr("sys.argv", ["jupyterlab-notify", "-m", "x"])

    assert cli.main() == 1

    assert capsys.readouterr().err.splitlines()[0] == \
        "URL: http://127.0.0.1:8888 (no server listed, using the default " \
        "address) | Type: info"


@pytest.mark.parametrize(
    # Three classes under a narrowing mutant: an empty scheme, a host mistaken
    # for one, and a scheme that is known but not ours.
    "url", ["localhost:8888", "not a url", "ftp://127.0.0.1:8888"],
)
def test_a_url_without_an_http_scheme_is_reported_as_a_bad_url(url):
    """Not as an unreachable server, and not by escaping every arm.

    urllib raises a bare ValueError for these, and the Request is built outside
    the try, so `localhost:8888` was reported as "cannot reach ... is JupyterLab
    running there?" about a healthy server and `not a url` reached main's last
    resort with the internal endpoint path glued onto urllib's own message.
    """
    with pytest.raises(RuntimeError) as excinfo:
        cli.send_notification_api(base_url=url, message="x")

    assert str(excinfo.value) == \
        f"bad URL {url}: needs an http:// or https:// prefix"


def test_the_python_copies_of_the_published_constants_agree():
    """cli.py must not import tornado, so these are copied on purpose.

    Nothing pinned the copies equal: test_cli.py reads cli's and test_routes.py
    reads routes', so a rename of one left both suites green and shipped a CLI
    that 404s on every send. The TypeScript copy stays guarded by the
    cross-referencing comments, because scraping it from pytest is machinery.
    """
    from jupyterlab_notifications_extension import routes

    assert cli.API_NAMESPACE == routes.API_NAMESPACE
    assert cli.DEFAULT_AUTO_CLOSE_MS == routes.DEFAULT_AUTO_CLOSE_MS


def test_a_non_ascii_url_is_reported_as_a_bad_url(monkeypatch):
    """The arm that names UnicodeEncodeError sat below the arm that took it.

    UnicodeEncodeError is a ValueError, so ordered the other way round the entry
    was dead and a pasted Cyrillic or smart-quote character was reported as an
    unreadable answer from a server that never replied. The order of the arms is
    the thing under test, so the exception comes from a stub: the real path
    raises it from http.client's request-line encoding, which needs a listener.
    """
    def fake_urlopen(req, *args, **kwargs):
        raise UnicodeEncodeError("ascii", "п", 0, 1, "ordinal not in range")

    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(RuntimeError) as excinfo:
        cli.send_notification_api(base_url="http://127.0.0.1:8913/п",
                                  message="x")

    # The codec's own text counts into http.client's encoded request line, not
    # into what the operator typed, so the message names the repair instead.
    # Escaped in the message, so the assertion carries the escape too.
    assert str(excinfo.value) == \
        "bad URL http://127.0.0.1:8913/\\u043f: remove the non-ASCII characters"


def test_an_unbalanced_ipv6_url_reports_one_line(capsys, monkeypatch):
    """An unbalanced IPv6 bracket, reported rather than raised.

    urlparse raises ValueError on unbalanced brackets, and main scrubs the URL
    before any guard, so the scrub reopened the traceback that defect closed. The
    scrub is total now and the scheme guard reports the parse failure in this
    tool's wording, so the operator gets one line rather than a stack.
    """
    monkeypatch.delenv("JUPYTERLAB_NOTIFY_TOKEN", raising=False)
    monkeypatch.setattr(cli, "_list_running_servers", lambda: [])
    monkeypatch.setattr("sys.argv",
                        ["jupyterlab-notify", "--url", "http://[::1:8888/",
                         "-m", "x"])

    assert cli.main() == 1

    assert capsys.readouterr().err.splitlines()[-1] == \
        "Failed to send notification: bad URL http://[::1:8888/: Invalid IPv6 URL"


def test_url_userinfo_never_reaches_the_request_or_stderr(captured_request,
                                                          monkeypatch, capsys):
    """A password pasted into --url is the same sink the query string was.

    This tool authenticates by token only, so userinfo could never be used:
    urllib sends the whole user:password@host as the hostname and the send dies
    in resolution. Dropped, the request reaches the real host and nothing on
    stderr carries the secret.
    """
    monkeypatch.delenv("JUPYTERLAB_NOTIFY_TOKEN", raising=False)
    monkeypatch.setattr(cli, "_list_running_servers", lambda: [])
    monkeypatch.setattr("sys.argv",
                        ["jupyterlab-notify", "--url",
                         "http://admin:s3cr3t@127.0.0.1:8941/user/alice/",
                         "-m", "x"])

    assert cli.main() == 0

    captured = capsys.readouterr()
    assert "s3cr3t" not in captured.err
    assert "s3cr3t" not in captured.out
    assert captured_request["request"].full_url == \
        f"http://127.0.0.1:8941/user/alice/{cli.API_NAMESPACE}/ingest"


@pytest.mark.parametrize(
    "url,expected",
    [
        # A bracket in the PASSWORD, which generators emit: urlparse rejects the
        # whole URL, so the scrub's unparsed path is reached with no typo at all.
        ("http://user:p[a]ss@127.0.0.1:8888/", "http://127.0.0.1:8888/"),
        ("http://admin:s3cr3t@[::1:8888/", "http://[::1:8888/"),
        ("http://admin:s3cr3t@[::1", "http://[::1"),
    ],
)
def test_a_credential_is_cut_from_a_url_that_cannot_be_parsed(url, expected):
    """Returning the text whole was how totality was first bought.

    urlparse rejects a bracket anywhere in the authority, so a password holding
    one took the URL down the unparsed path with the credential still in it, and
    main then printed it on the progress line and in the failure line.
    """
    assert cli._without_credentials(url) == expected


def test_a_non_ascii_token_names_the_token_not_the_url(monkeypatch):
    """The URL is blameless, and on the auto-detected path was never typed.

    http.client encodes the request line as ascii and a header VALUE as latin-1,
    and raises UnicodeEncodeError for both, so keying on the exception type told
    the operator to remove characters from a URL that had none.
    """
    def fake_urlopen(req, *args, **kwargs):
        # The value http.client encodes is the whole header, so the fake must
        # carry the 'token ' prefix; without it the object does not match and the
        # branch under test is never entered. That omission is why a non-ASCII
        # URL host reached this branch and was blamed on the token.
        raise UnicodeEncodeError("latin-1", "token abc​def", 9, 10,
                                 "ordinal not in range")

    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(RuntimeError) as excinfo:
        cli.send_notification_api(base_url="http://127.0.0.1:8888",
                                  message="x", token="abc​def")

    message = str(excinfo.value)
    assert message == cli._TOKEN_UNUSABLE
    assert "bad URL" not in message


def test_a_trailing_space_in_the_url_is_stripped(captured_request, monkeypatch):
    """The one whitespace shape that failed, and it failed with our own path.

    urlsplit lstrips space and removes tabs anywhere but never rstrips, so a
    leading space and a trailing tab both delivered while a trailing space was
    reported by quoting this tool's endpoint path back at the operator.
    """
    monkeypatch.delenv("JUPYTERLAB_NOTIFY_TOKEN", raising=False)

    cli.send_notification_api(base_url="http://127.0.0.1:8888/ ", message="x")

    assert captured_request["request"].full_url == \
        f"http://127.0.0.1:8888/{cli.API_NAMESPACE}/ingest"


@pytest.mark.parametrize(
    "url,expected",
    [
        # The retargeting: the text path partitioned on '/' only, so a query
        # before the first slash was swallowed into the authority and whatever
        # followed its last '@' became the host. Measured end to end: this URL
        # addressed localhost:9099, attached this host's ambient token and
        # exited 0 reporting success.
        ("http://[::1:8888?u=a@localhost:9099", "http://[::1:8888"),
        ("http://[::1:8888#f=a@localhost:9099", "http://[::1:8888"),
        # The credential half of the same cause, on the parse path: this shape is
        # the only guard left on the query removal there, since the _replace
        # keywords came out.
        ("http://[127.0.0.1]:8888/lab?token=SEKRIT", "http://[127.0.0.1]:8888/lab"),
    ],
)
def test_a_query_before_the_first_slash_cannot_become_the_host(url, expected):
    """The worst shape this helper has produced, and it is not a leak but a target.

    A URL the operator did not name became the destination, which is the harm
    rounds 13 and 14 narrowed the matcher to close, reached here by a different
    route. Cutting the fragment and the query before either path runs answers both
    halves with one line.
    """
    assert cli._without_credentials(url) == expected


def test_a_non_ascii_url_host_blames_the_url_not_the_token(captured_request,
                                                           monkeypatch):
    """Both of this arm's branches raise UnicodeEncodeError(encoding='latin-1').

    urllib adds a Host header built from the netloc and http.client encodes every
    header VALUE as latin-1, writing Host before Authorization, so keying the
    token branch on the encoding blamed the token for a fault in the host - while
    the line above it said no token was sent. The failing object is the exact
    discriminator: the Authorization value, or the netloc.
    """
    monkeypatch.delenv("JUPYTERLAB_NOTIFY_TOKEN", raising=False)

    def fake_urlopen(req, *args, **kwargs):
        raise UnicodeEncodeError("latin-1", "local​host:8888", 5, 6,
                                 "ordinal not in range")

    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(RuntimeError) as excinfo:
        cli.send_notification_api(base_url="http://local​host:8888",
                                  message="x", token="clean-ascii-token")

    message = str(excinfo.value)
    assert message == ("bad URL http://local\\u200bhost:8888: "
                       "remove the non-ASCII characters")


def test_a_non_numeric_port_is_not_blamed_on_a_non_ascii_character(monkeypatch):
    """Removing the character does not fix the port, so it must not be the advice."""
    monkeypatch.delenv("JUPYTERLAB_NOTIFY_TOKEN", raising=False)

    with pytest.raises(RuntimeError) as excinfo:
        cli.send_notification_api(base_url="http://127.0.0.1:abc/п",
                                  message="x")

    assert str(excinfo.value) == \
        ("bad URL http://127.0.0.1:abc/\\u043f: the port must be a number from 0 to "
         "65535 (Port could not be cast to integer value as 'abc')")


@pytest.mark.parametrize("bad", ["\r", "\n", "\0"])
def test_a_token_that_cannot_be_a_header_names_the_token(captured_request, bad):
    """A .env with CRLF endings gives exactly this, through every loader.

    http.client raises a BARE ValueError for CR and LF, with no .object, so it fell
    past the arm that separates a bad token from a bad URL and was reported as an
    unreadable answer from a server nothing had been sent to. docker --env-file,
    compose env_file and systemd EnvironmentFile all keep a trailing carriage
    return.
    """
    with pytest.raises(RuntimeError) as excinfo:
        cli.send_notification_api(base_url="http://127.0.0.1:8888", message="x",
                                  token=f"a-token{bad}")

    assert str(excinfo.value) == cli._TOKEN_UNUSABLE


@pytest.mark.parametrize("ok", [" a-token", "a-token ", "a\ttoken"])
def test_a_token_with_legal_whitespace_is_still_sent(captured_request, ok):
    """The guard must not be isprintable() or a strip() comparison.

    A space and a tab are both legal header-value bytes and a leading space does
    deliver, so a guard drawn around whitespace would refuse a working token.
    """
    cli.send_notification_api(base_url="http://127.0.0.1:8888", message="x",
                              token=ok)

    assert captured_request["request"].headers.get("Authorization") == \
        f"token {ok}"


def test_an_interrupt_reports_one_line_and_exits_130(monkeypatch, capsys):
    """Every other failure here is one line; this one printed urllib internals.

    except Exception does not reach BaseException, so KeyboardInterrupt walked out
    of main and printed a 40-line traceback. Without the arm this case does not
    report as a failure: the interrupt escapes and pytest ends the session with
    "no tests ran", naming this line.
    """
    def fake_urlopen(req, *args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.delenv("JUPYTERLAB_NOTIFY_TOKEN", raising=False)
    monkeypatch.setattr(cli, "_list_running_servers", lambda: [])
    monkeypatch.setattr("sys.argv",
                        ["jupyterlab-notify", "--url", "http://127.0.0.1:8888",
                         "-m", "x"])

    assert cli.main() == 130
    assert capsys.readouterr().err.splitlines()[-1] == "Interrupted"


def test_a_doubled_port_complains_about_the_port(captured_request):
    """It reached urllib and came back as a name-resolution error.

    .port validates lazily, so nothing had touched it before the request was
    built, and the operator was told the host could not be resolved when the host
    was fine.
    """
    with pytest.raises(RuntimeError) as excinfo:
        cli.send_notification_api(base_url="http://127.0.0.1:18888:19099",
                                  message="x")

    assert str(excinfo.value) == \
        ("bad URL http://127.0.0.1:18888:19099: the port must be a number from 0 to "
         "65535 (Port could not be cast to integer value as '18888:19099')")


def test_an_exported_empty_token_variable_is_an_absent_one(captured_request,
                                                           monkeypatch):
    """The only environment read in this tree that got this wrong, and it is the
    one carrying the token.

    An exported-empty value is not None, so it suppressed both the record's own
    token and the ambient gate below it, and the send went out with no credential
    at all.
    """
    monkeypatch.setenv("JUPYTERLAB_NOTIFY_TOKEN", "")

    cli.send_notification_api(
        base_url="http://127.0.0.1:8888", message="x",
        server={"port": 8888, "base_url": "/", "token": "record-token",
                "hostname": "localhost"})

    assert captured_request["request"].headers.get("Authorization") == \
        "token record-token"


def test_a_bad_url_with_no_token_is_not_blamed_on_the_token(monkeypatch):
    """A bad URL with no token must not be blamed on the token.

    InvalidURL has no .object, so comparing it against the Authorization local
    without a truthiness guard matches None against None and names a token that
    does not exist. Raised from a stub carrying what http.client really raises for
    a space in the path, which is the byte class \\x00-\\x20\\x7f.
    """
    def fake_urlopen(req, *args, **kwargs):
        raise cli.InvalidURL("URL can't contain control characters. "
                             "'/my lab' (found at least ' ')")

    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.delenv("JUPYTERLAB_NOTIFY_TOKEN", raising=False)
    for var in ("JUPYTERHUB_API_TOKEN", "JPY_API_TOKEN", "JUPYTER_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(cli, "detect_token", lambda: None)

    with pytest.raises(RuntimeError) as excinfo:
        cli.send_notification_api(base_url="http://127.0.0.1:8888/my lab",
                                  message="x")

    message = str(excinfo.value)
    assert message.startswith("bad URL ")
    assert message != cli._TOKEN_UNUSABLE


def test_a_pasted_newline_in_the_url_stays_on_one_line(monkeypatch):
    """backslashreplace left a newline alone, because a newline is ASCII.

    The report then spanned two lines, which is the thing repr was chosen to
    prevent in the transport arm below. The URL has to be one urlparse REJECTS:
    urlsplit removes newlines and tabs itself, so on the parsing path a newline
    never reaches the report and only the text path can carry one.
    """
    monkeypatch.delenv("JUPYTERLAB_NOTIFY_TOKEN", raising=False)
    assert "\n" in cli._without_credentials("http://[::1\n:8888/")

    with pytest.raises(RuntimeError) as excinfo:
        cli.send_notification_api(base_url="http://[::1\n:8888/", message="x")

    assert "\n" not in str(excinfo.value)


def test_an_empty_token_flag_is_an_absent_one(captured_request, monkeypatch):
    """A script passing an unset shell variable into --token.

    An empty string is not None, so it suppressed the record's own token and the
    ambient gate below it and the send carried no credential, taking a 403. The
    environment read of the same value was fixed a round earlier; this is the argv
    read of it.
    """
    monkeypatch.delenv("JUPYTERLAB_NOTIFY_TOKEN", raising=False)

    cli.send_notification_api(
        base_url="http://127.0.0.1:8888", message="x", token="",
        server={"port": 8888, "base_url": "/", "token": "record-token",
                "hostname": "localhost"})

    assert captured_request["request"].headers.get("Authorization") == \
        "token record-token"


@pytest.mark.parametrize(
    "argv,expected",
    [
        (["--action", "Open", "--command-args", '{"path": "x"}'],
         "--command-args needs --command"),
        # An unset shell variable interpolated into the flag. Tested for truth
        # rather than presence, this reached no check at all and the button went
        # out captioned "Close this notification".
        (["--action", "Open", "--command-args", ""],
         "--command-args needs --command"),
        (["--action", "Open", "--cmd", ""], "--command needs a command id"),
    ],
)
def test_an_unusable_command_is_refused_not_dropped(monkeypatch, capsys, argv,
                                                    expected):
    """The args were parsed, validated and then discarded, exit 0.

    The button went out captioned "Close this notification", which asserts the
    opposite of what was asked for, and a zero exit on an instruction that was not
    carried out is what this tool refuses elsewhere.
    """
    monkeypatch.setattr("sys.argv",
                        ["jupyterlab-notify", "-m", "x", "--url",
                         "http://127.0.0.1:8888"] + argv)

    with pytest.raises(SystemExit) as excinfo:
        cli.main()

    assert excinfo.value.code == 2, expected
    assert expected in capsys.readouterr().err


def test_a_command_with_an_id_still_carries_its_args(captured_request, monkeypatch):
    """The control: the refusal above must not reject a usable command."""
    monkeypatch.delenv("JUPYTERLAB_NOTIFY_TOKEN", raising=False)
    monkeypatch.setattr("sys.argv",
                        ["jupyterlab-notify", "-m", "x", "--url",
                         "http://127.0.0.1:8888", "--action", "Open Help",
                         "--cmd", "iframe:open",
                         "--command-args", '{"path": "local:///welcome.html"}'])

    assert cli.main() == 0

    action = json.loads(captured_request["request"].data)["actions"][0]
    assert action["commandId"] == "iframe:open"
    assert action["args"] == {"path": "local:///welcome.html"}


@pytest.mark.parametrize("value", ["", "  ", "{bad"])
def test_an_unparseable_data_value_is_reported(monkeypatch, capsys, value):
    """The empty string was the only value neither parsed nor refused.

    Tested for truth rather than presence, an unset shell variable interpolated
    into --data skipped the parse entirely and the notification went out with no
    data attached and exit 0 on the send.
    """
    monkeypatch.delenv("JUPYTERLAB_NOTIFY_TOKEN", raising=False)
    monkeypatch.setattr("sys.argv",
                        ["jupyterlab-notify", "-m", "x", "--url",
                         "http://127.0.0.1:8888", "--data", value])

    assert cli.main() == 1
    assert "Error parsing --data JSON" in capsys.readouterr().err


@pytest.mark.parametrize(
    "flag,label",
    [("--data", "--data"), ("--command-args", "--command-args")],
)
def test_json_that_raises_something_other_than_a_decode_error(monkeypatch, capsys,
                                                              flag, label):
    """json.loads raises RecursionError for deep nesting, which is not a ValueError.

    Past the 4300-digit integer limit it raises a plain ValueError, and neither is a
    JSONDecodeError, so both walked out of main and printed a traceback where the
    documented exit codes promise one line.
    """
    monkeypatch.delenv("JUPYTERLAB_NOTIFY_TOKEN", raising=False)
    argv = ["jupyterlab-notify", "-m", "x", "--url", "http://127.0.0.1:8888",
            flag, "[" * 30000 + "]" * 30000]
    if flag == "--command-args":
        argv += ["--action", "Open", "--cmd", "iframe:open"]
    monkeypatch.setattr("sys.argv", argv)

    assert cli.main() == 1
    assert f"Error parsing {label} JSON" in capsys.readouterr().err
