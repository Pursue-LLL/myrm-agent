"""Apply remote-exposed admission overlays to agent SecurityConfig JSON.

[POS]
Merge harness remote_exposed deny permissions into agent security config.
"""

from __future__ import annotations

from myrm_agent_harness.agent.security.config import remote_exposed_permissions
from myrm_agent_harness.agent.security.trust_context import RequestTrustContext


def merge_remote_security_overlay(
    raw: dict[str, object] | None,
    *,
    trust_zone: str | None,
    admission_path: str | None,
) -> dict[str, object] | None:
    """Tighten tool permissions when the HTTP request arrived via remote-exposed path."""
    ctx = RequestTrustContext.from_admission(
        trust_zone=trust_zone,
        admission_path=admission_path,
    )
    if not ctx.restrict_destructive_tools:
        return raw

    result: dict[str, object] = dict(raw or {})
    permissions_raw = result.get("permissions")
    permissions: dict[str, object] = dict(permissions_raw) if isinstance(permissions_raw, dict) else {}
    permissions.update(remote_exposed_permissions())
    result["permissions"] = permissions
    result["yoloModeEnabled"] = False
    result["yolo_mode_enabled"] = False
    result["requestTrustContext"] = {
        "trustZone": ctx.trust_zone.value,
        "admissionPath": ctx.admission_path,
        "restrictDestructiveTools": ctx.restrict_destructive_tools,
    }
    return result


__all__ = ["merge_remote_security_overlay"]
