"""Pydantic V2 schemas for Orchestrator Auto Squad Composition & Model-Deferred Wizard (Item 34).

[INPUT]
- ComposeSquadBlueprintRequest, MaterializeSquadRequest, and ModelDeferredChoiceDTO.

[OUTPUT]
- Strongly-typed DTOs for multi-agent roster blueprints, dynamic compute budgets,
  and materialized squad execution contexts.

[POS]
- Provides typed data contracts for Phase-1 goal decomposition and Phase-2 model-deferred
  squad instantiation.
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field


class SquadRoleTierEnum(enum.StrEnum):
    """Execution specialization and capability tier for squad members."""

    ORCHESTRATOR = "orchestrator"
    CODER = "coder"
    REVIEWER = "reviewer"
    RESEARCHER = "researcher"
    SPECIALIST = "specialist"


class StopConditionDTO(BaseModel):
    """Bounded stopping criteria and fan-out protection for an individual role."""

    model_config = ConfigDict(frozen=True)

    max_turns: int = Field(default=10, ge=1, le=50)
    max_tool_calls: int = Field(default=30, ge=1, le=120)
    allow_failure: bool = Field(default=False)


class MemberBlueprintDTO(BaseModel):
    """Pre-materialized role blueprint produced by the orchestrator in Phase 1."""

    model_config = ConfigDict(frozen=True)

    role_key: str
    display_name: str
    handle: str
    role_tier: SquadRoleTierEnum
    role_description: str
    soul_system_prompt: str
    required_tools: list[str] = Field(default_factory=list)
    required_skills: list[str] = Field(default_factory=list)
    budget_tokens: int
    max_cost_usd: float
    stop_condition: StopConditionDTO
    suggested_model_tier: str = "balanced"


class ComposeSquadBlueprintRequest(BaseModel):
    """Request payload to generate a multi-agent roster blueprint from a high-level goal."""

    model_config = ConfigDict(frozen=True)

    session_id: str = Field(..., min_length=1, description="Chat session identifier")
    goal_description: str = Field(..., min_length=1, description="High-level mission objective")
    total_budget_tokens: int = Field(default=150000, ge=1000, description="Total token quota")
    total_max_cost_usd: float = Field(default=2.00, gt=0, description="Total dollar expenditure ceiling")
    max_descendants_per_run: int = Field(default=8, ge=2, le=20, description="Safety fan-out limit")


class SquadBlueprintResponse(BaseModel):
    """Phase-1 response containing the orchestrator's synthesized team blueprint."""

    model_config = ConfigDict(frozen=True)

    squad_id: str
    goal_description: str
    members: list[MemberBlueprintDTO]
    total_budget_tokens: int
    total_max_cost_usd: float
    max_descendants_per_run: int
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))


class ModelDeferredChoiceDTO(BaseModel):
    """User-confirmed model selection for a role in Phase 2."""

    model_config = ConfigDict(frozen=True)

    role_key: str = Field(..., min_length=1)
    selected_model_id: str = Field(..., min_length=1)
    custom_instructions: str = ""


class MaterializeSquadRequest(BaseModel):
    """Request payload to finalize Phase 2 and instantiate the squad with selected models."""

    model_config = ConfigDict(frozen=True)

    session_id: str = Field(..., min_length=1)
    squad_id: str = Field(..., min_length=1)
    model_choices: list[ModelDeferredChoiceDTO] = Field(..., min_length=1)
    default_model_id: str = Field(default="gpt-4o-mini")


class MaterializedMemberDTO(BaseModel):
    """Fully instantiated and model-bound squad colleague workstation."""

    model_config = ConfigDict(frozen=True)

    role_key: str
    bot_id: str
    handle: str
    display_name: str
    role_tier: SquadRoleTierEnum
    selected_model_id: str
    allocated_budget_tokens: int
    allocated_max_cost_usd: float
    system_prompt: str
    tools: list[str]
    skills: list[str]
    stop_condition: StopConditionDTO


class MaterializedSquadResponse(BaseModel):
    """Phase-2 finalized squad execution context ready for coordinated dispatch."""

    model_config = ConfigDict(frozen=True)

    squad_id: str
    orchestrator_bot_id: str
    members: list[MaterializedMemberDTO]
    total_budget_tokens: int
    total_max_cost_usd: float
    status: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
