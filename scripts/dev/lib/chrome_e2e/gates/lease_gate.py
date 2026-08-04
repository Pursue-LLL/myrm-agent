"""Lease attestation for Browser Orchestrator session/page operations (§19.10 D1).

[INPUT]
- wave-orchestrator.json active leases
- MYRM_E2E_LEASE_ID, MYRM_CHROME_MCP_DIAGNOSTIC env

[OUTPUT]
- assert_orchestrator_lease_allowed(): fail-closed when lease missing/inactive
- cli main for orchestrator daemon subprocess validation

[POS]
Dev Gate data-plane gate — complements e2e_lease_pytest_gate (pytest spawn only).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict

from chrome_e2e.gates.entry_guard import is_e2e_chrome_mcp_diagnostic_mode
from dev_gate_contract import E2E_ORCHESTRATOR_LEASE_DENIED_TOKEN
from wave_state_paths import resolve_wave_state_file


class _LeaseRow(TypedDict, total=False):
    leaseId: str
    status: str
    expiresAt: str
    agentId: str


class _WaveRow(TypedDict, total=False):
    status: str


def _load_wave_payload(state_file: Path) -> dict[str, object]:
    try:
        raw = json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"{E2E_ORCHESTRATOR_LEASE_DENIED_TOKEN}: cannot read wave state {state_file}"
        ) from exc
    if not isinstance(raw, dict):
        raise RuntimeError(
            f"{E2E_ORCHESTRATOR_LEASE_DENIED_TOKEN}: invalid wave state shape"
        )
    return raw


def _active_lease(payload: dict[str, object], lease_id: str) -> _LeaseRow | None:
    leases = payload.get("leases")
    if not isinstance(leases, list):
        return None
    for item in leases:
        if isinstance(item, dict) and str(item.get("leaseId", "")).strip() == lease_id:
            return item  # type: ignore[return-value]
    return None


def _lease_is_active(lease: _LeaseRow) -> bool:
    if str(lease.get("status", "")).strip() != "active":
        return False
    expires_raw = lease.get("expiresAt")
    if not isinstance(expires_raw, str) or not expires_raw.strip():
        return False
    try:
        expires = datetime.fromisoformat(expires_raw.replace("Z", "+00:00"))
    except ValueError:
        return False
    return expires > datetime.now(UTC)


def resolve_required_lease_id(*, explicit: str | None = None) -> str:
    lease_id = (explicit or os.environ.get("MYRM_E2E_LEASE_ID", "")).strip()
    if lease_id:
        return lease_id
    if is_e2e_chrome_mcp_diagnostic_mode():
        return ""
    raise RuntimeError(
        f"{E2E_ORCHESTRATOR_LEASE_DENIED_TOKEN}: MYRM_E2E_LEASE_ID required — "
        "launch via ./myrm test -m chrome_e2e"
    )


def sync_agent_id_with_lease_owner(owner: str) -> bool:
    """Align MYRM_E2E_AGENT_ID with wave lease owner (active lease row is SSOT)."""
    if not owner:
        return False
    os.environ["MYRM_E2E_AGENT_ID"] = owner
    os.environ["MYRM_WAVE_AGENT_ID"] = owner
    return True


def assert_orchestrator_lease_allowed(
    *,
    lease_id: str | None = None,
    state_file: Path | None = None,
) -> str:
    resolved = resolve_required_lease_id(explicit=lease_id)
    if not resolved:
        return ""
    path = state_file or resolve_wave_state_file()
    payload = _load_wave_payload(path)
    wave = payload.get("wave")
    if not isinstance(wave, dict) or str(wave.get("status", "")).strip() != "open":
        raise RuntimeError(
            f"{E2E_ORCHESTRATOR_LEASE_DENIED_TOKEN}: wave is not open ({path})"
        )
    lease = _active_lease(payload, resolved)
    if lease is None:
        raise RuntimeError(
            f"{E2E_ORCHESTRATOR_LEASE_DENIED_TOKEN}: lease {resolved} not found"
        )
    if not _lease_is_active(lease):
        raise RuntimeError(
            f"{E2E_ORCHESTRATOR_LEASE_DENIED_TOKEN}: lease {resolved} is not active"
        )
    owner = str(lease.get("agentId", "")).strip()
    sync_agent_id_with_lease_owner(owner)
    return resolved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Orchestrator lease gate CLI")
    parser.add_argument("--lease-id", default="", help="Lease id to validate")
    args = parser.parse_args(argv)
    try:
        assert_orchestrator_lease_allowed(
            lease_id=args.lease_id.strip() or None,
        )
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
