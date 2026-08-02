"""Control Plane internal API client for theme marketplace install side-effects.

[INPUT]
app.config.settings::settings (POS: CP 内部 URL 来源)
app.platform_utils.deployment_capabilities (POS: 部署模式判断)

[OUTPUT]
verify_marketplace_entitlement(theme_id) -> bool
record_marketplace_install(theme_id, user) -> None

[POS]
Server → CP 内部 API 调用：校验用户主题市场 entitlement 和记录安装计数，
self-hosted 模式下跳过 CP 调用。
"""

from __future__ import annotations

import logging
import os

import httpx

from app.config.settings import settings
from app.platform_utils.deployment_capabilities import get_deployment_capabilities

logger = logging.getLogger(__name__)

_VERIFY_ENTITLEMENT_PATH = "/api/internal/theme-marketplace/verify-entitlement"
_RECORD_INSTALL_PATH = "/api/internal/theme-marketplace/record-install"
_TELEMETRY_TOKEN_ENV = "CONTROL_PLANE_TELEMETRY_TOKEN"
_SANDBOX_ID_ENV = "SANDBOX_ID"


def _internal_headers() -> dict[str, str] | None:
    token = os.getenv(_TELEMETRY_TOKEN_ENV, "").strip()
    sandbox_id = os.getenv(_SANDBOX_ID_ENV, "").strip()
    if not token or not sandbox_id:
        return None
    return {
        "X-Telemetry-Token": token,
        "X-Sandbox-Id": sandbox_id,
        "Content-Type": "application/json",
    }


def _cp_base_url() -> str:
    return settings.control_plane.url.strip().rstrip("/")


async def verify_marketplace_entitlement(*, listing_id: str) -> bool:
    """Return True when CP confirms the sandbox user may install this listing."""
    cp_url = _cp_base_url()
    headers = _internal_headers()
    if not cp_url or not headers:
        if get_deployment_capabilities().is_sandbox_instance:
            logger.error("CP entitlement verify unavailable in sandbox mode")
            return False
        return True

    payload = {"listing_id": listing_id}
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                f"{cp_url}{_VERIFY_ENTITLEMENT_PATH}",
                json=payload,
                headers=headers,
            )
        if response.status_code == 200:
            body = response.json()
            return bool(body.get("entitled"))
        logger.error(
            "CP entitlement verify failed: status=%s body=%s",
            response.status_code,
            response.text[:200],
        )
        return False
    except httpx.HTTPError as error:
        logger.error("CP entitlement verify HTTP error: %s", error)
        return False


async def record_marketplace_install(*, listing_id: str) -> None:
    """Notify CP that a marketplace theme was installed (authoritative counter)."""
    cp_url = _cp_base_url()
    headers = _internal_headers()
    if not cp_url or not headers:
        return

    payload = {"listing_id": listing_id}
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                f"{cp_url}{_RECORD_INSTALL_PATH}",
                json=payload,
                headers=headers,
            )
        if response.status_code >= 400:
            logger.warning(
                "CP record-install failed: status=%s body=%s",
                response.status_code,
                response.text[:200],
            )
    except httpx.HTTPError as error:
        logger.warning("CP record-install HTTP error: %s", error)
