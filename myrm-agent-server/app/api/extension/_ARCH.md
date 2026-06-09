# api/extension/

## Overview
Browser Extension Bridge API. WebSocket endpoint for extension connection + REST APIs for domain authorization management.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Exports router and ws_router | ✅ |
| router.py | Core | WebSocket endpoint for extension connection, REST endpoints for status/domains/tabs/disconnect | ✅ |

## Key Dependencies

- `app.services.extension.bridge`
- `app.config.settings`
