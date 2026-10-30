"""Coordinator PAGE_OPEN -> BODY seal for the local E2E session.

[INPUT]
- dev_gate.cli.send (coordinator RPC; imported at call time so the coordinator stays optional)
- MYRM_E2E_RUN_ID / MYRM_E2E_RUNTIME_OWNER_TOKEN (session identity exported by the runner)

[OUTPUT]
- seal_coordinator_body(): moves the coordinator session to BODY and prints E2E_DEV_GATE_BODY_START

[POS]
Dev Gate layer — split out of lifecycle.py, which owns the local wall clock and phases.
"""

from __future__ import annotations

import os
import sys
from typing import Final

# dev_gate.session.TERMINAL_STATES 的字符串镜像：并发 complete_bootstrap_phase
# 可能已把 coordinator session 推到终态（TEARDOWN→SUCCEEDED/FAILED/CANCELLED），
# 此时本地 BODY seal 不再必要，应静默返回而非误报（见 seal_coordinator_body）。
_TERMINAL_STATES: Final[frozenset[str]] = frozenset(
    {"SUCCEEDED", "FAILED", "CANCELLED"}
)


def seal_coordinator_body(*, current_node: str) -> None:
    """Seal coordinator PAGE_OPEN→BODY and emit the product SLO measurement."""
    session_id = os.environ.get("MYRM_E2E_RUN_ID", "").strip()
    owner_token = os.environ.get("MYRM_E2E_RUNTIME_OWNER_TOKEN", "").strip()
    if not session_id or not owner_token:
        return
    from dev_gate.cli import send

    response = send({"operation": "snapshot", "session_id": session_id})
    session = response.get("session") if isinstance(response, dict) else None
    if not isinstance(session, dict):
        raise TypeError(f"E2E_DEV_GATE_BODY_TRANSITION: session missing {session_id}")
    state = str(session.get("state", ""))
    if state == "PREPARING":
        response = send(
            {
                "operation": "transition",
                "session_id": session_id,
                "owner_token": owner_token,
                "target": "PAGE_OPEN",
                "current_node": "E2E_PYTEST_SUBPROCESS",
            }
        )
        session = response.get("session") if isinstance(response, dict) else None
        state = str(session.get("state", "")) if isinstance(session, dict) else ""
    if state == "PAGE_OPEN":
        # Re-snapshot before BODY: parallel open_mcp_page / post_cdp_bootstrap may
        # have sealed BODY while local wall phase is still bootstrap.
        response = send({"operation": "snapshot", "session_id": session_id})
        session = response.get("session") if isinstance(response, dict) else None
        state = str(session.get("state", "")) if isinstance(session, dict) else ""
        if state == "PAGE_OPEN":
            try:
                response = send(
                    {
                        "operation": "transition",
                        "session_id": session_id,
                        "owner_token": owner_token,
                        "target": "BODY",
                        "current_node": current_node,
                    }
                )
            except RuntimeError as exc:
                # TOCTOU: a concurrent complete_bootstrap_phase (pytest fixture +
                # post_cdp_bootstrap) may seal BODY between re-snapshot and this
                # transition. Treat an already-sealed BODY as success.
                if "BODY->BODY" not in str(exc):
                    raise
                response = send({"operation": "snapshot", "session_id": session_id})
            session = response.get("session") if isinstance(response, dict) else None
            state = str(session.get("state", "")) if isinstance(session, dict) else ""
    if state != "BODY" or not isinstance(session, dict):
        if state in _TERMINAL_STATES:
            # 并发 complete_bootstrap_phase（pytest fixture + post_cdp_bootstrap）
            # 可能已把 session 直接推到终态（TEARDOWN→SUCCEEDED/FAILED/CANCELLED）。
            # 本地 wall phase 独立运行，BODY seal 不再必要——静默返回避免误报。
            return
        raise RuntimeError(
            f"E2E_DEV_GATE_BODY_TRANSITION: expected BODY, got {state or 'UNKNOWN'}"
        )
    submitted_at = session.get("submitted_at")
    phase_started_at = session.get("phase_started_at")
    if not isinstance(submitted_at, (int, float)) or not isinstance(
        phase_started_at, (int, float)
    ):
        raise TypeError("E2E_DEV_GATE_BODY_TRANSITION: timestamps unavailable")
    admit_to_body = max(0.0, float(phase_started_at) - float(submitted_at))
    print(
        f"E2E_DEV_GATE_BODY_START: admit_to_body_sec={admit_to_body:.3f} "
        f"session={session_id} node={current_node}",
        file=sys.stderr,
        flush=True,
    )
