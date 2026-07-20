"""Shared helpers for desktop control approval Chrome E2E tests."""

from __future__ import annotations

import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parents[4] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))
