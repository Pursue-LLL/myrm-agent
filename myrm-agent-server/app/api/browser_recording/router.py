"""Browser Recording API — WebSocket + REST endpoints.


[INPUT]
- app.services.browser_recording.session_manager (POS: session lifecycle management)
- app.services.browser_recording.skill_generator (POS: skill generation from sessions)
- app.services.agent.gateway (POS: access to active BrowserSession via AgentGateway)
- app.core.infra.ws_origin_guard (POS: WebSocket origin verification)

[OUTPUT]
- router: FastAPI APIRouter with recording endpoints

[POS]
HTTP/WebSocket entry layer for Browser Skill Recording Wizard.
WebSocket `/ws/recording` for real-time control, REST for session queries and skill generation.
On `start`, bridges ActionCaptureEngine (Harness) to the active BrowserSession's Page,
forwarding captured steps to the frontend via WebSocket in real-time.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from app.api.browser_recording.schemas import (
    GenerateSkillRequest,
    GenerateSkillResponse,
    RecordingSessionResponse,
    RecordingStepResponse,
)
from app.core.infra.ws_origin_guard import verify_ws_origin
from app.services.browser_recording.session_manager import (
    get_session,
    get_session_export,
    list_active_sessions,
    register_session,
    step_to_dict,
)
from app.services.browser_recording.skill_generator import (
    generate_skill_from_session,
)

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.browser.action_capture import ActionStep

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/recording/sessions")
async def list_sessions() -> list[dict[str, object]]:
    """List active recording sessions."""
    return list_active_sessions()


@router.get("/recording/sessions/{session_id}", response_model=RecordingSessionResponse)
async def get_session_detail(session_id: str) -> RecordingSessionResponse:
    """Get recording session details with all steps."""
    export = get_session_export(session_id, include_screenshots=False)
    if not export:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

    steps = [RecordingStepResponse(**s) for s in export.get("steps", [])]  # type: ignore[arg-type]
    return RecordingSessionResponse(
        session_id=str(export["session_id"]),
        status=str(export["status"]),
        start_url=str(export.get("start_url", "")),
        step_count=int(export.get("step_count", 0)),
        steps=steps,
    )


@router.post("/recording/generate-skill", response_model=GenerateSkillResponse)
async def generate_skill(req: GenerateSkillRequest) -> GenerateSkillResponse:
    """Generate a Browser Skill from a completed recording session."""
    session = get_session(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session not found: {req.session_id}")

    if session.status != "stopped":
        raise HTTPException(
            status_code=400,
            detail=f"Session must be stopped before generating skill. Current status: {session.status}",
        )

    if not session.steps:
        raise HTTPException(status_code=400, detail="No recorded steps in session")

    skill_id, _content, credential_placeholders = generate_skill_from_session(
        session=session,
        skill_name=req.skill_name,
        description=req.description,
    )

    return GenerateSkillResponse(
        skill_id=skill_id,
        skill_name=req.skill_name,
        description=req.description or f"Browser skill from recording {req.session_id}",
        step_count=len(session.steps),
        credential_placeholders=credential_placeholders,
    )


class _WsStepForwarder:
    """Bridges ActionCaptureEngine callbacks to a WebSocket client."""

    def __init__(self, ws: WebSocket) -> None:
        self._ws = ws

    async def on_step(self, step: ActionStep) -> None:
        try:
            await self._ws.send_text(json.dumps({"type": "step", **step_to_dict(step)}))
        except Exception:
            pass


def _get_active_page() -> object | None:
    """Retrieve the Playwright Page from the active Agent's BrowserSession."""
    from app.services.agent.gateway import get_agent_gateway

    session = get_agent_gateway().get_active_browser_session()
    if session is None:
        return None
    tab_ctrl = getattr(session, "_tab_controller", None)
    if tab_ctrl is None:
        return None
    try:
        return tab_ctrl.get_active_page()
    except Exception:
        return None


@router.websocket("/ws/recording")
async def recording_websocket(ws: WebSocket) -> None:
    """WebSocket endpoint for real-time recording control.

    Client messages:
        {"type": "start", "url": "..."} — start recording (binds to Agent's active Page)
        {"type": "stop"} — stop recording
        {"type": "pause"} — pause recording
        {"type": "resume"} — resume recording
        {"type": "step", ...} — manually inject a step (fallback when no Page)
        {"type": "delete_step", "seq": N} — delete a step
        {"type": "ping"} — keepalive

    Server messages:
        {"type": "session_started", "session_id": "...", "mode": "auto"|"manual"}
        {"type": "step", ...} — new step captured
        {"type": "session_stopped", "session_id": "...", "step_count": N}
        {"type": "error", "message": "..."}
        {"type": "pong"}
    """
    if not await verify_ws_origin(ws):
        return
    await ws.accept()
    logger.info("Recording WebSocket client connected")

    from myrm_agent_harness.toolkits.browser.action_capture import (
        ActionCaptureEngine,
        ActionStep,
        ActionType,
        CaptureSession,
    )

    capture_engine: ActionCaptureEngine | None = None
    forwarder: _WsStepForwarder | None = None
    current_session: CaptureSession | None = None

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_text(json.dumps({"type": "error", "message": "Invalid JSON"}))
                continue

            msg_type = msg.get("type", "")

            if msg_type == "ping":
                await ws.send_text(json.dumps({"type": "pong"}))

            elif msg_type == "start":
                page = _get_active_page()
                mode = "auto" if page is not None else "manual"

                if page is not None:
                    capture_engine = ActionCaptureEngine(page, capture_screenshots=True)
                    forwarder = _WsStepForwarder(ws)
                    capture_engine.add_callback(forwarder)
                    current_session = await capture_engine.start(start_url=msg.get("url", ""))
                else:
                    session_id = uuid.uuid4().hex[:12]
                    current_session = CaptureSession(
                        session_id=session_id,
                        start_url=msg.get("url", ""),
                        start_time=time.time(),
                    )

                register_session(current_session)
                await ws.send_text(json.dumps({
                    "type": "session_started",
                    "session_id": current_session.session_id,
                    "mode": mode,
                }))
                if mode == "manual":
                    logger.info("Recording started in manual mode (no active browser page)")

            elif msg_type == "stop":
                if capture_engine:
                    await capture_engine.stop()
                    capture_engine = None
                if current_session:
                    current_session.status = "stopped"
                    await ws.send_text(json.dumps({
                        "type": "session_stopped",
                        "session_id": current_session.session_id,
                        "step_count": len(current_session.steps),
                    }))
                    current_session = None

            elif msg_type == "pause":
                if capture_engine:
                    await capture_engine.pause()
                elif current_session and current_session.status == "recording":
                    current_session.status = "paused"
                await ws.send_text(json.dumps({"type": "paused"}))

            elif msg_type == "resume":
                if capture_engine:
                    await capture_engine.resume()
                elif current_session and current_session.status == "paused":
                    current_session.status = "recording"
                await ws.send_text(json.dumps({"type": "resumed"}))

            elif msg_type == "step":
                if not current_session or current_session.status != "recording":
                    await ws.send_text(json.dumps({
                        "type": "error",
                        "message": "No active recording session",
                    }))
                    continue

                try:
                    action_type = ActionType(msg.get("action", "click"))
                except ValueError:
                    await ws.send_text(json.dumps({
                        "type": "error",
                        "message": f"Unknown action type: {msg.get('action')}",
                    }))
                    continue

                step = ActionStep(
                    seq=current_session.next_seq,
                    action=action_type,
                    selector=msg.get("selector", ""),
                    value=msg.get("value", ""),
                    url=msg.get("url", ""),
                    title=msg.get("title", ""),
                    element_text=msg.get("element_text", ""),
                    element_role=msg.get("element_role", ""),
                    is_password=msg.get("is_password", False),
                    screenshot_b64=msg.get("screenshot_b64"),
                )
                current_session.add_step(step)
                await ws.send_text(json.dumps({
                    "type": "step",
                    **step_to_dict(step),
                }))

            elif msg_type == "delete_step":
                if not current_session:
                    continue
                seq = msg.get("seq")
                if seq is not None:
                    current_session.steps = [s for s in current_session.steps if s.seq != seq]
                    await ws.send_text(json.dumps({
                        "type": "step_deleted",
                        "seq": seq,
                    }))

    except WebSocketDisconnect:
        logger.info("Recording WebSocket client disconnected")
    except Exception as exc:
        logger.error(f"Recording WebSocket error: {exc}")
    finally:
        if capture_engine:
            try:
                await capture_engine.stop()
            except Exception:
                pass
            if forwarder:
                capture_engine.remove_callback(forwarder)
        if current_session:
            if current_session.status in ("recording", "paused"):
                current_session.status = "stopped"
