"""Cluster launch FAIL_FAST suppression — peers hung-reap intentionally skips."""

from __future__ import annotations


def cluster_fail_fast_suppressed_for_active_test(row: dict[str, object]) -> bool:
    """Peers hung-reap intentionally skips must not cluster-block unrelated launches."""
    from dev_gate.contract import E2E_BODY_WALL_EXCEEDED_TOKEN  # noqa: PLC0415
    from e2e_session_runtime.registry import LiveE2ESessionRow  # noqa: PLC0415
    from e2e_core.stale_lease_reap import (  # noqa: PLC0415
        _body_wall_cap_for_pid,
        _desktop_soak_reap_immunity,
        _hung_reason_for_session,
        _process_has_desktop_soak_env,
    )

    pid_raw = row.get("pid")
    if not isinstance(pid_raw, int) or pid_raw <= 0:
        return False
    elapsed = row.get("elapsed_sec")
    session_row = LiveE2ESessionRow(
        pid=pid_raw,
        test_id=str(row.get("test_id") or row.get("label") or f"pid:{pid_raw}"),
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
    if _process_has_desktop_soak_env(pid_raw):
        body_elapsed = session_row.body_elapsed_sec
        if body_elapsed is not None and body_elapsed >= _body_wall_cap_for_pid(pid_raw):
            body_cap = _body_wall_cap_for_pid(pid_raw)
            reason = (
                f"{E2E_BODY_WALL_EXCEEDED_TOKEN}: "
                f"body_elapsed={int(body_elapsed)}s>={int(body_cap)}s"
            )
            if _desktop_soak_reap_immunity(session_row, reason):
                return True
    reason = _hung_reason_for_session(session_row)
    if reason is None:
        return False
    return _desktop_soak_reap_immunity(session_row, reason)
