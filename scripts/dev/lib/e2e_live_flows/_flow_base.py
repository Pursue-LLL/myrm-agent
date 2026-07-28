"""Shared LIVE chrome_e2e flow utilities."""

from __future__ import annotations

import time

from e2e_signoff_trace import signoff_trace_emit


class FlowLogger:
    """Structured progress log — mirrors to signoff trace (R97/R98)."""

    def __init__(self, *, prefix: str = "E2E_LIVE_FLOW") -> None:
        self._prefix = prefix
        self._t0 = time.monotonic()

    def emit(self, msg: str) -> None:
        elapsed = time.monotonic() - self._t0
        line = f"{self._prefix}: [{elapsed:.1f}s] {msg}"
        print(line, flush=True)
        signoff_trace_emit(line)
