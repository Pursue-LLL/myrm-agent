# computer_use/dref/

## Overview

Internal @dref element reference types and session-scoped registry for semantic desktop control.
Owned by `computer_use/` — not a standalone toolkit.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| types.py | Core | ElementRef, BBox, SnapshotMeta (`same_app`: same application name and process), SnapshotScope | ✅ |
| registry.py | Core | DRefRegistry session-scoped ref map. `adopt` makes a capture the registry content and issues the ids: they only grow, a retired id is never reused (the counter survives `clear`), and an element keeps its id across captures only inside the same application and when its non-empty (role, name) is unique on both sides. `normalize`/`get` resolve a model-supplied reference (`@d3`, `d3`, `3`); an unknown id raises `DRefStaleError` | ✅ |
| errors.py | Core | DRefStaleError, AXPermissionRequiredError (retryable message + `ACCESSIBILITY_SETTINGS_DEEPLINK`), AXTreeEmptyError | ✅ |
| __init__.py | Package | Public exports | ✅ |

## Consumers

- `computer_use/desktop_session/`
- `computer_use/perception/*`
- `computer_use/execution/healer.py`
