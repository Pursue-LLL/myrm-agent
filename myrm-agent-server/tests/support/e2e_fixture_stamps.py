"""Wall-clock stamps inside the live-E2E lease fixture, printed as one detach-log line."""

from __future__ import annotations

import time


class FixtureStamps:
    """Collect named wall-clock instants and emit them as one ``E2E_LEASE_FIXTURE_STAMPS`` line.

    One line (not one per stamp) keeps the detach log readable and lets the wait audit split the
    fixture's setup without pairing interleaved output. Stamp names are the contract with
    ``scripts/dev/e2e_wait_logs.py::FIXTURE_SPANS``; a test pins both sides.
    """

    def __init__(self) -> None:
        self._stamps: dict[str, float] = {}

    def mark(self, name: str) -> None:
        self._stamps[name] = time.time()

    def emit(self) -> None:
        body = " ".join(f"{name}={wall:.1f}" for name, wall in self._stamps.items())
        print(f"E2E_LEASE_FIXTURE_STAMPS: {body}", flush=True)
