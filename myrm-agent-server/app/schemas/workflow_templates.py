"""Pydantic schemas for workflow template library API.

[INPUT]
- (none — leaf module, depends only on pydantic/stdlib)

[OUTPUT]
- WorkflowTemplateSummary: Summary model for template listing
- WorkflowTemplateListResponse: Paginated list wrapper
- SaveWorkflowTemplateRequest: Create/update request body
- SaveWorkflowTemplateFromRunRequest: Save template from an existing run
- WorkflowTemplateDetailResponse: Full template detail with script code and bound Cron count
- AdmitTemplateRunRequest/Response: trunk admission with handoff and prior checklist
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from pydantic.alias_generators import to_camel


class WorkflowTemplateSummary(BaseModel):
    template_id: str
    display_name: str
    script_hash: str
    trust_latch: bool
    required_agent_types: list[str]
    placeholders: list[str] = Field(default_factory=list)
    is_trunk: bool = Field(default=False)
    created_at: str
    updated_at: str

    class Config:
        alias_generator = to_camel
        populate_by_name = True


class WorkflowTemplateListResponse(BaseModel):
    templates: list[WorkflowTemplateSummary]

    class Config:
        alias_generator = to_camel
        populate_by_name = True


class SaveWorkflowTemplateRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=128)
    script_code: str = Field(min_length=1)
    trust_latch: bool = False

    class Config:
        alias_generator = to_camel
        populate_by_name = True


class SaveWorkflowTemplateFromRunRequest(BaseModel):
    chat_id: str = Field(min_length=1, max_length=128)
    message_id: str = Field(min_length=1, max_length=128)
    template_id: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=128)
    trust_latch: bool = False

    class Config:
        alias_generator = to_camel
        populate_by_name = True


class WorkflowTemplateDetailResponse(BaseModel):
    template: WorkflowTemplateSummary
    script_code: str
    bound_cron_count: int = Field(default=0, ge=0)


class AdmitHandoffMaterial(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    excerpt: str = Field(min_length=1, max_length=4000)


class AdmitHandoff(BaseModel):
    # Deliberately lenient: completeness is judged by the evidence gate,
    # which returns friendly reasons instead of validation errors.
    source_flow: str = Field(default="", max_length=128)
    target_flow: str = Field(default="", max_length=128)
    intent: str = Field(default="", max_length=2000)
    materials: list[AdmitHandoffMaterial] = Field(default_factory=list, max_length=20)
    evidence_refs: list[str] = Field(default_factory=list, max_length=20)


class AdmitTemplateRunRequest(BaseModel):
    template_args: dict[str, str] | None = None
    handoff: AdmitHandoff | None = None
    prior_criteria: list[str] | None = None
    prior_deliverable: str | None = None


class AdmitTemplateRunResponse(BaseModel):
    admitted: bool
    template_id: str
    reason_code: str
    user_message: str

    class Config:
        alias_generator = to_camel
        populate_by_name = True
