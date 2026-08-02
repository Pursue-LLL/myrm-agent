"""Remote access HTTP routes: tunnel control, pairing tokens, mobile hub, node events.

[POS]
REST API for `/api/v1/remote-access/*` (tunnel, pairing, mobile sessions, node event ingestion).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, Request

from app.api.remote_access.schemas import (
    E2EEHelloRequest,
    MobileSpawnRequest,
    NodeEventRequest,
    PAIRING_PURPOSES,
    PairingTokenRequest,
    TunnelStartRequest,
)
from app.config.settings import settings
from app.core.infra.limiter import limiter
from app.core.utils.response_utils import success_response
from app.remote_access.e2ee import (
    e2ee_success_response,
    get_e2ee_session_store,
    load_or_create_daemon_keypair,
)
from app.remote_access.mobile_gate import (
    extract_pair_token,
    pair_token_authorizes_path,
    require_mobile_pair_chat_access,
    requires_mobile_remote_gate,
    resolve_request_pair_token,
)
from app.remote_access.pairing import (
    MOBILE_HUB_CONTROL_PURPOSE,
    create_pairing_token,
    parse_pairing_token,
    refresh_pairing_token,
)
from app.remote_access.pairing_links import (
    mobile_path_for_pairing_token,
    mobile_url_for_path,
)
from app.remote_access.tunnel_manager import get_tunnel_manager
from app.services.agent.gateway import get_agent_gateway

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/e2ee/public-key")
async def e2ee_public_key() -> dict[str, object]:
    keypair = load_or_create_daemon_keypair()
    return success_response(
        data={
            "publicKeyB64": keypair.public_key_b64,
            "algorithm": "nacl-box-curve25519",
        }
    )


@router.post("/e2ee/handshake")
@limiter.limit("30/minute")
async def e2ee_handshake(body: E2EEHelloRequest, request: Request) -> dict[str, object]:
    if body.type != "e2ee_hello":
        raise HTTPException(status_code=400, detail="Expected e2ee_hello")
    keypair = load_or_create_daemon_keypair()
    session = await get_e2ee_session_store().create_from_hello(
        client_public_key_b64=body.key,
        daemon_secret_key=keypair.secret_key,
    )
    return success_response(
        data={
            "type": "e2ee_ready",
            "sessionId": session.session_id,
            "serverPublicKeyB64": keypair.public_key_b64,
        }
    )


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
    if body.purpose not in PAIRING_PURPOSES:
        raise HTTPException(status_code=400, detail="Unsupported pairing token purpose")

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
        mobile_path = mobile_path_for_pairing_token(
            token=token,
            purpose=MOBILE_HUB_CONTROL_PURPOSE,
            chat_id=body.chat_id,
        )
        mobile_url = await mobile_url_for_path(mobile_path)
        return e2ee_success_response(
            request,
            data={"token": token, "mobilePath": mobile_path, "mobileUrl": mobile_url},
        )

    if body.purpose == MOBILE_HUB_LIST_PURPOSE and body.chat_id:
        raise HTTPException(status_code=400, detail="mobile_hub_list tokens must not bind chat_id")
    if body.purpose == MOBILE_HUB_CONTROL_PURPOSE and not body.chat_id:
        raise HTTPException(status_code=400, detail="mobile_hub control tokens require chat_id")
    if body.purpose == BROWSER_TAKEOVER_PURPOSE and not body.chat_id:
        raise HTTPException(status_code=400, detail="browser_takeover tokens require chat_id")
    token = create_pairing_token(chat_id=body.chat_id, purpose=body.purpose)
    mobile_path = mobile_path_for_pairing_token(
        token=token,
        purpose=body.purpose,
        chat_id=body.chat_id,
    )
    mobile_url = await mobile_url_for_path(mobile_path)
    return e2ee_success_response(
        request,
        data={"token": token, "mobilePath": mobile_path, "mobileUrl": mobile_url},
    )


@router.post("/pairing-token/refresh", response_model=None)
async def refresh_pairing_token_route(request: Request) -> dict[str, object]:
    token = extract_pair_token(request.headers, request.url.query)
    refreshed = refresh_pairing_token(token)
    if refreshed is None:
        raise HTTPException(status_code=401, detail="Invalid or expired pairing token")
    from app.remote_access.pairing import parse_pairing_token

    body = parse_pairing_token(refreshed)
    chat_id = body.get("chat_id") if body else None
    purpose = body.get("purpose") if body else MOBILE_HUB_LIST_PURPOSE
    mobile_path = mobile_path_for_pairing_token(
        token=refreshed,
        purpose=purpose if isinstance(purpose, str) else MOBILE_HUB_LIST_PURPOSE,
        chat_id=chat_id if isinstance(chat_id, str) else None,
    )
    mobile_url = await mobile_url_for_path(mobile_path)
    return e2ee_success_response(
        request,
        data={"token": refreshed, "mobilePath": mobile_path, "mobileUrl": mobile_url},
    )


@router.get("/mobile/spawn-options")
async def mobile_spawn_options(
    request: Request,
    pair: str | None = Query(default=None, min_length=8),
) -> dict[str, object]:
    """Return agent and project lists for mobile session spawn form."""
    trust_zone = getattr(request.state, "trust_zone", None)
    path = request.url.path
    pair_token = resolve_request_pair_token(request, pair)
    if requires_mobile_remote_gate(trust_zone=trust_zone, path=path):
        session_user = getattr(request.state, "session_username", None)
        pair_ok = bool(pair_token and pair_token_authorizes_path(pair_token, path))
        if not pair_ok and not session_user:
            raise HTTPException(status_code=401, detail="Valid pairing token or WebUI session required")

    from app.services.agent.agent_service import AgentService
    from app.services.project.project_service import ProjectService

    agents_raw, _ = await AgentService.get_agent_list(page=1, page_size=100)
    agents = [
        {"id": a.id, "name": a.display_name or a.id, "avatar": a.avatar}
        for a in agents_raw
    ]
    projects = await ProjectService.list_projects()
    project_items = [
        {"id": p["id"], "name": p["name"], "color": p.get("color")}
        for p in projects
    ]
    default_agent_id = agents[0]["id"] if agents else None

    return e2ee_success_response(
        request,
        data={
            "agents": agents,
            "projects": project_items,
            "defaultAgentId": default_agent_id,
        },
    )


@router.post("/mobile/spawn")
@limiter.limit("30/minute")
async def mobile_spawn(
    body: MobileSpawnRequest,
    request: Request,
) -> dict[str, object]:
    """Create a new chat session from Mobile Hub and return a scoped pair token."""
    trust_zone = getattr(request.state, "trust_zone", None)
    path = request.url.path
    pair_token = resolve_request_pair_token(request)
    if requires_mobile_remote_gate(trust_zone=trust_zone, path=path):
        session_user = getattr(request.state, "session_username", None)
        pair_ok = bool(pair_token and pair_token_authorizes_path(pair_token, path))
        if not pair_ok and not session_user:
            raise HTTPException(status_code=401, detail="Valid pairing token or WebUI session required")

    import uuid

    from app.database.dto import ChatCreate
    from app.services.chat.chat_crud import ChatService

    chat_id = str(uuid.uuid4())
    chat_data = ChatCreate(
        chat_id=chat_id,
        title=body.initial_message[:80],
        agent_id=body.agent_id,
    )
    await ChatService.create_or_update_chat(chat_data)

    if body.project_id:
        from app.services.project.project_service import ProjectService

        project = await ProjectService.get_project(body.project_id)
        if project:
            await ProjectService.move_chat_to_project(chat_id, body.project_id)

    token = create_pairing_token(chat_id=chat_id, purpose=MOBILE_HUB_CONTROL_PURPOSE)
    mobile_path = mobile_path_for_pairing_token(
        token=token,
        purpose=MOBILE_HUB_CONTROL_PURPOSE,
        chat_id=chat_id,
    )
    mobile_url = await mobile_url_for_path(mobile_path)

    return e2ee_success_response(
        request,
        data={
            "chatId": chat_id,
            "token": token,
            "mobilePath": mobile_path,
            "mobileUrl": mobile_url,
        },
    )


@router.get("/mobile/sessions")
async def mobile_sessions(
    request: Request,
    pair: str | None = Query(default=None, min_length=8),
) -> dict[str, object]:
    trust_zone = getattr(request.state, "trust_zone", None)
    path = request.url.path
    pair_token = resolve_request_pair_token(request, pair)
    if requires_mobile_remote_gate(trust_zone=trust_zone, path=path):
        session_user = getattr(request.state, "session_username", None)
        pair_ok = bool(pair_token and pair_token_authorizes_path(pair_token, path))
        if not pair_ok and not session_user:
            raise HTTPException(status_code=401, detail="Valid pairing token or WebUI session required")
    elif pair_token and not pair_token_authorizes_path(pair_token, path):
        raise HTTPException(status_code=401, detail="Invalid or expired pairing token")

    gateway = get_agent_gateway()
    return e2ee_success_response(
        request,
        data={
            "activeSessions": gateway.get_active_sessions(),
            "maxConcurrent": gateway.config.max_per_user,
            "availableSlots": gateway.get_available_slots(),
        },
    )


@router.get("/mobile/takeover/{chat_id}/snapshot")
async def mobile_takeover_snapshot(
    chat_id: str,
    request: Request,
    pair: str | None = Query(default=None, min_length=8),
) -> dict[str, object]:
    """Return browser snapshot for mobile takeover live preview."""
    trust_zone = getattr(request.state, "trust_zone", None)
    path = request.url.path
    pair_token = resolve_request_pair_token(request, pair)
    if requires_mobile_remote_gate(trust_zone=trust_zone, path=path):
        session_user = getattr(request.state, "session_username", None)
        pair_ok = bool(pair_token and pair_token_authorizes_path(pair_token, path))
        if not pair_ok and not session_user:
            raise HTTPException(status_code=401, detail="Valid pairing token or WebUI session required")
    elif pair_token and not pair_token_authorizes_path(pair_token, path):
        raise HTTPException(status_code=401, detail="Invalid or expired pairing token")

    require_mobile_pair_chat_access(request, chat_id)

    from app.services.agent.browser_snapshot import (
        BrowserSnapshotUnavailableError,
        collect_browser_snapshot_payload,
    )

    try:
        payload = await collect_browser_snapshot_payload(session_id=chat_id)
    except BrowserSnapshotUnavailableError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    return e2ee_success_response(request, data=payload)


# ---------------------------------------------------------------------------
# Node event ingestion — external systems / mobile nodes trigger automation
# ---------------------------------------------------------------------------


@router.post("/node/events")
@limiter.limit("60/minute")
async def receive_node_event(body: NodeEventRequest, request: Request) -> dict[str, object]:
    """Ingest a system event from a paired mobile node or external automation.

    Authenticated via pair_token (hub_list scope) or WebUI session.
    Dispatches the event to CronScheduler.dispatch_system_event which matches
    against active SystemEventTrigger rules.
    """
    trust_zone = getattr(request.state, "trust_zone", None)
    path = request.url.path
    if requires_mobile_remote_gate(trust_zone=trust_zone, path=path):
        pair_token = resolve_request_pair_token(request)
        session_user = getattr(request.state, "session_username", None)
        pair_ok = bool(pair_token and pair_token_authorizes_path(pair_token, path))
        if not pair_ok and not session_user:
            raise HTTPException(status_code=401, detail="Valid pairing token or WebUI session required")

    from app.core.cron.adapters.setup import get_cron_scheduler

    scheduler = get_cron_scheduler()
    try:
        triggered = await scheduler.dispatch_system_event(
            source=body.source,
            event_type=body.event_type,
            payload=body.payload,
        )
    except Exception as exc:
        logger.warning("Node event dispatch failed: %s", exc)
        triggered = 0

    return success_response(data={"triggered": triggered})


__all__ = ["router"]
