#!/usr/bin/env python3
"""
CLI tool to send notifications to JupyterLab via the notification extension.

Sends notifications via HTTP API to a running JupyterLab server.
Auto-detects URL from running servers. Localhost requests do not require authentication.

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


def send_notification_api(
    base_url: str = None,
    message: str = "Hello from notification script!",
    notification_type: str = "info",
    auto_close: int = 5000,
    actions: list = None,
    data: dict = None,
    token: str = None,
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
        verbose: Print debug information
    """
    # Auto-detect base URL if not provided
    if base_url is None:
        base_url = get_jupyter_base_url()

    if verbose:
        print(f"Using base URL: {base_url}")

    # Check if target is localhost
    is_localhost = (
        base_url.startswith('http://localhost') or
        base_url.startswith('http://127.0.0.1') or
        base_url.startswith('http://[::1]')
    )

    # Auto-detect token from environment variables if not provided (skip for localhost)
    if not is_localhost and token is None:
        token = (
            os.environ.get('JUPYTERHUB_API_TOKEN') or
            os.environ.get('JPY_API_TOKEN') or
            os.environ.get('JUPYTER_TOKEN')
        )

    if verbose:
        if is_localhost:
            print("Target is localhost - skipping authentication")
        elif token:
            print("Using authentication token")
        else:
            print("No token provided for remote host")
        print()

    # Construct the endpoint URL
    endpoint = f"{base_url}/jupyterlab-notifications-extension/ingest"

    # Add token to URL if available and not localhost
    if token and not is_localhost:
        separator = '&' if '?' in endpoint else '?'
        endpoint = f"{endpoint}{separator}token={token}"

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

    # Add authorization header if token is available and not localhost
    if token and not is_localhost:
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
            verbose=args.verbose
        )
        return 0
    except Exception:
        return 1


if __name__ == "__main__":
    exit(main())
