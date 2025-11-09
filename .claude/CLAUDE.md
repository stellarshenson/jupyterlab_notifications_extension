<!-- Import workspace-level CLAUDE.md configuration -->
<!-- See /home/lab/workspace/.claude/CLAUDE.md for complete rules -->

# Project-Specific Configuration

This file extends workspace-level configuration with project-specific rules.

## Project Context

**jupyterlab_notifications_extension** is a JupyterLab extension providing notification display capabilities in the main panel. Notifications can originate from JupyterHub administrators or other sources.

**Architecture**:

- Dual-component extension: Python server backend + TypeScript/React frontend
- Server extension provides REST API routes for notification management
- Frontend extension renders notifications in JupyterLab UI

**Technology Stack**:

- **Python**: >= 3.9, jupyter_server >= 2.4.0
- **TypeScript**: 5.8.0
- **React**: 18.0.26
- **JupyterLab**: >= 4.0.0
- **Build**: Hatchling (Python), JupyterLab builder (frontend)
- **Testing**: pytest (Python), Jest (JavaScript), Playwright (integration)

**Development Workflow**:

- Use `jlpm` (JupyterLab's pinned yarn) for NPM operations
- Frontend changes require rebuild: `jlpm build` or `jlpm watch` for auto-rebuild
- Development mode: `jupyter labextension develop . --overwrite`
- Server extension must be manually enabled: `jupyter server extension enable jupyterlab_notifications_extension`

**Naming Conventions**:

- Python package: `jupyterlab_notifications_extension` (snake_case)
- NPM package: `jupyterlab_notifications_extension` (matches Python)
- Module structure follows JupyterLab extension conventions

**Testing Requirements**:

- Python: `pytest -vv -r ap --cov jupyterlab_notifications_extension`
- JavaScript: `jlpm test`
- Integration: Playwright tests in `ui-tests/`

**Build Outputs**:

- Frontend labextension: `jupyterlab_notifications_extension/labextension/`
- Compiled TypeScript: `lib/`
- Distribution packages: wheel and sdist via hatchling
