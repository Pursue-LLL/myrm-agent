"""Pydantic V2 schemas for One-Model Multi-Agent Shared Context Token Budget Governance (Item 52).

[INPUT]
- RegisterRoleBudgetRequest, GovernancePrecheckRequest, RecordConsumptionRequest.

[OUTPUT]
- RoleBudgetSpecDTO, ConsumptionRecordDTO, GovernancePrecheckResponseDTO,
  DoctorNudgeAlertDTO, SharedTokenBudgetSnapshotDTO.

[POS]
- Server-side typed DTO schemas for token budget governance & routing overhead visualization.
"""

from __future__ import annotations

import enum

from pydantic import BaseModel, ConfigDict, Field

PrimitiveValue = str | int | float | bool | None


class ConsumptionCategoryEnum(enum.StrEnum):
    """Categorization of token expenditure in multi-agent runs."""

    ROUTING_OVERHEAD = "routing_overhead"
    EXECUTION_PAYLOAD = "execution_payload"


class NudgeSeverityEnum(enum.StrEnum):
    """Severity of doctor budget and routing warnings."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class RoleBudgetSpecDTO(BaseModel):
    """DTO representing declared budget ceiling and stop condition for an agent role."""

    model_config = ConfigDict(frozen=True)

    role_name: str = Field(..., min_length=1, max_length=128, description="Role name or agent identifier")
    token_ceiling: int = Field(..., ge=1, description="Hard token ceiling for this role")
    stop_condition: str = Field(
        default="halt_and_report",
        description="Stop condition: halt_and_report, degrade_to_lightweight, prompt_user",
    )
    allow_overflow: bool = Field(default=False, description="Whether soft overflow is permitted")


class ConsumptionRecordDTO(BaseModel):
    """DTO representing an individual token consumption record."""

    model_config = ConfigDict(frozen=True)

    record_id: str = Field(..., description="Unique record identifier")
    agent_role: str = Field(..., description="Agent role consuming the tokens")
    category: ConsumptionCategoryEnum = Field(..., description="Routing overhead vs execution payload")
    prompt_tokens: int = Field(..., ge=0, description="Prompt input tokens")
    completion_tokens: int = Field(..., ge=0, description="Completion output tokens")
    total_tokens: int = Field(..., ge=0, description="Total tokens consumed")
    timestamp: float = Field(..., description="Epoch seconds of consumption")
    metadata: dict[str, PrimitiveValue] = Field(default_factory=dict, description="Metadata dictionary")


class RegisterRoleBudgetRequest(BaseModel):
    """Request to declare a token budget ceiling for a specific agent role."""

    role_name: str = Field(..., min_length=1, max_length=128, description="Role name")
    token_ceiling: int = Field(..., ge=100, description="Token ceiling")
    stop_condition: str = Field(default="halt_and_report", description="Stop condition")
    allow_overflow: bool = Field(default=False, description="Allow overflow")


class GovernancePrecheckRequest(BaseModel):
    """Request to precheck fan-out budget before scheduling a turn to a role."""

    role_name: str = Field(..., min_length=1, max_length=128, description="Target role name")
    estimated_tokens: int = Field(..., ge=1, description="Estimated token requirement for fan-out turn")


class GovernancePrecheckResponseDTO(BaseModel):
    """Precheck decision output."""

    model_config = ConfigDict(frozen=True)

    passed: bool = Field(..., description="True if within budget ceilings, False if blocked")
    requested_tokens: int = Field(..., description="Tokens requested in precheck")
    remaining_budget: int = Field(..., description="Remaining token budget")
    reason: str = Field(..., description="Precheck evaluation reason / failure diagnostic")


class RecordConsumptionRequest(BaseModel):
    """Request to register token expenditure."""

    agent_role: str = Field(..., min_length=1, max_length=128, description="Agent role")
    category: ConsumptionCategoryEnum = Field(..., description="Routing overhead or execution payload")
    prompt_tokens: int = Field(..., ge=0, description="Prompt tokens")
    completion_tokens: int = Field(..., ge=0, description="Completion tokens")
    metadata: dict[str, PrimitiveValue] = Field(default_factory=dict, description="Metadata dictionary")


class DoctorNudgeAlertDTO(BaseModel):
    """DTO representing a Doctor Nudge warning for routing overhead or excessive handoffs."""

    model_config = ConfigDict(frozen=True)

    alert_id: str = Field(..., description="Alert identifier")
    severity: NudgeSeverityEnum = Field(..., description="Severity level")
    message: str = Field(..., description="Diagnostic warning message")
    handoff_count: int = Field(..., description="Cumulative handoffs observed")
    routing_ratio: float = Field(..., description="Ratio of routing tokens to total tokens")
    suggested_action: str = Field(..., description="Prescribed remediation action")
    created_at: float = Field(..., description="Alert timestamp")


class SharedTokenBudgetSnapshotDTO(BaseModel):
    """Global snapshot containing token breakdown, role ceilings, and active doctor alerts."""

    model_config = ConfigDict(frozen=True)

    session_id: str = Field(..., description="Chat session ID")
    primary_model: str = Field(..., description="Shared primary model name")
    shared_token_ceiling: int = Field(..., description="Total shared ceiling for session")
    total_tokens_spent: int = Field(..., description="Cumulative total tokens spent")
    routing_tokens_spent: int = Field(..., description="Tokens spent on routing overhead")
    execution_tokens_spent: int = Field(..., description="Tokens spent on execution payloads")
    routing_ratio: float = Field(..., description="Percentage of tokens consumed by routing")
    role_budgets: dict[str, RoleBudgetSpecDTO] = Field(..., description="Role-scoped budget declarations")
    role_usage: dict[str, int] = Field(..., description="Per-role cumulative token usage")
    active_alerts: list[DoctorNudgeAlertDTO] = Field(..., description="Active Doctor Nudge alerts")
