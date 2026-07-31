"""E2E access lease and Dev Gate session heartbeat."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

_E2E_HEARTBEAT_EXTEND_SEC = 900


def _wave_script() -> Path:
    # myrm-agent/scripts/dev/wave.sh (lib → dev → wave.sh)
    return Path(__file__).resolve().parents[1] / "wave.sh"


def _heartbeat_dev_gate_session() -> None:
    run_id = os.environ.get("MYRM_E2E_RUN_ID", "").strip()
    token = os.environ.get("MYRM_E2E_RUNTIME_OWNER_TOKEN", "").strip()
    if not run_id or not token:
        return
    from dev_gate_cli import send

    try:
        send(
            {
                "operation": "heartbeat",
                "session_id": run_id,
                "owner_token": token,
                "current_node": os.environ.get("E2E_ADMIT_NODE", "E2E_BODY"),
            }
        )
    except (ConnectionError, OSError, RuntimeError, TimeoutError):
        return


def heartbeat_e2e_lease() -> None:
    """Extend the active LIVE_AGENT (or other) lease TTL during long UI E2E runs."""
    _heartbeat_dev_gate_session()
    lease_id = os.environ.get("MYRM_E2E_LEASE_ID", "").strip()
    agent_id = os.environ.get("MYRM_E2E_AGENT_ID", "").strip()
    if not lease_id or not agent_id:
        return
    try:
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
    except subprocess.TimeoutExpired:
        # R225: parallel chrome_e2e can block wave.sh behind ADMIT queue — non-fatal.
        return
    if result.returncode != 0:
        message = result.stderr or result.stdout
        if "LEASE_NOT_ACTIVE" in message or "LEASE_NOT_FOUND" in message:
            return
        if "TimeoutError" in message or "timed out" in message:
            return
        raise RuntimeError(f"E2E_LEASE_HEARTBEAT_FAIL: {message}")
