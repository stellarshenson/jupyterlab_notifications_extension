# jupyterlab_notifications_extension

[![GitHub Actions](https://github.com/stellarshenson/jupyterlab_notifications_extension/actions/workflows/build.yml/badge.svg)](https://github.com/stellarshenson/jupyterlab_notifications_extension/actions/workflows/build.yml)
[![npm version](https://img.shields.io/npm/v/jupyterlab_notifications_extension.svg)](https://www.npmjs.com/package/jupyterlab_notifications_extension)
[![PyPI version](https://img.shields.io/pypi/v/jupyterlab-notifications-extension.svg)](https://pypi.org/project/jupyterlab-notifications-extension/)
[![Total PyPI downloads](https://static.pepy.tech/badge/jupyterlab-notifications-extension)](https://pepy.tech/project/jupyterlab-notifications-extension)
[![JupyterLab 4](https://img.shields.io/badge/JupyterLab-4-orange.svg)](https://jupyterlab.readthedocs.io/en/stable/)

JupyterLab extension enabling external systems to send notifications that appear in JupyterLab's notification center. Administrators, monitoring systems, and CI/CD pipelines can broadcast alerts, status updates, and system messages directly to users working in JupyterLab.

**Key capabilities**:
- REST API endpoint for external notification ingestion
- Automatic polling with 30-second refresh interval
- Support for multiple notification types (info, success, warning, error)
- Configurable auto-close behavior and action buttons
- Built on JupyterLab's native notification system

The extension consists of a Python server component providing REST endpoints and a TypeScript frontend that polls for new notifications and displays them using JupyterLab's built-in notification manager.

## Installation

```bash
pip install jupyterlab_notifications_extension
```

**Requirements**: JupyterLab >= 4.0.0

## Usage

External systems send notifications via HTTP POST to the `/jupyterlab-notifications-extension/ingest` endpoint. The server queues notifications in memory and the frontend polls every 30 seconds to fetch and display them.

### Notification API

POST notifications to `/jupyterlab-notifications-extension/ingest` with JSON payload:

```json
{
  "message": "Your notification message",
  "type": "info",
  "autoClose": 5000,
  "actions": [
    {
      "label": "Click here",
      "caption": "Additional info",
      "displayType": "accent"
    }
  ]
}
```

**Parameters**:
- `message` (required) - Notification text displayed to users
- `type` (optional) - Visual style: `default`, `info`, `success`, `warning`, `error`, `in-progress` (default: `info`)
- `autoClose` (optional) - Milliseconds before auto-dismiss, `false` to require manual dismiss, `0` for silent mode (default: `5000`)
- `actions` (optional) - Array of action buttons with `label`, `caption`, and `displayType` fields

Silent mode (`autoClose: 0`) adds notifications to the center without showing toast popups.

### Sending Notifications

**Python script** (auto-detects authentication tokens from environment):

```bash
# Basic notification
python scripts/send_notification.py --message "Deployment complete" --type success

# Persistent warning
python scripts/send_notification.py \
  --message "System maintenance in 1 hour" \
  --type warning \
  --no-auto-close

# Silent notification
python scripts/send_notification.py \
  --message "Background task finished" \
  --auto-close 0
```

The script automatically detects authentication tokens from `JUPYTERHUB_API_TOKEN`, `JPY_API_TOKEN`, or `JUPYTER_TOKEN` environment variables.

**cURL** (manual authentication):

```bash
# Info notification
curl -X POST http://localhost:8888/jupyterlab-notifications-extension/ingest \
  -H "Content-Type: application/json" \
  -H "Authorization: token YOUR_TOKEN" \
  -d '{"message": "Build completed", "type": "info"}'

# Error with action button
curl -X POST http://localhost:8888/jupyterlab-notifications-extension/ingest \
  -H "Content-Type: application/json" \
  -H "Authorization: token YOUR_TOKEN" \
  -d '{
    "message": "Build failed on main branch",
    "type": "error",
    "autoClose": false,
    "actions": [{
      "label": "View Logs",
      "caption": "Open build logs",
      "displayType": "accent"
    }]
  }'
```

### Architecture

The system uses a simple broadcast model where all notifications are delivered to all users.

**Flow**:
1. External system POSTs notification to `/jupyterlab-notifications-extension/ingest`
2. Server stores notification in memory queue
3. Frontend polls `/jupyterlab-notifications-extension/notifications` every 30 seconds
4. Notifications display via JupyterLab's native notification manager
5. Fetched notifications are removed from queue

## Troubleshooting

**Frontend installed but not working**:
```bash
jupyter server extension list  # Verify server extension enabled
```

**Server extension enabled but frontend missing**:
```bash
jupyter labextension list  # Verify frontend extension installed
```

**Notifications not appearing**: Check browser console for polling errors or verify JupyterLab was restarted after installation.

## Uninstall

```bash
pip uninstall jupyterlab_notifications_extension
```

## Development

### Setup

Requires NodeJS to build the extension. Uses `jlpm` (JupyterLab's pinned yarn) for package management.

```bash
# Install in development mode
python -m venv .venv
source .venv/bin/activate
pip install --editable ".[dev,test]"

# Link extension with JupyterLab
jupyter labextension develop . --overwrite
jupyter server extension enable jupyterlab_notifications_extension

# Build TypeScript
jlpm build
```

### Development workflow

Run `jlpm watch` in one terminal to auto-rebuild on changes, and `jupyter lab` in another. Refresh browser after rebuilds to load changes.

```bash
jlpm watch           # Auto-rebuild on file changes
jupyter lab          # Run JupyterLab
```

### Cleanup

```bash
jupyter server extension disable jupyterlab_notifications_extension
pip uninstall jupyterlab_notifications_extension
# Remove symlink: find via `jupyter labextension list`
```

### Testing

**Python tests** (Pytest):
```bash
pip install -e ".[test]"
pytest -vv -r ap --cov jupyterlab_notifications_extension
```

**Frontend tests** (Jest):
```bash
jlpm test
```

**Integration tests** (Playwright/Galata): See [ui-tests/README.md](ui-tests/README.md)

### Packaging

See [RELEASE.md](RELEASE.md) for release procedures.
