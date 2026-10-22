"""Pydantic V2 schemas for Per-Project Workspace Team Blueprint Auto-Reuse (Item 36).

[INPUT]
- BindWorkspaceBlueprintRequest and workspace identifiers.

[OUTPUT]
- Strongly-typed DTOs for workspace-to-blueprint bindings, resolution dispositions,
  and template listing.

[POS]
- Server-side typed contracts for per-project team blueprint binding & auto-reuse.
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field


class AutoReusePolicyEnum(enum.StrEnum):
    """Auto-reuse behavior policy for a workspace's bound team blueprint."""

    ALWAYS_REUSE = "always_reuse"
    PROMPT_REUSE = "prompt_reuse"
    MANUAL_ONLY = "manual_only"


class BindWorkspaceBlueprintRequest(BaseModel):
    """Request payload to bind or update a team blueprint for a workspace."""

    model_config = ConfigDict(frozen=True)

    blueprint_id: str = Field(..., min_length=1, description="Squad blueprint identifier")
    team_name: str = Field(..., min_length=1, description="Human-readable team name")
    auto_reuse_policy: AutoReusePolicyEnum = Field(
        default=AutoReusePolicyEnum.PROMPT_REUSE,
        description="Policy governing automatic instantiation",
    )
    member_count: int = Field(default=0, ge=0, description="Number of teammate roles in squad")
    total_budget_tokens: int = Field(default=0, ge=0, description="Aggregate compute token budget")
    project_label: str = Field(default="", description="Optional workspace or project display label")
    blueprint_snapshot: dict[str, str | int | float | bool] = Field(
        default_factory=dict,
        description="Compact snapshot of member roles and configs",
    )


class WorkspaceBlueprintBindingDTO(BaseModel):
    """Active persistent binding between a project workspace and a squad blueprint."""

    model_config = ConfigDict(frozen=True)

    workspace_id: str
    blueprint_id: str
    team_name: str
    auto_reuse_policy: AutoReusePolicyEnum
    bound_at: datetime
    last_used_at: datetime
    member_count: int
    total_budget_tokens: int
    project_label: str
    blueprint_snapshot: dict[str, str | int | float | bool] = Field(default_factory=dict)


class WorkspaceBlueprintResolutionDTO(BaseModel):
    """Resolution outcome indicating whether a workspace has a bound team ready for auto-reuse."""

    model_config = ConfigDict(frozen=True)

    workspace_id: str
    binding: WorkspaceBlueprintBindingDTO | None = None
    can_auto_instantiate: bool
    status_label: str
    resolution_rationale: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))


class WorkspaceBlueprintListResponse(BaseModel):
    """List response containing all registered workspace blueprint bindings."""

    model_config = ConfigDict(frozen=True)

    bindings: list[WorkspaceBlueprintBindingDTO]
    total_count: int
