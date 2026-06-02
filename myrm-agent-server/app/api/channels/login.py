"""Channel async login API endpoints.

Provides RESTful API for external channel authentication with real-time SSE.

[ENDPOINTS]
- GET /channels - List channels with login support
- POST /channels/{channel_id}/login/start - Start async login flow
- GET /channels/login/{session_id}/stream - SSE state stream
- DELETE /channels/login/{session_id} - Cancel login
- GET /channels/{channel_id}/login/oauth2/callback - OAuth2 callback

[INPUT]
- channel_id: Channel name (e.g., "wechat")
- method: Login method (e.g., "qr_code", "oauth2")
- session_id: Login session identifier

[OUTPUT]
- JSON responses + SSE event stream

[POS]
Business layer API router. Integrates framework AsyncLoginProtocol with
session management and credentials persistence.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncGenerator

import orjson
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.channels.protocols import LoginMethod, LoginStatus
from app.channels.storage import CredentialsStore, InMemorySessionStore
from app.channels.types import ChannelStatus, StartMode
from app.core.channel_bridge import channel_gateway
from app.schemas.streaming import SSE_RESPONSE_HEADERS

logger = logging.getLogger(__name__)

router = APIRouter()

session_store = InMemorySessionStore()
credentials_store = CredentialsStore()

_active_login_tasks: dict[str, asyncio.Task[None]] = {}
_on_demand_start_locks: dict[str, asyncio.Lock] = {}
_ON_DEMAND_START_TIMEOUT = 30  # seconds; prevents indefinite hang when Node subprocess stalls


class StartLoginRequest(BaseModel):
    """Request body for starting login flow."""

    method: str
    callback_url: str | None = None


class StartLoginResponse(BaseModel):
    """Response for starting login flow."""

    session_id: str
    channel_id: str
    method: str
    stream_url: str


class ChannelInfo(BaseModel):
    """Channel metadata."""

    id: str
    name: str
    supported_login_methods: list[str]


@router.get("", response_model=list[ChannelInfo])
async def list_channels_with_login() -> list[ChannelInfo]:
    """List all channels that support async login.

    Returns:
        List of channels with their supported login methods
    """
    channels_info: list[ChannelInfo] = []

    for channel_name, channel in channel_gateway.bus.channels.items():
        if channel.supported_login_methods:
            channels_info.append(
                ChannelInfo(
                    id=channel_name,
                    name=channel.name,
                    supported_login_methods=[method.value for method in channel.supported_login_methods],
                )
            )

    return channels_info


@router.post("/{channel_id}/login/start", response_model=StartLoginResponse)
async def start_login(
    channel_id: str,
    body: StartLoginRequest,
    request: Request,
) -> StartLoginResponse:
    """Start async login flow for channel.

    Args:
        channel_id: Channel name (e.g., "wechat")
        body: Login method and optional callback URL

    Returns:
        Session ID and SSE stream URL

    Raises:
        HTTPException: If channel not found or method not supported
    """
    channel = channel_gateway.bus.channels.get(channel_id)

    if not channel:
        raise HTTPException(status_code=404, detail=f"Channel {channel_id} not found")

    # On-demand channels need explicit start before login (lock prevents double-start race)
    if channel.start_mode == StartMode.ON_DEMAND and channel.status != ChannelStatus.RUNNING:
        lock = _on_demand_start_locks.setdefault(channel_id, asyncio.Lock())
        async with lock:
            if channel.status != ChannelStatus.RUNNING:
                try:
                    await asyncio.wait_for(channel.start(), timeout=_ON_DEMAND_START_TIMEOUT)
                except asyncio.TimeoutError:
                    logger.error("On-demand channel '%s' start timed out after %ds", channel_id, _ON_DEMAND_START_TIMEOUT)
                    try:
                        await channel.stop()
                    except Exception:
                        pass
                    raise HTTPException(
                        status_code=503,
                        detail=f"Channel {channel_id} start timed out",
                    ) from None
                except Exception as exc:
                    logger.error("Failed to start on-demand channel '%s': %s", channel_id, exc)
                    raise HTTPException(
                        status_code=503,
                        detail=f"Channel {channel_id} failed to start: {exc}",
                    ) from exc

    try:
        method_enum = LoginMethod(body.method)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid login method: {body.method}",
        ) from e

    if method_enum not in channel.supported_login_methods:
        raise HTTPException(
            status_code=400,
            detail=f"Channel {channel_id} does not support {body.method} login",
        )

    session_id = str(uuid.uuid4())
    state_token = str(uuid.uuid4())

    await session_store.create_session(
        session_id=session_id,
        channel_name=channel_id,
        method=body.method,
        state_token=state_token,
    )

    base_url = str(request.base_url).rstrip("/")
    stream_url = f"{base_url}/api/v1/channels/login/{session_id}/stream"

    return StartLoginResponse(
        session_id=session_id,
        channel_id=channel_id,
        method=body.method,
        stream_url=stream_url,
    )


@router.get("/login/{session_id}/stream")
async def stream_login_state(session_id: str, request: Request) -> StreamingResponse:
    """Stream login state updates via Server-Sent Events.

    Args:
        session_id: Login session ID from start_login

    Returns:
        SSE stream of LoginEvent JSON

    Raises:
        HTTPException: If session not found
    """
    session = await session_store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    channel = channel_gateway.bus.channels.get(session.channel_name)

    if not channel:
        raise HTTPException(
            status_code=404,
            detail=f"Channel {session.channel_name} not found",
        )

    async def event_generator() -> AsyncGenerator[str, None]:
        """Generate SSE events from login flow."""
        try:
            method_enum = LoginMethod(session.method)

            callback_url = None
            if method_enum == LoginMethod.OAUTH2:
                base_url = str(request.base_url).rstrip("/")
                callback_url = f"{base_url}/api/channels/{session.channel_name}/login/oauth2/callback"

            async for event in channel.start_login(
                method=method_enum,
                timeout=300.0,
                callback_url=callback_url,
            ):
                event_data = {
                    "timestamp": event.timestamp,
                    "state": {
                        "status": event.state.status.value,
                        "method": event.state.method.value,
                        "qr_code_base64": event.state.qr_code_base64,
                        "qr_expires_at": event.state.qr_expires_at,
                        "oauth_authorization_url": event.state.oauth_authorization_url,
                        "oauth_state_token": event.state.oauth_state_token,
                        "error_message": event.state.error_message,
                        "progress_percent": event.state.progress_percent,
                    },
                    "channel_name": event.channel_name,
                }

                if event.state.status == LoginStatus.SUCCESS and event.credentials:
                    await credentials_store.save(
                        channel_name=session.channel_name,
                        credentials=event.credentials,
                    )
                    event_data["credentials_saved"] = True

                yield f"event: login_state\ndata: {orjson.dumps(event_data).decode("utf-8")}\n\n"

                if event.state.status in (
                    LoginStatus.SUCCESS,
                    LoginStatus.FAILED,
                    LoginStatus.TIMEOUT,
                    LoginStatus.CANCELLED,
                ):
                    break

        except Exception as exc:
            logger.error(
                "Login stream error",
                extra={"session_id": session_id, "error": str(exc)},
                exc_info=True,
            )
            error_event = {
                "timestamp": asyncio.get_event_loop().time(),
                "state": {
                    "status": "failed",
                    "method": session.method,
                    "error_message": str(exc),
                },
                "channel_name": session.channel_name,
            }
            yield f"event: login_state\ndata: {orjson.dumps(error_event).decode("utf-8")}\n\n"

        finally:
            await session_store.delete_session(session_id)
            if session_id in _active_login_tasks:
                del _active_login_tasks[session_id]

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers=SSE_RESPONSE_HEADERS,
    )


@router.delete("/login/{session_id}")
async def cancel_login(session_id: str) -> dict[str, str]:
    """Cancel ongoing login flow.

    Args:
        session_id: Login session ID

    Returns:
        Success message

    Raises:
        HTTPException: If session not found
    """
    session = await session_store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    channel = channel_gateway.bus.channels.get(session.channel_name)

    if channel:
        await channel.cancel_login()

    await session_store.delete_session(session_id)

    if session_id in _active_login_tasks:
        task = _active_login_tasks[session_id]
        task.cancel()
        del _active_login_tasks[session_id]

    return {"status": "cancelled", "session_id": session_id}


@router.get("/{channel_id}/login/oauth2/callback")
async def oauth2_callback(
    channel_id: str,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> dict[str, object]:
    """Handle OAuth2 authorization callback.

    Args:
        channel_id: Channel name
        code: Authorization code (if success)
        state: CSRF state token
        error: OAuth2 error code (if denied)

    Returns:
        Success or error response

    Raises:
        HTTPException: If channel not found or state invalid
    """
    if error:
        return {"status": "error", "error": error}

    if not code or not state:
        raise HTTPException(
            status_code=400,
            detail="Missing code or state parameter",
        )

    channel = channel_gateway.bus.channels.get(channel_id)

    if not channel:
        raise HTTPException(status_code=404, detail=f"Channel {channel_id} not found")

    logger.info(
        "OAuth2 callback received",
        extra={"channel": channel_id, "state": state[:8]},
    )

    try:
        await channel.handle_oauth2_callback(code=code, state=state, error=error)
    except NotImplementedError:
        raise HTTPException(
            status_code=400,
            detail=f"Channel {channel_id} does not support OAuth2 login",
        ) from None
    except Exception as exc:
        logger.error("OAuth2 callback processing failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"OAuth2 callback processing failed: {exc}",
        ) from exc

    return {
        "status": "success",
        "message": "Authorization code received. You can close this window.",
    }
