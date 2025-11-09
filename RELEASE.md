# Release Notes

## 1.0.19 (2025-11-09)

First release of JupyterLab Notifications Extension.

**Core Features:**

- External notification ingestion via REST API
- Broadcast notifications to all JupyterLab users
- 30-second polling interval for notification delivery
- Support for multiple notification types (info, success, warning, error, in-progress, default)
- Configurable auto-close behavior
- Optional action buttons with visual styling
- Test script with token auto-detection from environment variables

**API:**

- POST `/jupyterlab-notifications-extension/ingest` - Send notifications
- GET `/jupyterlab-notifications-extension/notifications` - Fetch pending notifications (internal)
- Authentication via `Authorization: token` header or `?token=` query parameter
- Plain text messages (max 140 characters per JupyterLab specification)

**Architecture:**

- In-memory notification queue (cleared after fetch)
- Backend: Python/Tornado async handlers
- Frontend: TypeScript polling with JupyterLab command integration
- No persistence - notifications exist only until delivered

**Testing:**

- Python test suite with pytest
- Test coverage for notification creation, fetching, queue clearing, and action buttons
- CI/CD via GitHub Actions

**Documentation:**

- Complete API reference with parameter tables
- Usage examples (Python script and cURL)
- Modus primaris documentation standards
