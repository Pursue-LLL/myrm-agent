"""Effective Managed Approval Policy API (read-only, sandbox env derived).

[INPUT]
- myrm_agent_harness.agent.security.managed_approval_policy::get_process_managed_approval_policy (POS: 进程级 MAP)

[OUTPUT]
- REST GET /security/managed-policy/effective → public MAP payload + active flag
"""

from __future__ import annotations

from fastapi import APIRouter
from myrm_agent_harness.api.security import (
    ManagedApprovalPolicy,
    get_process_managed_approval_policy,
)

router = APIRouter(prefix="/security/managed-policy", tags=["security-managed-policy"])


@router.get("/effective")
async def get_effective_managed_policy() -> dict[str, object]:
    """Return process-wide MAP injected by control plane (empty on local/Tauri)."""
    policy = get_process_managed_approval_policy()
    payload = policy.to_public_dict()
    payload["active"] = policy != ManagedApprovalPolicy.empty()
    return payload
