"""Chrome E2E launch preflight gate (R166 UPAP).

[INPUT]
- e2e_api_verify.resolve_e2e_api_context / _compute_next_action (POS: Agent SSOT)
- e2e_lease_liveness.wave_lease_counts (POS: effective cap headroom)

[OUTPUT]
- chrome_e2e_launch_denial_reason() -> str | None
- assert_chrome_e2e_launch_allowed() -> None (exit 2 on deny)

[POS]
test.sh fail-closed gate before session dedupe when cluster NEXT_ACTION=FAIL_FAST.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING


from dev_gate.contract import e2e_launch_check_wall_sec

if TYPE_CHECKING:
    from e2e_core.api_verify import BackendCandidate


def shared_profile_can_use_deployed_epoch(
    *,
    next_action: str,
    execution_mode: str | None = None,
    candidates: tuple[BackendCandidate, ...] | None = None,
) -> bool:
    """SHARED profiles target the healthy deployed backend, not workspace code."""
    mode = execution_mode or os.environ.get("MYRM_E2E_EXECUTION_MODE", "")
    if mode.strip() != "SHARED":
        return False
    if next_action != "PRIVATE_EPOCH_REQUIRED":
        return False
    resolved_candidates = candidates
    if resolved_candidates is None:
        from e2e_core.api_verify import resolve_e2e_api_context  # noqa: PLC0415

        context = resolve_e2e_api_context(retry_after_apply=False)
        resolved_candidates = context.candidates
    return any(
        candidate.source == "shared" and candidate.health_ok
        for candidate in resolved_candidates
    )


def _launch_gate_wall_sec() -> float:
    return e2e_launch_check_wall_sec()


def _launch_gate_subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    lib = Path(__file__).resolve().parent
    scripts_dev = lib.parent
    monorepo = Path(__file__).resolve().parents[5]
    paths = [str(lib), str(scripts_dev), str(monorepo / "scripts" / "dev")]
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join([*paths, existing] if existing else paths)
    return env


def chrome_e2e_launch_denial_reason() -> str | None:
    """Return human+machine denial line when a new chrome_e2e launch must abort."""
    if os.environ.get("MYRM_E2E_LAUNCH_FORCE", "").strip() == "1":
        return None
    if os.environ.get("E2E_SIGNOFF", "").strip() == "1":
        return None
    if os.environ.get("MYRM_E2E_P0A_GATE", "").strip() == "1":
        return None
    if os.environ.get("MYRM_E2E_LAUNCH_CHECK_SUBPROCESS", "0") == "1":
        from e2e_core.readiness import (  # noqa: PLC0415
            launch_denial_line,
            resolve_chrome_e2e_readiness,
        )

        verdict = resolve_chrome_e2e_readiness()
        if shared_profile_can_use_deployed_epoch(next_action=verdict.next_action):
            return None
        return launch_denial_line(verdict)
    from e2e_core.readiness import _parse_emit_fields  # noqa: PLC0415

    lib = Path(__file__).resolve().parent
    wall = _launch_gate_wall_sec()
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "e2e_readiness", "emit"],
            capture_output=True,
            text=True,
            timeout=wall,
            check=False,
            cwd=str(lib),
            env=_launch_gate_subprocess_env(),
        )
    except subprocess.TimeoutExpired:
        return (
            f"E2E_LAUNCH_DENIED: WAIT:READINESS_PROBE_TIMEOUT; "
            f"readiness probe exceeded {int(wall)}s; "
            "run ./myrm e2e-context json and execute agent_rule (do not force "
            "launch or stop other pytest)"
        )
    fields = _parse_emit_fields(proc.stdout)
    if fields.get("E2E_LAUNCH_ALLOWED", "no").lower() == "yes":
        return None
    if shared_profile_can_use_deployed_epoch(
        next_action=fields.get("NEXT_ACTION", "")
    ):
        return None
    token = fields.get("MYRM_READINESS_TOKEN", "UNKNOWN")
    reason = fields.get("MYRM_READINESS_REASON", proc.stderr.strip() or "launch denied")
    return (
        f"E2E_LAUNCH_DENIED: {token}; {reason}; "
        "run ./myrm e2e-context json and execute agent_rule (do not force launch "
        "or stop other pytest)"
    )


def assert_chrome_e2e_launch_allowed() -> None:
    """Exit 2 when launch preflight denies a new chrome_e2e session."""
    reason = chrome_e2e_launch_denial_reason()
    if reason is None:
        return
    print(reason, file=sys.stderr, flush=True)
    raise SystemExit(2)
