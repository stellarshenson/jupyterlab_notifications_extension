#!/usr/bin/env python3
"""
Script to send notifications to JupyterLab via the notification extension.

Usage:
    python scripts/send_notification.py

Or with custom parameters:
    python scripts/send_notification.py --message "Your message here" --type warning
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
        token: Authentication token (automatically detected from environment if not provided)
    """

    # Auto-detect token from environment variables if not provided
    if token is None:
        token = (os.environ.get('JUPYTERHUB_API_TOKEN') or
                 os.environ.get('JPY_API_TOKEN') or
                 os.environ.get('JUPYTER_TOKEN'))

    # Construct the endpoint URL
    endpoint = f"{base_url}/jupyterlab-notifications-extension/ingest"

    # Add token to URL if available
    if token:
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
    data = json.dumps(payload).encode('utf-8')

    # Debug: print JSON body if verbose mode enabled
    if verbose:
        print(f"Sending JSON payload:")
        print(json.dumps(payload, indent=2))
        print()

    # Build headers
    headers = {
        'Content-Type': 'application/json'
    }

    # Add authorization header if token is available
    if token:
        headers['Authorization'] = f'token {token}'

    # Create request
    req = urllib.request.Request(
        endpoint,
        data=data,
        headers=headers,
        method='POST'
    )

    try:
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode('utf-8'))
            print(f"✓ Notification sent successfully!")
            print(f"  Notification ID: {result.get('notification_id')}")
            return result
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        print(f"✗ HTTP Error {e.code}: {e.reason}")
        print(f"  Response: {error_body}")
        raise
    except urllib.error.URLError as e:
        print(f"✗ URL Error: {e.reason}")
        print(f"  Is JupyterLab running at {base_url}?")
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Send notifications to JupyterLab notification extension",
        epilog="""
Examples:
  # Send a basic info notification
  %(prog)s --message "Hello World"

  # Send a warning that stays until dismissed
  %(prog)s --message "Maintenance in 1 hour" --type warning --no-auto-close

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
        "--message",
        required=True,
        help="Notification message (required)"
    )
    parser.add_argument(
        "--type",
        choices=["default", "info", "success", "warning", "error", "in-progress"],
        default="info",
        help="Notification type (default: info)"
    )
    parser.add_argument(
        "--auto-close",
        type=int,
        default=5000,
        help="Auto-close timeout in milliseconds (0 for silent mode, use --no-auto-close to disable)"
    )
    parser.add_argument(
        "--no-auto-close",
        action="store_true",
        help="Disable auto-close (notification stays until manually dismissed)"
    )
    parser.add_argument(
        "--token",
        default=None,
        help="Authentication token (auto-detected from JUPYTERHUB_API_TOKEN or JUPYTER_TOKEN env vars if not provided)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print JSON payload for debugging"
    )
    parser.add_argument(
        "--data",
        type=str,
        default=None,
        help="JSON string of arbitrary data to attach to notification (e.g., '{\"url\": \"https://example.com\"}')"
    )

    args = parser.parse_args()

    auto_close = False if args.no_auto_close else args.auto_close

    # Parse data JSON if provided
    data_dict = None
    if args.data:
        try:
            data_dict = json.loads(args.data)
        except json.JSONDecodeError as e:
            print(f"✗ Error parsing --data JSON: {e}")
            return

    # Example with action buttons
    actions = [
        {
            "label": "Dismiss",
            "caption": "Close this notification",
            "displayType": "default"
        }
    ]

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


if __name__ == "__main__":
    main()
