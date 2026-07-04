# browser_sessions/

## Overview

REST endpoints for managing saved browser login sessions (encrypted by SessionVault).
Lists session metadata, deletes individual sessions, and triggers expired session cleanup.
Never exposes raw storage_state (cookies/localStorage) — only metadata summaries.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package | Module entry — exports `router` | — |
| `router.py` | Core | REST endpoints for session CRUD + cleanup | ✅ |

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/browser/sessions` | List all saved sessions (metadata only) |
| DELETE | `/browser/sessions/{domain}` | Delete a specific saved session |
| POST | `/browser/sessions/cleanup` | Remove all expired sessions |

## Dependencies

- `app.core.security.browser_vault::get_global_session_vault` — global SessionVault singleton
- `myrm_agent_harness.toolkits.browser.session_vault::SessionVault` — encrypted session storage engine
