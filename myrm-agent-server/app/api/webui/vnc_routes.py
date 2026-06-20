"""VNC visual desktop API routes for local mode.

[INPUT]
- myrm_agent_harness.toolkits.vnc::VncServer (POS: VNC server lifecycle manager)
- myrm_agent_harness.toolkits.vnc::TakeoverCoordinator (POS: human-agent control handoff)
- fastapi (POS: HTTP routing)

[OUTPUT]
- router: APIRouter with VNC status/start/stop/takeover/resume endpoints

[POS]
HTTP API layer exposing VNC server control and takeover coordination
for local (non-SaaS) deployments. SaaS mode uses CP API instead.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.vnc import TakeoverCoordinator, VncServer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vnc", tags=["vnc"])

_vnc_server: VncServer | None = None
_takeover_coordinator: TakeoverCoordinator | None = None


class VncStatusResponse(BaseModel):
    available: bool
    status: str
    websocket_port: int = 6080
    password: str = ""
    display_num: int | None = None
    error: str | None = None


class TakeoverResponse(BaseModel):
    state: str
    started_at: float | None = None
    timeout_s: int = 300
    remaining_s: int | None = None


def _get_vnc_server() -> VncServer | None:
    """Lazy-import and cache VncServer singleton."""
    global _vnc_server  # noqa: PLW0603
    if _vnc_server is None:
        try:
            from myrm_agent_harness.toolkits.vnc import VncServer as _Cls

            _vnc_server = _Cls()
        except ImportError:
            return None
    return _vnc_server


def _get_takeover() -> TakeoverCoordinator | None:
    """Lazy-import and cache TakeoverCoordinator singleton."""
    global _takeover_coordinator  # noqa: PLW0603
    if _takeover_coordinator is None:
        try:
            from myrm_agent_harness.toolkits.vnc import TakeoverCoordinator as _Cls

            _takeover_coordinator = _Cls()
        except ImportError:
            return None
    return _takeover_coordinator


@router.get("/status", response_model=VncStatusResponse)
async def vnc_status() -> VncStatusResponse:
    """Get VNC server status and connection info."""
    server = _get_vnc_server()
    if server is None:
        return VncStatusResponse(available=False, status="unavailable", error="VNC module not available")

    if not server.is_available():
        return VncStatusResponse(
            available=False,
            status="unavailable",
            error="VNC requires Linux with DISPLAY, x11vnc, and websockify",
        )

    info = server.get_info()
    return VncStatusResponse(
        available=True,
        status=info.status,
        websocket_port=info.websocket_port,
        password=info.password,
        display_num=info.display_num,
        error=info.error,
    )


@router.post("/start", response_model=VncStatusResponse)
async def vnc_start() -> VncStatusResponse:
    """Start VNC server (lazy). Idempotent."""
    server = _get_vnc_server()
    if server is None:
        raise HTTPException(status_code=501, detail="VNC module not available")

    info = await server.start()
    return VncStatusResponse(
        available=info.status == "running",
        status=info.status,
        websocket_port=info.websocket_port,
        password=info.password,
        display_num=info.display_num,
        error=info.error,
    )


@router.post("/stop")
async def vnc_stop() -> dict[str, str]:
    """Stop VNC server."""
    server = _get_vnc_server()
    if server is None:
        raise HTTPException(status_code=501, detail="VNC module not available")

    await server.stop()
    return {"status": "stopped"}


@router.post("/takeover", response_model=TakeoverResponse)
async def vnc_takeover() -> TakeoverResponse:
    """Request human takeover — pauses Agent browser operations."""
    coordinator = _get_takeover()
    if coordinator is None:
        raise HTTPException(status_code=501, detail="Takeover module not available")

    info = await coordinator.request_takeover()
    return TakeoverResponse(
        state=info.state,
        started_at=info.started_at,
        timeout_s=info.timeout_s,
        remaining_s=info.remaining_s,
    )


@router.post("/resume", response_model=TakeoverResponse)
async def vnc_resume() -> TakeoverResponse:
    """Resume Agent control after takeover."""
    coordinator = _get_takeover()
    if coordinator is None:
        raise HTTPException(status_code=501, detail="Takeover module not available")

    info = await coordinator.resume_agent()
    return TakeoverResponse(
        state=info.state,
        started_at=info.started_at,
        timeout_s=info.timeout_s,
        remaining_s=info.remaining_s,
    )
