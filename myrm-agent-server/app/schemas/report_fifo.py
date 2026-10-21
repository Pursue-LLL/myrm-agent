"""[INPUT] Pydantic models for Subagent report delivery wakeup and ordered settlement FIFO REST APIs.
[OUTPUT] Strong DTOs: NamedSubagentInstanceConfigDTO, RegisterSubagentInstanceRequest, SubmitReportRequest, SubmitSettlementRequest, DrainQueueRequest, FifoQueueEnvelopeDTO, QueueDrainResponse, QueueStatusResponse.
[POS] Public schema models for report_fifo multi-agent subsystem.
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class NamedSubagentInstanceConfigDTO(BaseModel):
    """Configuration for multi-named subagent instance declarations."""

    instance_name: str = Field(..., description="Unique instance name (e.g. codex-worker-alpha)")
    role: str = Field(default="specialist", description="Functional specialty role")
    model_name: str = Field(default="deepseek-chat", description="Underlying model target")
    system_prompt: str = Field(default="", description="Dedicated instance system prompt")
    permission_mode: str = Field(default="approve-for-me", description="Unattended execution mode: never / approve-for-me / dangerously-bypass-approvals-and-sandbox")
    report_delivery: str = Field(default="next-step", description="Default report delivery policy: quiet / next-step")
    tools_allowed: List[str] = Field(default_factory=list, description="Permitted tool identifiers")


class RegisterSubagentInstanceRequest(BaseModel):
    """Request payload to register multi-named subagent instances."""

    instances: List[NamedSubagentInstanceConfigDTO] = Field(..., description="List of subagent configs to register")


class SubmitReportRequest(BaseModel):
    """Request payload to submit an active subagent progress report."""

    instance_name: str = Field(..., description="Reporting subagent instance identifier")
    task_id: str = Field(..., description="Associated subtask identifier")
    summary: str = Field(..., description="One-line summary of report findings")
    content: str = Field(default="", description="Detailed report body or diff")
    delivery_mode: Optional[str] = Field(default=None, description="Override delivery mode (quiet / next-step)")
    severity: str = Field(default="normal", description="Severity level: normal / critical")
    metadata: Dict[str, str] = Field(default_factory=dict, description="Metadata tags")


class SubmitSettlementRequest(BaseModel):
    """Request payload to submit automated settlement notice upon task termination."""

    instance_name: str = Field(..., description="Subagent instance identifier")
    task_id: str = Field(..., description="Associated subtask identifier")
    exit_code: int = Field(default=0, description="Termination exit code")
    status: str = Field(default="completed", description="Settlement state: completed / failed / canceled")
    summary: str = Field(default="", description="Automated settlement summary")


class DrainQueueRequest(BaseModel):
    """Request payload to drain ordered queue at parent step boundary."""

    max_items: int = Field(default=50, ge=1, le=200, description="Maximum items to drain in this step batch")


class SubagentReportItemDTO(BaseModel):
    """Active report envelope payload."""

    report_id: str = Field(..., description="Report unique identifier")
    subagent_id: str = Field(..., description="Source subagent ID")
    task_id: str = Field(..., description="Task identifier")
    summary: str = Field(..., description="Report summary")
    content: str = Field(default="", description="Report body")
    delivery_mode: str = Field(..., description="quiet or next-step")
    severity: str = Field(default="normal", description="Severity level: normal / critical")
    timestamp: float = Field(default_factory=time.time, description="Timestamp")
    metadata: Dict[str, str] = Field(default_factory=dict, description="Metadata tags")


class SettlementNoticeItemDTO(BaseModel):
    """Settlement notice envelope payload."""

    settlement_id: str = Field(..., description="Settlement unique identifier")
    subagent_id: str = Field(..., description="Source subagent ID")
    task_id: str = Field(..., description="Task identifier")
    exit_code: int = Field(..., description="Exit code")
    status: str = Field(..., description="Settlement status")
    summary: str = Field(..., description="Settlement summary")
    timestamp: float = Field(default_factory=time.time, description="Timestamp")


class FifoQueueEnvelopeDTO(BaseModel):
    """Strictly ordered queue envelope enforcing Report-before-Settlement."""

    sequence_id: int = Field(..., description="Monotonically increasing sequence number")
    item_type: str = Field(..., description="report or settlement")
    task_id: str = Field(..., description="Task identifier")
    subagent_id: str = Field(..., description="Source subagent instance name")
    wakes_parent: bool = Field(..., description="Whether this triggers parent step wakeup")
    urgent_interrupt: bool = Field(default=False, description="Whether this report urgently interrupts parent execution")
    timestamp: float = Field(..., description="Enqueue timestamp")
    report_payload: Optional[SubagentReportItemDTO] = Field(default=None, description="Report payload if report")
    settlement_payload: Optional[SettlementNoticeItemDTO] = Field(default=None, description="Settlement payload if settlement")


class QueueDrainResponse(BaseModel):
    """Outcome of draining ordered events at a step boundary."""

    drained_items: List[FifoQueueEnvelopeDTO] = Field(default_factory=list, description="Ordered envelopes drained")
    remaining_count: int = Field(default=0, description="Items still pending in queue")
    urgent_interrupt: bool = Field(default=False, description="Whether any drained item carries urgent interruption")
    summary_rollup: str = Field(default="", description="Aggregated natural language rollup summary for the drained batch")


class QueueStatusResponse(BaseModel):
    """Status overview of the ordered FIFO queue."""

    pending_count: int = Field(default=0, description="Pending items count")
    instances_count: int = Field(default=0, description="Registered named instances count")
    items: List[FifoQueueEnvelopeDTO] = Field(default_factory=list, description="All queued items preview")
