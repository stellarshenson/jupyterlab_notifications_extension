# Defects - jupyterlab_notifications_extension

`[ ]` open, `[x]` fixed. Dated notes under each track how it evolved. `DEF-N` ids are stable and never reused.

Most entries were found by the 2026-07-15 adversarial review (bug-hunter + architect panel) of the immediate-delivery (`--now` / WebSocket) feature. Several are pre-existing and were surfaced by that review; noted where so.

## Contents

- [Immediate delivery (WebSocket push)](#immediate-delivery-websocket-push)
- [Security](#security)
- [Maintainability and consistency](#maintainability-and-consistency)
- [Documentation](#documentation)

## Immediate delivery (WebSocket push)

- [x] `DEF-1` **"poll fallback never loses a notification" is false in multi-tab** - MEDIUM; `NotificationFetchHandler.get` does a destructive global drain (`notifications = _notification_store.copy(); _notification_store = []`), so the first tab to poll empties the queue for every tab; an `--now` notification pushed while one tab's socket is down (5s reconnect gap, or a tab opened just after the push) is shown by connected tabs via WebSocket, but the down tab's later poll returns empty and it never displays the item; the code comments and README over-promised; fix: corrected the contract to "best-effort single-consumer" in comments and README (deep per-client delivery not implemented - documented as best-effort); `jupyterlab_notifications_extension/routes.py:117-120`
  - 2026-07-15 reported: adversarial review (bug-hunter) finding 1, DO-NOT-SHIP; destructive drain is pre-existing, the over-stated "never loses" contract is new with this feature
  - 2026-07-15 fixed: reworded the `post()` queue comment and the README "Immediate Delivery" section to state poll is a best-effort single-consumer drain and the push reaches all connected tabs; per-client durable delivery left as a future enhancement
- [x] `DEF-2` **dedup id not robustly unique now that it is correctness-critical** - LOW; `id = f"notif_{int(time.time()*1000)}_{len(_notification_store)}"` used a `len()` suffix that resets to 0 on every drain; the feature promoted this id to the `seenNotificationIds` dedup key; fix: derive the id from a process-lifetime monotonic counter (`itertools.count`); `jupyterlab_notifications_extension/routes.py:26,106`
  - 2026-07-15 reported: architect rated MAJOR; bug-hunter tested and cleared it as not achievable in practice; reconciled to LOW hardening
  - 2026-07-15 fixed: `_id_counter = itertools.count(1)`, id now `notif_<ms>_<counter>`; added `test_notification_ids_unique_across_drains` (green)
- [x] `DEF-3` **`seenNotificationIds` grows unbounded for the tab lifetime** - LOW; every displayed notification id was inserted and never evicted (slow memory leak on long-lived tabs); fix: bounded the Set to `MAX_SEEN_IDS` (500), evicting the oldest (Set preserves insertion order); `src/index.ts:308-331`
  - 2026-07-15 reported: both reviewers (bug-hunter finding 3, architect minor)
  - 2026-07-15 fixed: cap + oldest-eviction in `displayNotification`
- [x] `DEF-4` **WebSocket reconnect has no backoff, cap, or stop condition** - LOW; `onerror -> close -> onclose -> setTimeout(connect, 5000)` unconditionally forever; a persistent 403/404/down server made every tab retry every 5s indefinitely; the delay was a bare literal beside the named `POLL_INTERVAL`; fix: named constants, capped exponential backoff, give up after `RECONNECT_MAX_ATTEMPTS` (10), reset on `onopen`; `src/index.ts` (`connectNotificationStream`)
  - 2026-07-15 reported: both reviewers (bug-hunter finding 4, architect minor - also covers the bare-literal consistency nit)
  - 2026-07-15 fixed: `RECONNECT_BASE_MS`/`RECONNECT_MAX_MS`/`RECONNECT_MAX_ATTEMPTS`, backoff `min(base*2^(n-1), max)`, give-up warns and falls back to poll
- [x] `DEF-5` **`_push_immediate` drops a listener on ANY write exception** - LOW; `except Exception: discard` treated a transient write error as a permanent disconnect; fix: discard only on `WebSocketClosedError`; other exceptions are logged and the listener kept; `jupyterlab_notifications_extension/routes.py`
  - 2026-07-15 reported: architect judgement finding
  - 2026-07-15 fixed: split except into `WebSocketClosedError` (discard) and `Exception` (log, keep)

## Security

- [x] `DEF-6` **localhost auth bypass on ingest trusts `remote_ip`** - MEDIUM; `_is_localhost()` + a dummy `get_current_user` skipped auth for any request whose `remote_ip` is loopback; behind a same-host reverse proxy that is `127.0.0.1` for ALL external clients (with `trust_xheaders` off), so any unauthenticated client could push `immediate` notifications carrying action buttons that execute commands; pre-existing, amplified by the new instant-push path; fix (user decision: opt-in, secure by default): bypass now fires only when `JUPYTERLAB_NOTIFICATIONS_ALLOW_UNAUTHENTICATED_LOCALHOST=1` is set, via `web_app.settings[ALLOW_UNAUTH_LOCALHOST_SETTING]` (default off, mirrors jupyter_server's own env-var idiom); the CLI now authenticates with a detected token (env or running-server token) so it keeps working under secure-by-default; `jupyterlab_notifications_extension/routes.py`, `__init__.py`, `cli.py`
  - 2026-07-15 reported: both reviewers (bug-hunter finding 2 with runtime trace, architect major); needs a deployment decision before changing
  - 2026-07-15 fixed: opt-in env-var gate (default off); dropped the dead `'localhost'` string too (see DEF-9); CLI `detect_token()` attaches a token for localhost; updated `test_localhost_bypass_is_opt_in` + `test_remote_ip_requires_auth` (green); README documents the env var
- [x] `DEF-7` **ingest 500 handler returns `str(e)` to the client** - LOW; the catch-all returned the raw exception string, leaking internal detail; fix: `self.log.exception(...)` server-side, return a generic `"Internal server error"`; `jupyterlab_notifications_extension/routes.py`
  - 2026-07-15 reported: architect minor; pre-existing
  - 2026-07-15 fixed: log-and-generalise
- [x] `DEF-12` **CLI auto-attached the local server token to an explicit remote `--url`** - MAJOR; regression from the DEF-6 CLI change: `send_notification_api` filled `token = detect_token()` whenever `--token` was omitted and attached it to any `base_url`, so `jupyterlab-notify --url http://remote-host -m x` with a local server running and no `--token` sent the LOCAL server's token to the remote host; cause: token auto-detection was not scoped to the target; fix: auto-detect a token only for a loopback target (host-parsed `_is_loopback_url`, covering the auto-detected URL and an explicit `127.0.0.1`/`localhost` `--url`); a genuinely remote `--url` gets no auto-token; also dropped the redundant `?token=` URL param so the token travels in the Authorization header only (keeps it out of access logs, subsumes the bug-hunter URL-token finding); `jupyterlab_notifications_extension/cli.py`
  - 2026-07-15 reported: round-2 architect re-review, MAJOR credential-leak regression (DO-NOT-SHIP); bug-hunter separately flagged the redundant URL token as a log leak
  - 2026-07-15 fixed: gate on `detect_token()`; removed the URL-token branch; module docstring corrected
  - 2026-07-15 refined: round-3 re-review returned SHIP but flagged that a `base_url is None` gate broke the documented explicit-loopback JupyterHub `--url` path (403); switched to a host-parsed `_is_loopback_url` check so loopback targets (auto or explicit) authenticate while a remote `--url` still gets no token; adversarial truth-table (userinfo `@evil.com`, `localhost.evil.com`, prefix/query spoofs, `::1`) verified - all correct

## Maintainability and consistency

- [x] `DEF-8` **API namespace string duplicated across 5 files** - LOW; `"jupyterlab-notifications-extension"` was hand-inlined in `routes.py` (x3), `request.ts`, `index.ts` (WS builder), `cli.py`, `scripts/send_notification.py`; fix (scoped to the active paths): `API_NAMESPACE` constant in `routes.py` (used by all 3 route patterns) and exported from `request.ts` (used by `requestAPI` and the `index.ts` WS builder); `cli.py` and the legacy standalone `scripts/send_notification.py` keep literals on purpose - both must run as standalone scripts (a package import would break direct execution / force heavy deps); `jupyterlab_notifications_extension/routes.py`, `src/request.ts`, `src/index.ts`
  - 2026-07-15 reported: architect major (maintainability); pre-existing pattern extended by this feature
  - 2026-07-15 fixed: 3->1 server-side, 2->1 frontend; standalone-script literals kept with documented rationale
- [x] `DEF-9` **dead `'localhost'` branch in `_is_localhost`** - LOW; `remote_ip` is always a resolved IP, so the literal `'localhost'` in the tuple could never match; fix: removed it (tuple is now `('127.0.0.1', '::1')`); `jupyterlab_notifications_extension/routes.py`
  - 2026-07-15 reported: architect minor; pre-existing
  - 2026-07-15 fixed: removed alongside the DEF-6 rework
- [x] `DEF-13` **second logging mechanism introduced by the DEF-5 fix** - LOW; the DEF-5 fix added `logging.getLogger(__name__)` for the `_push_immediate` warning while every other log site uses the jupyter app logger (`self.log` / `server_app.log`), so that one warning surfaced only via the root logger, not the ServerApp log; fix: `_push_immediate(notification, log)` now takes the caller's `self.log`; removed the module logger and `import logging`; `jupyterlab_notifications_extension/routes.py`
  - 2026-07-15 reported: round-2 architect re-review, MINOR consistency
  - 2026-07-15 fixed: warning routes through `self.log` like the other four sites

## Documentation

- [x] `DEF-10` **README advertised a 140-char message limit no code enforces** - LOW; the parameter table said `message` is "max 140 characters" but the handler validates only presence; fix: dropped the claim (no validation added, per scope); `README.md`
  - 2026-07-15 reported: architect minor; pre-existing
  - 2026-07-15 fixed: removed "(max 140 characters)"
- [x] `DEF-11` **README "Five notification types" contradicted the six the code accepts** - LOW; the feature list said five, but the param table, `cli.py` choices, and the `index.ts` type union enumerate six (`default` + five); fix: feature list now says six and includes `default`; `README.md`
  - 2026-07-15 reported: architect minor; pre-existing
  - 2026-07-15 fixed: "Five ... (info, ...)" -> "Six ... (default, info, ...)"
- [x] `DEF-14` **README response example showed an impossible notification id** - LOW; the sample response used `notif_1762549476180_0`, but the DEF-2 counter starts at `itertools.count(1)` so the `_0` suffix can never occur; fix: changed the example suffix to `_1`; `README.md`
  - 2026-07-15 reported: round-2 architect re-review, MINOR doc drift
  - 2026-07-15 fixed: example id suffix `_0` -> `_1`
