# perception/

## Overview
Platform AX/UIA/AT-SPI snapshot capture, tree rendering, incremental diff, element invoke dispatch, and native API routing hints for Semantic Desktop Control.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Platform AX/UIA/AT-SPI perception package | — |
| ax_dispatch.py | Core | Platform routing: capture_snapshot, inspect_backend, invoke_element (a platform without an AX route answers UNSUPPORTED); `run_ax_call` awaits any of them (and the iPhone Mirroring probe) on a worker thread for the macOS backend so an osascript wait never freezes the event loop, and inline for the other platforms; `read_foreground_identity` is the light foreground read (name, window title, app id) of the vision frame check: `macos_ax.read_foreground_meta` on macOS and `linux_x11.read_foreground_meta` on Linux, each on a worker thread, blank on Windows and any other platform | ✅ |
| ax_result.py | Core | `AxInvokeResult`: the `ActionResult` of a native action, which on failure carries an `AxFailure` saying what it proves about delivery. `UNSUPPORTED`: the native route cannot do it and nothing reached the element, so a coordinate click is allowed; `STALE`: the element or its window is gone or changed, so its old coordinates may belong to something else; `UNKNOWN`: the action may have been delivered | ✅ |
| ax_diff.py | Core | Incremental AX tree diff producing `RefDiff`. `diff_adopted` compares the content the model was last shown with the newly adopted one, where an id present on both sides is the same element (new / changed / retired by id), with a 3-layer full-view fallback (first snapshot / app change / high change ratio). `compute_ref_diff` compares two raw captures, whose ids carry no identity, via (role, name) matching + bbox proximity, with a 4-layer fallback (adds low identity confidence); the skill recorder uses it | ✅ |
| overlay_roles.py | Core | Cross-platform overlay role SSOT for SOM + Inspector | ✅ |
| renderer.py | Core | AX tree text rendering: `render_snapshot_tree` (full) + `render_diff_tree` (incremental diff with +/~/- markers; states that the ids it does not list are still valid and that a removed id is no longer valid); optional `[N]` SOM line prefixes | ✅ |
| macos_ax/ | Platform | macOS Accessibility API snapshot + invoke + native API routing hints (package; see its `_ARCH.md`); targeted capture by app name (exact name with contains fallback, auto-restores minimized windows, bypasses frontmost; not found falls back to foreground with `scope` reflecting `foreground`). A password field is identified by its **subrole** (`AXSecureTextField`) and its `value` is never read | ✅ |
| windows_ax.py | Platform | Windows UI Automation snapshot + invoke (pattern actions delegated to `windows_ax_actions`; a missing target window or a stale index is STALE, a missing library or an unsupported action UNSUPPORTED, an exception raised during the action UNKNOWN) + COM/PowerShell routing hints; targeted capture by process name via shared `_locate_window` with auto-restore of minimized windows and rendering settle wait (capture and invoke reuse it for index consistency). A password edit (`IsPassword`) skips the ValuePattern read and is reported as `PasswordBox`. The snapshot `app_id` (`win:<exe>`, the stable trust key) and the process-name window match both resolve the executable through `windows_process` | ✅ |
| windows_ax_actions.py | Platform | UIA actions on one element: `apply_uia_toggle` (**idempotent** `check`/`uncheck` via ToggleState; `toggle` always flips), `apply_uia_expand_collapse`, `apply_uia_invoke` (each falls back to Click when the control lacks the pattern), `send_uia_text` (SendKeys with `{` and `}` escaped, so the value is typed literally instead of read as key names) | ✅ |
| windows_process.py | Platform | `process_name_by_pid`: executable file name of a process id via Win32 `OpenProcess` + `QueryFullProcessImageNameW` (UI Automation has no pid-to-name lookup); declares ctypes prototypes so the 64-bit HANDLE is not truncated; returns `""` for protected processes and non-Windows platforms | ✅ |
| linux_ax.py | Platform | Linux AT-SPI snapshot + invoke (pyatspi doAction/EditableText/grabFocus; supports toggle/expand/invoke actions; a fill on an element without EditableText fails as unsupported so the caller's coordinate fallback clicks it and types through the backend) + D-Bus routing hints; one traversal (`_iter_interactive`) orders the interactive elements for both snapshot and invoke, and a `backend_key` is `<application>@<pid>:<ordinal>` (ordinal counted per application instance, i.e. per name and process, before any query/role filter; the pid is empty when AT-SPI cannot report it), so an invoke needs neither a name nor the focus to be where the snapshot was, and while the pid is readable never reaches another process of the same program (instances whose pid is unreadable share one ordinal space, which the role/name check below guards); invoke also requires the element found at that position to keep the snapshot's role and name, otherwise it fails as stale and the caller does not click the old coordinates; the foreground snapshot lists the application owning the active window (matched by process id) and every application when no process matches (logged at debug level); the foreground application is named by the active X11 window (see `linux_x11.py`), never by AT-SPI, which lists every running application; with an empty AT-SPI tree `inspect_foreground` still returns that name, so the sensitive-app guard always sees the application in front | ✅ |
| linux_x11.py | Platform | Active X11 window identity without AT-SPI: `read_foreground_meta` (WM_CLASS class and title via xdotool / xprop) and `foreground_pid` (xdotool); each query is bounded by a 2 s timeout and yields empty when the tool is missing, times out or fails; `read_foreground_meta` is also the Linux route of the dispatcher's `read_foreground_identity` | ✅ |

## Dependencies

- `computer_use/dref/types.py` (POS: @dref types)
- `computer_use/backends/protocols.py` (POS: ComputerBackend protocol)
- Used by `desktop_session/` (POS: semantic desktop orchestrator; `snapshot.py`, `interact.py`, `vision.py`, `views.py`, `guards.py` call into this package)

## Key Design: Incremental AX Tree Diff

`ax_diff.py` re-sends only the added, updated and removed refs in continuous-interact scenarios instead of the whole tree.
When `desktop_interact` completes, the follow-up snapshot compares what the model was last shown with the new capture
via `diff_adopted`; the registry has already given every element that is the same one its old id, so the comparison is
by id. If the diff is reliable (same app, low change ratio), only changed entries (+added, ~updated, -removed) are
rendered to the agent context, together with the statement that every unlisted id is still valid. Three fallback
conditions automatically revert to full-tree rendering. `compute_ref_diff` serves captures that have no stable ids
(the skill recorder) and keeps matching by (role, name) and position.

## Key Design: Secure Field Redaction

Every platform resolver identifies a password field from the platform's own marker and **skips the value read entirely**, rather than masking a value that was already read into the process:

- macOS: role is `AXTextField`; only the **subrole** (`AXSecureTextField`) distinguishes it, so the AppleScript resolves the subrole before the `value` read.
- Windows: UIA exposes `IsPassword` on the edit control; the `ValuePattern` read is skipped.
- Linux: `_INTERACTIVE_ROLES` contains no password role (AT-SPI's password role is absent from the set), so the field is excluded from the snapshot; the collector reads no widget content for any role either.

The resolved role is reported as `AXSecureTextField` / `PasswordBox`, which `dref.types.is_secure_role` recognises. This matters twice over: it keeps the secret out of the model context (the renderer prints `value`), and it closes the `ElementRef.name or value` fallback, which would otherwise leak the secret through the element name.

## Key Design: Failure Classes of a Native Action

A native action that did not succeed reports what it proves about delivery (`ax_result.AxFailure`), and `desktop_interact` acts on that class alone:

- `UNSUPPORTED`: the native route cannot do it and nothing reached the element (no permission, no such action, no editable text). The element is where the snapshot put it, so the caller may click its coordinates.
- `STALE`: the element or its window is gone or changed (target window not found, index out of range, a different role or name at that position). Its old coordinates may belong to something else now, so nothing is clicked and the model is told to read the screen again.
- `UNKNOWN`: the action may have been delivered (timeout, a killed or crashed script, an exception during the action, an answer nobody expects). It is neither retried nor clicked, because repeating it could duplicate its effect; the model is told to look at the screen first.

macOS classifies by the AppleScript error number, because the message text is localized: `-1728` and `-1719` (the object or the list index does not exist) are STALE, `-25211` and `-1743` (no assistive access, Apple events not authorized) are UNSUPPORTED. Any other failed fill is UNSUPPORTED, since a value that could not be set was not set; any other failed click is UNKNOWN, because the script's second attempt clicks the element's position.

## Key Design: Native API Routing Hints

Each platform's `inspect_foreground()` builds the `recommendation` field from `_SNAPSHOT_RECOMMENDATION_BASE` (snapshot-first workflow plus `scope='target'` guidance for acting on a background app) and appends a routing hint when the frontmost app supports native automation (AppleScript/COM/D-Bus). The routing hint guides the Agent to prefer `bash_code_execute_tool` with native scripts for data retrieval or bulk actions — faster and more reliable than GUI interaction — without adding new tools or breaking prompt cache.

## Architecture Overview

Detailed design: [DESKTOP_SYSTEM.md](../DESKTOP_SYSTEM.md)
