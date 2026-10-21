"""Sandbox entitlement guard — resolves CP internal entitlements for SaaS sandbox mode."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from app.config.settings import settings

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT: float = 5.0


@dataclass(frozen=True)
class SandboxEntitlement:
    plan: str
    enable_cron: bool
    enable_public_ingress: bool
    max_cron_triggers: int
    balance_wu: int
    enable_subagent: bool
    enable_vnc: bool


class EntitlementGuardError(Exception):
    """Raised when entitlement check fails or feature is not allowed."""


def _headers() -> dict[str, str]:
    cp = settings.control_plane
    return {
        "X-Telemetry-Token": cp.telemetry_token.get_secret_value(),
        "X-Sandbox-Id": cp.sandbox_id,
        "Content-Type": "application/json",
    }


def _base_url() -> str:
    return settings.control_plane.url.strip().rstrip("/")


def fetch_sandbox_entitlements() -> SandboxEntitlement | None:
    """Fetch entitlements from CP internal API. Returns None when not configured."""
    from app.platform_utils.deployment_capabilities import get_deployment_capabilities

    if not get_deployment_capabilities().uses_cp_entitlements:
        return None

    cp = settings.control_plane
    base = _base_url()
    token = cp.telemetry_token.get_secret_value()
    sandbox_id = cp.sandbox_id
    if not base or not token or not sandbox_id:
        logger.warning("Entitlement guard skipped: missing CONTROL_PLANE_URL, token, or SANDBOX_ID")
        return None

    try:
        with httpx.Client(timeout=_REQUEST_TIMEOUT) as client:
            response = client.get(f"{base}/api/internal/billing/entitlements", headers=_headers())
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        logger.error("Failed to fetch sandbox entitlements: %s", exc)
        raise EntitlementGuardError("Entitlement service unavailable") from exc

    return SandboxEntitlement(
        plan=str(payload.get("plan", "free")),
        enable_cron=bool(payload.get("enable_cron", False)),
        enable_public_ingress=bool(payload.get("enable_public_ingress", False)),
        max_cron_triggers=int(payload.get("max_cron_triggers", 0)),
        balance_wu=int(payload.get("balance_wu", 0)),
        enable_subagent=bool(payload.get("enable_subagent", False)),
        enable_vnc=bool(payload.get("enable_vnc", False)),
    )


def require_cron_entitlement() -> None:
    entitlements = fetch_sandbox_entitlements()
    if entitlements is None:
        return
    if not entitlements.enable_cron:
        raise EntitlementGuardError("Cron is not available on the current plan. Upgrade to Companion or above.")


def require_cron_slot(current_job_count: int) -> None:
    """Ensure the user has not exceeded max_cron_triggers for their plan."""
    entitlements = fetch_sandbox_entitlements()
    if entitlements is None:
        return
    require_cron_entitlement()
    if current_job_count >= entitlements.max_cron_triggers:
        raise EntitlementGuardError(
            f"Cron job limit reached ({entitlements.max_cron_triggers}). Upgrade your plan for more scheduled tasks."
        )


def require_public_ingress_entitlement() -> None:
    entitlements = fetch_sandbox_entitlements()
    if entitlements is None:
        return
    if not entitlements.enable_public_ingress:
        raise EntitlementGuardError("Public ingress is not available on the current plan. Upgrade to Companion or above.")


def require_subagent_entitlement() -> None:
    """No-op: subagent is a base capability; Work Unit balance gates consumption."""
    return


def require_vnc_entitlement() -> None:
    entitlements = fetch_sandbox_entitlements()
    if entitlements is None:
        return
    if not entitlements.enable_vnc:
        raise EntitlementGuardError("Visual desktop (VNC) is not available on the current plan. Upgrade to Pro or above.")
