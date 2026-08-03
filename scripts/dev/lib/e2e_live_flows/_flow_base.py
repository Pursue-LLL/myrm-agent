"""Shared LIVE chrome_e2e flow utilities."""

from __future__ import annotations

import time


class FlowLogger:
    """Structured progress log for LIVE chrome_e2e flows."""

    def __init__(self, *, prefix: str = "E2E_LIVE_FLOW") -> None:
        self._prefix = prefix
        self._t0 = time.monotonic()

    def emit(self, msg: str) -> None:
        elapsed = time.monotonic() - self._t0
        line = f"{self._prefix}: [{elapsed:.1f}s] {msg}"
        print(line, flush=True)
