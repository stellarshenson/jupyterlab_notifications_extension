#!/usr/bin/env python3
"""
CLI tool to send notifications to JupyterLab via the notification extension.

Sends notifications via HTTP API to a running JupyterLab server.
Auto-detects the URL and auth token from running servers. Remote servers
(explicit --url) require an explicit --token.

Usage:
    # Basic notification (auto-detects URL)
    jupyterlab-notify -m "Your message here"

    # With explicit URL (e.g., JupyterHub)
    jupyterlab-notify --url "http://127.0.0.1:8888/jupyterhub/user/konrad" -m "Test"

    # Remote server (requires token)
    jupyterlab-notify --url "http://remote-server:8888" -m "Test" --token "your-token"
"""

import argparse
import json
import os
import subprocess
import urllib.request
import urllib.error
from urllib.parse import urlparse


def get_jupyter_base_url():
    """
    Auto-detect JupyterLab base URL.

    Checks in order:
    1. jupyter server list --json - query running servers (uses localhost)
    2. JUPYTERHUB_SERVICE_PREFIX - JupyterHub environment variable
    3. Default: http://localhost:8888
    """
    # Try to detect from running Jupyter servers (preferred - always uses localhost)
    try:
        result = subprocess.run(
            ['jupyter', 'server', 'list', '--json'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            # Parse first server (one JSON object per line)
            first_line = result.stdout.strip().split('\n')[0]
            server_info = json.loads(first_line)
            port = server_info.get('port', 8888)
            base_url = server_info.get('base_url', '/').rstrip('/')
            return f"http://127.0.0.1:{port}{base_url}"
    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
        pass  # Fall through to other methods

    # Check for JupyterHub environment
    service_prefix = os.environ.get('JUPYTERHUB_SERVICE_PREFIX')
    if service_prefix:
        port = os.environ.get('JUPYTER_PORT', '8888')
        return f"http://127.0.0.1:{port}{service_prefix.rstrip('/')}"

    # Default
    port = os.environ.get('JUPYTER_PORT', '8888')
    return f"http://localhost:{port}"


def detect_token():
    """
    Auto-detect an auth token.

    Localhost ingest is secured by default server-side (the token-free
    bypass is opt-in), so the CLI authenticates with a real token wherever
    one is available - environment first, then a running server's token.

    Checks in order:
    1. JUPYTERHUB_API_TOKEN / JPY_API_TOKEN / JUPYTER_TOKEN env vars
    2. jupyter server list --json - the running server's token
    """
    token = (
        os.environ.get('JUPYTERHUB_API_TOKEN') or
        os.environ.get('JPY_API_TOKEN') or
        os.environ.get('JUPYTER_TOKEN')
    )
    if token:
        return token

    try:
        result = subprocess.run(
            ['jupyter', 'server', 'list', '--json'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            first_line = result.stdout.strip().split('\n')[0]
            server_info = json.loads(first_line)
            return server_info.get('token') or None
    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
        pass

    return None


def _is_loopback_url(url):
    """True if the URL's host is loopback - safe to attach a locally-detected token.

    Uses the parsed hostname (not a substring match) so tricks like
    http://127.0.0.1@evil.com/ or http://localhost.evil.com/ resolve to the
    real host (evil.com) and are correctly treated as remote.
    """
    return urlparse(url).hostname in ('127.0.0.1', 'localhost', '::1')


def send_notification_api(
    base_url: str = None,
    message: str = "Hello from notification script!",
    notification_type: str = "info",
    auto_close: int = 5000,
    actions: list = None,
    data: dict = None,
    token: str = None,
    immediate: bool = False,
    verbose: bool = False
):
    """
    Send a notification via HTTP API to a JupyterLab server.

    Args:
        base_url: Base URL of the JupyterLab server (auto-detected if not provided)
        message: Notification message text
        notification_type: Type of notification (default, info, success, warning, error, in-progress)
        auto_close: Auto-close timeout in milliseconds, or False to disable
        actions: List of action dictionaries with label, caption, and displayType
        data: Optional arbitrary data to attach to the notification
        token: Authentication token (optional for localhost)
        immediate: Push instantly to connected clients via WebSocket (--now)
        verbose: Print debug information
    """
    # Auto-detect base URL if not provided (always a loopback address).
    if base_url is None:
        base_url = get_jupyter_base_url()

    if verbose:
        print(f"Using base URL: {base_url}")

    # Auto-detect a token only for a loopback target (auto-detected, or an
    # explicit 127.0.0.1/localhost --url). The server's token-free localhost
    # bypass is opt-in / off by default, so a token is normally required; but
    # never auto-attach the local server's token to a remote --url - that would
    # leak it. Pass --token explicitly for a remote server.
    if token is None and _is_loopback_url(base_url):
        token = detect_token()

    if verbose:
        if token:
            print("Using authentication token")
        else:
            print("No authentication token (pass --token for a remote server)")
        print()

    # Construct the endpoint URL. The token travels in the Authorization header
    # only (below), never in the URL, so it does not land in server access logs.
    endpoint = f"{base_url}/jupyterlab-notifications-extension/ingest"

    # Build notification payload
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

    # Convert to JSON
    json_data = json.dumps(payload).encode('utf-8')

    # Debug: print JSON body if verbose mode enabled
    if verbose:
        print("Sending JSON payload:")
        print(json.dumps(payload, indent=2))
        print()

    # Build headers
    headers = {
        'Content-Type': 'application/json'
    }

    # Add authorization header if a token is available
    if token:
        headers['Authorization'] = f'token {token}'

    # Create request
    req = urllib.request.Request(
        endpoint,
        data=json_data,
        headers=headers,
        method='POST'
    )

    try:
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode('utf-8'))
            print(f"Notification sent: {result.get('notification_id')}")
            return result
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        print(f"HTTP Error {e.code}: {e.reason}")
        print(f"Response: {error_body}")
        raise
    except urllib.error.URLError as e:
        print(f"URL Error: {e.reason}")
        print(f"Is JupyterLab running at {base_url}?")
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Send notifications to JupyterLab",
        epilog="""
Examples:
  # Basic notification
  %(prog)s -m "Hello World"

  # With JupyterHub base path
  %(prog)s --url "http://127.0.0.1:8888/jupyterhub/user/alice" -m "Hello"

  # Warning that stays until dismissed
  %(prog)s -m "Maintenance in 1 hour" -t warning --no-auto-close

  # Dismiss button
  %(prog)s -m "Task complete" --action "Dismiss"

  # Action button that executes a JupyterLab command
  %(prog)s -m "Help Available!" --action "Open Help" --cmd "iframe:open" --command-args '{"path": "local:///welcome.html"}'

  # Silent notification (notification center only)
  %(prog)s -m "Background task done" --auto-close 0

  # Immediate display (push now, don't wait for the next poll)
  %(prog)s -m "Deploy finished" --now
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--url",
        default=None,
        help="JupyterLab base URL (auto-detected from running servers via 'jupyter server list')"
    )
    parser.add_argument(
        "--message", "-m",
        default=None,
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
        default=5000,
        help="Auto-close timeout in milliseconds (default: 5000, use 0 for silent)"
    )
    parser.add_argument(
        "--no-auto-close",
        action="store_true",
        help="Disable auto-close (stays until dismissed)"
    )
    parser.add_argument(
        "--token",
        default=None,
        help="Auth token for API mode (auto-detected from JUPYTERHUB_API_TOKEN, JPY_API_TOKEN, or JUPYTER_TOKEN)"
    )
    parser.add_argument(
        "--now",
        action="store_true",
        dest="immediate",
        help="Display instantly via WebSocket push instead of waiting for the next poll"
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

    # Show help if no message provided
    if args.message is None:
        parser.print_help()
        return 0

    auto_close = False if args.no_auto_close else args.auto_close

    # Parse data JSON if provided
    data_dict = None
    if args.data:
        try:
            data_dict = json.loads(args.data)
        except json.JSONDecodeError as e:
            print(f"Error parsing --data JSON: {e}")
            return 1

    # Parse command args JSON if provided
    command_args = None
    if args.command_args:
        try:
            command_args = json.loads(args.command_args)
        except json.JSONDecodeError as e:
            print(f"Error parsing --command-args JSON: {e}")
            return 1

    # Build actions if requested
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

    # Get URL (auto-detect if not specified)
    url = args.url if args.url else get_jupyter_base_url()
    print(f"URL: {url} | Type: {args.type}")

    try:
        send_notification_api(
            base_url=args.url,
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
    except Exception:
        return 1


if __name__ == "__main__":
    exit(main())
