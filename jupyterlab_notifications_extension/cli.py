#!/usr/bin/env python3
"""
CLI tool to send notifications to JupyterLab via the notification extension.

Sends notifications via HTTP API to a running JupyterLab server.
Auto-detects the URL and auth token from running servers. A remote target
(explicit --url) is never given an auto-detected token: aim one at it with
JUPYTERLAB_NOTIFY_TOKEN, or with --token, which puts the secret in argv where
every local account can read /proc/<pid>/cmdline.

Usage:
    # Basic notification (auto-detects URL)
    jupyterlab-notify -m "Your message here"

    # With explicit URL (e.g., JupyterHub)
    jupyterlab-notify --url "http://127.0.0.1:8888/jupyterhub/user/konrad" -m "Test"

    # Remote server - the variable keeps the token out of argv
    JUPYTERLAB_NOTIFY_TOKEN=... jupyterlab-notify --url "http://remote-server:8888" -m "Test"
"""

import argparse
import json
import os
import subprocess
import sys
import urllib.request
import urllib.error
from urllib.parse import urlparse, urlunparse
from http.client import HTTPException, InvalidURL

# The port a Jupyter server uses when it does not say otherwise.
DEFAULT_PORT = '8888'

# How long a notification stays on screen when the sender does not say. The
# server and the send dialog apply the same default.
DEFAULT_AUTO_CLOSE_MS = 5000

# The URL path this extension serves. routes.py and src/request.ts each name it
# too; the three copies are a published contract, and this module must not
# import tornado to send one POST.
API_NAMESPACE = 'jupyterlab-notifications-extension'

# Bounds the one network call. A server that accepts the connection and never
# answers - an IOLoop blocked on a slow save, a suspended process, a stale
# runtime record whose port another process now holds - otherwise blocks the
# send for ever, and the sender is usually an unattended script. The local
# `jupyter server list` call is already bounded by SERVER_LIST_TIMEOUT_S.
REQUEST_TIMEOUT_S = 10

# Bounds the `jupyter server list` subprocess.
SERVER_LIST_TIMEOUT_S = 5


def _list_running_servers():
    """Run `jupyter server list --json` and parse what it prints.

    `jupyter server list` walks the runtime directory with os.listdir, so the
    order carries no meaning and the first entry is not a choice. Two call
    sites in mutually exclusive branches, so one call per run: a memo here held
    a module global that memoized a single read.
    """
    try:
        result = subprocess.run(
            ['jupyter', 'server', 'list', '--json'],
            capture_output=True,
            text=True,
            timeout=SERVER_LIST_TIMEOUT_S
        )
    except (subprocess.TimeoutExpired, OSError):
        return []
    if result.returncode != 0 or not result.stdout.strip():
        return []
    servers = []
    for line in result.stdout.strip().split('\n'):
        try:
            servers.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return servers


def _select_server(servers):
    """Pick which running server to talk to, or None when it is ambiguous.

    JUPYTERHUB_SERVICE_PREFIX names the server this process belongs to, so it
    decides when a listed record matches it - a prefix matching nothing does not
    refuse, because it is exported in every terminal of a spawned container and
    refusing would stop a hub user notifying a lab they started by hand.
    Otherwise one server is unambiguous and several are not -
    guessing there is how a notification lands in a lab nobody is watching.
    """
    prefix = os.environ.get('JUPYTERHUB_SERVICE_PREFIX')
    if prefix:
        wanted = prefix.rstrip('/') + '/'
        for server in servers:
            if server.get('base_url', '/') == wanted:
                return server
    if len(servers) == 1:
        return servers[0]
    return None


def _match_listed_server(url, servers):
    """Find the listed server an explicit --url points at, or None.

    Matched on the loopback literals the URL's host and the record's bind
    address can each reach, plus port, scheme and base path. Host text alone
    is not enough: localhost reaches both families and resolves to ::1 first.
    """
    try:
        # Inside the guard: urlparse raises for an unbracketed IPv6 literal
        # such as http://[::1:8941/, and this runs before main's own try, so
        # the operator got a traceback where every sibling gets one line.
        if not _is_loopback_url(url):
            return None
        parsed = urlparse(url)
        explicit_port = parsed.port
    except ValueError:
        # A port that is not a number matches no listed record by definition,
        # and raising here would precede the URL line and the one-line report.
        return None
    # The scheme's own default, not this project's. `or` treated port 0 and a
    # portless URL alike and fell back to 8888, so --url http://127.0.0.1/
    # matched the 8888 record while urlopen addressed port 80 - handing that
    # server's token to whatever else answers there.
    if explicit_port is not None:
        port = explicit_port
    else:
        port = 443 if parsed.scheme == 'https' else 80
    path = parsed.path.rstrip('/')
    # What this URL's host can reach, against what the record's bind can be
    # reached at. A hand-written rule here mapped every non-::1 host to
    # 127.0.0.1, so a localhost URL matched an IPv4-only record and then
    # urllib resolved localhost to ::1 and sent that record's token there.
    reachable = _LOOPBACK_URL_HOSTS[parsed.hostname]
    for server in servers:
        if not set(reachable) & set(_loopback_literals_for(server)):
            continue
        if server.get('port') != port:
            continue
        # A record carries its own scheme. An https URL must not match a
        # plaintext server because their ports agree.
        if bool(server.get('secure')) != (parsed.scheme == 'https'):
            continue
        if server.get('base_url', '/').rstrip('/') == path:
            return server
    return None


# Bind addresses a record can carry whose server loopback reaches, each mapped
# to every loopback literal that reaches it, most preferred first. Tornado
# binds an AF_INET6 socket with IPV6_V6ONLY set (tornado/netutil.py), so
# 127.0.0.1 reaches neither ::1 nor ::, and a plain 127.0.0.1 bind is not
# reachable over ::1 either. `localhost` reaches both families, which is why
# the value is a tuple: _server_url needs one literal and the matcher needs all
# of them, and a membership set answers neither.
# Anything not listed - a server started with --ip=<a specific address>, and a
# record carrying no hostname at all - reaches no loopback literal, so it can
# never match a loopback URL and never lends that URL its token. A server bound to
# a unix socket is a third shape this table gets wrong rather than excludes: its
# record carries hostname localhost and port 0, so it matches and is addressed at
# an unconnectable port. Every record
# `jupyter server list` prints carries a hostname, because ServerApp.server_info
# always writes one, so the second case is a record this CLI did not produce.
# Compare _LOOPBACK_URL_HOSTS, a different question.
_LOOPBACK_HOST_FOR = {
    '0.0.0.0': ('127.0.0.1',),
    'localhost': ('127.0.0.1', '[::1]'),
    '127.0.0.1': ('127.0.0.1',),
    '::': ('[::1]',),
    '::1': ('[::1]',),
}


def _loopback_literals_for(server):
    """The loopback literals that reach this record's server, if any."""
    return _LOOPBACK_HOST_FOR.get(server.get('hostname', ''), ())


# Said by the pre-flight guard and by the except arm, which catch overlapping but
# different faults: the arm sees a character no header encoding can carry, the guard
# alone sees CR, LF and NUL. http.client refuses CR and LF itself but ACCEPTS NUL,
# so for that byte the guard is the only check and deleting it removes the only one.
# One string, because the two messages must never diverge.
_TOKEN_UNUSABLE = ("the authentication token has a line break or a character an "
                   "HTTP header cannot carry; --help lists every place this tool "
                   "reads a token from")


def _without_credentials(url):
    """Query and fragment removed, and userinfo that urlsplit reads as such.

    A --url pasted out of a browser address bar carries the browser's own
    ?token=, and one copied from a proxy note carries user:password@. Everything
    downstream treats the URL as text: the endpoint is appended to it, the
    progress line prints it, and every failure message interpolates it. Removing
    all three where a URL enters keeps the credential out of the request line and
    out of stderr, which for an unattended sender is a log file. A record's URL is
    already clean, because _server_url rebuilds it.

    Two shapes fall outside that reading and keep their userinfo: a URL with no
    // at all, where urlsplit puts the whole user:pass@host into the path, and one
    whose password holds an unencoded /, where the authority ends at that slash.
    Both are malformed under RFC 3986, and any rule that hunted for an @ past the
    first / would corrupt /user/alice@example.com/, the standard JupyterHub path
    for an e-mail username.

    Userinfo is dropped rather than passed through because this tool
    authenticates by token only, as the epilog says, so it could never be used:
    urllib sends the whole user:password@host as the hostname and the send dies
    in DNS resolution. Dropped, the request reaches the real host and the proxy
    answers 401, which names the cause.

    Total, not partial: urlparse raises ValueError on unbalanced IPv6 brackets,
    and this runs in main before any guard, so raising here printed a traceback.
    The caller reports it instead. Returning the
    text unchanged there was not enough: urlparse rejects a bracket anywhere in
    the authority, so a password containing one - which generators emit - took
    the whole URL down the unparsed path with the credential still in it. The
    authority is therefore cut by text on that path. A string with no // has no
    authority to cut and is returned whole.
    """
    # Stripped first: urlsplit lstrips space and removes tabs anywhere, but never
    # rstrips, so a pasted trailing space was the one whitespace shape that failed,
    # and it failed by quoting this tool's own endpoint path back at the operator.
    # Cut before parsing, so the unparsed path is covered by the same line.
    # Exact, because both characters must be percent-encoded anywhere else in a
    # URL.
    url = url.strip().partition('#')[0].partition('?')[0]
    try:
        parsed = urlparse(url)
    except ValueError:
        head, sep, rest = url.partition('//')
        authority, slash, tail = rest.partition('/')
        return f"{head}{sep}{authority.rpartition('@')[2]}{slash}{tail}"
    netloc = parsed.netloc.rpartition('@')[2]
    return urlunparse(parsed._replace(netloc=netloc))


def _server_url(server):
    """Build the base URL for one server record, honouring its scheme and host."""
    scheme = 'https' if server.get('secure') else 'http'
    port = server['port']
    base_url = server.get('base_url', '/').rstrip('/')
    hostname = server.get('hostname', '')
    literals = _loopback_literals_for(server)
    host = literals[0] if literals else None
    if host is None:
        # A bare IPv6 literal must be bracketed or urlparse reads the port as
        # part of the address and .port raises.
        host = f"[{hostname}]" if ':' in hostname else hostname
    return f"{scheme}://{host}:{port}{base_url}"


def get_jupyter_base_url(server):
    """
    Build the JupyterLab base URL for an already-selected server.

    Checks in order:
    1. the record the caller selected, when there is one
    2. JUPYTERHUB_SERVICE_PREFIX - JupyterHub environment variable
    3. Default: http://127.0.0.1:$JUPYTER_PORT, port 8888 when unset

    Selecting the record is the caller's job. Re-selecting it here could only
    recompute the None it was handed, because main reaches this with None only
    when the server list is empty.
    """
    if server is not None:
        return _server_url(server)

    service_prefix = os.environ.get('JUPYTERHUB_SERVICE_PREFIX')
    if service_prefix:
        # `or`, not a get() default: an exported but empty JUPYTER_PORT= is
        # not an absent one, and it built http://127.0.0.1:/<path>, which
        # http.client reads as port 80 - with the ambient token attached.
        port = os.environ.get('JUPYTER_PORT') or DEFAULT_PORT
        return f"http://127.0.0.1:{port}{service_prefix.rstrip('/')}"

    port = os.environ.get('JUPYTER_PORT') or DEFAULT_PORT
    return f"http://127.0.0.1:{port}"


def _readable_reason(error):
    """Return ': <reason>' from a JSON error body, or '' when there is none.

    The server answers under 'error' and jupyter_server under 'message'. Any
    other shape - a proxy's HTML page, an empty body, a bare list - has no
    reason worth showing, and the status line already says what happened.
    """
    try:
        body = json.loads(error.read().decode('utf-8', errors='replace'))
    except (ValueError, OSError, HTTPException):
        # A body cut short mid-read raises IncompleteRead, which is an
        # HTTPException and not an OSError, so it escaped this guard and
        # replaced the whole report with a read error. Named classes, not
        # `except Exception`: a coding error in these three lines must surface.
        return ''
    if not isinstance(body, dict):
        return ''
    reason = body.get('message') or body.get('error')
    if not isinstance(reason, str) or not reason:
        return ''
    # jupyter_server sets 'message' to the status phrase when the error carries
    # no log message, which printed "HTTP 403 Forbidden ...: Forbidden".
    if reason.strip().lower() == str(getattr(error, 'reason', '')).lower():
        return ''
    return f": {reason}"


def detect_token():
    """
    Find an ambient auth token for this host.

    Checks JUPYTERHUB_API_TOKEN, then JPY_API_TOKEN, then JUPYTER_TOKEN.

    Deliberately knows nothing about any server record. The addressed server's
    own token is read from that record by send_notification_api, which takes it
    ahead of anything here - a record's credential belongs to the address that
    record names, and these variables belong to this host. Holding a copy of
    that rule here as well made the order unobservable: the send path reached
    the record's token first, so the branch could not run and no test that went
    through the send path could see the precedence change.
    """
    return (
        os.environ.get('JUPYTERHUB_API_TOKEN') or
        os.environ.get('JPY_API_TOKEN') or
        os.environ.get('JUPYTER_TOKEN') or
        None
    )


# The hosts a URL can name that are loopback destinations. Deliberately NOT
# _LOOPBACK_HOST_FOR's keys: that map answers "is this record's BIND address
# reachable over loopback", and its wildcards belong there. Adding '' or
# '0.0.0.0' here would make --url http://0.0.0.0:8888/ carry a token.
_LOOPBACK_URL_HOSTS = {
    '127.0.0.1': ('127.0.0.1',),
    # getaddrinfo returns ::1 first for localhost under RFC 6724, and urllib
    # follows that, so a localhost URL can land on either family.
    'localhost': ('127.0.0.1', '[::1]'),
    '::1': ('[::1]',),
}


def _is_loopback_url(url):
    """True if the URL's host is loopback - safe to attach a locally-detected token.

    Uses the parsed hostname (not a substring match) so tricks like
    http://127.0.0.1@evil.com/ or http://localhost.evil.com/ resolve to the
    real host (evil.com) and are correctly treated as remote.
    """
    return urlparse(url).hostname in _LOOPBACK_URL_HOSTS


def send_notification_api(
    base_url: str,
    message: str,
    server: dict = None,
    notification_type: str = "info",
    auto_close: int = DEFAULT_AUTO_CLOSE_MS,
    actions: list = None,
    data: dict = None,
    token: str = None,
    immediate: bool = False,
    verbose: bool = False
):
    """
    Send a notification via HTTP API to a JupyterLab server.

    Args:
        base_url: Base URL of the JupyterLab server. Required: main resolves
            the target once so the URL printed is the URL used, and resolving
            it again here would pick a server without the token that belongs
            to it.
        server: Already-selected `jupyter server list` record, so the list is read once
        message: Notification message text
        notification_type: Type of notification (default, info, success, warning, error, in-progress)
        auto_close: Auto-close timeout in milliseconds, or False to disable
        actions: List of action dictionaries with label, caption, and displayType
        data: Optional arbitrary data to attach to the notification
        token: Authentication token; every target needs one
        immediate: Push instantly to connected clients via WebSocket (--now)
        verbose: Print debug information
    """

    # Scrubbed before anything reads it, so the endpoint, every failure message
    # below and any caller's own logging all use the same clean text.
    base_url = _without_credentials(base_url)

    # Escaped once, for every message below that echoes the URL: a zero-width
    # space and a Cyrillic homoglyph both render as the correct address, so an
    # unescaped echo shows the operator nothing to remove. str.strip does not
    # help, because '\u200b'.isspace() is False. main's progress line stays
    # verbatim on purpose - the contrast between what was typed and what the bytes
    # are is the diagnosis.
    shown = base_url.encode('unicode_escape').decode() or "''"

    # urllib raises a bare ValueError for a URL with no usable scheme, and the
    # Request is built outside the try below, so `--url localhost:8888` was
    # reported as "cannot reach ... is JupyterLab running there?" about a server
    # that was running, and a --url with no colon at all escaped to main's last
    # resort carrying urllib's own jargon with the internal endpoint path glued
    # on. Checked here rather than by moving the Request inside the try, where a
    # bare ValueError would be taken by the unreadable-answer arm.
    try:
        parsed_base = urlparse(base_url)
        scheme = parsed_base.scheme
    except ValueError as e:
        raise RuntimeError(f"bad URL {shown}: {e}") from e

    # Touched, not just read: .port validates lazily, so without this a doubled or
    # percent-escaped port reached urllib and came back as a name-resolution error.
    # Its own try rather than sniffing the message text for the word port.
    try:
        parsed_base.port
    except ValueError as e:
        raise RuntimeError(
            f"bad URL {shown}: the port must be a number from 0 to 65535 ({e})"
        ) from e
    if scheme not in ('http', 'https'):
        raise RuntimeError(
            f"bad URL {shown}: needs an http:// or https:// prefix"
        )

    # A token the user set for this tool is theirs to aim anywhere, including a
    # remote host, and it keeps the secret out of argv where every local account
    # can read /proc/<pid>/cmdline.
    if not token:
        token = os.environ.get('JUPYTERLAB_NOTIFY_TOKEN') or None

    # The record names this host and this port, so its own token is the right
    # credential for this target whatever the host text looks like. A server
    # bound with --ip=<an address> might not be loopback, and is still the
    # right target. main only ever passes a record it resolved
    # from the list or matched to an explicit loopback --url, so a remote --url
    # still carries no record and still gets nothing.
    if token is None and server is not None:
        token = server.get('token') or None

    # The ambient variables belong to this host, not to the target, so they
    # stay gated on the target being loopback.
    if token is None and _is_loopback_url(base_url):
        token = detect_token()

    if token and any(c in token for c in '\r\n\0'):
        raise RuntimeError(_TOKEN_UNUSABLE)

    # stderr with the rest of the diagnostics: --verbose exists to diagnose,
    # and on stdout it produced nothing under `1>/dev/null`.
    # The no-token line is not gated on --verbose: a 403 cannot be told from a
    # withheld credential without it, and the two states printed the same bytes.
    if not token:
        print("Sending without an authentication token", file=sys.stderr)
    elif verbose:
        print("Using authentication token", file=sys.stderr)
    if verbose:
        print(file=sys.stderr)

    # The token travels in the Authorization header only (below), never in the
    # URL, so it does not land in server access logs.
    # rstrip: `jupyter server list` prints URLs with a trailing slash and a hub
    # user's address bar ends /user/<name>/, so that is the likeliest form an
    # operator pastes. Without it the path became //<namespace>/ingest and the
    # server answered 404 for a notification that would otherwise deliver.
    endpoint = f"{base_url.rstrip('/')}/{API_NAMESPACE}/ingest"

    payload = {
        "message": message,
        "type": notification_type,
        "autoClose": auto_close
    }

    if actions is not None:
        payload["actions"] = actions

    if data is not None:
        payload["data"] = data

    if immediate:
        payload["immediate"] = True

    json_data = json.dumps(payload).encode('utf-8')

    if verbose:
        print("Sending JSON payload:", file=sys.stderr)
        print(json.dumps(payload, indent=2), file=sys.stderr)
        print(file=sys.stderr)

    headers = {
        'Content-Type': 'application/json'
    }

    authorization = f'token {token}' if token else None
    if authorization:
        headers['Authorization'] = authorization

    req = urllib.request.Request(
        endpoint,
        data=json_data,
        headers=headers,
        method='POST'
    )

    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as response:
            result = json.loads(response.read().decode('utf-8'))
            # Indexed, not .get(): a 2xx from something that is not this
            # endpoint printed "Notification sent: None" and exited 0, so a
            # script's exit-code check passed for a notification nothing
            # ingested.
            print(f"Notification sent: {result['notification_id']}")
            return result
    except TimeoutError as e:
        # A read timeout is a bare TimeoutError, an OSError but not a
        # URLError, so it escapes both arms below and would report a lone
        # "timed out" with no URL.
        raise RuntimeError(
            f"no answer from {shown} within {REQUEST_TIMEOUT_S}s; "
            f"is that server responding?"
        ) from e
    except (InvalidURL, UnicodeEncodeError) as e:
        # Above the ValueError arm, not below it: UnicodeEncodeError IS a
        # ValueError, so ordered the other way round this entry was dead and a
        # non-ASCII selector was reported as an unreadable answer from a server
        # that never replied. http.client encodes the request line as ASCII, so
        # one pasted Cyrillic or smart-quote character raises before a byte is
        # sent. Both are the URL being wrong, not the transport. A port that is
        # not a number no longer reaches here, because the pre-flight .port touch
        # takes it first; InvalidURL still does, through a space in the path.
        # Also above HTTPException below, which
        # InvalidURL subclasses.
        if authorization and getattr(e, 'object', None) == authorization:
            # The failing object IS the Authorization header's value, so this is
            # the token and not the URL. Keying on e.encoding was not enough:
            # urllib builds a Host header from the netloc and http.client encodes
            # every header value as latin-1, so a non-ASCII HOST raised the same
            # encoding and was blamed on the token. Named, because on the
            # auto-detected path the operator never typed the token.
            raise RuntimeError(_TOKEN_UNUSABLE) from e
        detail = ("remove the non-ASCII characters"
                  if isinstance(e, UnicodeEncodeError) else f"{e}")
        raise RuntimeError(f"bad URL {shown}: {detail}") from e
    except (ValueError, KeyError, TypeError) as e:
        raise RuntimeError(
            f"unreadable answer from {shown}; only this extension's ingest "
            f"endpoint answers here"
        ) from e
    except urllib.error.HTTPError as e:
        # Raised, not printed: main() reports once, and a bare re-raise would
        # end the report on "Bad Request" with the reason two lines above it.
        # Only a readable reason is appended. A proxy answers a restart with its
        # own HTML page, and a mistyped --url ending in /lab answers 405 with the
        # whole lab document, so interpolating the body put a hundred lines of
        # markup between the operator and the one line that matters.
        raise RuntimeError(
            f"HTTP {e.code} {e.reason} from {shown}"
            f"{_readable_reason(e)}"
        ) from e
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"cannot reach {shown}: {e.reason}; is JupyterLab running there?"
        ) from e
    except (HTTPException, OSError) as e:
        # Every transport failure that is not one of the arms above. Last,
        # because urllib.error.URLError subclasses OSError and this arm would
        # otherwise swallow every HTTP status. urllib wraps only h.request in
        # URLError and leaves h.getresponse bare, so a response-read failure
        # arrives unwrapped: IncompleteRead for a body cut short,
        # RemoteDisconnected for a close with no answer, BadStatusLine for a
        # reply in another protocol, ConnectionResetError for a reset,
        # ssl.SSLError for TLS state lost - except its
        # SSLCertVerificationError subclass, which urllib wraps in URLError and
        # the URLError arm above therefore takes - and a bare OSError for
        # EHOSTUNREACH,
        # ENETUNREACH or ENETDOWN. HTTPException is named because it alone is
        # not an OSError. repr, not str: BadStatusLine carries the peer's own
        # bytes, and a raw CRLF in them made the report two lines. The server
        # appends the notification before it replies, so if this really was
        # the ingest endpoint a blind retry can send it twice.
        raise RuntimeError(
            f"connection to {shown} failed before a usable answer arrived "
            f"({e!r}); if that was this server's ingest endpoint, the "
            f"notification may already have been created"
        ) from e


def main():
    """Entry point. Only the interrupt is handled here.

    Reading the server list takes most of this process's wall time and sits
    outside the send's own try, so an arm inside that try does not cover it.
    Wrapping the whole of _run keeps `except Exception` narrow, so a coding error
    in target resolution still raises rather than being reported as a failed send.
    """
    try:
        return _run()
    except KeyboardInterrupt:
        # One line, like every other failure here. 130 is the shell's convention
        # for a process ended by SIGINT.
        print("Interrupted", file=sys.stderr)
        return 130


def _run():
    parser = argparse.ArgumentParser(
        description="Send notifications to JupyterLab",
        epilog="""
Examples:
  # Basic notification
  %(prog)s -m "Hello World"

  # With JupyterHub base path
  %(prog)s -m "Hello" \\
      --url "http://127.0.0.1:8888/jupyterhub/user/alice"

  # Warning that stays until dismissed
  %(prog)s -m "Maintenance in 1 hour" -t warning --no-auto-close

  # Dismiss button
  %(prog)s -m "Task complete" --action "Dismiss"

  # Action button that executes a JupyterLab command
  %(prog)s -m "Help Available!" --action "Open Help" \\
      --cmd "iframe:open" --command-args '{"path": "local:///welcome.html"}'

  # Silent notification (notification center only)
  %(prog)s -m "Background task done" --auto-close 0

  # Immediate display (push now, don't wait for the next poll)
  %(prog)s -m "Deploy finished" --now

  # Remote server - the variable keeps the token out of argv
  JUPYTERLAB_NOTIFY_TOKEN=... %(prog)s -m "Hello" \\
      --url "http://remote-host:8888"

authentication:
  JUPYTERLAB_NOTIFY_TOKEN is this tool's own variable and is used for ANY
  target, so a remote send need not put the secret in argv where every local
  account can read it.
  The ambient Jupyter variables are used ONLY when the target is loopback - a
  --url whose host is 127.0.0.1, localhost or ::1 - so this host's credentials
  are never sent to a host you named. The addressed server's OWN token, read
  from its runtime record, is used for the address that record is reached at:
  127.0.0.1 for a server bound to 0.0.0.0, and a host that might not be
  loopback if that server was started with --ip <an address>. The token
  travels in the Authorization header, never in the URL.
  The addressed server's own token is preferred over the ambient variables, so
  a host with JUPYTERHUB_API_TOKEN set can still notify a different loopback
  server. On JupyterHub this changes nothing, because a hub-spawned server's own
  token is that same variable; the variables are the fallback for a server that
  carries none.
  A 403 whose reason mentions '_xsrf' means the request was not authenticated
  by token: jupyter_server runs its XSRF check only on requests it did not
  already authenticate that way, so the XSRF complaint is the first failure it
  reports. Either the server has a token and did not get it - send the right
  one - or the server has no token to send, having been started with
  --ServerApp.token='' or configured with a password instead. This tool
  authenticates by token only, so it cannot deliver to that second kind at all:
  give that server a token. Do not disable its XSRF protection instead.
  A 404 has two causes: the extension is not enabled on that server - check
  `jupyter server extension list` there - or the --url is missing the server's
  base path, which on JupyterHub is /user/<name>.

  A server started with --certfile is reached at the address its runtime record
  names - 127.0.0.1 or [::1] for a loopback or wildcard bind, the --ip address
  for a server bound to one - so its certificate must cover that address and
  must already be trusted by your system. An explicit --url is replaced by the
  record's address only when it matches a listed record, which requires a
  loopback host; a non-loopback --url keeps the host you typed, and then needs
  JUPYTERLAB_NOTIFY_TOKEN or --token. A self-signed certificate is rejected
  rather than bypassed, because this tool carries tokens.

environment:
  JUPYTERLAB_NOTIFY_TOKEN
                        token for any target, checked first
  JUPYTERHUB_API_TOKEN, JPY_API_TOKEN, JUPYTER_TOKEN
                        loopback targets only, in that order, and only when the
                        addressed server has no token of its own
  JUPYTERHUB_SERVICE_PREFIX
                        names this process's own server, so it also picks among
                        several that are running; and the base path when none is
                        found
  JUPYTER_PORT          port used when no running server is found (default 8888)

exit codes:
  0                     notification accepted by the server
  1                     bad --data/--command-args JSON, a --url this tool
                        cannot use, or the request failed
  2                     usage error: the error message names the cause, or
                        several servers are running and none matches
                        JUPYTERHUB_SERVICE_PREFIX
  130                   interrupted with Ctrl+C
""",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--url",
        default=None,
        help="JupyterLab base URL, without the /lab path the browser shows "
             "(auto-detected from running servers via 'jupyter server list'). "
             "When it matches a listed server, that server's own address is "
             "used, so the host printed can differ from the host you typed"
    )
    parser.add_argument(
        "--message", "-m",
        required=True,
        help="Notification message (required)"
    )
    parser.add_argument(
        "--type", "-t",
        choices=["default", "info", "success", "warning", "error", "in-progress"],
        default="info",
        help="Notification type (default: info)"
    )
    parser.add_argument(
        "--auto-close",
        type=int,
        default=DEFAULT_AUTO_CLOSE_MS,
        help="Auto-close timeout in milliseconds "
             "(default: %(default)s, use 0 for silent)"
    )
    parser.add_argument(
        "--no-auto-close",
        action="store_true",
        help="Disable auto-close (stays until dismissed)"
    )
    parser.add_argument(
        "--token",
        default=None,
        help="Auth token, placed in argv where every local account can read "
             "it. See the authentication section below for what is used "
             "without it"
    )
    parser.add_argument(
        "--now",
        action="store_true",
        dest="immediate",
        help="Push to every open tab now. Without this the notification waits "
             "for the next poll, and the first tab to poll is the only one "
             "that receives it"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print debug information"
    )
    parser.add_argument(
        "--data",
        type=str,
        default=None,
        help="JSON data to attach (e.g., '{\"key\": \"value\"}')"
    )
    parser.add_argument(
        "--action",
        type=str,
        default=None,
        help="Add button with custom label (dismiss-only unless --command specified)"
    )
    parser.add_argument(
        "--command", "--cmd",
        type=str,
        default=None,
        dest="command",
        help="JupyterLab command ID to execute when action button clicked"
    )
    parser.add_argument(
        "--command-args",
        type=str,
        default=None,
        help="JSON args for command (e.g., '{\"path\": \"/notebooks\"}')"
    )

    args = parser.parse_args()

    # Refused rather than dropped: a zero exit on an instruction that was not
    # carried out is the shape this tool already refuses for a notification
    # nothing ingested.
    if args.command is not None and not args.command:
        parser.error("--command needs a command id")
    if args.command_args is not None and not args.command:
        parser.error("--command-args needs --command")

    auto_close = False if args.no_auto_close else args.auto_close

    data_dict = None
    if args.data is not None:
        try:
            data_dict = json.loads(args.data)
        except (json.JSONDecodeError, RecursionError, ValueError) as e:
            print(f"Error parsing --data JSON: {e}", file=sys.stderr)
            return 1

    command_args = None
    if args.command_args is not None:
        try:
            command_args = json.loads(args.command_args)
        except (json.JSONDecodeError, RecursionError, ValueError) as e:
            print(f"Error parsing --command-args JSON: {e}", file=sys.stderr)
            return 1

    actions = None
    if args.action or args.command:
        action_obj = {
            "label": args.action or "Action",
            "displayType": "default"
        }
        if args.command:
            action_obj["commandId"] = args.command
            action_obj["caption"] = f"Execute: {args.command}"
            if command_args:
                action_obj["args"] = command_args
        else:
            action_obj["caption"] = "Close this notification"
        actions = [action_obj]

    # Resolve the target once, so the URL printed is the URL used.
    chosen = None
    if args.url is not None:
        # Scrubbed here as well as in send_notification_api, because the
        # progress line below prints this text before the request is built.
        url = _without_credentials(args.url)
        # --url already named the target, so the ambiguity that stops
        # _select_server does not apply: find the record it points at, or the
        # request goes out unauthenticated and the server answers 403.
        chosen = _match_listed_server(url, _list_running_servers())
        if chosen is not None:
            # Address the record the matcher validated, not the spelling the
            # operator typed. The matcher has already proved the record's
            # scheme, port and base path equal this URL's, so only the host
            # changes - and it must, because urllib resolves `localhost`
            # itself and takes ::1 first, which is not where an IPv4-only
            # server is listening. Leaving the text in place sent that
            # server's token to whatever held the other family's port.
            url = _server_url(chosen)
    else:
        servers = _list_running_servers()
        chosen = _select_server(servers)
        if chosen is None and len(servers) > 1:
            # stderr, so `jupyterlab-notify ... 1>/dev/null` in a script
            # still shows why nothing was sent.
            print("Several Jupyter servers are listed. Pass --url to say "
                  "which one to notify:", file=sys.stderr)
            for server in servers:
                root = server.get('root_dir') or ''
                suffix = f"  (root: {root})" if root else ''
                print(f"  {_server_url(server)}{suffix}", file=sys.stderr)
            print("If a server listed above is no longer running, its record "
                  "is stale. Remove the jpserver-<pid>.json file naming its "
                  "port from the directory `jupyter --runtime-dir` prints.",
                  file=sys.stderr)
            return 2
        url = get_jupyter_base_url(chosen)
    # Progress, not result: on stderr it cannot be reordered after an
    # unbuffered error, and it leaves the sent id as the only stdout line.
    # Says where the address came from, because the line alone could not tell
    # "matched your server, its token attached" from "matched nothing, no
    # credential" from "found nothing, used the default" - all three printed
    # the same bytes, and on a 403 that sent the operator to the server when
    # the cause was a --url that matched no record.
    if chosen:
        source = 'listed server'
    elif args.url is not None:
        source = 'no listed server matched'
    else:
        source = 'no server listed, using the default address'
    shown_url = url.translate({10: '\\n', 13: '\\r'}) or "''"
    print(f"URL: {shown_url} ({source}) | Type: {args.type}", file=sys.stderr)

    try:
        send_notification_api(
            base_url=url,
            server=chosen,
            message=args.message,
            notification_type=args.type,
            auto_close=auto_close,
            actions=actions,
            data=data_dict,
            token=args.token,
            immediate=args.immediate,
            verbose=args.verbose
        )
        return 0
    except Exception as error:
        print(f"Failed to send notification: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
