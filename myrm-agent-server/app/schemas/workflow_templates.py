"""Pydantic schemas for workflow template library API."""

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

    class Config:
        alias_generator = to_camel
        populate_by_name = True
