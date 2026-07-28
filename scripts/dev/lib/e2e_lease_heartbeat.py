"""E2E lease + mux admission heartbeat SSOT (R98 · lib layer)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_E2E_HEARTBEAT_EXTEND_SEC = 900


def _wave_script() -> Path:
    # myrm-agent/scripts/dev/wave.sh (lib → dev → wave.sh)
    return Path(__file__).resolve().parents[1] / "wave.sh"


def _heartbeat_deferred_mux_admission() -> None:
    run_id = os.environ.get("MYRM_E2E_RUN_ID", "").strip()
    token = os.environ.get("MYRM_E2E_MUX_ADMISSION_TOKEN", "").strip()
    if not run_id or not token:
        return
    admission_py = Path(__file__).resolve().parent / "e2e_mux_admission.py"
    if not admission_py.is_file():
        return
    subprocess.run(
        [
            sys.executable,
            str(admission_py),
            "heartbeat",
            "--session-id",
            run_id,
            "--owner-token",
            token,
        ],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )


def heartbeat_e2e_lease() -> None:
    """Extend the active LIVE_AGENT (or other) lease TTL during long UI E2E runs."""
    _heartbeat_deferred_mux_admission()
    lease_id = os.environ.get("MYRM_E2E_LEASE_ID", "").strip()
    agent_id = os.environ.get("MYRM_E2E_AGENT_ID", "").strip()
    if not lease_id or not agent_id:
        return
    result = subprocess.run(
        [
            "bash",
            str(_wave_script()),
            "--agent",
            agent_id,
            "lease",
            "heartbeat",
            lease_id,
            "--extend",
            str(_E2E_HEARTBEAT_EXTEND_SEC),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr or result.stdout
        if "LEASE_NOT_ACTIVE" in message or "LEASE_NOT_FOUND" in message:
            return
        if "TimeoutError" in message or "timed out" in message:
            return
        raise RuntimeError(f"E2E_LEASE_HEARTBEAT_FAIL: {message}")
