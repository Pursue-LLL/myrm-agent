"""Shared LIVE chrome_e2e flow utilities."""

from __future__ import annotations

import sys
import time


class FlowLogger:
    """Structured progress log for LIVE chrome_e2e flows."""

    def __init__(self, *, prefix: str = "E2E_LIVE_FLOW") -> None:
        self._prefix = prefix
        self._t0 = time.monotonic()

    def emit(self, msg: str) -> None:
        elapsed = time.monotonic() - self._t0
        line = f"{self._prefix}: [{elapsed:.1f}s] {msg}"
        # stderr, not stdout: pytest captures stdout and replays it only for
        # *failing* tests, so a passing run's takeover evidence (gate confirmed,
        # banner appeared, DONE) was invisible in the detach log — the exact
        # artifact an operator reads to judge a green run. stderr reaches the
        # log live regardless of outcome, matching the session-phase markers in
        # `e2e_session_runtime/lifecycle.py` that make the rest of the flow
        # auditable. Keep flush so the ordering is real, not buffered.
        print(line, file=sys.stderr, flush=True)
