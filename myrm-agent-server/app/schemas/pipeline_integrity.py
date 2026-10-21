"""Pydantic V2 schemas for Open Source Handoff Gap Lint & Pipeline Integrity Doctor Pack (Item 53).

[INPUT]
- LintPipelineRequest, AutoHealPipelineRequest, InspectDecisionChainRequest.

[OUTPUT]
- HandoffMetadataDTO, HandoffStepDTO, PipelineDefinitionDTO,
  HandoffGapDiagnosticDTO, DecisionChainLinkDTO, PipelineIntegrityDoctorReportDTO.

[POS]
- Server-side typed DTO schemas for pipeline integrity linting, gap diagnosis & auto-healing.
"""

from __future__ import annotations

import enum

from pydantic import BaseModel, ConfigDict, Field


class GapCategoryEnum(enum.StrEnum):
    """Categorization of pipeline handoff and integrity gaps."""

    MISSING_HANDOFF_METADATA = "missing_handoff_metadata"
    MISSING_APPROVAL_GATE = "missing_approval_gate"
    MISSING_PUBLISH_ARTIFACT = "missing_publish_artifact"
    MISSING_VERIFICATION_STEP = "missing_verification_step"


class GapSeverityEnum(enum.StrEnum):
    """Severity classification for diagnostics."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class StepStageEnum(enum.StrEnum):
    """Execution stages within a multi-agent pipeline."""

    ROUTING = "routing"
    ANALYSIS = "analysis"
    EXECUTION = "execution"
    REVIEW = "review"
    VERIFICATION = "verification"
    DELIVERY = "delivery"


class HandoffMetadataDTO(BaseModel):
    """Metadata contract accompanying an inter-agent delegation or handoff."""

    model_config = ConfigDict(frozen=True)

    source_agent: str = Field(..., min_length=1, max_length=128, description="Source agent role")
    target_agent: str = Field(..., min_length=1, max_length=128, description="Target agent role")
    transfer_reason: str = Field(..., min_length=1, max_length=512, description="Delegation or transfer justification")
    context_keys: list[str] = Field(default_factory=list, description="Keys carried in handoff context")


class HandoffStepDTO(BaseModel):
    """Specification of an individual step in a multi-agent orchestration pipeline."""

    model_config = ConfigDict(frozen=True)

    step_id: str = Field(..., min_length=1, max_length=64, description="Unique step identifier")
    stage: StepStageEnum = Field(..., description="Pipeline execution stage")
    agent_role: str = Field(..., min_length=1, max_length=128, description="Agent role assigned to this step")
    requires_approval: bool = Field(default=False, description="Whether this step requires human or policy approval")
    requires_verification: bool = Field(default=False, description="Whether this step requires automated verification")
    produced_artifacts: list[str] = Field(default_factory=list, description="Identifiers of artifacts output by this step")
    metadata: HandoffMetadataDTO | None = Field(default=None, description="Accompanying handoff metadata contract")


class PipelineDefinitionDTO(BaseModel):
    """Complete specification of a multi-agent orchestration pipeline."""

    model_config = ConfigDict(frozen=True)

    pipeline_id: str = Field(..., min_length=1, max_length=64, description="Unique pipeline identifier")
    name: str = Field(..., min_length=1, max_length=256, description="Human readable pipeline name")
    steps: list[HandoffStepDTO] = Field(default_factory=list, description="Ordered steps in this pipeline")
    version: str = Field(default="1.0.0", description="Semantic version string")


class HandoffGapDiagnosticDTO(BaseModel):
    """Detailed diagnostic item produced by the Pipeline Integrity Doctor."""

    model_config = ConfigDict(frozen=True)

    rule_id: str = Field(..., description="Unique rule code triggering the finding")
    category: GapCategoryEnum = Field(..., description="Category of integrity gap")
    severity: GapSeverityEnum = Field(..., description="Severity level")
    step_id: str = Field(..., description="Affected step identifier")
    message: str = Field(..., description="Diagnostic explanation")
    suggested_fix: str = Field(..., description="Recommended remediation action")


class DecisionChainLinkDTO(BaseModel):
    """Transparent, inspectable record of an agent delegation decision."""

    model_config = ConfigDict(frozen=True)

    step_id: str = Field(..., description="Step identifier")
    from_role: str = Field(..., description="Source role initiating delegation")
    to_role: str = Field(..., description="Target role assuming execution")
    stage: StepStageEnum = Field(..., description="Execution stage")
    reason: str = Field(..., description="Rationale for delegation")


class PipelineIntegrityDoctorReportDTO(BaseModel):
    """Summary report detailing findings from the pipeline integrity analysis."""

    model_config = ConfigDict(frozen=True)

    pipeline_id: str = Field(..., description="Analyzed pipeline identifier")
    total_steps: int = Field(..., ge=0, description="Total steps inspected")
    is_healthy: bool = Field(..., description="Whether pipeline is free of blocking error gaps")
    gaps: list[HandoffGapDiagnosticDTO] = Field(default_factory=list, description="Detected integrity gaps")
    decision_chain: list[DecisionChainLinkDTO] = Field(default_factory=list, description="Inspectable decision chain")
    scanned_at: float = Field(default=0.0, description="Epoch timestamp of analysis scan")


class LintPipelineRequest(BaseModel):
    """Request payload to analyze a pipeline definition."""

    model_config = ConfigDict(frozen=True)

    pipeline: PipelineDefinitionDTO = Field(..., description="Pipeline definition to lint")


class AutoHealPipelineRequest(BaseModel):
    """Request payload to auto-heal an existing pipeline definition."""

    model_config = ConfigDict(frozen=True)

    pipeline: PipelineDefinitionDTO = Field(..., description="Pipeline definition to remediate")


class InspectDecisionChainRequest(BaseModel):
    """Request payload to extract decision chains from steps."""

    model_config = ConfigDict(frozen=True)

    steps: list[HandoffStepDTO] = Field(..., description="Pipeline steps to inspect")
