"""Parallel caps: the single cap root and the pools derived from it."""

from __future__ import annotations

from typing import Final

# --- Parallel caps ---

# S2: single cap root — private credits, mux workers, and bootstrap slots derive here.
LIVE_SHPOIB_MAX_CONCURRENT: Final[int] = 4

DEFAULT_BOOTSTRAP_SLOTS: Final[int] = LIVE_SHPOIB_MAX_CONCURRENT
SHARED_BROWSER_WORKERS: Final[int] = LIVE_SHPOIB_MAX_CONCURRENT
MUX_COLD_ATTACH_SLOTS: Final[int] = SHARED_BROWSER_WORKERS

LIVE_SHARED_HOT_MAX_CONCURRENT: Final[int] = 1
