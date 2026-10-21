"""Pydantic V2 schemas for Conversational Multi-Specialist Summoning & Context Aggregation (Item 54).

[INPUT]
- SummonSpecialistRequest, DetectIntentRequest.

[OUTPUT]
- SpecialistProfileDTO, StructuredAggregationCardDTO, SummonSessionExecutionDTO,
  SpecialistCatalogResponse, DetectIntentResponse.

[POS]
- Server-side typed DTO schemas for specialist summoning, intent detection & structured card returns.
"""

from __future__ import annotations

import enum

from pydantic import BaseModel, ConfigDict, Field


class SpecialistDomainEnum(enum.StrEnum):
    """Vertical domain categories supported by conversational specialists."""

    COPYWRITING_POLISH = "copywriting_polish"
    VISUAL_DESIGN = "visual_design"
    CODE_AUDIT = "code_audit"
    MARKET_RESEARCH = "market_research"
    DATA_ANALYSIS = "data_analysis"


class SummonTriggerSourceEnum(enum.StrEnum):
    """Origin of a specialist invocation."""

    EXPLICIT_MENTION = "explicit_mention"
    INTENT_DETECTION = "intent_detection"


class AggregationCardTypeEnum(enum.StrEnum):
    """Artifact classification of the deliverable returned by the specialist."""

    TEXT_POLISH = "text_polish"
    VISUAL_SPEC = "visual_spec"
    AUDIT_VERDICT = "audit_verdict"
    RESEARCH_REPORT = "research_report"
    DATA_CHART = "data_chart"


class SummonExecutionStatusEnum(enum.StrEnum):
    """Lifecycle status of a specialist isolated execution."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class SpecialistProfileDTO(BaseModel):
    """Specification of a specialist agent eligible for dynamic conversational summoning."""

    model_config = ConfigDict(frozen=True)

    specialist_id: str = Field(..., description="Unique specialist identifier")
    name: str = Field(..., description="Display name of the specialist")
    mention_tag: str = Field(..., description="Invocation mention tag, e.g. @去AI味专家")
    domain: SpecialistDomainEnum = Field(..., description="Vertical specialist domain")
    description: str = Field(..., description="Capability overview")
    system_prompt_addon: str = Field(..., description="Specialist specific system prompt instructions")
    suggested_keywords: list[str] = Field(default_factory=list, description="Keywords for intent sensing")


class StructuredAggregationCardDTO(BaseModel):
    """Standardized structured card contract bridging specialist deliverables back to parent stream."""

    model_config = ConfigDict(frozen=True)

    card_id: str = Field(..., description="Unique aggregation card identifier")
    summon_id: str = Field(..., description="Corresponding summon identifier")
    specialist_id: str = Field(..., description="Identifier of the executing specialist")
    specialist_name: str = Field(..., description="Display name of the executing specialist")
    card_type: AggregationCardTypeEnum = Field(..., description="Artifact category")
    headline: str = Field(..., description="High-level summary headline of deliverable")
    deliverable_payload: str = Field(..., description="Main deliverable content or formatted text")
    artifacts: list[str] = Field(default_factory=list, description="Associated file or payload artifacts")
    created_at: float = Field(default=0.0, description="Epoch timestamp of deliverable generation")


class SummonSessionExecutionDTO(BaseModel):
    """Execution state container for an isolated specialist run."""

    model_config = ConfigDict(frozen=True)

    summon_id: str = Field(..., description="Unique summon identifier")
    chat_id: str = Field(..., description="Parent chat session identifier")
    specialist_id: str = Field(..., description="Executing specialist identifier")
    status: SummonExecutionStatusEnum = Field(..., description="Current execution status")
    trigger_source: SummonTriggerSourceEnum = Field(..., description="How execution was triggered")
    instruction: str = Field(..., description="Cleaned instruction given to specialist")
    aggregation_card: StructuredAggregationCardDTO | None = Field(
        default=None, description="Structured return card if completed"
    )
    execution_seconds: float = Field(default=0.0, description="Execution duration in seconds")
    error_message: str | None = Field(default=None, description="Error details if execution failed")


class SummonSpecialistRequest(BaseModel):
    """Request payload to dispatch a task to a specialized agent."""

    model_config = ConfigDict(frozen=True)

    specialist_id: str = Field(..., description="Identifier of the target specialist")
    instruction: str = Field(..., min_length=1, max_length=4096, description="Task instruction for specialist")
    trigger_source: SummonTriggerSourceEnum = Field(
        default=SummonTriggerSourceEnum.EXPLICIT_MENTION, description="Invocation source"
    )
    parent_context_slice: str = Field(
        default="", max_length=8192, description="Optional brief context slice from parent session"
    )


class DetectIntentRequest(BaseModel):
    """Request payload to scan user text for @-mention or implicit intent keywords."""

    model_config = ConfigDict(frozen=True)

    message: str = Field(..., min_length=1, max_length=4096, description="User input text to inspect")


class DetectIntentResponse(BaseModel):
    """Result of intent or @-mention detection."""

    model_config = ConfigDict(frozen=True)

    matched: bool = Field(..., description="Whether a specialist was matched")
    specialist: SpecialistProfileDTO | None = Field(default=None, description="Matched specialist if any")
    trigger_source: SummonTriggerSourceEnum | None = Field(default=None, description="Detected trigger source")
    cleaned_instruction: str | None = Field(default=None, description="Instruction stripped of mention tag")
