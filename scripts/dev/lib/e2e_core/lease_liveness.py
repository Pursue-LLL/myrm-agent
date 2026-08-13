"""Wave lease liveness SSOT for `./myrm e2e-context` (R74-OBS-3/4).

[INPUT]
- wave_orchestrator.core.wave_status (POS: active lease records)
- wave_orchestrator.lease_state.owner_bashpid_from_agent_id / _process_is_alive
- parallel snapshot active_tests[] (pytest pid + test_id)

[OUTPUT]
- load_wave_snapshot(), wave_lease_counts(), build_lease_liveness()
- format_lease_liveness_human() → E2E_LEASE_LIVENESS lines
- WaveLeaseCounts.effective_* root-lease cap semantics (excludes parentLeaseId children)

[POS]
Single wave state read for cap headroom + liveness; replaces duplicate subprocess counts.
"""

from __future__ import annotations

import subprocess
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from dev_gate.contract import STALL_PROGRESS_SEC

LIVE_E2E_SHARED_HOT_NAMESPACE = "e2e:shared_hot"
PRIVATE_BACKEND_NAMESPACE_PREFIX = "e2e:private:"


def _lease_parent_id(item: dict[str, object]) -> str | None:
    parent = item.get("parentLeaseId")
    if isinstance(parent, str) and parent.strip():
        return parent.strip()
    return None


def _lease_is_root(item: dict[str, object]) -> bool:
    return _lease_parent_id(item) is None


def is_private_backend_lease(item: dict[str, object]) -> bool:
    """Return whether a wave lease belongs to an isolated PRIVATE backend."""
    namespace = str(item.get("namespace", "")).strip()
    return namespace.startswith(PRIVATE_BACKEND_NAMESPACE_PREFIX)


def shared_effective_lease_count(snapshot: dict[str, object]) -> int:
    """Count root leases that can mutate or pin the shared backend stack.

    PRIVATE sessions keep their wave lease for ownership and cleanup, but their
    isolated backend must not defer shared epoch promotion or shared-backend
    crash healing.
    """
    raw_leases = snapshot.get("activeLeases")
    if not isinstance(raw_leases, list):
        return 0
    return sum(
        1
        for item in raw_leases
        if isinstance(item, dict)
        and _lease_is_root(item)
        and not is_private_backend_lease(item)
    )


@dataclass(frozen=True, slots=True)
class WaveLeaseCounts:
    total: int
    live_agent_shpoib: int
    live_agent_shared_hot: int
    read_page: int
    effective_total: int
    effective_live_agent_shpoib: int
    effective_live_agent_shared_hot: int
    effective_read_page: int


@dataclass(frozen=True, slots=True)
class LeaseLivenessRow:
    lease_id: str
    lane: str
    namespace: str
    owner_pid: int | None
    owner_alive: bool
    heartbeat_age_sec: int | None
    ttl_remaining_sec: int | None
    heartbeat_stale: bool
    parent_lease_id: str | None
    linked_pytest: str | None


def load_wave_snapshot() -> dict[str, object]:
    import sys
    from pathlib import Path

    from dev_paths import scripts_dev_dir

    dev_dir = scripts_dev_dir(Path(__file__))
    dev_text = str(dev_dir)
    if dev_text not in sys.path:
        sys.path.insert(0, dev_text)
    from wave_orchestrator.core import wave_status

    try:
        return wave_status()
    except PermissionError:
        from wave_orchestrator.lease_state import active_leases
        from wave_orchestrator.paths import resolve_wave_paths
        from wave_orchestrator.stack_pin import read_stack_pin
        from wave_orchestrator.store import load_state

        paths = resolve_wave_paths()
        state = load_state(paths.state_file)
        active = active_leases(state)
        try:
            stack_pin = read_stack_pin(paths=paths)
        except PermissionError:
            stack_pin = None
        return {
            "wave": state["wave"],
            "activeLeaseCount": len(active),
            "activeLeases": active,
            "leaseHistoryCount": len(state["leases"]),
            "activeResourceCount": sum(
                item.get("status") == "active" for item in state.get("resources", [])
            ),
            "resourceHistoryCount": len(state.get("resources", [])),
            "stackPin": stack_pin,
            "readOnlyFallback": True,
        }


def load_wave_snapshot_observation() -> dict[str, object]:
    """Observation-only wave read — no flock; slightly stale under parallel writers."""
    import sys
    from pathlib import Path

    from dev_paths import scripts_dev_dir

    dev_dir = scripts_dev_dir(Path(__file__))
    dev_text = str(dev_dir)
    if dev_text not in sys.path:
        sys.path.insert(0, dev_text)
    from wave_orchestrator.lease_state import active_leases
    from wave_orchestrator.paths import resolve_wave_paths
    from wave_orchestrator.stack_pin import read_stack_pin
    from wave_orchestrator.store import load_state

    paths = resolve_wave_paths()
    state = load_state(paths.state_file)
    active = active_leases(state)
    try:
        stack_pin = read_stack_pin(paths=paths)
    except PermissionError:
        stack_pin = None
    return {
        "wave": state["wave"],
        "activeLeaseCount": len(active),
        "activeLeases": active,
        "leaseHistoryCount": len(state["leases"]),
        "activeResourceCount": sum(
            item.get("status") == "active" for item in state.get("resources", [])
        ),
        "resourceHistoryCount": len(state.get("resources", [])),
        "stackPin": stack_pin,
        "readOnlyFallback": True,
    }


def _live_agent_bucket(namespace: str) -> str:
    ns = namespace.strip()
    if ns == LIVE_E2E_SHARED_HOT_NAMESPACE:
        return "shared_hot"
    return "shpoib"


def wave_lease_counts(snapshot: dict[str, object]) -> WaveLeaseCounts:
    raw_leases = snapshot.get("activeLeases")
    if not isinstance(raw_leases, list):
        return WaveLeaseCounts(
            total=0,
            live_agent_shpoib=0,
            live_agent_shared_hot=0,
            read_page=0,
            effective_total=0,
            effective_live_agent_shpoib=0,
            effective_live_agent_shared_hot=0,
            effective_read_page=0,
        )
    live_shpoib = 0
    live_shared_hot = 0
    read_page = 0
    eff_shpoib = 0
    eff_shared_hot = 0
    eff_read_page = 0
    total = 0
    effective_total = 0
    for item in raw_leases:
        if not isinstance(item, dict):
            continue
        is_root = _lease_is_root(item)
        total += 1
        if is_root:
            effective_total += 1
        lane = str(item.get("lane", ""))
        if lane == "LIVE_AGENT":
            bucket = _live_agent_bucket(str(item.get("namespace", "")))
            if bucket == "shared_hot":
                live_shared_hot += 1
                if is_root:
                    eff_shared_hot += 1
            else:
                live_shpoib += 1
                if is_root:
                    eff_shpoib += 1
        elif lane == "READ":
            read_page += 1
            if is_root:
                eff_read_page += 1
    return WaveLeaseCounts(
        total=total,
        live_agent_shpoib=live_shpoib,
        live_agent_shared_hot=live_shared_hot,
        read_page=read_page,
        effective_total=effective_total,
        effective_live_agent_shpoib=eff_shpoib,
        effective_live_agent_shared_hot=eff_shared_hot,
        effective_read_page=eff_read_page,
    )


def _parse_iso_timestamp(raw: object) -> datetime | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _pytest_owner_index(active_tests: list[dict[str, object]]) -> dict[int, str]:
    pids = [
        int(item["pid"])
        for item in active_tests
        if isinstance(item.get("pid"), int) and int(item["pid"]) > 0
    ]
    if not pids:
        return {}
    try:
        proc = subprocess.run(
            ["ps", "-eo", "pid=,ppid="],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return {}
    if proc.returncode != 0:
        return {}
    pid_set = set(pids)
    ppid_by_pid: dict[int, int] = {}
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        try:
            pid = int(parts[0])
            ppid = int(parts[1])
        except ValueError:
            continue
        if pid in pid_set:
            ppid_by_pid[pid] = ppid
    owner_to_test: dict[int, str] = {}
    for item in active_tests:
        pid_raw = item.get("pid")
        test_id = item.get("test_id")
        if not isinstance(pid_raw, int) or not isinstance(test_id, str):
            continue
        ppid = ppid_by_pid.get(pid_raw)
        if ppid is None:
            continue
        owner_to_test.setdefault(ppid, test_id)
    return owner_to_test


def build_lease_liveness(
    snapshot: dict[str, object],
    *,
    active_tests: list[dict[str, object]] | None = None,
) -> list[LeaseLivenessRow]:
    import sys
    from pathlib import Path

    from dev_paths import scripts_dev_dir

    dev_dir = scripts_dev_dir(Path(__file__))
    dev_text = str(dev_dir)
    if dev_text not in sys.path:
        sys.path.insert(0, dev_text)
    from wave_orchestrator.lease_state import (
        _process_is_alive,
        owner_bashpid_from_agent_id,
    )

    raw_leases = snapshot.get("activeLeases")
    if not isinstance(raw_leases, list):
        return []
    tests = active_tests or []
    owner_to_test = _pytest_owner_index(tests)
    now = datetime.now(tz=UTC)
    rows: list[LeaseLivenessRow] = []
    for item in raw_leases:
        if not isinstance(item, dict):
            continue
        agent_id = str(item.get("agentId", ""))
        owner_pid = owner_bashpid_from_agent_id(agent_id)
        owner_alive = owner_pid is not None and _process_is_alive(owner_pid)
        last_hb = _parse_iso_timestamp(item.get("lastHeartbeatAt"))
        expires = _parse_iso_timestamp(item.get("expiresAt"))
        hb_age: int | None = None
        ttl_remaining: int | None = None
        heartbeat_stale = False
        if last_hb is not None:
            hb_age = max(0, int((now - last_hb).total_seconds()))
            heartbeat_stale = hb_age >= int(STALL_PROGRESS_SEC)
        if expires is not None:
            ttl_remaining = max(0, int((expires - now).total_seconds()))
        parent = item.get("parentLeaseId")
        parent_text = (
            str(parent).strip() if isinstance(parent, str) and parent.strip() else None
        )
        linked = owner_to_test.get(owner_pid) if owner_pid is not None else None
        rows.append(
            LeaseLivenessRow(
                lease_id=str(item.get("leaseId", "")),
                lane=str(item.get("lane", "")),
                namespace=str(item.get("namespace", "")),
                owner_pid=owner_pid,
                owner_alive=owner_alive,
                heartbeat_age_sec=hb_age,
                ttl_remaining_sec=ttl_remaining,
                heartbeat_stale=heartbeat_stale,
                parent_lease_id=parent_text,
                linked_pytest=linked,
            )
        )
    return rows


def format_lease_liveness_human(rows: list[LeaseLivenessRow]) -> list[str]:
    if not rows:
        return ["E2E_LEASE_LIVENESS: none"]
    lines: list[str] = []
    for row in rows:
        lease_short = row.lease_id[:8] if row.lease_id else "unknown"
        owner_note = (
            f"owner_pid={row.owner_pid} owner_alive={'yes' if row.owner_alive else 'no'}"
            if row.owner_pid is not None
            else "owner_pid=unknown owner_alive=unknown"
        )
        hb_note = (
            f"hb_age={row.heartbeat_age_sec}s hb_stale={'yes' if row.heartbeat_stale else 'no'}"
            if row.heartbeat_age_sec is not None
            else "hb_age=unknown hb_stale=unknown"
        )
        ttl_note = (
            f"ttl_remaining={row.ttl_remaining_sec}s"
            if row.ttl_remaining_sec is not None
            else "ttl_remaining=unknown"
        )
        parent_note = row.parent_lease_id[:8] if row.parent_lease_id else "none"
        pytest_note = row.linked_pytest or "unknown"
        ns = row.namespace or "none"
        lines.append(
            "E2E_LEASE_LIVENESS: "
            f"id={lease_short} lane={row.lane} ns={ns} "
            f"{owner_note} {hb_note} {ttl_note} "
            f"parent={parent_note} linked_pytest={pytest_note}"
        )
    return lines


def lease_liveness_to_dict(rows: list[LeaseLivenessRow]) -> list[dict[str, object]]:
    return [asdict(row) for row in rows]
