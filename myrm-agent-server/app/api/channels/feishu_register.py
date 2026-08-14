"""Feishu/Lark QR scan-to-create Bot registration endpoints.

Proxies the Feishu device-code registration flow, allowing users
to scan a QR code to automatically create a bot application.

[ENDPOINTS]
- POST /channels/manage/feishu/qr-register     - Start registration, get QR URL
- POST /channels/manage/feishu/qr-register/poll - Poll for scan status

[INPUT]
- app.channels.providers.feishu.registration::FeishuAppRegistration
- app.core.channel_bridge.channel_gateway::add_channel, remove_channel
- app.core.channel_bridge.channel_factory::create_channel_instance, flatten_credential_strings
- app.services.config.service::ConfigService
- app.api.channels.router::channel_credentials_key

[OUTPUT]
- router: FastAPI APIRouter for feishu QR registration
- _save_credentials_to_db / _provision_feishu_instance: 凭据落库与多应用实例创建（失败自动回滚）

[POS]
Business layer API. Bridges harness-layer FeishuAppRegistration with
frontend QR code display and credential persistence via existing config API.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

if TYPE_CHECKING:
    from app.channels.providers.feishu.registration import (
        FeishuAppRegistration,
    )

logger = logging.getLogger(__name__)

router = APIRouter()

_SESSION_TTL_S = 900


class _RegistrationSession:
    """Tracks an active QR registration flow with TTL."""

    __slots__ = ("registration", "device_code", "created_at", "target_display_name")

    def __init__(
        self,
        registration: FeishuAppRegistration,
        device_code: str,
        target_display_name: str | None = None,
    ) -> None:
        self.registration = registration
        self.device_code = device_code
        self.created_at = time.monotonic()
        self.target_display_name = target_display_name


_active_sessions: dict[str, _RegistrationSession] = {}


def _cleanup_expired_sessions() -> None:
    """Remove sessions older than TTL to prevent memory leak."""
    now = time.monotonic()
    expired = [sid for sid, s in _active_sessions.items() if now - s.created_at > _SESSION_TTL_S]
    for sid in expired:
        _active_sessions.pop(sid, None)


class QRRegisterRequest(BaseModel):
    """Request for starting QR registration.

    When *display_name* is provided, the registered bot is provisioned as a
    new channel instance (multi-app support); otherwise it updates the
    default ``feishu`` instance.
    """

    display_name: str | None = None


class QRRegisterResponse(BaseModel):
    """Response for starting QR registration."""

    session_id: str
    qr_url: str
    expire_in: int
    interval: int


class QRPollRequest(BaseModel):
    """Request for polling registration status."""

    session_id: str


class QRPollResponse(BaseModel):
    """Response for polling registration status."""

    status: str  # pending | success | denied | expired
    credentials: dict[str, str | None] | None = None
    instance_id: str | None = None
    channel_name: str | None = None


@router.post("/feishu/qr-register", response_model=QRRegisterResponse)
async def start_feishu_qr_register(
    body: QRRegisterRequest | None = None,
) -> QRRegisterResponse:
    """Start Feishu/Lark QR scan-to-create registration flow.

    When ``body.display_name`` is provided, the resulting bot is provisioned
    as a new multi-app channel instance; otherwise it updates the default
    ``feishu`` instance credentials.

    Returns QR URL for the frontend to render as a QR code image.
    Frontend should poll the companion endpoint for scan status.

    Raises:
        HTTPException: If registration initialization fails
    """
    _cleanup_expired_sessions()
    try:
        from app.channels.providers.feishu.registration import (
            FeishuAppRegistration as _FeishuAppRegistration,
        )

        reg = _FeishuAppRegistration(domain="feishu")
        result = await reg.begin()

        session_id = str(uuid.uuid4())
        _active_sessions[session_id] = _RegistrationSession(
            registration=reg,
            device_code=result["device_code"],
            target_display_name=(body.display_name.strip() if body and body.display_name else None),
        )

        return QRRegisterResponse(
            session_id=session_id,
            qr_url=result["qr_url"],
            expire_in=result["expire_in"],
            interval=result["interval"],
        )
    except RuntimeError as exc:
        logger.warning("Feishu QR registration init failed: %s", exc)
        raise HTTPException(status_code=503, detail="Feishu registration service unavailable") from exc
    except Exception as exc:
        logger.error("Feishu QR registration unexpected error: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Failed to start Feishu registration",
        ) from exc


@router.post("/feishu/qr-register/poll", response_model=QRPollResponse)
async def poll_feishu_qr_register(body: QRPollRequest) -> QRPollResponse:
    """Poll Feishu/Lark QR registration status.

    Frontend should call this every ~5s after displaying the QR code.
    On success, credentials are automatically saved to the config DB.

    Raises:
        HTTPException: If session not found
    """
    _cleanup_expired_sessions()

    session = _active_sessions.get(body.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Registration session not found or expired")

    reg = session.registration

    poll_result = await reg.poll(session.device_code)

    if poll_result["status"] == "success" and poll_result["credentials"]:
        creds = poll_result["credentials"]

        bot_info = await reg.probe_bot(creds["app_id"], creds["app_secret"])
        creds["bot_name"] = bot_info.get("bot_name")
        creds["bot_open_id"] = bot_info.get("bot_open_id")

        instance = await _save_credentials_to_db(
            creds,
            display_name=session.target_display_name,
        )

        _active_sessions.pop(body.session_id, None)

        return QRPollResponse(
            status="success",
            credentials={
                "appId": creds["app_id"],
                "appSecret": creds["app_secret"],
                "useLark": str(creds["domain"] == "lark").lower(),
                "botOpenId": creds.get("bot_open_id") or "",
            },
            instance_id=instance.get("instanceId") if instance else None,
            channel_name=instance.get("channelName") if instance else None,
        )

    if poll_result["status"] in ("denied", "expired"):
        _active_sessions.pop(body.session_id, None)

    return QRPollResponse(status=poll_result["status"], credentials=None)


async def _save_credentials_to_db(
    creds: dict[str, str | None],
    *,
    display_name: str | None = None,
) -> dict[str, str] | None:
    """Save registration credentials to UserConfig DB via ConfigService.

    With *display_name*, the bot is provisioned as a new multi-app instance:
    credentials are persisted under ``feishu_{id}Credentials`` and the channel
    is hot-registered. Otherwise the default ``feishuCredentials`` are updated.

    Returns instance metadata (``instanceId`` / ``channelName``) when a new
    instance was created, else None.
    """
    try:
        value: dict[str, object] = {
            "appId": creds["app_id"],
            "appSecret": creds["app_secret"],
            "botOpenId": creds.get("bot_open_id") or "",
            "verificationToken": "",
            "encryptKey": "",
            "useLark": creds["domain"] == "lark",
            "renderMode": "auto",
            "transport": "websocket",
            "botPolicy": "deny",
        }

        if display_name:
            instance = await _provision_feishu_instance(value, display_name.strip())
            return instance

        from app.services.config.service import ConfigService

        await ConfigService().set("feishuCredentials", value, device_id="feishu-qr-register")

        logger.info("Feishu QR registration credentials saved to DB")
        from app.api.config.router import _try_hot_register_channel

        await _try_hot_register_channel("feishuCredentials")
        return None
    except Exception as exc:
        logger.error("Failed to save Feishu registration credentials: %s", exc)
        raise


async def _provision_feishu_instance(
    value: dict[str, object],
    display_name: str,
) -> dict[str, str]:
    """Create a new Feishu channel instance and persist its credentials.

    Generates a unique instance id, saves the credentials under
    ``feishu_{id}Credentials``, hot-registers the channel in the gateway,
    and records it in the persisted instance list.
    """
    from app.api.channels.router import channel_credentials_key
    from app.core.channel_bridge import channel_gateway
    from app.core.channel_bridge.channel_factory import (
        create_channel_instance as factory_create,
    )
    from app.core.channel_bridge.channel_factory import (
        flatten_credential_strings,
        generate_instance_id,
        load_persisted_instances,
        save_persisted_instances,
    )
    from app.services.config.service import ConfigService

    instance_id = generate_instance_id()
    config_key = channel_credentials_key(f"feishu_{instance_id}")
    registered_name: str | None = None

    try:
        await ConfigService().set(config_key, value, device_id="feishu-qr-register")

        channel = await factory_create(
            channel_type="feishu",
            instance_id=instance_id,
            credentials=flatten_credential_strings(value),
        )
        channel.display_name = display_name
        registered_name = await channel_gateway.add_channel(channel)

        current = await load_persisted_instances()
        current.append(
            {
                "channelType": "feishu",
                "instanceId": instance_id,
                "displayName": display_name,
            }
        )
        await save_persisted_instances(current)
    except Exception:
        # Roll back every side effect of a failed provisioning: delete the
        # persisted credentials (avoid orphaned config keys) and, if the
        # channel was already hot-registered, remove it from the gateway.
        await ConfigService().delete(config_key)
        if registered_name is not None:
            try:
                await channel_gateway.remove_channel(registered_name)
            except Exception:
                logger.warning(
                    "Failed to roll back channel %s after provisioning failure", registered_name, exc_info=True
                )
        raise

    logger.info("Feishu QR registration provisioned instance %s", registered_name)
    return {"instanceId": instance_id, "channelName": registered_name}
