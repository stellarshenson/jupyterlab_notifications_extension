# Changelog

All notable changes to this project will be documented in this file.

<!-- <START NEW CHANGELOG ENTRY> -->

## 1.1.8

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
