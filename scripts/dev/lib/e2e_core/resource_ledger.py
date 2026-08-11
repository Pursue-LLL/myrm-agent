"""E2E runtime resource ledger SSOT (R98 · lib layer)."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from e2e_session_runtime.heartbeat import heartbeat_once

ResourceKind = Literal[
    "chat", "project", "agent", "cron", "file", "kanban_board", "kanban_task"
]


def _wave_script() -> Path:
    return Path(__file__).resolve().parents[1] / "wave.sh"


def _ledger_agent_id() -> str:
    return (
        os.environ.get("MYRM_E2E_AGENT_ID", "").strip()
        or f"pytest-ledger:{os.getpid()}"
    )


def register_e2e_resource(
    lease_id: str,
    *,
    kind: ResourceKind,
    ref: str,
    namespace: str,
) -> None:
    resource_ref = ref.strip()
    if not resource_ref:
        raise ValueError("E2E resource ref must not be empty")
    ns = namespace.strip()
    if not ns:
        raise ValueError("E2E resource namespace must not be empty")
    result = subprocess.run(
        [
            "bash",
            str(_wave_script()),
            "--agent",
            _ledger_agent_id(),
            "ledger",
            "register",
            lease_id,
            kind,
            resource_ref,
            "--namespace",
            ns,
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


@dataclass(frozen=True, slots=True)
class E2EResourceLedger:
    lease_id: str
    namespace: str
    ephemeral_runtime: bool = False

    def register(self, kind: ResourceKind, ref: str) -> None:
        heartbeat_once()
        if self.ephemeral_runtime:
            return
        register_e2e_resource(
            self.lease_id,
            kind=kind,
            ref=ref,
            namespace=self.namespace,
        )
