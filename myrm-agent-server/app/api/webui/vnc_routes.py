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
Registers lifecycle hooks on TakeoverCoordinator to capture pre/post
page snapshots and persist TakeoverTrace events to EventLog.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.vnc import TakeoverCoordinator, VncServer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vnc", tags=["vnc"])

_vnc_server: VncServer | None = None
_takeover_coordinator: TakeoverCoordinator | None = None
_pre_takeover_snapshot: str = ""
_pre_takeover_url: str = ""
_takeover_start_time: float = 0.0


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
    learned: bool = False


class TakeoverRequest(BaseModel):
    reason: str = ""


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

            _takeover_coordinator = _Cls(
                on_takeover_start=_on_takeover_start,
                on_takeover_end=_on_takeover_end,
            )
        except ImportError:
            return None
    return _takeover_coordinator


async def _capture_page_state() -> tuple[str, str]:
    """Capture current page ARIA tree and URL from active browser session.

    Returns (aria_tree, page_url). Empty strings if unavailable.
    """
    try:
        from app.services.agent.gateway import get_agent_gateway

        gateway = get_agent_gateway()
        session = gateway.get_active_browser_session()
        if session is None:
            return "", ""

        from myrm_agent_harness.toolkits.browser.session import BrowserSession

        if not isinstance(session, BrowserSession):
            return "", ""

        tab_ctrl = getattr(session, "_tab_controller", None)
        if tab_ctrl is None:
            return "", ""

        page = tab_ctrl.get_active_page()
        if page is None:
            return "", ""

        page_url = page.url

        frame_registry = getattr(session, "_frame_registry", None)
        if frame_registry is None:
            from myrm_agent_harness.toolkits.browser.snapshot.page_snapshot import FrameRegistry

            frame_registry = FrameRegistry(page)

        aria_tree, _, _ = await frame_registry.capture(
            include_iframes=False,
            force_full=True,
            compact=True,
            max_tokens=1500,
        )
        return aria_tree, page_url
    except Exception as e:
        logger.debug("Failed to capture page state for takeover trace: %s", e)
        return "", ""


async def _on_takeover_start(reason: str) -> None:
    """Lifecycle hook: capture pre-takeover page state."""
    global _pre_takeover_snapshot, _pre_takeover_url, _takeover_start_time  # noqa: PLW0603
    _takeover_start_time = time.time()
    _pre_takeover_snapshot, _pre_takeover_url = await _capture_page_state()
    if _pre_takeover_snapshot:
        logger.info("Takeover trace: pre-snapshot captured (url=%s)", _pre_takeover_url)


async def _on_takeover_end(reason: str) -> None:
    """Lifecycle hook: capture post-takeover page state and write TakeoverTrace event."""
    global _pre_takeover_snapshot, _pre_takeover_url, _takeover_start_time  # noqa: PLW0603

    if not _pre_takeover_snapshot:
        return

    post_snapshot, post_url = await _capture_page_state()
    duration_s = round(time.time() - _takeover_start_time, 1)

    pre_snap = _pre_takeover_snapshot
    pre_url = _pre_takeover_url
    _pre_takeover_snapshot = ""
    _pre_takeover_url = ""
    _takeover_start_time = 0.0

    if not post_snapshot:
        return

    has_page_change = (pre_snap != post_snapshot) or (pre_url != post_url)
    if not has_page_change:
        logger.debug("Takeover trace: no page change detected, skipping event")
        return

    trace_data: dict[str, object] = {
        "pre_url": pre_url,
        "post_url": post_url,
        "pre_aria_tree": pre_snap[:3000],
        "post_aria_tree": post_snapshot[:3000],
        "reason": reason,
        "duration_s": duration_s,
    }

    try:
        from app.services.agent.gateway import get_agent_gateway

        gateway = get_agent_gateway()
        result = gateway.get_active_event_log_backend()
        if result is None:
            logger.debug("Takeover trace: no active agent with EventLogBackend")
            return

        session_id, backend = result

        from myrm_agent_harness.agent.event_log.types import EventPayload, StructuredEvent

        event = StructuredEvent(
            sequence=0,
            timestamp=time.time(),
            event_type="takeover_trace",
            session_id=session_id,
            data=EventPayload(**trace_data),
        )
        await backend.append([event])
        logger.info("Takeover trace: event written (session=%s, duration=%.1fs)", session_id, duration_s)
    except Exception as e:
        logger.warning("Failed to write takeover trace event: %s", e)


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
async def vnc_takeover(body: TakeoverRequest | None = None) -> TakeoverResponse:
    """Request human takeover — pauses Agent browser operations."""
    coordinator = _get_takeover()
    if coordinator is None:
        raise HTTPException(status_code=501, detail="Takeover module not available")

    reason = body.reason if body else ""
    info = await coordinator.request_takeover(reason=reason)
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

    had_pre_snapshot = bool(_pre_takeover_snapshot)
    info = await coordinator.resume_agent()
    return TakeoverResponse(
        state=info.state,
        started_at=info.started_at,
        timeout_s=info.timeout_s,
        remaining_s=info.remaining_s,
        learned=had_pre_snapshot,
    )
