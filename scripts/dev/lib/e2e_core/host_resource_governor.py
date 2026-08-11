"""Host Resource Governor (P1): unified CPU/memory pressure → browser + PRIVATE credits."""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypedDict
from real_user_home import real_user_home

MAX_BROWSER_SLOTS = 4
MIN_BROWSER_SLOTS = 1
CPU_CRITICAL_MIN_BROWSER_SLOTS = 2

DOWNGRADE_LOAD_RATIO = 0.90
UPGRADE_LOAD_RATIO = 0.55
CRITICAL_LOAD_RATIO = 1.20

MEMORY_DOWNGRADE_BYTES = int(1.5 * 1024**3)
MEMORY_UPGRADE_BYTES = int(3.0 * 1024**3)
CRITICAL_MEMORY_BYTES = int(1.0 * 1024**3)

COOLDOWN_SEC = 30.0
TRANSITION_LOG_COMPACT_BYTES = 256 * 1024
TRANSITION_LOG_RETAIN_ROWS = 128


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


def _darwin_available_memory_bytes() -> int:
    """Return reclaimable macOS memory without spawning ``vm_stat`` per probe."""
    import ctypes

    class VmStatistics64(ctypes.Structure):
        _fields_ = [
            ("free_count", ctypes.c_uint32),
            ("active_count", ctypes.c_uint32),
            ("inactive_count", ctypes.c_uint32),
            ("wire_count", ctypes.c_uint32),
            ("zero_fill_count", ctypes.c_uint64),
            ("reactivations", ctypes.c_uint64),
            ("pageins", ctypes.c_uint64),
            ("pageouts", ctypes.c_uint64),
            ("faults", ctypes.c_uint64),
            ("cow_faults", ctypes.c_uint64),
            ("lookups", ctypes.c_uint64),
            ("hits", ctypes.c_uint64),
            ("purges", ctypes.c_uint64),
            ("purgeable_count", ctypes.c_uint32),
            ("speculative_count", ctypes.c_uint32),
            ("decompressions", ctypes.c_uint64),
            ("compressions", ctypes.c_uint64),
            ("swapins", ctypes.c_uint64),
            ("swapouts", ctypes.c_uint64),
            ("compressor_page_count", ctypes.c_uint32),
            ("throttled_count", ctypes.c_uint32),
            ("external_page_count", ctypes.c_uint32),
            ("internal_page_count", ctypes.c_uint32),
            ("total_uncompressed_pages_in_compressor", ctypes.c_uint64),
        ]

    libsystem = ctypes.CDLL("/usr/lib/libSystem.B.dylib")
    host = libsystem.mach_host_self()
    stats = VmStatistics64()
    count = ctypes.c_uint32(ctypes.sizeof(stats) // ctypes.sizeof(ctypes.c_uint32))
    kern_success = 0
    host_vm_info64 = 4
    result = libsystem.host_statistics64(
        host,
        host_vm_info64,
        ctypes.byref(stats),
        ctypes.byref(count),
    )
    if result != kern_success:
        return 0
    page_size = int(os.sysconf("SC_PAGE_SIZE"))
    available_pages = (
        int(stats.free_count)
        + int(stats.inactive_count)
        + int(stats.speculative_count)
        + int(stats.purgeable_count)
    )
    return available_pages * page_size


def _available_memory_bytes() -> int:
    if sys.platform == "darwin":
        try:
            return _darwin_available_memory_bytes()
        except (AttributeError, OSError, TypeError, ValueError):
            return 0
    try:
        return int(os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE"))
    except (AttributeError, OSError, TypeError, ValueError):
        return 0


def collect_host_pressure_snapshot(*, now: float | None = None) -> HostPressureSnapshot:
    captured_at = time.time() if now is None else now
    cpu_count = max(1, os.cpu_count() or 1)
    load_1m = 0.0
    load_5m = 0.0
    try:
        load_1m, _, load_5m = os.getloadavg()
    except (AttributeError, OSError):
        pass
    memory_available = _available_memory_bytes()
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


def _critical_browser_slot_floor(snapshot: HostPressureSnapshot) -> int:
    """CPU-only pressure keeps two I/O credits; critical memory may fall to one."""
    if 0 < snapshot.memory_available_bytes < CRITICAL_MEMORY_BYTES:
        return MIN_BROWSER_SLOTS
    return CPU_CRITICAL_MIN_BROWSER_SLOTS


def _transition_log_path() -> Path:
    override = os.getenv("MYRM_DEV_STATE_DIR", "").strip()
    base = Path(override) if override else real_user_home() / ".local/state/myrm-dev"
    return base / "host-governor-transitions.jsonl"


def _persist_transition(entry: dict[str, object]) -> None:
    path = _transition_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and path.stat().st_size > TRANSITION_LOG_COMPACT_BYTES:
        retained = path.read_text(encoding="utf-8").splitlines()[
            -TRANSITION_LOG_RETAIN_ROWS:
        ]
        path.write_text(
            "\n".join(retained) + ("\n" if retained else ""),
            encoding="utf-8",
        )
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
                target = _critical_browser_slot_floor(snapshot)
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


def _snapshot_effective_slots(snapshot: HostPressureSnapshot) -> int:
    override = _override_slots()
    if override is not None:
        return override
    if not _governor_enabled():
        return MAX_BROWSER_SLOTS
    load_ratio = snapshot.load_avg_1m / snapshot.cpu_count
    if load_ratio >= CRITICAL_LOAD_RATIO:
        return _critical_browser_slot_floor(snapshot)
    if 0 < snapshot.memory_available_bytes < CRITICAL_MEMORY_BYTES:
        return MIN_BROWSER_SLOTS
    with _lock:
        current = _state.effective_slots
    if _pressure_high(snapshot)[0]:
        return max(MIN_BROWSER_SLOTS, current - 1)
    return current


def host_resource_governor_snapshot(
    *, now: float | None = None
) -> HostGovernorSnapshot:
    captured_at = time.time() if now is None else now
    snapshot = collect_host_pressure_snapshot(now=captured_at)
    # Observability is read-only. Calling tick here made every short-lived
    # `e2e-context` process reset 4→1 and append another transition row.
    effective = _snapshot_effective_slots(snapshot)
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
