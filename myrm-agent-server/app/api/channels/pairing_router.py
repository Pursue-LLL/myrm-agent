"""Channel Pairing & Handshake API Router.

[INPUT]
- services.channels.pairing::pairing_types (POS: 请求响应数据契约)
- services.channels.pairing::channel_handshake_service (POS: 配对握手服务单例)
- fastapi: APIRouter, HTTPException, Depends

[OUTPUT]
- pairing_router: FastApi APIRouter 暴露可视化配对会话生命周期与一键连通性自测端点

[POS]
API 层路由。为前端可视化向导提供模型无关化的渠道动态扫码、会话状态机轮询、Token 绑定与 Ping 测试能力。
"""

from __future__ import annotations

import logging
from fastapi import APIRouter, HTTPException

from app.services.channels.pairing.channel_handshake_service import (
    channel_handshake_service,
)
from app.services.channels.pairing.pairing_types import (
    ChannelPingRequest,
    ChannelPingResponse,
    PairingConfirmRequest,
    PairingConfirmResponse,
    PairingSessionCreateRequest,
    PairingSessionResponse,
)

logger = logging.getLogger(__name__)

pairing_router = APIRouter()


@pairing_router.post("/session", response_model=PairingSessionResponse)
async def create_pairing_session(
    request: PairingSessionCreateRequest,
) -> PairingSessionResponse:
    """Create a new model-agnostic visual pairing session with dynamic QR code."""
    try:
        return channel_handshake_service.create_pairing_session(request)
    except Exception as exc:
        logger.error("Failed to create channel pairing session: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@pairing_router.get("/session/{session_id}", response_model=PairingSessionResponse)
async def get_pairing_session_status(
    session_id: str,
) -> PairingSessionResponse:
    """Retrieve current state of a pairing session."""
    session = channel_handshake_service.get_session_status(session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail=f"Pairing session '{session_id}' not found.",
        )
    return session


@pairing_router.post(
    "/session/{session_id}/confirm",
    response_model=PairingConfirmResponse,
)
async def confirm_pairing_session(
    session_id: str,
    request: PairingConfirmRequest,
) -> PairingConfirmResponse:
    """Submit scan confirmation or webhook callback to finalize token binding."""
    result = await channel_handshake_service.confirm_pairing(session_id, request)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Pairing session '{session_id}' not found.",
        )
    return result


@pairing_router.post("/verify-ping", response_model=ChannelPingResponse)
async def verify_channel_ping(
    request: ChannelPingRequest,
) -> ChannelPingResponse:
    """Send an immediate ping test message and return real round-trip delivery latency."""
    try:
        return await channel_handshake_service.verify_ping(request)
    except Exception as exc:
        logger.error("Channel ping verification failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
