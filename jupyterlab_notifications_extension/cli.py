#!/usr/bin/env python3
"""
CLI tool to send notifications to JupyterLab via the notification extension.

Two modes of operation:
- Local (default): Adds notification directly to the in-memory store
- API (--use-api): Sends via HTTP API to a running JupyterLab server

Usage:
    # Local mode (default) - adds directly to notification store
    jupyter-notify -m "Your message here"

    # API mode - sends via HTTP to JupyterLab server
    jupyter-notify --use-api -m "Your message here"

    # API mode with JupyterHub base path
    jupyter-notify --use-api --url "http://127.0.0.1:8888/jupyterhub/user/konrad" -m "Test"

    # API mode to remote server (requires token)
    jupyter-notify --use-api --url "http://remote-server:8888" -m "Test" --token "your-token"
"""

import argparse
import json
import os
import time
import urllib.request
import urllib.error


def send_notification_local(
    message: str,
    notification_type: str = "info",
    auto_close: int = 5000,
    actions: list = None,
    data: dict = None,
    verbose: bool = False
):
    """
    Send a notification by adding directly to the in-memory store.

    This works when the notification extension is installed in the same
    Python environment. The notification will be picked up by JupyterLab
    on the next poll cycle.
    """
    from jupyterlab_notifications_extension.routes import _notification_store

    notification = {
        "id": f"notif_{int(time.time() * 1000)}_{len(_notification_store)}",
        "message": message,
        "type": notification_type,
        "autoClose": auto_close,
        "createdAt": int(time.time() * 1000),
        "actions": actions or [],
        "data": data
    }

    if verbose:
        print("Adding notification directly to store:")
        print(json.dumps(notification, indent=2))
        print()

    _notification_store.append(notification)
    print(f"Notification queued: {notification['id']}")
    return {"success": True, "notification_id": notification["id"]}


def get_jupyter_base_url():
    """
    Auto-detect JupyterLab base URL from environment.

    Checks in order:
    1. JUPYTER_SERVER_URL - explicit server URL
    2. JUPYTERHUB_SERVICE_PREFIX with JUPYTERHUB_API_URL - JupyterHub environment
    3. Default: http://localhost:8888
    """
    # Check for explicit server URL
    server_url = os.environ.get('JUPYTER_SERVER_URL')
    if server_url:
        return server_url.rstrip('/')

    # Check for JupyterHub environment
    service_prefix = os.environ.get('JUPYTERHUB_SERVICE_PREFIX')
    if service_prefix:
        # In JupyterHub, construct URL from service prefix
        # Default to localhost since we're running locally
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
  # Local mode (default) - adds directly to notification store
  %(prog)s -m "Hello World"

  # API mode - sends via HTTP to JupyterLab server
  %(prog)s --use-api -m "Hello World"

  # API mode with JupyterHub base path
  %(prog)s --use-api --url "http://127.0.0.1:8888/jupyterhub/user/alice" -m "Hello"

  # Warning that stays until dismissed
  %(prog)s -m "Maintenance in 1 hour" -t warning --no-auto-close

  # Silent notification (notification center only)
  %(prog)s -m "Background task done" --auto-close 0
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--use-api",
        action="store_true",
        help="Use HTTP API instead of direct local access (required for remote servers)"
    )
    parser.add_argument(
        "--url",
        default=None,
        help="JupyterLab base URL for API mode (auto-detected from JUPYTER_SERVER_URL, JUPYTERHUB_SERVICE_PREFIX, or defaults to localhost:8888)"
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
        help="Add dismiss button with custom label"
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

    # Build actions if requested
    actions = None
    if args.action:
        actions = [{
            "label": args.action,
            "caption": "Close this notification",
            "displayType": "default"
        }]

    # If URL is specified, use API mode
    use_api = args.use_api or args.url is not None

    # Print execution settings
    mode = "API" if use_api else "Local"
    if use_api:
        url = args.url if args.url else get_jupyter_base_url()
        print(f"Mode: {mode} | URL: {url} | Type: {args.type}")
    else:
        print(f"Mode: {mode} | Type: {args.type}")

    try:
        if use_api:
            # API mode - send via HTTP
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
        else:
            # Local mode - add directly to store
            send_notification_local(
                message=args.message,
                notification_type=args.type,
                auto_close=auto_close,
                actions=actions,
                data=data_dict,
                verbose=args.verbose
            )
        return 0
    except Exception:
        return 1


if __name__ == "__main__":
    exit(main())
