"""macOS accessibility tree capture and invoke via AppleScript.

[INPUT]
- .capture::capture_ax_snapshot
- .foreground::inspect_foreground
- .invoke::invoke_ax_element

[OUTPUT]
- capture_ax_snapshot: AX tree capture with targeted app support, auto-unminimize and foreground fallback
- invoke_ax_element: AX element invocation with targeted app support
- inspect_foreground: frontmost app metadata and native API routing hints

[POS]
Facade of the macOS AX backend; the platform dispatcher calls these three entry points.
"""

from __future__ import annotations

from .capture import capture_ax_snapshot
from .foreground import inspect_foreground
from .invoke import invoke_ax_element

__all__ = ["capture_ax_snapshot", "inspect_foreground", "invoke_ax_element"]
