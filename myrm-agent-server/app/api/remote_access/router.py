"""Remote access HTTP routes: tunnel control, pairing tokens, mobile hub."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.config.settings import settings
from app.core.utils.response_utils import success_response
from app.remote_access.mobile_gate import pair_token_authorizes_path, requires_mobile_remote_gate
from app.remote_access.pairing import create_pairing_token
from app.remote_access.tunnel_manager import get_tunnel_manager
from app.services.agent.gateway import get_agent_gateway

router = APIRouter()


class PairingTokenRequest(BaseModel):
    chat_id: str | None = Field(default=None, min_length=1, max_length=128)
    purpose: str = Field(default="mobile_hub", min_length=1, max_length=64)


class PairingTokenResponse(BaseModel):
    token: str
    mobile_path: str


class TunnelStartRequest(BaseModel):
    local_port: int | None = Field(default=None, ge=1, le=65535)


@router.get("/tunnel/status")
async def tunnel_status() -> dict[str, object]:
    status = get_tunnel_manager().status()
    return success_response(
        data={
            "state": status.state.value,
            "publicUrl": status.public_url,
            "error": status.error,
            "provider": status.provider,
        }
    )


@router.post("/tunnel/start")
async def tunnel_start(body: TunnelStartRequest) -> dict[str, object]:
    port = body.local_port or settings.webui.port
    status = await get_tunnel_manager().start(local_port=port)
    if status.state.value == "error":
        raise HTTPException(status_code=503, detail=status.error or "Tunnel start failed")
    return success_response(
        data={
            "state": status.state.value,
            "publicUrl": status.public_url,
            "error": status.error,
            "provider": status.provider,
        }
    )


@router.post("/tunnel/stop")
async def tunnel_stop() -> dict[str, object]:
    status = await get_tunnel_manager().stop()
    return success_response(
        data={
            "state": status.state.value,
            "publicUrl": status.public_url,
            "error": status.error,
            "provider": status.provider,
        }
    )


@router.post("/pairing-token", response_model=None)
async def issue_pairing_token(body: PairingTokenRequest, request: Request) -> dict[str, object]:
    token = create_pairing_token(chat_id=body.chat_id, purpose=body.purpose)
    if body.chat_id:
        mobile_path = f"/mobile/status/{body.chat_id}?pair={token}"
    else:
        mobile_path = f"/mobile?pair={token}"
    return success_response(data={"token": token, "mobilePath": mobile_path})


@router.get("/mobile/sessions")
async def mobile_sessions(
    request: Request,
    pair: str | None = Query(default=None, min_length=8),
) -> dict[str, object]:
    trust_zone = getattr(request.state, "trust_zone", None)
    path = request.url.path
    if requires_mobile_remote_gate(trust_zone=trust_zone, path=path):
        session_user = getattr(request.state, "session_username", None)
        pair_ok = bool(pair and pair_token_authorizes_path(pair, path))
        if not pair_ok and not session_user:
            raise HTTPException(status_code=401, detail="Valid pairing token or WebUI session required")
    elif pair and not pair_token_authorizes_path(pair, path):
        raise HTTPException(status_code=401, detail="Invalid or expired pairing token")

    gateway = get_agent_gateway()
    return success_response(
        data={
            "activeSessions": gateway.get_active_sessions(),
            "maxConcurrent": gateway.config.max_per_user,
            "availableSlots": gateway.get_available_slots(),
        }
    )


__all__ = ["router"]
