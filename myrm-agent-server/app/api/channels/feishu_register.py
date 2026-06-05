"""Feishu/Lark QR scan-to-create Bot registration endpoints.

Proxies the Feishu device-code registration flow, allowing users
to scan a QR code to automatically create a bot application.

[ENDPOINTS]
- POST /channels/manage/feishu/qr-register     - Start registration, get QR URL
- POST /channels/manage/feishu/qr-register/poll - Poll for scan status

[INPUT]
- app.channels.providers.feishu.registration

[OUTPUT]
- router: FastAPI APIRouter for feishu QR registration

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

    __slots__ = ("registration", "device_code", "created_at")

    def __init__(self, registration: FeishuAppRegistration, device_code: str) -> None:
        self.registration = registration
        self.device_code = device_code
        self.created_at = time.monotonic()


_active_sessions: dict[str, _RegistrationSession] = {}


def _cleanup_expired_sessions() -> None:
    """Remove sessions older than TTL to prevent memory leak."""
    now = time.monotonic()
    expired = [sid for sid, s in _active_sessions.items() if now - s.created_at > _SESSION_TTL_S]
    for sid in expired:
        _active_sessions.pop(sid, None)


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


@router.post("/feishu/qr-register", response_model=QRRegisterResponse)
async def start_feishu_qr_register() -> QRRegisterResponse:
    """Start Feishu/Lark QR scan-to-create registration flow.

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
        )

        return QRRegisterResponse(
            session_id=session_id,
            qr_url=result["qr_url"],
            expire_in=result["expire_in"],
            interval=result["interval"],
        )
    except RuntimeError as exc:
        logger.warning("Feishu QR registration init failed: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
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

        await _save_credentials_to_db(creds)

        _active_sessions.pop(body.session_id, None)

        return QRPollResponse(
            status="success",
            credentials={
                "appId": creds["app_id"],
                "appSecret": creds["app_secret"],
                "useLark": str(creds["domain"] == "lark").lower(),
                "botOpenId": creds.get("bot_open_id") or "",
            },
        )

    if poll_result["status"] in ("denied", "expired"):
        _active_sessions.pop(body.session_id, None)

    return QRPollResponse(status=poll_result["status"], credentials=None)


async def _save_credentials_to_db(creds: dict[str, str | None]) -> None:
    """Save registration credentials to UserConfig DB via existing config API."""
    try:
        from sqlalchemy import select

        from app.database.connection import get_session
        from app.database.models import UserConfig
        from app.services.config.encryption import get_encryption_service

        config_key = "feishuCredentials"
        value = {
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

        encryption_service = get_encryption_service()
        encrypted_value = encryption_service.encrypt_config_value(config_key, value)

        async with get_session() as session:
            result = await session.execute(select(UserConfig).where(UserConfig.config_key == config_key))
            existing = result.scalar_one_or_none()

            if existing:
                existing.config_value = encrypted_value
            else:
                session.add(UserConfig(config_key=config_key, config_value=encrypted_value))

            await session.commit()

        logger.info("Feishu QR registration credentials saved to DB")
    except Exception as exc:
        logger.error("Failed to save Feishu registration credentials: %s", exc)
        raise
