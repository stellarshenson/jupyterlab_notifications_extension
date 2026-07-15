# Acceptance Criteria - jupyterlab_notifications_extension

Consolidated acceptance criteria, one `##` section per feature. `[ ]` todo / `[x]` done; each item carries a `log:` line. Immediate-delivery items marked `[x]` are covered by unit tests or the build; browser-observable behaviours not yet verified in a live tab stay `[ ]` with a `pending live verification` log.

## Contents

- [Immediate Delivery](#immediate-delivery)
- [Time-Ago Indicator](#time-ago-indicator)
- [API](#api)

## Immediate Delivery

`--now` (CLI) / `"immediate": true` (REST) pushes a notification over a WebSocket to every open tab instantly, instead of waiting up to 30s for the poll. Push is an accelerator over a best-effort poll baseline, deduped by notification id.

- [x] **CLI flag** - `jupyterlab-notify --now` sets `immediate: true` in the POST payload
  - log: 2026-07-15 implemented
- [x] **REST field** - `"immediate": true` in the ingest body triggers the push path
  - log: 2026-07-15 implemented
- [x] **Server push** - on ingest with `immediate`, the notification is written to every connected stream listener via `_push_immediate`
  - log: 2026-07-15 implemented; unit-verified (push + dead-listener cleanup)
- [x] **Queue still populated** - an immediate notification is appended to `_notification_store` before the push, so it is also available to the poll
  - log: 2026-07-15 implemented
- [x] **Stream route** - `NotificationStreamHandler` mounted at `/<namespace>/stream` as a WebSocket
  - log: 2026-07-15 implemented
- [x] **Stream auth** - the WebSocket enforces `@ws_authenticated`; only authenticated sessions register as listeners
  - log: 2026-07-15 implemented; confirmed by bug-hunter review
- [x] **Keepalive** - the stream inherits `WebSocketMixin` ping/pong so idle sockets survive proxy timeouts
  - log: 2026-07-15 implemented
- [x] **Id uniqueness** - notification id uses a process-lifetime monotonic counter, unique across store drains
  - log: 2026-07-15 implemented; `test_notification_ids_unique_across_drains` green
- [x] **Dedup by id** - `displayNotification` shows a given id once across the push and poll paths
  - log: 2026-07-15 implemented (jest covers helper; path dedup by construction)
- [x] **Dedup set bounded** - `seenNotificationIds` capped at 500, oldest evicted, no unbounded growth
  - log: 2026-07-15 implemented (DEF-3)
- [x] **Reconnect backoff** - stream reconnects with capped exponential backoff and gives up after 10 attempts, falling back to poll-only
  - log: 2026-07-15 implemented (DEF-4)
- [x] **Poll baseline retained** - the 30s poll runs regardless of the socket
  - log: 2026-07-15 implemented
- [ ] **Live: instant display** - an `--now` notification appears in an open tab within ~1s, without waiting for the poll
  - log: 2026-07-15 implemented, pending live verification
- [ ] **Live: all connected tabs** - the push reaches every currently-open tab, not just one
  - log: 2026-07-15 implemented, pending live verification
- [ ] **Edge: socket down at push (multi-tab)** - a tab whose socket is down when the push fires is NOT guaranteed the notification via poll (destructive single-consumer drain); documented as best-effort, not a durable per-client queue
  - log: 2026-07-15 behaviour accepted and documented (DEF-1); durable per-client delivery deferred
- [ ] **Edge: server older than frontend** - `/stream` 404s; reconnect backs off and gives up after 10 attempts; poll still delivers
  - log: 2026-07-15 implemented, pending live verification
- [ ] **Edge: token rotation / 403** - handshake rejected; reconnect gives up, degrades to poll-only, no 5s hammer loop
  - log: 2026-07-15 implemented, pending live verification
- [x] **Edge: `immediate` absent/falsy** - no push; notification delivered by poll only
  - log: 2026-07-15 implemented
- [x] **Edge: no listeners connected** - push is a no-op; poll delivers on next cycle
  - log: 2026-07-15 implemented
- [x] **Edge: listener write fails** - a closed socket is discarded; any other write error is logged and the listener kept
  - log: 2026-07-15 implemented (DEF-5)
- [x] **Security: localhost bypass opt-in** - token-free localhost ingest fires only when `JUPYTERLAB_NOTIFICATIONS_ALLOW_UNAUTHENTICATED_LOCALHOST=1`; off by default
  - log: 2026-07-15 implemented (DEF-6); `test_localhost_bypass_is_opt_in` green
- [x] **Security: remote requires auth** - a non-loopback request always goes through parent auth, even with the opt-in enabled
  - log: 2026-07-15 implemented; `test_remote_ip_requires_auth` green
- [x] **Security: CLI authenticates loopback only** - the CLI attaches a detected token (env or running-server token) only for a loopback target (auto-detected, or an explicit `127.0.0.1`/`localhost` `--url`), so it works under secure-by-default including the JupyterHub loopback path
  - log: 2026-07-15 implemented (DEF-6 follow-through); scoped to loopback via host-parsed `_is_loopback_url` (DEF-12)
- [x] **Security: no token leak to remote `--url`** - an explicit `--url` never receives the auto-detected local token; a remote server requires an explicit `--token`
  - log: 2026-07-15 implemented (DEF-12)
- [x] **Security: token not in URL** - the CLI sends the token in the Authorization header only, never as a `?token=` URL param, so it does not land in server access logs
  - log: 2026-07-15 implemented (DEF-12)
- [x] **Security: generic 500** - ingest errors are logged server-side and return a generic message, no internal detail leaked
  - log: 2026-07-15 implemented (DEF-7)

## Time-Ago Indicator

Each notification shows a relative timestamp that refreshes while visible, injected into the toast and notification-center DOM, using the server-side `createdAt`.

- [x] **Relative label** - shows `just now`, `Xm ago`, `Xh ago`, `Xd ago`; anything under 60s is `just now`
  - log: 2026-07-15 implemented (v1.2.22); jest covers `formatTimeAgo`
- [x] **Refresh** - the label updates every 10s while the notification is visible
  - log: 2026-07-15 implemented
- [x] **Placement** - appears below the message when no action buttons exist, inline in `.jp-toast-buttonBar` when buttons exist
  - log: 2026-07-15 implemented (v1.2.13)
- [x] **Toast + center** - injected into both toast popups and the notification-center list
  - log: 2026-07-15 implemented
- [x] **All toast sources** - notifications from JupyterLab itself (culler, uploads, kernel) also get time-ago via the MutationObserver
  - log: 2026-07-15 implemented (v1.2.21)
- [x] **Authoritative timestamp** - center and toast use the server `createdAt`, so both show the same age
  - log: 2026-07-15 implemented (v1.2.18)
- [x] **Edge: multiline message** - messages rendered with `<br>` match via `innerText` + whitespace normalisation
  - log: 2026-07-15 implemented (v1.2.20)
- [x] **Edge: no cumulative duplication** - the center injector guards against re-adding time-ago (checks message and button-bar sibling), no cascading duplicates
  - log: 2026-07-15 implemented (v1.2.15)

## API

- `POST /jupyterlab-notifications-extension/ingest` body `{message, type?, autoClose?, immediate?, actions?, data?}` -> `{success, notification_id}`; 400 missing `message` / invalid JSON, 500 generic
- `GET /jupyterlab-notifications-extension/notifications` -> `{notifications: [...]}` (destructive single-consumer drain)
- `WS /jupyterlab-notifications-extension/stream` - authenticated; server -> client only; frames are `{notifications: [<notification>]}`
- Server setting `JUPYTERLAB_NOTIFICATIONS_ALLOW_UNAUTHENTICATED_LOCALHOST=1` (env) opts in to token-free loopback ingest; off by default
