"""Apply remote-exposed admission overlays to agent SecurityConfig JSON.

[POS]
Lay harness remote_exposed permissions over the agent security config: a permission they name takes their
value, and a saved denial always stays final.
"""

from __future__ import annotations

from myrm_agent_harness.agent.security.config import layer_permissions, remote_exposed_permissions
from myrm_agent_harness.agent.security.trust_context import RequestTrustContext


def merge_remote_security_overlay(
    raw: dict[str, object] | None,
    *,
    trust_zone: str | None,
    admission_path: str | None,
    device_policy: dict[str, object] | None = None,
) -> dict[str, object] | None:
    """Tighten tool permissions when the HTTP request arrived via remote-exposed path."""
    ctx = RequestTrustContext.from_admission(
        trust_zone=trust_zone,
        admission_path=admission_path,
    )
    result: dict[str, object] = dict(raw or {})
    if device_policy:
        result["devicePolicy"] = device_policy

    if not ctx.restrict_destructive_tools:
        return result if device_policy else raw

    permissions_raw = result.get("permissions")
    result["permissions"] = layer_permissions(
        permissions_raw if isinstance(permissions_raw, dict) else {},
        remote_exposed_permissions(),
    )
    result["yoloModeEnabled"] = False
    result["yolo_mode_enabled"] = False
    result["requestTrustContext"] = {
        "trustZone": ctx.trust_zone.value,
        "admissionPath": ctx.admission_path,
        "restrictDestructiveTools": ctx.restrict_destructive_tools,
    }
    return result


__all__ = ["merge_remote_security_overlay"]
