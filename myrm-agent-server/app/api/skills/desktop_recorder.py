"""
[INPUT]
- fastapi::APIRouter, HTTPException, Depends
- myrm_agent_harness.api::DesktopRecordedEvent, SynthesizedSkillDraft, synthesize_desktop_skill_draft, WorkflowIntentPlan, WorkflowSkillCompiler
- app.api.skills.desktop_recorder_schemas::*
- app.core.skills.store.service::skills_service
- pathlib, time, typing

[OUTPUT]
- router with /desktop-recorder/* endpoints

[POS]
API endpoints for managing Desktop Workflow Skill Recording sessions, synthesizing SKILL.md from events, and publishing to local skills store.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from myrm_agent_harness.api import (
    DesktopRecordedEvent,
    WorkflowIntentPlan,
    WorkflowSkillCompiler,
    synthesize_desktop_skill_draft,
)

from app.api.skills.desktop_recorder_schemas import (
    AnalyzeDesktopPlanRequest,
    AnalyzeDesktopPlanResponse,
    CompileDesktopPlanRequest,
    CompileDesktopPlanResponse,
    PublishDesktopSkillRequest,
    PublishDesktopSkillResponse,
    RecordDesktopEventRequest,
    RecordingSessionState,
    StartDesktopRecordingRequest,
    StartDesktopRecordingResponse,
    StopDesktopRecordingRequest,
    StopDesktopRecordingResponse,
    SynthesizeDesktopSkillRequest,
    WorkflowIntentPlanSchema,
    WorkflowPlanStepSchema,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/desktop-recorder", tags=["skills-desktop-recorder"])

# In-memory session store for active recording sessions (bounded ring-buffer per session)
_ACTIVE_SESSIONS: dict[str, RecordingSessionState] = {}


@router.post("/start", response_model=StartDesktopRecordingResponse)
async def start_desktop_recording(
    request: StartDesktopRecordingRequest,
) -> StartDesktopRecordingResponse:
    """Start a new desktop workflow recording session."""
    session = RecordingSessionState(
        session_id=request.session_id, app_scope=request.app_scope
    )
    _ACTIVE_SESSIONS[request.session_id] = session
    logger.info("Started desktop skill recording session: %s", request.session_id)
    return StartDesktopRecordingResponse(
        session_id=session.session_id,
        status=session.status,
        started_at=session.started_at,
    )


@router.post("/event")
async def record_desktop_event(request: RecordDesktopEventRequest) -> dict[str, Any]:
    """Append a recorded interaction event to the active session."""
    session = _ACTIVE_SESSIONS.get(request.session_id)
    if not session:
        raise HTTPException(
            status_code=404, detail=f"Recording session not found: {request.session_id}"
        )
    if session.status != "recording":
        raise HTTPException(
            status_code=400,
            detail=f"Recording session is not active: status is {session.status}",
        )

    ev = DesktopRecordedEvent(
        seq=request.seq,
        timestamp=time.time(),
        action=request.action,
        app_name=request.app_name,
        bundle_id=request.bundle_id,
        window_title=request.window_title,
        dref_id=request.dref_id,
        element_role=request.element_role,
        element_title=request.element_title,
        value=request.value,
        is_password=request.is_password,
        modifiers=request.modifiers,
        screenshot_b64=request.screenshot_b64,
    )
    session.add_event(ev)
    return {"status": "ok", "recorded_count": len(session.events)}


@router.post("/stop", response_model=StopDesktopRecordingResponse)
async def stop_desktop_recording(
    request: StopDesktopRecordingRequest,
) -> StopDesktopRecordingResponse:
    """Stop the recording session."""
    session = _ACTIVE_SESSIONS.get(request.session_id)
    if not session:
        raise HTTPException(
            status_code=404, detail=f"Recording session not found: {request.session_id}"
        )

    session.status = "stopped"
    session.stopped_at = time.time()
    duration = session.stopped_at - session.started_at
    logger.info(
        "Stopped desktop skill recording session %s with %d events",
        session.session_id,
        len(session.events),
    )

    return StopDesktopRecordingResponse(
        session_id=session.session_id,
        status=session.status,
        event_count=len(session.events),
        duration_seconds=duration,
    )


@router.get("/session/{session_id}")
async def get_desktop_recording_session(session_id: str) -> dict[str, Any]:
    """Get the current recording session state and events."""
    session = _ACTIVE_SESSIONS.get(session_id)
    if not session:
        raise HTTPException(
            status_code=404, detail=f"Recording session not found: {session_id}"
        )

    return {
        "session_id": session.session_id,
        "status": session.status,
        "app_scope": session.app_scope,
        "started_at": session.started_at,
        "stopped_at": session.stopped_at,
        "events_count": len(session.events),
        "events": [e.to_dict() for e in session.events],
    }


@router.post("/synthesize")
async def synthesize_desktop_skill(
    request: SynthesizeDesktopSkillRequest,
) -> dict[str, Any]:
    """Synthesize a structured skill draft from the recorded event trace."""
    session = _ACTIVE_SESSIONS.get(request.session_id)
    if not session:
        raise HTTPException(
            status_code=404, detail=f"Recording session not found: {request.session_id}"
        )
    if not session.events:
        raise HTTPException(
            status_code=400, detail="No events recorded in this session to synthesize."
        )

    draft = synthesize_desktop_skill_draft(
        events=session.events,
        skill_name=request.skill_name,
        description=request.description,
    )
    session.latest_draft = draft
    return draft.to_dict()


@router.post("/analyze-plan", response_model=AnalyzeDesktopPlanResponse)
async def analyze_desktop_plan(
    request: AnalyzeDesktopPlanRequest,
) -> AnalyzeDesktopPlanResponse:
    """Analyze recorded session events into a structured Intent + Ordered Steps Plan."""
    session = _ACTIVE_SESSIONS.get(request.session_id)
    if not session:
        raise HTTPException(
            status_code=404, detail=f"Recording session not found: {request.session_id}"
        )
    if not session.events:
        raise HTTPException(
            status_code=400, detail="No events recorded in this session to analyze."
        )

    # Aggregate events into ordered semantic plan steps
    steps: list[WorkflowPlanStepSchema] = []
    variables: dict[str, str] = {}
    current_app = ""
    step_idx = 1

    for ev in session.events:
        app_name = ev.app_name or "System"
        title = ""
        desc = ""
        tool_hint = (
            "browser_interact_tool"
            if "browser" in app_name.lower() or "chrome" in app_name.lower()
            else "shell_execute"
        )

        if ev.action in ("click", "double_click"):
            elem = ev.element_title or ev.element_role or "target element"
            title = f"Interact with {elem} in {app_name}"
            desc = f"Perform {ev.action} on '{elem}' (Window: {ev.window_title or 'active'})."
        elif ev.action in ("input", "type"):
            var_key = f"input_val_{step_idx}"
            variables[var_key] = f"Input value for {ev.element_title or 'form field'}"
            title = f"Input value into {ev.element_title or 'field'} in {app_name}"
            desc = f"Enter `{{{{{var_key}}}}}` into {ev.element_title or 'input'}."
        elif ev.action == "app_switch" or app_name != current_app:
            current_app = app_name
            title = f"Switch to application {app_name}"
            desc = f"Activate {app_name} (Window: {ev.window_title or 'Main'})."
            tool_hint = ""
        else:
            title = f"Execute {ev.action} in {app_name}"
            desc = f"Action {ev.action} recorded on {ev.window_title or app_name}."

        steps.append(
            WorkflowPlanStepSchema(
                step_id=f"step-{step_idx}",
                title=title,
                description=desc,
                tool_hint=tool_hint,
                target_app=app_name,
                variables_used=(
                    [f"input_val_{step_idx}"] if ev.action in ("input", "type") else []
                ),
            )
        )
        step_idx += 1

    plan = WorkflowIntentPlanSchema(
        name=request.skill_name,
        description=f"Automated multi-app workflow for {request.skill_name}.",
        intent=request.intent_hint
        or f"Automates recorded sequence across {len(set(e.app_name for e in session.events if e.app_name))} applications.",
        steps=steps,
        variables=variables,
        allowed_tools=[
            "browser_navigate_tool",
            "browser_interact_tool",
            "shell_execute",
            "read_file",
            "write_file",
        ],
    )

    harness_plan = WorkflowIntentPlan.from_dict(plan.model_dump())
    validation_errors = WorkflowSkillCompiler.validate_plan(harness_plan)

    return AnalyzeDesktopPlanResponse(
        plan=plan,
        event_count=len(session.events),
        validation_errors=validation_errors,
    )


@router.post("/compile-plan", response_model=CompileDesktopPlanResponse)
async def compile_desktop_plan(
    request: CompileDesktopPlanRequest,
) -> CompileDesktopPlanResponse:
    """Validate and compile a finalized WorkflowIntentPlan into clean SKILL.md markdown."""
    harness_plan = WorkflowIntentPlan.from_dict(request.plan.model_dump())
    validation_errors = WorkflowSkillCompiler.validate_plan(harness_plan)
    markdown_content = WorkflowSkillCompiler.compile(harness_plan)

    return CompileDesktopPlanResponse(
        markdown_content=markdown_content,
        validation_errors=validation_errors,
    )


@router.post("/publish", response_model=PublishDesktopSkillResponse)
async def publish_desktop_skill(
    request: PublishDesktopSkillRequest,
) -> PublishDesktopSkillResponse:
    """Publish the synthesized skill to the local skill store."""
    from app.core.skills.models import DEFAULT_LOCAL_SKILL_PATHS
    from app.core.skills.store.service import skills_service

    safe_name = re_sub_name(request.skill_name)
    if not safe_name:
        raise HTTPException(
            status_code=400,
            detail="Invalid skill name. Must start with letter and contain alphanumerics.",
        )

    config = await skills_service.user_config.get_config()
    target_base = (
        config.local_skill_paths[0]
        if config.local_skill_paths
        else DEFAULT_LOCAL_SKILL_PATHS[0]
    )
    target_dir = Path(target_base).expanduser() / safe_name
    target_dir.mkdir(parents=True, exist_ok=True)

    skill_file = target_dir / "SKILL.md"
    skill_file.write_text(request.markdown_content, encoding="utf-8")
    logger.info("Published recorded desktop skill to %s", skill_file)

    # Invalidate skill cache/version
    try:
        from app.core.skills.config_version import bump_skill_config_version

        bump_skill_config_version()
    except Exception as exc:
        logger.warning("Failed to bump skill config version: %s", exc)

    return PublishDesktopSkillResponse(
        skill_id=safe_name,
        skill_name=request.skill_name,
        status="published",
        file_path=str(skill_file),
    )


def re_sub_name(name: str) -> str:
    """Normalize skill name to alphanumeric snake_case."""
    import re

    cleaned = re.sub(r"[^a-zA-Z0-9_]+", "_", name.strip().lower())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    if cleaned and not cleaned[0].isalpha():
        cleaned = f"skill_{cleaned}"
    return cleaned
