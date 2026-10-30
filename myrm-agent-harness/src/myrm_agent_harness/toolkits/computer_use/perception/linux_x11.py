"""Active X11 window identity — application name, title and process id without AT-SPI.

[INPUT]
- None (xdotool / xprop subprocesses only)

[OUTPUT]
- read_foreground_meta: (application name, window title) of the active window
- foreground_pid: process id owning the active window

[POS]
Foreground-identity primitive for Linux accessibility perception. AT-SPI lists every running application, so
the application in front is named by the window manager's active window instead. Every query is bounded and
returns empty when the helper tool is missing, times out or fails.
"""

from __future__ import annotations

import re
import subprocess

# One X11 query must not stall the safety check that depends on it.
_QUERY_TIMEOUT_S = 2
_QUOTED_STRING = re.compile(r'"([^"]*)"')


def _query(argv: list[str]) -> str:
    """Stdout of one X11 helper command; empty when the tool is missing, times out or fails."""
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=_QUERY_TIMEOUT_S, check=False)
    except (subprocess.TimeoutExpired, OSError):
        return ""
    return proc.stdout.strip() if proc.returncode == 0 else ""


def read_foreground_meta() -> tuple[str, str]:
    """(application name, window title) of the active X11 window.

    The application name is the window's WM_CLASS class. Either field is empty when it cannot be read.
    """
    win_id = _query(["xdotool", "getactivewindow"])
    if not win_id:
        return "", ""
    title = _query(["xdotool", "getwindowname", win_id])
    # xprop prints: WM_CLASS(STRING) = "instance", "Class"
    quoted = _QUOTED_STRING.findall(_query(["xprop", "-id", win_id, "WM_CLASS"]))
    return (quoted[-1] if quoted else ""), title


def foreground_pid() -> int | None:
    """Process id owning the active X11 window; None when it cannot be read."""
    out = _query(["xdotool", "getactivewindow", "getwindowpid"])
    return int(out) if out.isdigit() and int(out) > 0 else None
