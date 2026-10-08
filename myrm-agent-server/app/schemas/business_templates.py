"""Pydantic schemas for business scenario experience templates, escalation evaluation and validation feedback.

[INPUT]
- pydantic::{BaseModel, ConfigDict, Field} (POS: validated request and response models)

[OUTPUT]
- ChecklistStepDTO, BusinessExperienceTemplateDTO, ListTemplatesResponseDTO: template catalogue
- EscalationEvaluationRequest, EscalationEvaluationResponseDTO: escalation decision payloads (aliased EvaluateEscalationRequest/EvaluateEscalationResponse)
- RecordValidationRequest, RecordValidationResponseDTO: template validation feedback (response aliased RecordValidationResponse)
- ExportProcedureMemoryItem, ExportProcedureMemoriesResponseDTO: templates exported as procedure memories

[POS]
API contracts of business scenario experience templates, shared by its router and service.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ChecklistStepDTO(BaseModel):
    """Discrete step within a business checklist procedure."""

    model_config = ConfigDict(extra="forbid")

    step_index: int = Field(..., description="1-based step index")
    name: str = Field(..., description="Step title")
    description: str = Field(..., description="Operational guidance for this step")
    mandatory: bool = Field(default=True, description="Whether this step is mandatory")
    validation_rule: str = Field(..., description="Criteria or predicate to verify step completion")


class BusinessExperienceTemplateDTO(BaseModel):
    """DTO representing a business experience template."""

    model_config = ConfigDict(extra="forbid")

    template_id: str = Field(..., description="Unique template identifier")
    name: str = Field(..., description="Template title")
    category: str = Field(..., description="Template category (business_analysis, retail_exchange, escalation_gate)")
    summary: str = Field(..., description="High-level description of review method or procedure")
    checklist_steps: list[ChecklistStepDTO] = Field(default_factory=list, description="Ordered checklist steps")
    boundary_conditions: list[str] = Field(default_factory=list, description="Boundary conditions and constraints")
    sample_trajectory_ref: str = Field(default="", description="Reference session trajectory id")
    version: str = Field(default="1.0.0", description="Semantic version")
    tags: list[str] = Field(default_factory=list, description="Searchable tags")
    metadata: dict[str, str] = Field(default_factory=dict, description="Metadata key-value pairs")
    validated_count: int = Field(default=0, description="Successful validation confirmations")
    rejected_count: int = Field(default=0, description="Disputed or rejected validations")
    last_validated_at: str | None = Field(default=None, description="ISO timestamp of last validation")


class ListTemplatesResponseDTO(BaseModel):
    """Response payload listing business experience templates."""

    model_config = ConfigDict(extra="forbid")

    status: str = Field(default="ok")
    total_count: int = Field(..., description="Total number of templates returned")
    templates: list[BusinessExperienceTemplateDTO] = Field(default_factory=list)


class EscalationEvaluationRequest(BaseModel):
    """Request payload to evaluate an operational or retail context against escalation boundary gates."""

    model_config = ConfigDict(extra="forbid")

    order_id: str | None = Field(default=None, description="Target order identifier")
    user_id: str | None = Field(default=None, description="Customer or actor identifier")
    intent: str = Field(default="", description="Customer intent or request description")
    shipment_status: str = Field(default="delivered", description="Current shipment fulfillment state")
    warranty_valid: bool = Field(default=True, description="Whether item is within warranty/exchange window")
    inventory_available: bool = Field(default=True, description="Whether target exchange SKU has sufficient stock")
    user_dispute_count: int = Field(default=0, description="Number of times customer disputed or corrected the agent")
    is_custom_order: bool = Field(default=False, description="Whether this item is customized or non-refundable")
    policy_clear: bool = Field(default=True, description="Whether applicable return/exchange policy is unambiguous")
    user_confirmed: bool = Field(default=False, description="Whether user explicitly confirmed exchange parameters")


class EscalationEvaluationResponseDTO(BaseModel):
    """Response payload returning human escalation boundary gate decision."""

    model_config = ConfigDict(extra="forbid")

    action: str = Field(..., description="proceed_automated or escalate_to_human")
    reason: str = Field(..., description="Categorical reason for escalation")
    message: str = Field(..., description="Human readable explanation")
    required_context: dict[str, str] = Field(default_factory=dict, description="Context variables collected for human agent")
    suggested_skill_or_tool: str = Field(default="", description="Next recommended skill or routing target")


class RecordValidationRequest(BaseModel):
    """Request payload to record operator or trajectory validation feedback."""

    model_config = ConfigDict(extra="forbid")

    template_id: str = Field(..., description="Target template identifier")
    is_validated: bool = Field(..., description="True if validation confirmed, False if rejected")
    note: str = Field(default="", description="Optional operator notes")


class RecordValidationResponseDTO(BaseModel):
    """Response payload returning validation feedback result."""

    model_config = ConfigDict(extra="forbid")

    status: str = Field(default="ok")
    record_id: str = Field(..., description="Unique record identifier")
    template_id: str = Field(..., description="Target template identifier")
    is_validated: bool = Field(..., description="True if validation confirmed, False if rejected")
    validated_count: int = Field(..., description="Updated cumulative validation confirmations")
    rejected_count: int = Field(..., description="Updated cumulative rejection counts")
    timestamp: str = Field(..., description="ISO 8601 timestamp of validation event")


class ExportProcedureMemoryItem(BaseModel):
    """Exported standard procedure memory entry."""

    model_config = ConfigDict(extra="forbid")

    entry_id: str = Field(..., description="Unique entry ID")
    name: str = Field(..., description="Human readable procedure name")
    retrieval_anchor: str = Field(..., description="Anchor tokens for dual node retrieval")
    operation_intent: str = Field(..., description="Intent and purpose of the procedure")
    preconditions: list[str] = Field(default_factory=list, description="Preconditions")
    immutable_boundary: list[str] = Field(default_factory=list, description="Mandatory boundary rules")
    procedure_steps: list[str] = Field(default_factory=list, description="Ordered steps")
    confidence: float = Field(default=1.0, description="Confidence score")


class ExportProcedureMemoriesResponseDTO(BaseModel):
    """Response payload containing exported standard procedure memory items."""

    model_config = ConfigDict(extra="forbid")

    status: str = Field(default="ok")
    total_count: int = Field(..., description="Total exported procedure items")
    items: list[ExportProcedureMemoryItem] = Field(default_factory=list)


# Aliases for compatibility
EvaluateEscalationRequest = EscalationEvaluationRequest
EvaluateEscalationResponse = EscalationEvaluationResponseDTO
RecordValidationResponse = RecordValidationResponseDTO

