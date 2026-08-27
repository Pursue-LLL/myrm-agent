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

import time
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from myrm_agent_harness.api import DesktopRecordedEvent, SynthesizedSkillDraft

_MAX_EVENTS_PER_SESSION = 500


class RecordingSessionState:
    def __init__(self, session_id: str, app_scope: str = "all") -> None:
        self.session_id: str = session_id
        self.app_scope: str = app_scope
        self.status: str = "recording"
        self.started_at: float = time.time()
        self.stopped_at: float | None = None
        self.events: list[DesktopRecordedEvent] = []
        self.latest_draft: SynthesizedSkillDraft | None = None

    def add_event(self, event: DesktopRecordedEvent) -> None:
        if len(self.events) >= _MAX_EVENTS_PER_SESSION:
            self.events.pop(0)
        self.events.append(event)


class StartDesktopRecordingRequest(BaseModel):
    session_id: str = Field(..., description="Unique ID for this recording session")
    app_scope: str = Field(default="all", description="Scope of application tracking (all or specific app)")


class StartDesktopRecordingResponse(BaseModel):
    session_id: str
    status: str
    started_at: float


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
