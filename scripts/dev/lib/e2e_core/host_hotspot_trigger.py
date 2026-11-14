"""When to capture a hotspot, and the sample-source wrapper that does it.

[INPUT]
- LoadSample rows from host_load_sampler (CPU idle, per-role footprint, kernel pressure level)
- host_hotspot_capture.capture_hotspot (the per-process capture)
- host_load_store (hotspot files under dev_state_dir)

[OUTPUT]
- SampleSource: anything with ``sample() -> LoadSample | None``
- HotspotTrigger.reasons(sample) -> list[str]: why a capture is due, [] when none is
- HotspotRecorder: a SampleSource that passes samples through and stores a hotspot on a trigger

[POS]
A calm tick compares the sample against two thresholds and the last few minutes of per-role
footprints; the process table is read only when a reason holds, at most once per cooldown.
Reasons: ``cpu_saturated`` (idle at or below SATURATED_IDLE_PCT: almost no spare CPU),
``memory_pressure`` (kernel level warn or worse) and ``memory_surge:<role>`` (a role's
footprint rose by SURGE_MB or more within SURGE_WINDOW_SEC). The capture is an
optional extra on the primary recording: whatever goes wrong in it is logged with its
traceback, and the wrapped source's sample is returned either way.
"""

from __future__ import annotations

import logging
from collections import deque
from collections.abc import Callable, Sequence
from datetime import date
from pathlib import Path
from typing import Final, Protocol

from e2e_core.host_hotspot_capture import (
    HostContext,
    Hotspot,
    capture_hotspot,
)
from e2e_core.host_load_sampler import LoadSample
from e2e_core.host_load_store import append_hotspot, prune_expired_hotspots
from e2e_core.host_vm_stats import PRESSURE_WARN

SATURATED_IDLE_PCT: Final = 15.0
SURGE_MB: Final = 4096
SURGE_WINDOW_SEC: Final = 600.0
COOLDOWN_SEC: Final = 300.0

logger = logging.getLogger(__name__)

Capture = Callable[[float, Sequence[str], HostContext], Hotspot]


class SampleSource(Protocol):
    def sample(self) -> LoadSample | None: ...


class HotspotTrigger:
    """Stateful: surge detection needs the footprints of the last few minutes."""

    def __init__(
        self,
        *,
        saturated_idle_pct: float = SATURATED_IDLE_PCT,
        surge_mb: int = SURGE_MB,
        surge_window_sec: float = SURGE_WINDOW_SEC,
        cooldown_sec: float = COOLDOWN_SEC,
    ) -> None:
        self._saturated_idle_pct = saturated_idle_pct
        self._surge_mb = surge_mb
        self._surge_window_sec = surge_window_sec
        self._cooldown_sec = cooldown_sec
        self._history: deque[tuple[float, dict[str, int]]] = deque()
        self._last_fired: float | None = None

    def reasons(self, sample: LoadSample) -> list[str]:
        """Reasons to capture now; empty when the host is fine or a capture was just taken."""
        ts = sample["ts"]
        footprints = {
            role: stat["foot_mb"]
            for role, stat in sample["roles"].items()
            if "foot_mb" in stat
        }
        found: list[str] = []
        if sample["cpu_idle"] <= self._saturated_idle_pct:
            found.append("cpu_saturated")
        vm = sample.get("vm")
        if vm is not None and vm["pressure"] >= PRESSURE_WARN:
            found.append("memory_pressure")
        found.extend(
            f"memory_surge:{role}" for role in sorted(self._surged(ts, footprints))
        )
        self._remember(ts, footprints)
        if not found or self._cooling(ts):
            return []
        self._last_fired = ts
        return found

    def _cooling(self, ts: float) -> bool:
        if self._last_fired is None:
            return False
        # A negative gap means the wall clock moved back: do not stay silent until it catches up.
        return 0 <= ts - self._last_fired < self._cooldown_sec

    def _surged(self, ts: float, footprints: dict[str, int]) -> set[str]:
        surged: set[str] = set()
        for role, size in footprints.items():
            earlier = [
                seen[role]
                for at, seen in self._history
                if role in seen and 0 <= ts - at <= self._surge_window_sec
            ]
            if earlier and size - min(earlier) >= self._surge_mb:
                surged.add(role)
        return surged

    def _remember(self, ts: float, footprints: dict[str, int]) -> None:
        if self._history and ts < self._history[-1][0]:
            self._history.clear()
        self._history.append((ts, footprints))
        while ts - self._history[0][0] > self._surge_window_sec:
            self._history.popleft()


def _context(sample: LoadSample) -> HostContext:
    vm = sample.get("vm")
    return HostContext(
        load1=sample["load1"],
        cpu_idle=sample["cpu_idle"],
        mem_avail_mb=sample["mem_avail_mb"],
        pressure=vm["pressure"] if vm is not None else None,
    )


class HotspotRecorder:
    """Wraps a sample source; stores a hotspot beside the sample when the trigger fires."""

    def __init__(
        self,
        source: SampleSource,
        directory: Path,
        *,
        trigger: HotspotTrigger | None = None,
        capture: Capture = capture_hotspot,
    ) -> None:
        self._source = source
        self._directory = directory
        self._trigger = trigger or HotspotTrigger()
        self._capture = capture

    def sample(self) -> LoadSample | None:
        sample = self._source.sample()
        if sample is not None:
            self._record(sample)
        return sample

    def _record(self, sample: LoadSample) -> None:
        try:
            reasons = self._trigger.reasons(sample)
            if not reasons:
                return
            hotspot = self._capture(sample["ts"], reasons, _context(sample))
            append_hotspot(self._directory, hotspot)
        except Exception:
            # An extra must never stop the primary recording; the traceback keeps bugs visible.
            logger.warning("Hotspot capture skipped", exc_info=True)

    def prune_expired(self, today: date) -> int:
        return prune_expired_hotspots(self._directory, today=today)
