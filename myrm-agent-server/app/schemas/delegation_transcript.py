# -*- coding: utf-8 -*-
"""Pydantic schemas for subagent live transcript and persistent delegation ledger.

Aligned with Hermes v0.19 delegation transparency, persistent ledger, and MoA reasoning.
Strict typing: No Any types.
"""

from pydantic import BaseModel, Field

JsonPrimitive = str | int | float | bool | None
JsonValue = (
    JsonPrimitive
    | list[JsonPrimitive]
    | dict[str, JsonPrimitive]
    | list[dict[str, JsonPrimitive]]
)


class SubagentTranscriptEventDTO(BaseModel):
    task_id: str
    subagent_id: str
    seq: int = Field(ge=1)
    timestamp: float
    kind: str
    human_readable: str
    payload: dict[str, JsonValue] = Field(default_factory=dict)


class DelegationTaskRecordDTO(BaseModel):
    task_id: str
    session_id: str
    subagent_id: str
    role: str
    prompt: str
    reasoning_effort: str = "medium"
    status: str = "pending"
    created_at: float
    updated_at: float
    finished_at: float | None = None
    checkpoint_step: int = 0
    event_count: int = 0
    artifacts: list[dict[str, str]] = Field(default_factory=list)
    summary: str | None = None
    error_message: str | None = None


class CreateDelegationTaskRequest(BaseModel):
    task_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    subagent_id: str = Field(min_length=1)
    role: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    reasoning_effort: str = Field(default="medium")


class UpdateDelegationStatusRequest(BaseModel):
    status: str = Field(min_length=1)
    summary: str | None = None
    error_message: str | None = None


class SaveCheckpointRequest(BaseModel):
    checkpoint_step: int = Field(ge=0)
    artifacts: list[dict[str, str]] = Field(default_factory=list)


class EmitTranscriptEventRequest(BaseModel):
    subagent_id: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    human_readable: str = Field(min_length=1)
    payload: dict[str, JsonValue] = Field(default_factory=dict)


class SmartApprovalRequestDTO(BaseModel):
    approval_id: str
    task_id: str
    subagent_id: str
    command: str
    command_hash: str
    risk_score: float = Field(ge=0.0, le=1.0)
    risk_reasons: list[str] = Field(default_factory=list)
    created_at: float


class EvaluateCommandApprovalRequest(BaseModel):
    task_id: str = Field(min_length=1)
    subagent_id: str = Field(min_length=1)
    command: str = Field(min_length=1)


class ResolveApprovalRequest(BaseModel):
    decision: str = Field(min_length=1)
    deny_reason: str | None = None


class SmartApprovalResolutionDTO(BaseModel):
    approval_id: str
    decision: str
    deny_reason: str | None = None
    remediation_prompt: str | None = None
    resolved_at: float


class ConsumeApprovalResponse(BaseModel):
    approval_id: str
    consumed: bool
    message: str


class RecoverOrphansResponse(BaseModel):
    recovered_count: int = Field(ge=0)
    recovered_tasks: list[DelegationTaskRecordDTO] = Field(default_factory=list)


class MoAReasoningAllocationRequest(BaseModel):
    role: str = Field(min_length=1)


class MoAReasoningAllocationResponse(BaseModel):
    role: str
    effort: str
    token_budget: int = Field(ge=0)
