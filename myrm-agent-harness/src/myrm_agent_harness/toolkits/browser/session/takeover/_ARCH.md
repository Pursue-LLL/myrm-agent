# browser/session/takeover/

## Overview
Session-level half of the human-takeover fence. While a person drives the browser, every session call that acts on the page waits for them first; the tool gate (`tools/user_control_gate.py`) is the other half and vets a tool call once, before it starts. Whether a person drives is the process-wide `UserControl` (`utils/runtime/user_control.py`), which the session only consults. The session stays locked on timeout rather than act behind the person's back.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package | Public facade: `BrowserSessionTakeoverMixin`, `UserTakeoverTimeoutError`, `UserTakeoverDuringScriptError`. | ✅ |
| `mixin.py` | Core | `BrowserSessionTakeoverMixin._ensure_not_user_takeover`: waits while a person drives, hard-refuses past the timeout via `UserTakeoverTimeoutError`, and inside a running script raises `UserTakeoverDuringScriptError` once control changed hands since the script was planned (`plan_is_stale`). | ✅ |
| `errors.py` | Core | The two `BrowserError`s of the wait: `UserTakeoverTimeoutError` (a person kept the browser past the wait budget) and `UserTakeoverDuringScriptError` (a running script's next step comes after a person used the page it was planned against). Their text says what did not happen and what to do next. | ✅ |

## Key Dependencies

- `toolkits/browser/exceptions` (`BrowserError`)
- `toolkits/browser/session/session_host` (typed host contract of the session mixins)
- `utils/runtime/user_control` (process-wide human-control hold, wait budget, script pin)
