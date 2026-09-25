"""Re-exports for Desktop Workflow Skill Recording Schemas.

[INPUT]
- app.schemas.desktop_recorder (POS: 数据模型与 DTO 定义)

[OUTPUT]
- RecordingSessionState, StartDesktopRecordingRequest, StartDesktopRecordingResponse,
  RecordDesktopEventRequest, StopDesktopRecordingRequest, StopDesktopRecordingResponse,
  SynthesizeDesktopSkillRequest, WorkflowPlanStepSchema, WorkflowIntentPlanSchema,
  AnalyzeDesktopPlanRequest, AnalyzeDesktopPlanResponse, CompileDesktopPlanRequest,
  CompileDesktopPlanResponse, PublishDesktopSkillRequest, PublishDesktopSkillResponse

[POS]
API compatibility layer re-exporting schemas from app.schemas.desktop_recorder.
"""

from __future__ import annotations

from app.schemas.desktop_recorder import (
    SESSION_IDLE_TIMEOUT_SEC,
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
