"""Wave resource ledger helpers for live UI E2E runners."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def _wave_script() -> Path:
    return Path(__file__).resolve().parent.parent / "wave.sh"


def maybe_register_e2e_chat(chat_id: str) -> None:
    """Register a chat ref when pytest/live E2E env is configured."""
    ref = chat_id.strip()
    if not ref:
        return
    lease_id = os.environ.get("MYRM_E2E_LEASE_ID", "").strip()
    namespace = os.environ.get("MYRM_E2E_LEDGER_NAMESPACE", "").strip()
    agent_id = os.environ.get("MYRM_E2E_AGENT_ID", "").strip()
    if not lease_id or not namespace or not agent_id:
        return
    result = subprocess.run(
        [
            "bash",
            str(_wave_script()),
            "--agent",
            agent_id,
            "ledger",
            "register",
            lease_id,
            "chat",
            ref,
            "--namespace",
            namespace,
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if result.returncode == 0:
        return
    message = result.stderr or result.stdout
    if "already registered" in message:
        return
    if "active lease not found" in message or "LEASE_NOT_ACTIVE" in message:
        return
    raise RuntimeError(f"E2E_LEDGER_REGISTER_FAIL: {message}")
