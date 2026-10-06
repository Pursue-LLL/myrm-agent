"""
[POS] app/schemas/hindsight_reflection.py
[INPUT] pydantic
[OUTPUT] FailureTurnInput, FailureTrajectoryInput, HindsightRuleResponse, ReflectTaskFailureRequest, ReflectTaskFailureResponse, PreExecutionWarningQuery, PreExecutionWarningResponse, PreExecutionWarningsListResponse, ReflectionBufferStatsResponse
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class FailureTurnInput(BaseModel):
    """Represents a single executed turn within a failed task trajectory."""

    model_config = ConfigDict(extra="forbid")

    turn_index: int = Field(..., ge=1, description="Sequential turn index")
    tool_name: str = Field(..., min_length=1, description="Invoked tool identifier")
    tool_input: dict[str, str | int | float | bool] = Field(
        default_factory=dict, description="Input parameters passed to the tool"
    )
    tool_output: str = Field(default="", description="Output or error from tool execution")
    error_message: str = Field(default="", description="Explicit error or exception message")
    timestamp: float | None = Field(default=None, description="Execution epoch timestamp")


class FailureTrajectoryInput(BaseModel):
    """Sequence of turns comprising a failed task session."""

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(..., min_length=1, description="Unique task or session identifier")
    task_goal: str = Field(..., min_length=1, description="Original user prompt or agent goal")
    turns: list[FailureTurnInput] = Field(
        default_factory=list, description="Ordered history of execution turns"
    )
    terminal_error: str = Field(default="", description="Terminal fatal error description")


class HindsightRuleResponse(BaseModel):
    """Actionable hindsight failure prevention rule."""

    model_config = ConfigDict(extra="forbid")

    rule_id: str
    task_pattern: str
    mistake_signature: str
    correction_advice: str
    tags: list[str]
    confidence: float
    hit_count: int
    created_at: float


class ReflectTaskFailureRequest(BaseModel):
    """Payload to trigger retrospective scrubbing and counterfactual rule extraction."""

    model_config = ConfigDict(extra="forbid")

    trajectory: FailureTrajectoryInput
    max_turns: int = Field(default=5, ge=1, le=20, description="Max recent turns to evaluate")


class ReflectTaskFailureResponse(BaseModel):
    """Outcome of hindsight reflection extraction."""

    model_config = ConfigDict(extra="forbid")

    rule: HindsightRuleResponse
    status: str = "success"
    message: str = "Hindsight reflection extracted and registered"


class PreExecutionWarningQuery(BaseModel):
    """Query payload to match cautionary guidelines before initiating execution."""

    model_config = ConfigDict(extra="forbid")

    task_goal: str = Field(..., min_length=1, description="Upcoming task goal or prompt")
    intended_tools: list[str] | None = Field(
        default=None, description="Optional planned tools to invoke"
    )
    top_k: int = Field(default=3, ge=1, le=10, description="Max warnings to retrieve")


class PreExecutionWarningResponse(BaseModel):
    """Cautionary advisory directive for the agent prior to starting actions."""

    model_config = ConfigDict(extra="forbid")

    rule_id: str
    task_pattern: str
    warning_text: str
    recommended_action: str
    confidence: float


class PreExecutionWarningsListResponse(BaseModel):
    """Aggregated list of proactive pre-execution warnings."""

    model_config = ConfigDict(extra="forbid")

    warnings: list[PreExecutionWarningResponse]
    total_warnings: int
    task_goal: str


class ReflectionBufferStatsResponse(BaseModel):
    """Operational telemetry of the hindsight reflection buffer."""

    model_config = ConfigDict(extra="forbid")

    total_rules: int
    avg_confidence: float
    total_hits: int
