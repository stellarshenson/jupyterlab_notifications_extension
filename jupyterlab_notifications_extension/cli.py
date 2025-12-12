#!/usr/bin/env python3
"""
CLI tool to send notifications to JupyterLab via the notification extension.

Localhost requests do not require authentication tokens.
Remote requests require token via --token argument or environment variables.

Usage:
    # Default (localhost on port 8888)
    jupyter-notify --message "Your message here"

    # With custom type
    jupyter-notify --message "Your message here" --type warning

    # JupyterHub environment (use 127.0.0.1 with full path)
    jupyter-notify --url "http://127.0.0.1:8888/jupyterhub/user/konrad" --message "Test"

    # Remote server (requires token)
    jupyter-notify --url "http://remote-server:8888" --message "Test" --token "your-token"
"""

import argparse
import json
import os
import urllib.request
import urllib.error


def send_notification(
    base_url: str = "http://localhost:8888",
    message: str = "Hello from notification script!",
    notification_type: str = "info",
    auto_close: int = 5000,
    actions: list = None,
    data: dict = None,
    token: str = None,
    verbose: bool = False
):
    """
    Send a notification to the JupyterLab notification extension.

    Args:
        base_url: Base URL of the JupyterLab server (default: http://localhost:8888)
        message: Notification message text
        notification_type: Type of notification (default, info, success, warning, error, in-progress)
        auto_close: Auto-close timeout in milliseconds, or False to disable
        actions: List of action dictionaries with label, caption, and displayType
        data: Optional arbitrary data to attach to the notification
        token: Authentication token (optional for localhost)
        verbose: Print debug information
    """

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
  # Send a basic info notification
  %(prog)s --message "Hello World"

  # Send a warning that stays until dismissed
  %(prog)s --message "Maintenance in 1 hour" --type warning --no-auto-close

  # JupyterHub with base path
  %(prog)s --url "http://127.0.0.1:8888/jupyterhub/user/alice" --message "Hello"

  # Silent notification (notification center only)
  %(prog)s --message "Background task done" --auto-close 0
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--url",
        default="http://localhost:8888",
        help="JupyterLab base URL (default: http://localhost:8888)"
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
        help="Auth token (auto-detected from JUPYTERHUB_API_TOKEN, JPY_API_TOKEN, or JUPYTER_TOKEN)"
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

    try:
        send_notification(
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
