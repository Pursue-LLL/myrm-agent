"""Schemas and session state models for Desktop Workflow Skill Recording.

[INPUT]
- pydantic::BaseModel, Field
- myrm_agent_harness.api::DesktopRecordedEvent, SynthesizedSkillDraft

[OUTPUT]
- RecordingSessionState, StartDesktopRecordingRequest, StartDesktopRecordingResponse,
  RecordDesktopEventRequest, StopDesktopRecordingRequest, StopDesktopRecordingResponse,
  SynthesizeDesktopSkillRequest, WorkflowPlanStepSchema, WorkflowIntentPlanSchema,
  AnalyzeDesktopPlanRequest, AnalyzeDesktopPlanResponse, CompileDesktopPlanRequest,
  CompileDesktopPlanResponse, PublishDesktopSkillRequest, PublishDesktopSkillResponse

[POS]
Data transfer objects and active recording session state container for desktop recorder endpoints.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    pass

from app.services.skills.desktop_recording.state import (
    SESSION_IDLE_TIMEOUT_SEC,
    RecordingSessionState,
)


class StartDesktopRecordingRequest(BaseModel):
    session_id: str = Field(..., description="Unique ID for this recording session")
    app_scope: str = Field(default="all", description="Scope of application tracking (all or specific app)")


class StartDesktopRecordingResponse(BaseModel):
    session_id: str
    status: str
    started_at: float
    capture_active: bool = False
    capture_error: str | None = None


class RecordDesktopEventRequest(BaseModel):
    session_id: str
    seq: int
    action: str
    app_name: str = ""
    bundle_id: str | None = None
    window_title: str = ""
    dref_id: str | None = None
    element_role: str | None = None
    element_title: str | None = None
    value: str | None = None
    is_password: bool = False
    modifiers: list[str] = Field(default_factory=list)
    screenshot_b64: str | None = None


class StopDesktopRecordingRequest(BaseModel):
    session_id: str


class StopDesktopRecordingResponse(BaseModel):
    session_id: str
    status: str
    event_count: int
    duration_seconds: float


class SynthesizeDesktopSkillRequest(BaseModel):
    session_id: str
    skill_name: str
    description: str = ""


class WorkflowPlanStepSchema(BaseModel):
    step_id: str
    title: str
    description: str
    tool_hint: str = ""
    target_app: str = ""
    variables_used: list[str] = Field(default_factory=list)


class WorkflowIntentPlanSchema(BaseModel):
    name: str
    description: str = ""
    intent: str = ""
    steps: list[WorkflowPlanStepSchema] = Field(default_factory=list)
    variables: dict[str, str] = Field(default_factory=dict)
    allowed_tools: list[str] = Field(default_factory=list)


class AnalyzeDesktopPlanRequest(BaseModel):
    session_id: str
    skill_name: str = "desktop-workflow-skill"
    intent_hint: str = ""


class AnalyzeDesktopPlanResponse(BaseModel):
    plan: WorkflowIntentPlanSchema
    event_count: int
    validation_errors: list[str] = Field(default_factory=list)


class CompileDesktopPlanRequest(BaseModel):
    plan: WorkflowIntentPlanSchema


class CompileDesktopPlanResponse(BaseModel):
    markdown_content: str
    validation_errors: list[str] = Field(default_factory=list)


class PublishDesktopSkillRequest(BaseModel):
    session_id: str
    skill_name: str
    markdown_content: str
    description: str = ""


class PublishDesktopSkillResponse(BaseModel):
    skill_id: str
    skill_name: str
    status: str
    file_path: str


__all__ = [
    "SESSION_IDLE_TIMEOUT_SEC",
    "RecordingSessionState",
    "StartDesktopRecordingRequest",
    "StartDesktopRecordingResponse",
    "RecordDesktopEventRequest",
    "StopDesktopRecordingRequest",
    "StopDesktopRecordingResponse",
    "SynthesizeDesktopSkillRequest",
    "WorkflowPlanStepSchema",
    "WorkflowIntentPlanSchema",
    "AnalyzeDesktopPlanRequest",
    "AnalyzeDesktopPlanResponse",
    "CompileDesktopPlanRequest",
    "CompileDesktopPlanResponse",
    "PublishDesktopSkillRequest",
    "PublishDesktopSkillResponse",
]
