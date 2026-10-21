"""Pydantic V2 schemas for Subagent Workspace Context Inheritance & Prompt Enrichment (Item 56).

[INPUT]
- InspectWorkspaceRulesRequest, EnrichChildPromptRequest.

[OUTPUT]
- ContextRuleSnippetDTO, InspectWorkspaceRulesResponse, EnrichChildPromptResponse,
  InheritanceAuditRecordDTO, InheritanceAuditHistoryResponse.

[POS]
- Server-side typed DTO schemas for workspace context discovery, token budget capping,
  and child agent prompt enrichment.
"""

from __future__ import annotations

import enum

from pydantic import BaseModel, ConfigDict, Field


class ContextSourceTypeEnum(enum.StrEnum):
    """Source classification of inherited workspace rules."""

    RULES = ".rules"
    AGENTS_MD = "AGENTS.md"
    README_MD = "README.md"
    CUSTOM = "custom"


class RulePriorityEnum(enum.StrEnum):
    """Priority weights for context budget capping and differential compacting."""

    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class SubagentRoleEnum(enum.StrEnum):
    """Role classification directing context enrichment focus."""

    WORKER = "worker"
    REVIEWER = "reviewer"
    SPECIALIST = "specialist"
    COORDINATOR = "coordinator"


class ContextRuleSnippetDTO(BaseModel):
    """Parsed rule snippet extracted from a workspace context document."""

    model_config = ConfigDict(frozen=True)

    source_type: ContextSourceTypeEnum = Field(..., description="Document source classification")
    file_path: str = Field(..., description="Absolute or relative file path")
    priority: RulePriorityEnum = Field(..., description="Assigned priority weight")
    title: str = Field(..., description="Section or rule title")
    content: str = Field(..., description="Full rule content or constraint directive")
    token_count: int = Field(..., description="Estimated token footprint")


class InspectWorkspaceRulesRequest(BaseModel):
    """Request payload to discover and inspect rules in a workspace."""

    workspace_root: str = Field(..., description="Absolute path to workspace root")


class InspectWorkspaceRulesResponse(BaseModel):
    """Response detailing all discovered rules in the workspace."""

    model_config = ConfigDict(frozen=True)

    workspace_root: str = Field(..., description="Evaluated workspace root path")
    snippets: list[ContextRuleSnippetDTO] = Field(default_factory=list, description="Extracted rule snippets")
    total_snippets: int = Field(..., description="Count of discovered snippets")
    estimated_total_tokens: int = Field(..., description="Total estimated token footprint")


class EnrichChildPromptRequest(BaseModel):
    """Request payload to enrich a child agent's system prompt with workspace invariants."""

    workspace_root: str = Field(..., description="Absolute path to workspace root")
    base_prompt: str = Field(..., description="Baseline child agent system prompt")
    role: SubagentRoleEnum = Field(SubagentRoleEnum.WORKER, description="Role determining context focus")
    max_context_tokens: int = Field(2000, ge=10, le=8000, description="Hard token budget cap for injected context")


class EnrichChildPromptResponse(BaseModel):
    """Response containing the enriched child agent system prompt and injection metrics."""

    model_config = ConfigDict(frozen=True)

    original_prompt: str = Field(..., description="Original un-enriched prompt")
    enriched_prompt: str = Field(..., description="Synthesized prompt containing workspace context block")
    injected_token_count: int = Field(..., description="Tokens added by context injection")
    is_compacted: bool = Field(..., description="Whether differential compacting was triggered")
    matched_sources: list[str] = Field(default_factory=list, description="Names of rule sources included")
    applied_snippets: list[ContextRuleSnippetDTO] = Field(default_factory=list, description="Applied rule snippets")


class InheritanceAuditRecordDTO(BaseModel):
    """Audit entry documenting an inheritance event."""

    model_config = ConfigDict(frozen=True)

    audit_id: str = Field(..., description="Unique audit record ID")
    workspace_root: str = Field(..., description="Workspace root path")
    subagent_role: SubagentRoleEnum = Field(..., description="Role of the enriched child agent")
    injected_tokens: int = Field(..., description="Tokens consumed by injection")
    compacted: bool = Field(..., description="Whether compacting was applied")
    timestamp: float = Field(..., description="Epoch timestamp of enrichment")
    matched_files: list[str] = Field(default_factory=list, description="Matched context file list")


class InheritanceAuditHistoryResponse(BaseModel):
    """List response for recent inheritance audit logs."""

    model_config = ConfigDict(frozen=True)

    records: list[InheritanceAuditRecordDTO] = Field(default_factory=list, description="Audit entries")
    total: int = Field(..., description="Total audit records available")
