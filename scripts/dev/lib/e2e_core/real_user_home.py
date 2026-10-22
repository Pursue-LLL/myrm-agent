"""Real login user home resolution for dev tooling.

Bypasses sandboxed HOME (e.g. Cursor's ~/.cursor-3) so that dev state, logs,
and harness data always land on the real user's data directory instead of
splitting across sandboxed and real homes.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

_CURSOR_SANDBOX_SEGMENT_RE = re.compile(r"^\.?cursor(?:-[^/]+)?$", re.IGNORECASE)


def is_cursor_sandbox_path(path: Path | str) -> bool:
    """Return True when any path segment is a Cursor sandbox directory (.cursor, .cursor-3, .cursor-latest, etc.)."""
    p = path if isinstance(path, Path) else Path(path)
    return any(_CURSOR_SANDBOX_SEGMENT_RE.match(part) is not None for part in p.parts)


def real_user_home() -> Path:
    """Resolve the real login user's home directory.

    Honors MYRM_REAL_HOME for tests/CI overrides. Falls back to non-sandboxed HOME,
    then pwd, then Path.home() when the platform has no pwd module (e.g. Windows).
    """
    override = os.environ.get("MYRM_REAL_HOME", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    env_home = os.environ.get("HOME", "").strip()
    if env_home and not is_cursor_sandbox_path(env_home):
        return Path(env_home).expanduser().resolve()
    try:
        import pwd

        return Path(pwd.getpwuid(os.getuid()).pw_dir).resolve()
    except (ImportError, KeyError, OSError):
        return Path.home().expanduser().resolve()
