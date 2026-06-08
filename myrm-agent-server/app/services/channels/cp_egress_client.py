"""Control Plane channel egress client — sandbox outbound bridge.

[INPUT]
- Agent reply messages destined for external channels

[OUTPUT]
- HTTP POST to Control Plane egress endpoint for channel delivery

[POS]
Sandbox-to-CP outbound bridge for delivering agent replies to external channels.
"""

from __future__ import annotations

import logging
import os

import httpx

from app.config.settings import settings
from app.platform_utils.deployment_capabilities import get_deployment_capabilities

logger = logging.getLogger(__name__)

_CP_EGRESS_PATH = "/api/internal/channel/egress"
_TELEMETRY_TOKEN_ENV = "CONTROL_PLANE_TELEMETRY_TOKEN"
_SANDBOX_ID_ENV = "SANDBOX_ID"

SAAS_CP_CHANNELS = frozenset({"feishu", "slack", "discord", "telegram"})


def should_route_via_control_plane(channel: str, metadata: dict[str, object] | None) -> bool:
    """Return True when outbound must go through CP egress (SaaS + CP ingress)."""
    if not get_deployment_capabilities().is_sandbox_instance:
        return False
    if channel not in SAAS_CP_CHANNELS:
        return False
    if isinstance(metadata, dict) and metadata.get("trusted_inbound") == "control_plane":
        return True
    return get_deployment_capabilities().is_sandbox_instance and channel in SAAS_CP_CHANNELS


async def send_via_control_plane(
    *,
    channel: str,
    chat_id: str,
    content: str,
    tenant_id: str,
    reply_to_message_id: str | None = None,
    update_message_id: str | None = None,
    thread_id: str | None = None,
) -> str | None:
    """POST outbound message to CP internal egress API."""
    cp_url = settings.control_plane.url.strip().rstrip("/")
    token = os.getenv(_TELEMETRY_TOKEN_ENV, "").strip()
    sandbox_id = os.getenv(_SANDBOX_ID_ENV, "").strip()
    if not cp_url or not token or not sandbox_id:
        logger.error("CP egress bridge missing config (url/token/sandbox_id)")
        return None

    payload = {
        "channel_type": channel,
        "chat_id": chat_id,
        "content": content,
        "tenant_id": tenant_id,
        "reply_to_message_id": reply_to_message_id,
        "update_message_id": update_message_id,
        "thread_id": thread_id,
    }
    headers = {
        "X-Telemetry-Token": token,
        "X-Sandbox-Id": sandbox_id,
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{cp_url}{_CP_EGRESS_PATH}", json=payload, headers=headers)
        if resp.status_code >= 400:
            logger.error("CP egress failed: %s %s", resp.status_code, resp.text[:200])
            return None
        data = resp.json()
        msg_id = data.get("message_id")
        return str(msg_id) if msg_id else "sent"
    except Exception as exc:
        logger.error("CP egress request error: %s", exc)
        return None
