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
import urllib.request
import urllib.error


def send_notification(
    base_url: str = "http://localhost:8888",
    message: str = "Hello from notification script!",
    notification_type: str = "info",
    auto_close: int = 5000,
    target_users: list = None,
    actions: list = None
):
    """
    Send a notification to the JupyterLab notification extension.

    Args:
        base_url: Base URL of the JupyterLab server (default: http://localhost:8888)
        message: Notification message text
        notification_type: Type of notification (default, info, success, warning, error, in-progress)
        auto_close: Auto-close timeout in milliseconds, or False to disable
        target_users: List of usernames to target, or None for all users
        actions: List of action dictionaries with label, caption, and displayType
    """

    # Construct the endpoint URL
    endpoint = f"{base_url}/jupyterlab-notifications-extension/ingest"

    # Build notification payload
    payload = {
        "message": message,
        "type": notification_type,
        "autoClose": auto_close
    }

    if target_users is not None:
        payload["target_users"] = target_users

    if actions is not None:
        payload["actions"] = actions

    # Convert to JSON
    data = json.dumps(payload).encode('utf-8')

    # Create request
    req = urllib.request.Request(
        endpoint,
        data=data,
        headers={
            'Content-Type': 'application/json'
        },
        method='POST'
    )

    try:
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode('utf-8'))
            print(f"✓ Notification sent successfully!")
            print(f"  Notification ID: {result.get('notification_id')}")
            print(f"  Target users: {result.get('target_users')}")
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
        description="Send notifications to JupyterLab notification extension"
    )
    parser.add_argument(
        "--url",
        default="http://localhost:8888",
        help="JupyterLab base URL (default: http://localhost:8888)"
    )
    parser.add_argument(
        "--message",
        default="Hello from notification script!",
        help="Notification message"
    )
    parser.add_argument(
        "--type",
        choices=["default", "info", "success", "warning", "error", "in-progress"],
        default="info",
        help="Notification type"
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
        "--users",
        nargs="+",
        default=None,
        help="Target specific users (space-separated usernames)"
    )

    args = parser.parse_args()

    auto_close = False if args.no_auto_close else args.auto_close

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
        target_users=args.users,
        actions=actions
    )


if __name__ == "__main__":
    main()
