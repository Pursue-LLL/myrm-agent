"""Remote access HTTP routes: tunnel control, pairing tokens, mobile hub.

[POS]
REST API for `/api/v1/remote-access/*` (tunnel, pairing, mobile sessions).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.config.settings import settings
from app.core.utils.response_utils import success_response
from app.remote_access.mobile_gate import PAIR_TOKEN_HEADER, extract_pair_token, pair_token_authorizes_path, requires_mobile_remote_gate
from app.remote_access.pairing import (
    MOBILE_HUB_CONTROL_PURPOSE,
    MOBILE_HUB_LIST_PURPOSE,
    create_pairing_token,
    parse_pairing_token,
    refresh_pairing_token,
)
from app.remote_access.tunnel_manager import get_tunnel_manager
from app.services.agent.gateway import get_agent_gateway

router = APIRouter()


class PairingTokenRequest(BaseModel):
    chat_id: str | None = Field(default=None, min_length=1, max_length=128)
    purpose: str = Field(default=MOBILE_HUB_LIST_PURPOSE, min_length=1, max_length=64)


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
    caller_pair = extract_pair_token(request.headers, request.url.query)
    caller_parsed = parse_pairing_token(caller_pair)
    if caller_parsed and caller_parsed.get("purpose") == MOBILE_HUB_LIST_PURPOSE:
        if not body.chat_id:
            raise HTTPException(status_code=400, detail="chat_id required to open a session")
        gateway = get_agent_gateway()
        active_chat_ids = {
            str(session.get("chatId"))
            for session in gateway.get_active_sessions()
            if session.get("chatId")
        }
        if body.chat_id not in active_chat_ids:
            raise HTTPException(status_code=404, detail="No active session for this chat")
        token = create_pairing_token(chat_id=body.chat_id, purpose=MOBILE_HUB_CONTROL_PURPOSE)
        mobile_path = f"/mobile/status/{body.chat_id}?pair={token}"
        return success_response(data={"token": token, "mobilePath": mobile_path})

    if body.purpose == MOBILE_HUB_LIST_PURPOSE and body.chat_id:
        raise HTTPException(status_code=400, detail="mobile_hub_list tokens must not bind chat_id")
    if body.purpose == MOBILE_HUB_CONTROL_PURPOSE and not body.chat_id:
        raise HTTPException(status_code=400, detail="mobile_hub control tokens require chat_id")
    token = create_pairing_token(chat_id=body.chat_id, purpose=body.purpose)
    if body.chat_id:
        mobile_path = f"/mobile/status/{body.chat_id}?pair={token}"
    else:
        mobile_path = f"/mobile?pair={token}"
    return success_response(data={"token": token, "mobilePath": mobile_path})


@router.post("/pairing-token/refresh", response_model=None)
async def refresh_pairing_token_route(request: Request) -> dict[str, object]:
    token = extract_pair_token(request.headers, request.url.query)
    refreshed = refresh_pairing_token(token)
    if refreshed is None:
        raise HTTPException(status_code=401, detail="Invalid or expired pairing token")
    from app.remote_access.pairing import parse_pairing_token

    body = parse_pairing_token(refreshed)
    chat_id = body.get("chat_id") if body else None
    if isinstance(chat_id, str):
        mobile_path = f"/mobile/status/{chat_id}?pair={refreshed}"
    else:
        mobile_path = f"/mobile?pair={refreshed}"
    return success_response(data={"token": refreshed, "mobilePath": mobile_path})


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
