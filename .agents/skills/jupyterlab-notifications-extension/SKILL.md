---
name: jupyterlab-notifications-extension
description: Send a notification to a running JupyterLab, through the `jupyterlab-notify` CLI of jupyterlab_notifications_extension. Use when telling the user a long job finished, pushing a message to an open lab tab, giving them a button that runs a JupyterLab command, handing them a web app started on a local port, or "send a jupyterlab notification".
---

# jupyterlab-notify

Runs next to a JupyterLab server. POSTs a notification, the lab tab shows it. Flags, auth, environment, exit codes: `jupyterlab-notify --help`. Read first.

## Rules

- Poll delivery is destructive, single consumer. First tab to poll takes the notification, other tabs never see it. Want every tab, pass `--now`
- `--now` interrupts every open tab at once. Use for a job that finished, not for chatter
- `--command` runs any JupyterLab command id when the button is clicked, `--command-args` carries its JSON arguments: `help:open` opens a URL, `docmanager:open` a file, `terminal:create-new` a terminal. Never put a command button on a message whose text came from somewhere you do not trust
- Server must have the extension loaded. No extension, request 404s and nothing shows

## Local web app, handed over as a button

Started a server on a port beside the lab? The user's browser cannot reach that port. The lab proxies it at `<base path>proxy/<port>/`, so send the page rather than the port number:

```bash
jupyterlab-notify -m "Dashboard is up" --action "Open dashboard" \
  --cmd help:open \
  --command-args '{"url": "/user/alice/proxy/8501/", "text": "Dashboard", "newBrowserTab": true}'
```

- Base path is the one the CLI prints in its own line: `$JUPYTERHUB_SERVICE_PREFIX` on JupyterHub, `/` on a plain lab. A bare `/proxy/<port>/` misses the user prefix and 404s there
- `newBrowserTab: true` opens a real browser tab. Without it the page lands in a lab tab inside a sandboxed frame with no storage, where some apps fail
- Port must be on the lab server's own host, with `jupyter-server-proxy` installed there. App's own links broken, try `proxy/absolute/<port>/`
