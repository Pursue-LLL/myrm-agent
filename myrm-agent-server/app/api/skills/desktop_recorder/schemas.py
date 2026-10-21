"""Desktop Workflow Skill Recorder request/response contract.

[INPUT]
- app.schemas.desktop_recorder (POS: 请求/响应 DTO)
- app.services.skills.desktop_recording::state (POS: 会话运行时状态容器)

[OUTPUT]
- SESSION_IDLE_TIMEOUT_SEC, RecordingSessionState, StartDesktopRecordingRequest,
  StartDesktopRecordingResponse, RecordDesktopEventRequest, StopDesktopRecordingRequest,
  StopDesktopRecordingResponse, SynthesizeDesktopSkillRequest, WorkflowPlanStepSchema,
  WorkflowIntentPlanSchema, AnalyzeDesktopPlanRequest, AnalyzeDesktopPlanResponse,
  CompileDesktopPlanRequest, CompileDesktopPlanResponse, PublishDesktopSkillRequest,
  PublishDesktopSkillResponse

[POS]
Recorder endpoint contract for the API layer: re-exports the shared DTOs and the service-owned
session state, so the API depends on services rather than the reverse.
"""

from __future__ import annotations

from app.schemas.desktop_recorder import (
    AnalyzeDesktopPlanRequest,
    AnalyzeDesktopPlanResponse,
    CompileDesktopPlanRequest,
    CompileDesktopPlanResponse,
    PublishDesktopSkillRequest,
    PublishDesktopSkillResponse,
    RecordDesktopEventRequest,
    StartDesktopRecordingRequest,
    StartDesktopRecordingResponse,
    StopDesktopRecordingRequest,
    StopDesktopRecordingResponse,
    SynthesizeDesktopSkillRequest,
    WorkflowIntentPlanSchema,
    WorkflowPlanStepSchema,
)
from app.services.skills.desktop_recording.state import (
    SESSION_IDLE_TIMEOUT_SEC,
    RecordingSessionState,
)

__all__ = [
    "SESSION_IDLE_TIMEOUT_SEC",
    "AnalyzeDesktopPlanRequest",
    "AnalyzeDesktopPlanResponse",
    "CompileDesktopPlanRequest",
    "CompileDesktopPlanResponse",
    "PublishDesktopSkillRequest",
    "PublishDesktopSkillResponse",
    "RecordDesktopEventRequest",
    "RecordingSessionState",
    "StartDesktopRecordingRequest",
    "StartDesktopRecordingResponse",
    "StopDesktopRecordingRequest",
    "StopDesktopRecordingResponse",
    "SynthesizeDesktopSkillRequest",
    "WorkflowIntentPlanSchema",
    "WorkflowPlanStepSchema",
]
