# Release Notes

## 1.1.11

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
