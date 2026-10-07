# [POS]: app/schemas/authoritative_conclusions.py
# [INPUT]: None (Standard library & Pydantic)
# [OUTPUT]: AuthoritativeConclusionDTO, ConclusionAuditRecordDTO, ConclusionAnchorProjectionDTO, WriteConclusionRequest, DeprecateConclusionRequest, DeleteConclusionRequest

"""Pydantic schemas and DTOs for Explicit Authoritative Conclusions and Audit Tooling Suite (Item 111)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AuthoritativeConclusionDTO(BaseModel):
    """Data transfer object for authoritative conclusions."""

    conclusion_id: str = Field(description="Unique system identifier for the conclusion")
    peer_id: str = Field(description="Originating participant peer ID (user or agent)")
    content: str = Field(description="Explicit authoritative decision statement")
    status: str = Field(description="Lifecycle status: proposed, confirmed, or deprecated")
    scope_tag: str = Field(description="Domain category (e.g. architecture, security, code_style)")
    created_at: str = Field(description="Creation ISO timestamp")
    confirmed_at: str | None = Field(default=None, description="Confirmation ISO timestamp")
    deprecated_at: str | None = Field(default=None, description="Deprecation ISO timestamp")


class ConclusionAuditRecordDTO(BaseModel):
    """Data transfer object for immutable conclusion audit records."""

    audit_id: str = Field(description="Unique audit record identifier")
    conclusion_id: str = Field(description="Target conclusion identifier")
    action: str = Field(description="Action executed: write, list, deprecate, or delete")
    operator_peer_id: str = Field(description="Actor peer who performed this change")
    previous_status: str | None = Field(default=None, description="Status prior to mutation")
    new_status: str | None = Field(default=None, description="Status after mutation")
    rationale: str = Field(default="", description="Justification or rationale for this action")
    timestamp: str = Field(description="Audit timestamp in ISO format")


class ConclusionAnchorProjectionDTO(BaseModel):
    """Data transfer object for anti-dilution prompt injection block."""

    formatted_prompt_block: str = Field(
        description="Rendered markdown block anchoring active authoritative conclusions"
    )
    total_active_conclusions: int = Field(default=0, description="Count of confirmed conclusions")
    token_estimate: int = Field(default=0, description="Estimated token overhead of anchor block")


class WriteConclusionRequest(BaseModel):
    """Request payload to declare a new authoritative conclusion."""

    content: str = Field(description="Explicit authoritative decision statement")
    peer_id: str = Field(default="user_operator", description="Originating peer identifier")
    scope_tag: str = Field(default="general", description="Domain scope category")
    conclusion_id: str | None = Field(default=None, description="Optional custom conclusion ID")
    auto_confirm: bool = Field(default=True, description="Whether to automatically mark as confirmed")
    rationale: str = Field(default="", description="Optional justification or context note")


class DeprecateConclusionRequest(BaseModel):
    """Request payload to deprecate an existing conclusion."""

    operator_peer_id: str = Field(description="Actor peer marking conclusion as deprecated")
    rationale: str = Field(default="", description="Justification for deprecation")


class DeleteConclusionRequest(BaseModel):
    """Request payload to physically erase a conclusion for PII/policy compliance."""

    operator_peer_id: str = Field(description="Actor peer requesting physical deletion")
    rationale: str = Field(default="", description="Justification for deletion")
