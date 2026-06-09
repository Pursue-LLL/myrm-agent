# services/extension/

## Overview
Browser Extension Bridge service. Manages WebSocket connection from the official browser extension (Chrome/Edge MV3), providing CDP proxy capabilities for Agent browser automation tasks.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Exports ExtensionBridgeService | ✅ |
| bridge.py | Core | WebSocket connection lifecycle, heartbeat, CDP proxy, domain authorization. Implements harness ExtensionBridge Protocol. | ✅ |

## Key Design Decisions

- **Playwright singleton**: `_ensure_playwright()` caches a single Playwright instance across all CDP connections, stopping it only on `disconnect()`. Avoids memory leaks from spawning a new process per connection.
- **Wildcard domain matching**: `_match_domain()` uses `fnmatch` for `*.example.com` patterns. Both `connect_to_domain()` and `list_tabs()` route through this method.
- **Auth token**: Validated against `settings.extension_auth_token` (SecretStr) in the WS endpoint.

## Key Dependencies

- `myrm_agent_harness.toolkits.browser.pool.extension_bridge` (Protocol contract)
- `myrm_agent_harness.toolkits.browser.pool.browser_launcher` (BrowserInstance)
- `starlette.websockets`
- `patchright.async_api`
- `fnmatch` (stdlib, wildcard domain matching)
