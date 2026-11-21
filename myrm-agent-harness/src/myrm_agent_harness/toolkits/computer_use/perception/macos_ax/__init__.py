"""macOS accessibility tree capture and invoke via AppleScript.

[INPUT]
- .capture::capture_ax_snapshot
- .foreground::inspect_foreground, read_foreground_meta
- .invoke::invoke_ax_element

[OUTPUT]
- capture_ax_snapshot: AX tree capture with targeted app support, auto-unminimize and foreground fallback
- invoke_ax_element: AX element invocation with targeted app support
- inspect_foreground: frontmost app metadata and native API routing hints
- read_foreground_meta: the frontmost app's name, window title and bundle id from one osascript read, without walking the tree

[POS]
Facade of the macOS AX backend; the platform dispatcher calls these four entry points.
"""

from __future__ import annotations

from .capture import capture_ax_snapshot
from .foreground import inspect_foreground, read_foreground_meta
from .invoke import invoke_ax_element

__all__ = ["capture_ax_snapshot", "inspect_foreground", "invoke_ax_element", "read_foreground_meta"]
