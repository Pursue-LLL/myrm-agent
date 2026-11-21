# macos_ax/

## Overview
macOS Accessibility backend of Semantic Desktop Control: an AppleScript (System Events) snapshot, an element invoke and a foreground probe. The package facade exports the four entry points the platform dispatcher (`perception/ax_dispatch.py`) calls.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Facade | Exports `capture_ax_snapshot`, `inspect_foreground`, `invoke_ax_element`, `read_foreground_meta` | ✅ |
| scripts.py | Core | The osascript text and how a script finds its process: snapshot script builder (whole app, query, role filter; a password field is resolved by its **subrole** before the `value` read), invoke script builder, application selector (bundle id for known apps, exact name with a contains fallback), element cap and role filter. Nothing here executes a process | ✅ |
| capture.py | Core | `capture_ax_snapshot` (targeted capture by app name, auto-restore of minimized windows, foreground fallback when the target is not found), `_run_ax_snapshot` (15 s timeout), `_parse_ax_output`, `MacAxSnapshot` | ✅ |
| invoke.py | Core | `invoke_ax_element`: one element action by the backend key a capture produced (10 s timeout). A failure carries its `AxFailure` class, taken from the AppleScript error number rather than the localized text (see `perception/_ARCH.md`) | ✅ |
| foreground.py | Core | `inspect_foreground` (frontmost app identity, readable-tree estimate, recommendation text), `read_foreground_meta` (single osascript read of the app name, window title and bundle id, with no tree walk and no window touched; the fallback of `inspect_foreground` and, through the dispatcher, the light read of the vision frame check), `_native_api_hint` + `_SCRIPTABLE_APPS` (AppleScript routing hint) | ✅ |

## Dependencies

- `computer_use/dref/` (POS: @dref types and AX errors)
- `computer_use/backends/macos/permissions.py` (POS: System Settings deep links injected into the permission error)
- `computer_use/perception/ax_result.py` (POS: `AxInvokeResult` and the `AxFailure` class of a failed action)
- Used by `perception/ax_dispatch.py` through the facade

## Architecture Overview

```
ax_dispatch ──▶ __init__ ──▶ capture.py ──▶ scripts.py
                         ├─▶ foreground.py ──▶ capture.py
                         └─▶ invoke.py ──▶ scripts.py
```

A collaborator is looked up in the module that calls it, so a test patches `...macos_ax.<module>.<name>`: `capture._run_ax_snapshot` (capture flow), `foreground.capture_ax_snapshot` and `foreground.read_foreground_meta` (foreground probe). `subprocess.run` is the standard-library function, patched as `subprocess.run`.

Parent: [perception/_ARCH.md](../_ARCH.md) · Detailed design: [DESKTOP_SYSTEM.md](../../DESKTOP_SYSTEM.md)
