"""Cluster launch FAIL_FAST suppression — peers hung-reap intentionally skips.

[POS]
Dev Gate layer. R030-J contract: FAIL_FAST and hung-reap must judge the SAME
session row from the SAME clock. The coordinator ``phase_started_at`` clock
(active_tests rows) can lead the true pytest BODY clock when a holder reports
BODY early or a long bootstrap precedes BODY — judging FAIL_FAST from it while
hung-reap judges from the per-pytest snapshot reproduces the split-clock cluster
lock (body over cap blocks every new launch while the reaper sees a healthy body).
"""

from __future__ import annotations

import re


def _file_part_of_test_id(test_id: str) -> str:
    """Extract the ``tests/e2e/...`` file segment from any test_id shape.

    Handles ``tests/e2e/x.py::node`` and ``-m chrome_e2e myrm-agent/.../x.py``.
    """
    if not test_id:
        return ""
    if " -m " in test_id:
        test_id = test_id.split(" -m ", 1)[0].strip()
    match = re.search(r"(tests/e2e/[^\s]+\.py)", test_id)
    if match is not None:
        return match.group(1)
    return test_id


def _same_test_file(left: str, right: str) -> bool:
    left_part = _file_part_of_test_id(left)
    right_part = _file_part_of_test_id(right)
    if not left_part or not right_part:
        return False
    return (
        left_part == right_part
        or left_part.endswith("/" + right_part)
        or right_part.endswith("/" + left_part)
    )


def _authoritative_live_row(test_id: str):
    """Resolve the authoritative registry row (per-pytest snapshot) for a test.

    list_live_e2e_sessions groups snapshots by test_id and keeps the most advanced
    phase — the pytest subprocess row, which carries the real bodyStartedMonotonic
    clock. Returns None when no snapshot exists yet (fall back to active_tests data).
    """
    if not test_id:
        return None
    from e2e_session_runtime.registry import (  # noqa: PLC0415
        list_live_e2e_sessions,
    )

    best = None
    for live in list_live_e2e_sessions():
        if not _same_test_file(live.test_id, test_id):
            continue
        if best is None or _phase_rank(live.phase) > _phase_rank(best.phase):
            best = live
    return best


def _phase_rank(phase: str) -> int:
    order = {"admit": 0, "delegated": 1, "bootstrap": 2, "body": 3, "teardown": 4}
    return order.get(phase.strip().lower(), -1)


def _session_row_from_active_test(row: dict[str, object]):
    from e2e_session_runtime.registry import LiveE2ESessionRow  # noqa: PLC0415

    pid_raw = row.get("pid")
    pid = int(pid_raw) if isinstance(pid_raw, int) and pid_raw > 0 else 0
    elapsed = row.get("elapsed_sec")
    return LiveE2ESessionRow(
        pid=pid,
        test_id=str(row.get("test_id") or row.get("label") or f"pid:{pid}"),
        elapsed_sec=float(elapsed) if isinstance(elapsed, (int, float)) else 0.0,
        state=str(row.get("state") or "?"),
        phase=str(row.get("wall_phase") or row.get("phase") or "body").strip().lower(),
        current_node=(
            str(row.get("current_node")).strip()
            if isinstance(row.get("current_node"), str)
            and str(row.get("current_node")).strip()
            else None
        ),
        wall_phase=str(row.get("wall_phase") or row.get("phase") or "body").strip().lower(),
        admit_elapsed_sec=(
            float(row["admit_elapsed_sec"])
            if isinstance(row.get("admit_elapsed_sec"), (int, float))
            else None
        ),
        body_elapsed_sec=(
            float(row["body_elapsed_sec"])
            if isinstance(row.get("body_elapsed_sec"), (int, float))
            else None
        ),
        node_elapsed_sec=(
            float(row["node_elapsed_sec"])
            if isinstance(row.get("node_elapsed_sec"), (int, float))
            else None
        ),
    )


def cluster_fail_fast_suppressed_for_active_test(row: dict[str, object]) -> bool:
    """True when FAIL_FAST must NOT block unrelated launches for this peer.

    R030-J contract: judge the authoritative registry row (per-pytest snapshot),
    exactly like hung-reap. A peer the reaper judges healthy must never block the
    cluster, even when the coordinator ``phase_started_at`` clock claims an over-cap
    body (split-clock lock). A peer the reaper will reap is NOT suppressed, so
    FAIL_FAST refuses launches only for the short window before the SIGINT lands.
    Desktop-soak peers are immune on both sides.
    """
    from dev_gate.contract import E2E_BODY_WALL_EXCEEDED_TOKEN  # noqa: PLC0415
    from e2e_core.stale_lease_reap import (  # noqa: PLC0415
        _body_wall_cap_for_pid,
        _desktop_soak_reap_immunity,
        _hung_reason_for_session,
        _process_has_desktop_soak_env,
    )

    test_id = str(row.get("test_id") or row.get("label") or "")
    authority = _authoritative_live_row(test_id)
    if authority is not None:
        if _process_has_desktop_soak_env(authority.pid):
            body_elapsed = authority.body_elapsed_sec
            if body_elapsed is not None and body_elapsed >= _body_wall_cap_for_pid(
                authority.pid, test_id=authority.test_id
            ):
                body_cap = _body_wall_cap_for_pid(
                    authority.pid, test_id=authority.test_id
                )
                reason = (
                    f"{E2E_BODY_WALL_EXCEEDED_TOKEN}: "
                    f"body_elapsed={int(body_elapsed)}s>={int(body_cap)}s"
                )
                if _desktop_soak_reap_immunity(authority, reason):
                    return True
        reason = _hung_reason_for_session(authority)
        if reason is None:
            # hung-reap judges this peer healthy → never cluster-block it.
            return True
        return _desktop_soak_reap_immunity(authority, reason)
    session_row = _session_row_from_active_test(row)
    if _process_has_desktop_soak_env(session_row.pid):
        body_elapsed = session_row.body_elapsed_sec
        if body_elapsed is not None and body_elapsed >= _body_wall_cap_for_pid(
            session_row.pid, test_id=session_row.test_id
        ):
            body_cap = _body_wall_cap_for_pid(
                session_row.pid, test_id=session_row.test_id
            )
            reason = (
                f"{E2E_BODY_WALL_EXCEEDED_TOKEN}: "
                f"body_elapsed={int(body_elapsed)}s>={int(body_cap)}s"
            )
            if _desktop_soak_reap_immunity(session_row, reason):
                return True
    reason = _hung_reason_for_session(session_row)
    if reason is None:
        # No pytest snapshot yet, but the reaper would not stop this peer —
        # a fresh healthy session must not block unrelated launches.
        return True
    return _desktop_soak_reap_immunity(session_row, reason)
