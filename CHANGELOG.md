# Changelog

All notable changes to this project will be documented in this file.

<!-- <START NEW CHANGELOG ENTRY> -->

## [1.2.29] - 2026-10-07

### Added

- The shipped agent skill says how to hand the user a web application started on a port beside the lab: the server proxies that port at `<base path>proxy/<port>/`, the built-in `help:open` command opens it, and `newBrowserTab: true` gives it a real browser tab rather than a sandboxed frame inside the lab

### Changed

- The agent skill's `--command` rule states that a notification button can run any JupyterLab command id, with `--command-args` carrying its arguments, and names `help:open`, `docmanager:open` and `terminal:create-new`

### Fixed

- The test for a JSON payload that raises something other than a decode error: its 30000 levels of nesting are parsed by Python 3.14, so the test failed against correct code. The payloads are now 200000 levels and a 5001-digit integer, and the test asserts `json.loads` still raises before it runs the CLI

## [1.2.28] - 2026-09-29

### Added

- The agent skill for the `jupyterlab-notify` CLI installs with the wheel, at `<sys.prefix>/share/jupyter/agents/skills/jupyterlab-notifications-extension/SKILL.md`. No agent reads that directory and a wheel cannot write into the home directory, so the README gives the link line that makes it readable; the 1.2.27 entry below still says the skill is not in the wheel, being true of 1.2.27
- A test comparing the installed copy of the agent skill with the repository copy, so a wheel built without the packaging entry, or from an older `SKILL.md`, fails the suite instead of shipping a stale skill. 187 pytest tests

### Changed

- The README's Agent Skill section carries both link lines: `~/.agents/skills` from the installed copy under `sys.prefix`, and `~/.claude/skills` from a clone

## [1.2.27] - 2026-09-29

### Added

- Agent skill at `.agents/skills/jupyterlab-notifications-extension/SKILL.md` telling an AI assistant how to drive the `jupyterlab-notify` CLI; it ships in the repository, not in the wheel, and the command reference stays in `jupyterlab-notify --help`
- `JUPYTERLAB_NOTIFY_TOKEN` environment variable, this tool's own token source, used for any target including a remote one; prefer it over `--token`, which puts the secret in argv where every local account can read `/proc/<pid>/cmdline`
- The `data` payload field is documented in the API reference, including the rule that every number inside it must be finite
- Python test suite for the CLI and a claim sweep that fails while any shipped surface still carries a retired wording; 186 pytest and 18 jest tests

### Changed

- Ingest validates element types, not only presence: a body that is not a JSON object, a `message` that is missing, empty or not a string, and an `actions` element that is not an object with a string `label` are each answered 400 with a message naming the cause
- `jupyterlab-notify` builds the URL from the server record's own scheme, host and port, substituting a loopback address for a wildcard bind, instead of assuming `http://127.0.0.1`
- `jupyterlab-notify` exits 2 and lists the candidates when several servers are running and none matches `JUPYTERHUB_SERVICE_PREFIX`, instead of silently taking the first
- `jupyterlab-notify` prints one line naming the URL it will use, where that address came from, and whether a token is being sent
- The ambient `JUPYTERHUB_API_TOKEN`, `JPY_API_TOKEN` and `JUPYTER_TOKEN` belong to the host the CLI runs on, so they are now sent only to a loopback target; a listed server's own runtime token is sent to the address that record is reached at
- The notification stream reconnects with capped exponential backoff, 5 seconds doubling to a 60-second ceiling, and keeps retrying for as long as the tab is open; it previously gave up after 10 attempts and stayed poll-only for the rest of the session without saying so
- Send dialog inputs are associated with their labels, the seconds field states its unit and range, and the type list reads as words rather than API values
- Requirements raised to JupyterLab >= 4.6, Python >= 3.10 and jupyter_server >= 2.21; build tooling upgraded to the canonical Makefile 1.43

### Removed

- `JUPYTERLAB_NOTIFICATIONS_ALLOW_UNAUTHENTICATED_LOCALHOST` server setting and the token-free loopback ingest it enabled; every ingest request now needs a token, including from localhost. Behind a same-host reverse proxy every external client's address appears as `127.0.0.1`, so the setting could not distinguish a genuine loopback caller from any client on the network. The 1.2.23 entry below still lists it, being true of 1.2.23
- `scripts/send_notification.py`, superseded by the `jupyterlab-notify` CLI
- `setup.py` shim and the committed `package-lock.json`, neither used by the hatchling and jlpm build

### Fixed

- A non-finite number anywhere in the payload (`NaN`, `Infinity`, or a literal that overflows to one) is rejected with 400 at ingest. It was accepted before, and because the poll queue is drained before it is serialised, one such number made the whole batch unparseable in the browser and every other sender's notification in it was lost with no error shown
- A query string or fragment in `--url` is removed before the endpoint path is appended; `--url 'http://host:8888/?token=abc'` previously sent the request to a path containing the token, which reached the server access log and returned 404
- A `user:password@` part in `--url` is dropped, because this tool authenticates by token only
- A malformed body that raises something other than a decode error, such as nesting past the recursion limit or an integer past the 4300-digit limit, is answered 400 like every other malformed body instead of 500, and the CLI reports it in one line instead of a traceback
- The live time-ago element is hidden from assistive technology; the toast is an assertive live region, so rewriting the label every 10 seconds re-announced the entire notification
- `jupyterlab-notify` exits 130 on an interrupt instead of printing a traceback

## [1.2.26] - 2026-08-19

### Changed

- Per-event and one-time lifecycle logs (poll received, stream connected, send ok, activation, polling started) demoted from `console.log` to `console.debug` to reduce console noise; genuine errors and warnings are unchanged
- Build tooling upgraded to the canonical Makefile 1.37: node, npm and yarn now resolve from a project-local `.nodeenv` instead of the ambient environment, the version is read lazily so a fresh clone cannot publish an unbumped version, and `make test` also runs the Python suite

## [1.2.24] - 2026-07-15

### Fixed

- Notification poll no longer logs a console error on every cycle during a transient network outage; it now warns once when it goes offline and logs once when it reconnects

## [1.2.23] - 2026-07-15

### Added

- `--now` CLI flag and `"immediate": true` REST field for instant WebSocket push to every open tab, bypassing the 30-second poll
- Authenticated WebSocket stream endpoint (`/jupyterlab-notifications-extension/stream`) for immediate delivery
- Opt-in `JUPYTERLAB_NOTIFICATIONS_ALLOW_UNAUTHENTICATED_LOCALHOST` server setting for token-free loopback ingest (off by default)

### Changed

- Localhost auth bypass is now opt-in and secure by default
- Notification ids are now unique across queue drains (process-lifetime monotonic counter)
- Notifications are deduplicated by id across push and poll, with a bounded seen-set and capped exponential-backoff WebSocket reconnect

### Fixed

- CLI no longer leaks the local server token to a remote `--url` (token scoped to loopback targets, sent via the Authorization header only, not the URL)
- Ingest server errors return a generic message instead of leaking internal detail
- Documentation corrections: removed the unenforced 140-character message limit, corrected the notification-type count, clarified the best-effort poll delivery contract

## 1.1.11

### Features

- Add auto-close checkbox with seconds input to notification dialog
- Add Send Notification command to command palette
- Add JupyterLab command for sending notifications
- Add input dialog for Send Notification command
- Enhance notification dialog with type selector and dismiss button option
- Add data field support (undocumented)
- Add screenshots for documentation

### Bug Fixes

- Use Dialog with Widget wrapper for proper form display
- Use sync fixture to clear notification store directly
- Add pytest fixture to clear notification store before each test

### Documentation

- Add release notes for version 1.1.8
- Clarify usage of native JupyterLab notification system
- Move screenshots to beginning with descriptive captions
- Update features list with dialog capabilities and technical details
- Add programmatic command usage examples to README
- Simplify and clarify feature list in README
- Remove references to users (notifications target JupyterLab server)
- Remove notebook JavaScript example (window.jupyterlab not available)
- Clarify action buttons are visual only and dismiss notifications
- Convert RELEASE.md to release notes format
- Add comprehensive API reference with complete parameter documentation

### Testing

- Add Playwright integration test for command palette and dialog
- Simplify tests by removing verbose comments and consolidating logic

### CI/CD

- Fix prettier formatting
- Add pytest-check-links-ignore file for unpublished package URLs
- Fix ignore_links syntax using multiline format
- Add comprehensive notification tests and finalize CI/CD workflows

## 1.0.19

### Features

- Implement external notification ingestion and display system
- Add token authentication and simplify notification architecture
- Support for five notification types (info, success, warning, error, in-progress)
- Configurable auto-close behavior
- Optional action buttons
- REST API endpoint for notification ingestion
- 30-second polling interval for delivery
- Test script with token auto-detection from environment variables

### Architecture

- In-memory notification queue cleared after fetch
- Backend: Python/Tornado async handlers
- Frontend: TypeScript polling with JupyterLab command integration
- Broadcast-only model

<!-- <END NEW CHANGELOG ENTRY> -->
