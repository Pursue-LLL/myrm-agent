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


def _launch_gate_wall_sec() -> float:
    raw = os.environ.get("E2E_LAUNCH_CHECK_WALL_SEC", "").strip()
    if not raw:
        return 45.0
    try:
        parsed = float(raw)
    except ValueError:
        return 45.0
    return parsed if parsed > 0 else 45.0


def _launch_gate_subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    lib = Path(__file__).resolve().parent
    scripts_dev = lib.parent
    monorepo = scripts_dev.parent.parent
    paths = [str(lib), str(scripts_dev), str(monorepo / "scripts" / "dev")]
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join([*paths, existing] if existing else paths)
    return env


def chrome_e2e_launch_denial_reason() -> str | None:
    """Return human+machine denial line when a new chrome_e2e launch must abort."""
    if os.environ.get("MYRM_E2E_LAUNCH_FORCE", "").strip() == "1":
        return None
    if os.environ.get("MYRM_E2E_SIGNOFF_CLARIFY_POOL", "").strip() == "1":
        return None
    if os.environ.get("MYRM_E2E_LAUNCH_CHECK_SUBPROCESS", "1") != "1":
        from e2e_readiness import (  # noqa: PLC0415
            launch_denial_line,
            resolve_chrome_e2e_readiness,
        )

        verdict = resolve_chrome_e2e_readiness()
        return launch_denial_line(verdict)
    from e2e_readiness import _parse_emit_fields  # noqa: PLC0415

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
            "run ./myrm e2e-context; maintainer override MYRM_E2E_LAUNCH_FORCE=1 "
            "(do not stop other pytest)"
        )
    fields = _parse_emit_fields(proc.stdout)
    if fields.get("E2E_LAUNCH_ALLOWED", "no").lower() == "yes":
        return None
    token = fields.get("MYRM_READINESS_TOKEN", "UNKNOWN")
    reason = fields.get("MYRM_READINESS_REASON", proc.stderr.strip() or "launch denied")
    return (
        f"E2E_LAUNCH_DENIED: {token}; {reason}; "
        "run ./myrm e2e-context; maintainer override MYRM_E2E_LAUNCH_FORCE=1 "
        "(do not stop other pytest)"
    )


def assert_chrome_e2e_launch_allowed() -> None:
    """Exit 2 when launch preflight denies a new chrome_e2e session."""
    reason = chrome_e2e_launch_denial_reason()
    if reason is None:
        return
    print(reason, file=sys.stderr, flush=True)
    raise SystemExit(2)
