# Changelog

All notable changes to this project will be documented in this file.

<!-- <START NEW CHANGELOG ENTRY> -->

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
