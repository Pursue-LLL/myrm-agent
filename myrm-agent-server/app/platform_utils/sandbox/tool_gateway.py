"""Sandbox Unified Tool Gateway credential resolver.

[INPUT]
- Sandbox control-plane gateway URL and auth from settings

[OUTPUT]
- ResolvedToolGatewayConfig for harness tool gateway routing

[POS]
Resolves whether sandbox execution should route tools through the unified gateway.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache

import httpx

from app.config.settings import settings

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT: float = 5.0


@dataclass(frozen=True)
class ResolvedToolGatewayConfig:
    use_gateway: bool
    gateway_url: str
    auth_token: str


def _telemetry_headers() -> dict[str, str] | None:
    cp = settings.control_plane
    base = cp.url.strip().rstrip("/")
    token = cp.telemetry_token.get_secret_value().strip()
    sandbox_id = cp.sandbox_id.strip()
    if not base or not token or not sandbox_id:
        return None
    return {
        "X-Telemetry-Token": token,
        "X-Sandbox-Id": sandbox_id,
        "Content-Type": "application/json",
    }


@lru_cache(maxsize=1)
def fetch_sandbox_tool_gateway_config() -> ResolvedToolGatewayConfig | None:
    """Fetch CP-minted tool gateway credentials once per process (sandbox mode)."""
    from app.platform_utils.deployment_capabilities import get_deployment_capabilities

    if not get_deployment_capabilities().is_sandbox_instance:
        return None

    headers = _telemetry_headers()
    if headers is None:
        logger.warning("Tool gateway resolver skipped: missing CONTROL_PLANE_URL, token, or SANDBOX_ID")
        return None

    base = settings.control_plane.url.strip().rstrip("/")
    sandbox_id = settings.control_plane.sandbox_id.strip()
    url = f"{base}/api/internal/sandboxes/{sandbox_id}/tool-gateway"

    try:
        with httpx.Client(timeout=_REQUEST_TIMEOUT) as client:
            response = client.get(url, headers=headers)
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        logger.warning("Failed to fetch sandbox tool gateway credentials: %s", exc)
        return None

    gateway_url = str(payload.get("gateway_url", "")).strip()
    auth_token = str(payload.get("auth_token", "")).strip()
    use_gateway = bool(payload.get("use_gateway", False))
    if not use_gateway or not gateway_url or not auth_token:
        return None

    return ResolvedToolGatewayConfig(
        use_gateway=True,
        gateway_url=gateway_url,
        auth_token=auth_token,
    )


def merge_tool_gateway_config(
    agent_config: dict[str, object] | None,
) -> dict[str, object] | None:
    """Apply sandbox platform gateway defaults when the agent has no explicit override."""
    from app.config.deploy_mode import is_sandbox

    if not is_sandbox():
        return agent_config

    platform_cfg = fetch_sandbox_tool_gateway_config()
    if platform_cfg is None:
        return agent_config

    if agent_config and agent_config.get("use_gateway"):
        return agent_config

    return {
        "use_gateway": platform_cfg.use_gateway,
        "gateway_url": platform_cfg.gateway_url,
        "auth_token": platform_cfg.auth_token,
    }


def clear_tool_gateway_cache() -> None:
    fetch_sandbox_tool_gateway_config.cache_clear()


__all__ = [
    "ResolvedToolGatewayConfig",
    "clear_tool_gateway_cache",
    "fetch_sandbox_tool_gateway_config",
    "merge_tool_gateway_config",
]
