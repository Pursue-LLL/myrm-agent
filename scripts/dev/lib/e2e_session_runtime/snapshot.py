"""Per-pid Chrome E2E session snapshot SSOT (R62 Phase B).

[INPUT]
- e2e_session_runtime.lifecycle ENV_WALL_* (phase + monotonic clocks)

[OUTPUT]
- write_session_snapshot / read_session_snapshot / body_elapsed_from_snapshot
- nodeStartedMonotonic + node elapsed for e2e_stall_guard (R96-B6)

[POS]
Dev Gate layer — parallel-safe progress for ./myrm e2e-context and hung pytest reap.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from e2e_session_runtime.lifecycle import (
    ENV_PROGRESS_AT,
    ENV_WALL_PHASE,
    ENV_WALL_STARTED,
    current_phase,
    wall_started_monotonic,
)

_SESSION_DIR_BASENAME = "myrm-e2e-session"


def session_snapshot_dir() -> Path:
    return Path(os.environ.get("TMPDIR", "/tmp")) / _SESSION_DIR_BASENAME


def session_snapshot_path(pid: int | None = None) -> Path:
    resolved = os.getpid() if pid is None else pid
    return session_snapshot_dir() / f"{resolved}.json"


def _pytest_node_from_env() -> str:
    raw = os.environ.get("PYTEST_CURRENT_TEST", "").strip()
    if not raw:
        return ""
    return raw.split(" ", 1)[0]


def _session_started_monotonic(
    existing: dict[str, object] | None, *, now: float
) -> float:
    if existing is None:
        return now
    for key in ("sessionStartedMonotonic", "bodyStartedMonotonic"):
        raw = existing.get(key)
        if raw is None:
            continue
        try:
            return float(raw)
        except (TypeError, ValueError):
            continue
    return now


def _write_snapshot_file(*, pid: int, payload: dict[str, object]) -> None:
    session_snapshot_dir().mkdir(parents=True, exist_ok=True)
    session_snapshot_path(pid).write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )


def write_holder_session_snapshot(
    *,
    holder_pid: int,
    test_id: str,
    current_node: str,
    lane: str = "",
    shpoib: bool = False,
) -> None:
    """R144: test.sh ADMIT session sidecar — visible before inner pytest spawns."""
    now = time.monotonic()
    existing = read_session_snapshot(holder_pid)
    started = _session_started_monotonic(existing, now=now)
    node_started = now
    if existing is not None:
        prev_node = str(existing.get("currentNode") or "").strip()
        if prev_node == current_node.strip():
            raw_node_started = existing.get("nodeStartedMonotonic")
            if raw_node_started is not None:
                try:
                    node_started = float(raw_node_started)
                except (TypeError, ValueError):
                    pass
    payload = {
        "pid": holder_pid,
        "holderPid": holder_pid,
        "testId": test_id.strip(),
        "currentNode": current_node,
        "phase": "delegated" if current_node == "E2E_PYTEST_SUBPROCESS" else "admit",
        "lane": lane.strip(),
        "shpoib": bool(shpoib),
        "sessionStartedMonotonic": started,
        "bodyStartedMonotonic": started,
        "nodeStartedMonotonic": node_started,
        "progressAtMonotonic": now,
        "updatedAtEpoch": time.time(),
    }
    run_id = os.environ.get("MYRM_E2E_RUN_ID", "").strip()
    if run_id:
        payload["runId"] = run_id
    _write_snapshot_file(pid=holder_pid, payload=payload)


def touch_holder_session_progress(
    *,
    holder_pid: int,
    current_node: str | None = None,
) -> None:
    existing = read_session_snapshot(holder_pid)
    if existing is None:
        return
    node = (current_node or str(existing.get("currentNode") or "")).strip()
    if not node:
        return
    write_holder_session_snapshot(
        holder_pid=holder_pid,
        test_id=str(existing.get("testId") or node),
        current_node=node,
        lane=str(existing.get("lane") or ""),
        shpoib=bool(existing.get("shpoib")),
    )


def _resolve_body_started_monotonic(
    *,
    now: float,
    resolved_phase: str,
    existing: dict[str, object] | None,
) -> float:
    """Body clock for hung-reap — ADMIT/BOOTSTRAP queue must not consume BODY budget (R62)."""
    if resolved_phase != "body":
        if existing is not None:
            raw = existing.get("bodyStartedMonotonic")
            if raw is not None:
                try:
                    return float(raw)
                except (TypeError, ValueError):
                    pass
        return wall_started_monotonic() or now
    prev_phase = ""
    if existing is not None:
        prev_phase = str(existing.get("phase") or "").strip().lower()
    if prev_phase == "body" and existing is not None:
        raw = existing.get("bodyStartedMonotonic")
        if raw is not None:
            try:
                return float(raw)
            except (TypeError, ValueError):
                pass
    return now


def write_session_snapshot(
    *,
    current_node: str,
    phase: str | None = None,
    test_id: str | None = None,
) -> None:
    """Persist per-pytest session state for e2e-context + hung reap (parallel-safe)."""
    now = time.monotonic()
    resolved_phase = (phase or current_phase()).strip().lower() or "body"
    existing = read_session_snapshot(os.getpid())
    started = _resolve_body_started_monotonic(
        now=now,
        resolved_phase=resolved_phase,
        existing=existing,
    )
    node_started = now
    session_started = _session_started_monotonic(existing, now=started)
    if existing is not None:
        prev_node = str(existing.get("currentNode") or "").strip()
        if prev_node == current_node.strip():
            raw_node_started = existing.get("nodeStartedMonotonic")
            if raw_node_started is not None:
                try:
                    node_started = float(raw_node_started)
                except (TypeError, ValueError):
                    pass
    resolved_test_id = (test_id or _pytest_node_from_env() or current_node).strip()
    payload: dict[str, object] = {
        "pid": os.getpid(),
        "currentNode": current_node,
        "phase": resolved_phase,
        "testId": resolved_test_id,
        "sessionStartedMonotonic": session_started,
        "bodyStartedMonotonic": started,
        "nodeStartedMonotonic": node_started,
        "progressAtMonotonic": now,
        "updatedAtEpoch": time.time(),
    }
    lane = os.environ.get("MYRM_E2E_LANE", "").strip()
    if lane:
        payload["lane"] = lane.upper()
    workload = os.environ.get("MYRM_E2E_WORKLOAD", "").strip()
    if workload:
        payload["workload"] = workload.upper()
    run_id = os.environ.get("MYRM_E2E_RUN_ID", "").strip()
    if run_id:
        payload["runId"] = run_id
    if os.environ.get("MYRM_E2E_SHPOIB", "").strip() == "1":
        payload["shpoib"] = True
    try:
        from e2e_session_runtime.lifecycle import phase_cap_sec

        if resolved_phase in {"admit", "bootstrap", "body", "teardown"}:
            existing_cap = existing.get("phaseCapSec") if existing is not None else None
            existing_phase = (
                str(existing.get("phase") or "").strip().lower()
                if existing is not None
                else ""
            )
            if (
                existing_cap is not None
                and isinstance(existing_cap, (int, float))
                and existing_phase == resolved_phase
            ):
                payload["phaseCapSec"] = float(existing_cap)
            else:
                try:
                    payload["phaseCapSec"] = phase_cap_sec(resolved_phase)  # type: ignore[arg-type]
                except (OSError, RuntimeError, TimeoutError, ValueError):
                    # Progress stamps must never block CDP evaluate under parallel coordinator load.
                    fallback = os.environ.get("MYRM_E2E_BOOTSTRAP_CAP_SEC", "180")
                    try:
                        payload["phaseCapSec"] = float(fallback)
                    except ValueError:
                        payload["phaseCapSec"] = 180.0
    except ImportError:
        pass
    if existing is not None and existing.get("holderPid") is not None:
        payload["holderPid"] = existing["holderPid"]
    if existing is not None:
        if "lane" not in payload and existing.get("lane"):
            payload["lane"] = existing["lane"]
        if "shpoib" not in payload and existing.get("shpoib") is not None:
            payload["shpoib"] = existing["shpoib"]
    hot_path = os.environ.get("MYRM_E2E_BOOTSTRAP_HOT_PATH", "").strip()
    if hot_path:
        payload["bootstrapHotPath"] = hot_path
    elif existing is not None and existing.get("bootstrapHotPath"):
        payload["bootstrapHotPath"] = existing["bootstrapHotPath"]
    _write_snapshot_file(pid=os.getpid(), payload=payload)
    holder_raw = os.environ.get("MYRM_E2E_DEDUPE_HOLDER_PID", "").strip()
    if holder_raw.isdigit():
        holder_pid = int(holder_raw)
        if holder_pid != os.getpid():
            clear_session_snapshot(holder_pid)


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _load_all_session_snapshots(
    *, live_only: bool = True
) -> tuple[tuple[int, dict[str, object]], ...]:
    directory = session_snapshot_dir()
    if not directory.is_dir():
        return ()
    rows: list[tuple[int, dict[str, object]]] = []
    for path in directory.glob("*.json"):
        try:
            pid = int(path.stem)
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        if live_only and not _pid_alive(pid):
            continue
        rows.append((pid, payload))
    return tuple(rows)


def read_session_snapshot(pid: int) -> dict[str, object] | None:
    if not _pid_alive(pid):
        return None
    path = session_snapshot_path(pid)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def progress_at_from_snapshot(snapshot: dict[str, object]) -> float | None:
    raw = snapshot.get("progressAtMonotonic")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def admit_elapsed_from_snapshot(snapshot: dict[str, object]) -> float | None:
    phase = str(snapshot.get("phase") or "").strip().lower()
    if phase != "admit":
        return None
    return phase_elapsed_from_snapshot(snapshot)


def body_elapsed_from_snapshot(snapshot: dict[str, object]) -> float | None:
    phase = str(snapshot.get("phase") or "").strip().lower()
    if phase != "body":
        return None
    return phase_elapsed_from_snapshot(snapshot)


def phase_elapsed_from_snapshot(snapshot: dict[str, object]) -> float | None:
    """Monotonic seconds since current phase wall started (bootstrap or body)."""
    started = snapshot.get("bodyStartedMonotonic")
    if started is None:
        return None
    try:
        started_f = float(started)
    except (TypeError, ValueError):
        return None
    return max(0.0, time.monotonic() - started_f)


def progress_stale_sec(snapshot: dict[str, object]) -> float | None:
    progress_at = progress_at_from_snapshot(snapshot)
    if progress_at is None:
        return None
    return max(0.0, time.monotonic() - progress_at)


def annotate_bootstrap_hot_path(mode: str) -> None:
    """Persist bootstrap hot/cold path for e2e-context observers (§19.11 TAB-6)."""
    text = mode.strip()
    if not text:
        return
    os.environ["MYRM_E2E_BOOTSTRAP_HOT_PATH"] = text
    existing = read_session_snapshot(os.getpid())
    if existing is None:
        return
    payload = dict(existing)
    payload["bootstrapHotPath"] = text
    payload["progressAtMonotonic"] = time.monotonic()
    payload["updatedAtEpoch"] = time.time()
    _write_snapshot_file(pid=os.getpid(), payload=payload)


def touch_session_progress(*, current_node: str | None = None) -> None:
    """Update env progress stamp + per-pid snapshot for parallel observers."""
    stamp = time.monotonic()
    os.environ[ENV_PROGRESS_AT] = str(stamp)
    node = (current_node or _pytest_node_from_env()).strip()
    if node:
        write_session_snapshot(current_node=node, phase=current_phase())


def clear_session_snapshot(pid: int | None = None) -> None:
    path = session_snapshot_path(pid)
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def prune_stale_session_snapshots() -> int:
    """Remove snapshot sidecars whose pid is no longer alive."""
    removed = 0
    directory = session_snapshot_dir()
    if not directory.is_dir():
        return removed
    for path in directory.glob("*.json"):
        try:
            pid = int(path.stem)
        except ValueError:
            continue
        if _pid_alive(pid):
            continue
        try:
            path.unlink(missing_ok=True)
            removed += 1
        except OSError:
            continue
    return removed


def normalize_e2e_test_id(test_id: str) -> str:
    text = test_id.strip()
    if " -m " in text and "::" not in text:
        return text.split(" -m ", 1)[0].strip()
    return text


def test_ids_match(ps_test_id: str, snapshot_node: str) -> bool:
    left = ps_test_id.strip()
    right = snapshot_node.strip()
    if not left or not right:
        return False
    if left == right:
        return True
    left_norm = normalize_e2e_test_id(left)
    right_norm = normalize_e2e_test_id(right)
    if left_norm == right_norm:
        return True
    if "::" in right and right.startswith(left_norm):
        return True
    if "::" in left and left.startswith(right_norm):
        return True
    return False


def read_session_snapshot_by_test_id(
    test_id: str,
) -> tuple[int, dict[str, object]] | None:
    target = test_id.strip()
    if not target:
        return None
    for pid, payload in _load_all_session_snapshots(live_only=True):
        stored = str(payload.get("testId") or "").strip()
        node = str(payload.get("currentNode") or "").strip()
        if stored and test_ids_match(target, stored):
            return pid, payload
        if test_ids_match(target, node):
            return pid, payload
    return None


def resolve_session_snapshot(
    *,
    pid: int,
    test_id: str | None = None,
) -> dict[str, object] | None:
    direct = read_session_snapshot(pid)
    if direct is not None:
        return direct
    if test_id is None:
        return None
    match = read_session_snapshot_by_test_id(test_id)
    if match is None:
        return None
    return match[1]


def snapshot_env_keys() -> tuple[str, str, str]:
    return ENV_WALL_STARTED, ENV_WALL_PHASE, ENV_PROGRESS_AT
