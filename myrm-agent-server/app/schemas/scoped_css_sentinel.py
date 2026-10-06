"""Pydantic schemas for Scoped CSS Isolation and Parallel Micro-Agent Boundary Sentinel API.

[INPUT]
Pydantic BaseModel and Field.

[OUTPUT]
CssValidationViolation, CssValidationRequest, CssValidationResponse,
AgentContainerBoundarySpec, MultiAgentSandboxLayoutResponse.

[POS]
Schema contracts for scoped CSS sanitization and parallel micro-agent DOM isolation.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class GlobalSelectorViolationResponse(BaseModel):
    """Details of an unconfined global root selector detected in a style patch."""

    selector: str
    reason: str
    severity: str
    line_number: int | None = None


class ScopeCssRequest(BaseModel):
    """Payload to scope raw micro-agent CSS rules to a specific component identifier."""

    css_content: str = Field(..., description="Raw CSS string to be checked and rewritten")
    scope_id: str = Field(..., description="Component scope root selector, e.g. 'drawer-dialog' or '#modal'")


class ScopeCssResponse(BaseModel):
    """Result of CSS scoping inspection and AST rewriting."""

    is_valid: bool = Field(..., description="Whether CSS passed global root containment checks")
    original_css: str
    scoped_css: str
    scope_id: str
    violations: list[GlobalSelectorViolationResponse]
    rules_rewritten: int


class ConcurrentStylePatchRequest(BaseModel):
    """Style patch submitted by a concurrent micro-agent."""

    agent_id: str = Field(..., description="Sub-agent identifier, e.g. 'drawer_agent'")
    component_target_id: str = Field(..., description="Target component container identifier")
    css_content: str = Field(..., description="Proposed CSS style content")


class CheckConflictRequest(BaseModel):
    """Payload to check a batch of concurrent agent patches for style collisions."""

    patches: list[ConcurrentStylePatchRequest] = Field(
        ..., description="List of concurrent micro-agent patches to validate"
    )


class CheckConflictResponse(BaseModel):
    """Collision detection outcome across concurrent patches."""

    has_conflict: bool
    conflicting_agents: list[str]
    reason: str
    merged_scoped_css: str | None = None
