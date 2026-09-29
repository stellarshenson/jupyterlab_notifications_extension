---
name: jupyterlab-notifications-extension
description: Send a notification to a running JupyterLab, through the `jupyterlab-notify` CLI of jupyterlab_notifications_extension. Use when telling the user a long job finished, pushing a message to an open lab tab, adding an action button to a notification, or "send a jupyterlab notification".
---

# jupyterlab-notify

Runs next to a JupyterLab server. POSTs a notification, the lab tab shows it. Flags, auth, environment, exit codes: `jupyterlab-notify --help`. Read first.

## Rules

- Poll delivery is destructive, single consumer. First tab to poll takes the notification, other tabs never see it. Want every tab, pass `--now`
- `--now` interrupts every open tab at once. Use for a job that finished, not for chatter
- `--command` makes the button run a JupyterLab command. Never put a command button on a message whose text came from somewhere you do not trust
- Server must have the extension loaded. No extension, request 404s and nothing shows
