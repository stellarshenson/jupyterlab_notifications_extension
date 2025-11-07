# jupyterlab_notifications_extension

[![GitHub Actions](https://github.com/stellarshenson/jupyterlab_notifications_extension/actions/workflows/build.yml/badge.svg)](https://github.com/stellarshenson/jupyterlab_notifications_extension/actions/workflows/build.yml)
[![npm version](https://img.shields.io/npm/v/jupyterlab_notifications_extension.svg)](https://www.npmjs.com/package/jupyterlab_notifications_extension)
[![PyPI version](https://img.shields.io/pypi/v/jupyterlab-notifications-extension.svg)](https://pypi.org/project/jupyterlab-notifications-extension/)
[![Total PyPI downloads](https://static.pepy.tech/badge/jupyterlab-notifications-extension)](https://pepy.tech/project/jupyterlab-notifications-extension)
[![JupyterLab 4](https://img.shields.io/badge/JupyterLab-4-orange.svg)](https://jupyterlab.readthedocs.io/en/stable/)

Jupyterlab extension to receive and display notifications in the main panel. Those can be from the jupyterjub administrator or from other places.

This extension is composed of a Python package named `jupyterlab_notifications_extension`
for the server extension and a NPM package named `jupyterlab_notifications_extension`
for the frontend extension.

## Requirements

- JupyterLab >= 4.0.0

## Install

To install the extension, execute:

```bash
pip install jupyterlab_notifications_extension
```

## Usage

This extension enables external systems (administrators, monitoring systems, CI/CD pipelines) to send notifications that appear in JupyterLab's notification center.

### Sending Notifications

The extension provides a POST endpoint at `/jupyterlab-notifications-extension/ingest` that accepts notification payloads.

**Notification Schema:**

```json
{
  "message": "Your notification message",
  "type": "info",
  "autoClose": 5000,
  "target_users": ["user1", "user2"],
  "actions": [
    {
      "label": "Click here",
      "caption": "Additional info",
      "displayType": "accent"
    }
  ]
}
```

**Field Descriptions:**

- `message` (required): The notification message text
- `type` (optional): Notification type - `default`, `info`, `success`, `warning`, `error`, or `in-progress` (default: `info`)
- `autoClose` (optional): Auto-close timeout in milliseconds, or `false` to disable auto-close (default: `5000`)
  - Use `0` for silent mode (adds to notification center without toast popup)
- `target_users` (optional): Array of usernames to target, or `null`/omit for all users
- `actions` (optional): Array of action buttons to display
  - `label`: Button text
  - `caption`: Tooltip text
  - `displayType`: Visual style - `default`, `accent`, `warn`, or `link`

### Example: Using the Test Script

A test script is provided for sending notifications:

```bash
# Basic usage
python scripts/send_notification.py

# Custom message and type
python scripts/send_notification.py --message "Deployment complete!" --type success

# Warning that requires manual dismiss
python scripts/send_notification.py \
  --message "System maintenance in 1 hour" \
  --type warning \
  --no-auto-close

# Target specific users
python scripts/send_notification.py \
  --message "Your job has completed" \
  --type success \
  --users alice bob

# Silent notification (no toast, only in notification center)
python scripts/send_notification.py \
  --message "Background task finished" \
  --auto-close 0
```

### Example: Using cURL

```bash
# Send a basic notification
curl -X POST http://localhost:8888/jupyterlab-notifications-extension/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Hello from cURL!",
    "type": "info",
    "autoClose": 5000
  }'

# Send an error notification with action button
curl -X POST http://localhost:8888/jupyterlab-notifications-extension/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Build failed on main branch",
    "type": "error",
    "autoClose": false,
    "actions": [
      {
        "label": "View Logs",
        "caption": "Click to see build logs",
        "displayType": "accent"
      }
    ]
  }'
```

### How It Works

1. External systems POST notifications to the `/jupyterlab-notifications-extension/ingest` endpoint
2. Server stores notifications in memory per user
3. Frontend polls every 30 seconds for new notifications via `/jupyterlab-notifications-extension/notifications`
4. Notifications are displayed using JupyterLab's built-in notification system
5. Once fetched, notifications are removed from the server queue

## Uninstall

To remove the extension, execute:

```bash
pip uninstall jupyterlab_notifications_extension
```

## Troubleshoot

If you are seeing the frontend extension, but it is not working, check
that the server extension is enabled:

```bash
jupyter server extension list
```

If the server extension is installed and enabled, but you are not seeing
the frontend extension, check the frontend extension is installed:

```bash
jupyter labextension list
```

## Contributing

### Development install

Note: You will need NodeJS to build the extension package.

The `jlpm` command is JupyterLab's pinned version of
[yarn](https://yarnpkg.com/) that is installed with JupyterLab. You may use
`yarn` or `npm` in lieu of `jlpm` below.

```bash
# Clone the repo to your local environment
# Change directory to the jupyterlab_notifications_extension directory

# Set up a virtual environment and install package in development mode
python -m venv .venv
source .venv/bin/activate
pip install --editable ".[dev,test]"

# Link your development version of the extension with JupyterLab
jupyter labextension develop . --overwrite
# Server extension must be manually installed in develop mode
jupyter server extension enable jupyterlab_notifications_extension

# Rebuild extension Typescript source after making changes
# IMPORTANT: Unlike the steps above which are performed only once, do this step
# every time you make a change.
jlpm build
```

You can watch the source directory and run JupyterLab at the same time in different terminals to watch for changes in the extension's source and automatically rebuild the extension.

```bash
# Watch the source directory in one terminal, automatically rebuilding when needed
jlpm watch
# Run JupyterLab in another terminal
jupyter lab
```

With the watch command running, every saved change will immediately be built locally and available in your running JupyterLab. Refresh JupyterLab to load the change in your browser (you may need to wait several seconds for the extension to be rebuilt).

By default, the `jlpm build` command generates the source maps for this extension to make it easier to debug using the browser dev tools. To also generate source maps for the JupyterLab core extensions, you can run the following command:

```bash
jupyter lab build --minimize=False
```

### Development uninstall

```bash
# Server extension must be manually disabled in develop mode
jupyter server extension disable jupyterlab_notifications_extension
pip uninstall jupyterlab_notifications_extension
```

In development mode, you will also need to remove the symlink created by `jupyter labextension develop`
command. To find its location, you can run `jupyter labextension list` to figure out where the `labextensions`
folder is located. Then you can remove the symlink named `jupyterlab_notifications_extension` within that folder.

### Testing the extension

#### Server tests

This extension is using [Pytest](https://docs.pytest.org/) for Python code testing.

Install test dependencies (needed only once):

```sh
pip install -e ".[test]"
# Each time you install the Python package, you need to restore the front-end extension link
jupyter labextension develop . --overwrite
```

To execute them, run:

```sh
pytest -vv -r ap --cov jupyterlab_notifications_extension
```

#### Frontend tests

This extension is using [Jest](https://jestjs.io/) for JavaScript code testing.

To execute them, execute:

```sh
jlpm
jlpm test
```

#### Integration tests

This extension uses [Playwright](https://playwright.dev/docs/intro) for the integration tests (aka user level tests).
More precisely, the JupyterLab helper [Galata](https://github.com/jupyterlab/jupyterlab/tree/master/galata) is used to handle testing the extension in JupyterLab.

More information are provided within the [ui-tests](./ui-tests/README.md) README.

### Packaging the extension

See [RELEASE](RELEASE.md)
