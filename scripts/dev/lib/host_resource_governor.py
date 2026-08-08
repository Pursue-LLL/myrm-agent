"""Host Resource Governor (P1): unified CPU/memory pressure → browser + PRIVATE credits."""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypedDict
from real_user_home import real_user_home

MAX_BROWSER_SLOTS = 4
MIN_BROWSER_SLOTS = 1

DOWNGRADE_LOAD_RATIO = 0.90
UPGRADE_LOAD_RATIO = 0.55
CRITICAL_LOAD_RATIO = 1.20

MEMORY_DOWNGRADE_BYTES = int(1.5 * 1024**3)
MEMORY_UPGRADE_BYTES = int(3.0 * 1024**3)
CRITICAL_MEMORY_BYTES = int(1.0 * 1024**3)

COOLDOWN_SEC = 30.0


class HostGovernorSnapshot(TypedDict, total=False):
    enabled: bool
    effective_browser_slots: int
    effective_private_capacity: int
    max_browser_slots: int
    load_avg_1m: float
    load_avg_5m: float
    cpu_count: int
    memory_available_bytes: int
    memory_pressure: str
    thermal: str
    last_change_reason: str
    last_change_at: float
    cooldown_remaining_sec: float


@dataclass(slots=True)
class HostPressureSnapshot:
    load_avg_1m: float
    load_avg_5m: float
    cpu_count: int
    memory_available_bytes: int
    thermal: str
    captured_at: float


@dataclass(slots=True)
class _GovernorState:
    effective_slots: int = MAX_BROWSER_SLOTS
    last_change_at: float = 0.0
    last_change_reason: str = "init"
    stable_low_since: float | None = None
    transition_log: list[dict[str, object]] = field(default_factory=list)


_lock = threading.Lock()
_state = _GovernorState()


def _governor_enabled() -> bool:
    return os.environ.get("MYRM_HOST_GOVERNOR", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _override_slots() -> int | None:
    raw = os.environ.get("MYRM_EFFECTIVE_BROWSER_SLOTS", "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return max(MIN_BROWSER_SLOTS, min(MAX_BROWSER_SLOTS, value))


def collect_host_pressure_snapshot(*, now: float | None = None) -> HostPressureSnapshot:
    captured_at = time.time() if now is None else now
    cpu_count = max(1, os.cpu_count() or 1)
    load_1m = 0.0
    load_5m = 0.0
    try:
        load_1m, _, load_5m = os.getloadavg()
    except (AttributeError, OSError):
        pass
    memory_available = 0
    try:
        memory_available = int(
            os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
        )
    except (OSError, ValueError):
        pass
    return HostPressureSnapshot(
        load_avg_1m=float(load_1m),
        load_avg_5m=float(load_5m),
        cpu_count=cpu_count,
        memory_available_bytes=memory_available,
        thermal="unavailable",
        captured_at=captured_at,
    )


def _memory_pressure_label(available_bytes: int) -> str:
    if available_bytes <= 0:
        return "unknown"
    if available_bytes < CRITICAL_MEMORY_BYTES:
        return "critical"
    if available_bytes < MEMORY_DOWNGRADE_BYTES:
        return "elevated"
    if available_bytes < MEMORY_UPGRADE_BYTES:
        return "moderate"
    return "low"


def _pressure_high(snapshot: HostPressureSnapshot) -> tuple[bool, str]:
    load_ratio = snapshot.load_avg_1m / snapshot.cpu_count
    if load_ratio >= CRITICAL_LOAD_RATIO:
        return True, f"load_critical ratio={load_ratio:.2f}"
    if load_ratio >= DOWNGRADE_LOAD_RATIO:
        return True, f"load_elevated ratio={load_ratio:.2f}"
    if (
        snapshot.memory_available_bytes > 0
        and snapshot.memory_available_bytes < MEMORY_DOWNGRADE_BYTES
    ):
        return True, f"memory_elevated bytes={snapshot.memory_available_bytes}"
    return False, ""


def _pressure_low(snapshot: HostPressureSnapshot) -> bool:
    load_ratio = snapshot.load_avg_1m / snapshot.cpu_count
    if load_ratio > UPGRADE_LOAD_RATIO:
        return False
    if snapshot.memory_available_bytes <= 0:
        return load_ratio <= UPGRADE_LOAD_RATIO * 0.5
    return snapshot.memory_available_bytes >= MEMORY_UPGRADE_BYTES


def _transition_log_path() -> Path:
    override = os.getenv("MYRM_DEV_STATE_DIR", "").strip()
    base = Path(override) if override else real_user_home() / ".local/state/myrm-dev"
    return base / "host-governor-transitions.jsonl"


def _persist_transition(entry: dict[str, object]) -> None:
    path = _transition_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def recent_transition_log(*, limit: int = 16) -> list[dict[str, object]]:
    capped = max(1, limit)
    rows = list(_state.transition_log[-capped:])
    path = _transition_log_path()
    if path.is_file():
        file_rows: list[dict[str, object]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                file_rows.append(payload)
        if len(file_rows) > capped:
            file_rows = file_rows[-capped:]
        if len(file_rows) > len(rows):
            rows = file_rows
    return rows[-capped:]


def _record_transition(
    *,
    before: int,
    after: int,
    reason: str,
    snapshot: HostPressureSnapshot,
    now: float,
) -> None:
    entry = {
        "before": before,
        "after": after,
        "reason": reason,
        "load_avg_1m": snapshot.load_avg_1m,
        "memory_available_bytes": snapshot.memory_available_bytes,
        "at": now,
    }
    _state.transition_log.append(entry)
    if len(_state.transition_log) > 32:
        _state.transition_log.pop(0)
    try:
        _persist_transition(entry)
    except OSError:
        pass


def tick_governor(*, now: float | None = None) -> int:
    """Evaluate pressure and adjust effective browser/PRIVATE slot cap (1–4)."""
    override = _override_slots()
    if override is not None:
        return override
    if not _governor_enabled():
        return MAX_BROWSER_SLOTS

    captured_at = time.time() if now is None else now
    snapshot = collect_host_pressure_snapshot(now=captured_at)
    with _lock:
        current = _state.effective_slots
        high, high_reason = _pressure_high(snapshot)
        if high:
            if snapshot.load_avg_1m / snapshot.cpu_count >= CRITICAL_LOAD_RATIO:
                target = MIN_BROWSER_SLOTS
                reason = high_reason
            elif current > MIN_BROWSER_SLOTS:
                target = current - 1
                reason = high_reason
            else:
                target = current
                reason = ""
            if target < current:
                _record_transition(
                    before=current,
                    after=target,
                    reason=reason,
                    snapshot=snapshot,
                    now=captured_at,
                )
                _state.effective_slots = target
                _state.last_change_at = captured_at
                _state.last_change_reason = reason
                _state.stable_low_since = None
            return _state.effective_slots

        if _pressure_low(snapshot):
            if _state.stable_low_since is None:
                _state.stable_low_since = captured_at
            elif (
                captured_at - _state.stable_low_since >= COOLDOWN_SEC
                and captured_at - _state.last_change_at >= COOLDOWN_SEC
                and current < MAX_BROWSER_SLOTS
            ):
                target = current + 1
                reason = "pressure_stable_upgrade"
                _record_transition(
                    before=current,
                    after=target,
                    reason=reason,
                    snapshot=snapshot,
                    now=captured_at,
                )
                _state.effective_slots = target
                _state.last_change_at = captured_at
                _state.last_change_reason = reason
                _state.stable_low_since = captured_at
        else:
            _state.stable_low_since = None
        return _state.effective_slots


def effective_browser_operation_credits() -> int:
    return tick_governor()


def effective_private_capacity_credits() -> int:
    """PRIVATE configured capacity uses the same pressure snapshot as browser dispatch."""
    return effective_browser_operation_credits()


def reset_governor_for_tests(*, slots: int = MAX_BROWSER_SLOTS) -> None:
    with _lock:
        _state.effective_slots = max(MIN_BROWSER_SLOTS, min(MAX_BROWSER_SLOTS, slots))
        _state.last_change_at = 0.0
        _state.last_change_reason = "test_reset"
        _state.stable_low_since = None
        _state.transition_log.clear()


def host_resource_governor_snapshot(
    *, now: float | None = None
) -> HostGovernorSnapshot:
    captured_at = time.time() if now is None else now
    snapshot = collect_host_pressure_snapshot(now=captured_at)
    effective = tick_governor(now=captured_at)
    with _lock:
        last_change_at = _state.last_change_at
        last_reason = _state.last_change_reason
    cooldown_remaining = max(
        0.0,
        COOLDOWN_SEC - (captured_at - last_change_at),
    )
    return HostGovernorSnapshot(
        enabled=_governor_enabled() and _override_slots() is None,
        effective_browser_slots=effective,
        effective_private_capacity=effective,
        max_browser_slots=MAX_BROWSER_SLOTS,
        load_avg_1m=snapshot.load_avg_1m,
        load_avg_5m=snapshot.load_avg_5m,
        cpu_count=snapshot.cpu_count,
        memory_available_bytes=snapshot.memory_available_bytes,
        memory_pressure=_memory_pressure_label(snapshot.memory_available_bytes),
        thermal=snapshot.thermal,
        last_change_reason=last_reason,
        last_change_at=last_change_at,
        cooldown_remaining_sec=cooldown_remaining,
    )
