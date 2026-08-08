"""Real login user home resolution for dev tooling.

Bypasses sandboxed HOME (e.g. Cursor's ~/.cursor2) so that dev state, logs,
and harness data always land on the real user's data directory instead of
splitting across sandboxed and real homes.
"""

from __future__ import annotations

import os
from pathlib import Path


def real_user_home() -> Path:
    """Resolve the real login user's home directory.

    Honors MYRM_REAL_HOME for tests/CI overrides. Falls back to pwd, then to
    Path.home() when the platform has no pwd module (e.g. Windows).
    """
    override = os.environ.get("MYRM_REAL_HOME", "").strip()
    if override:
        return Path(override).resolve()
    try:
        import pwd

        return Path(pwd.getpwuid(os.getuid()).pw_dir)
    except (ImportError, KeyError, OSError):
        return Path.home()
