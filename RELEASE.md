# Release Notes

## 1.1.8 (2025-11-09)

Major feature release adding command palette integration with interactive dialog.

**New Features:**
- Command palette integration with "Send Notification" command
- Interactive dialog with form controls (message input, type selector, auto-close timing, action buttons)
- Auto-close checkbox with configurable seconds input (converts to milliseconds)
- Dismiss button toggle in dialog
- Programmatic command API (`jupyterlab-notifications:send`) for extensions
- Playwright integration test for command and dialog

**Improvements:**
- Enhanced README with screenshots showing notification types, command palette, and dialog
- Documentation clarifies use of native JupyterLab notification system
- Simplified test suite with proper isolation using pytest fixtures
- Prettier formatting enforcement in CI/CD

**Technical Details:**
- Dialog implementation using `@jupyterlab/apputils` Dialog class with Widget wrapper
- Command registered with ICommandPalette dependency
- Form elements dynamically created and managed in TypeScript
- Auto-close timing converted from seconds to milliseconds on submit

## 1.0.19 (2025-11-09)

Initial release of JupyterLab Notifications Extension.

**Core Features:**
- REST API endpoint for external notification ingestion
- Broadcast notifications to JupyterLab server
- 30-second polling interval for delivery
- Five notification types with visual styling (info, success, warning, error, in-progress)
- Configurable auto-close behavior (milliseconds or false)
- Optional action buttons
- Token authentication via header or query parameter
- Python test script with environment variable token detection

**API:**
- POST `/jupyterlab-notifications-extension/ingest` - Send notifications
- GET `/jupyterlab-notifications-extension/notifications` - Fetch pending (internal)
- Plain text messages (max 140 characters per JupyterLab spec)

**Architecture:**
- In-memory notification queue cleared after fetch
- Backend: Python/Tornado async handlers
- Frontend: TypeScript polling with JupyterLab command integration
- No persistence

**Testing:**
- Python test suite with pytest
- CI/CD via GitHub Actions
- Test coverage for creation, fetching, queue clearing, action buttons
