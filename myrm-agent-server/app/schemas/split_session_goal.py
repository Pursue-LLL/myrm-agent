"""
[POS] app/schemas/split_session_goal.py
[INPUT] typing, pydantic
[OUTPUT] SplitSessionPhaseLiteral, ShipDossierDTO, NextIterationPlanDTO, SplitSessionGoalTemplateDTO, SplitSessionGoalInstanceDTO, CreateSplitSessionGoalRequestDTO, AdvanceSplitSessionRequestDTO

Pydantic schemas for Split-Session 2-Window (Window 1: Ship / Window 2: Plan) Goal templates and lifecycle state machine.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SplitSessionPhaseLiteral = Literal[
    "window1_shipping",
    "window1_completed",
    "window2_planning",
    "all_completed",
]


class ShipDossierDTO(BaseModel):
    """Artifact deliverables, test results, and modified files produced during Window 1 (Ship)."""

    model_config = ConfigDict(extra="forbid")

    deliverables: list[str] = Field(default_factory=list, description="List of generated artifacts/code paths")
    test_results_summary: str = Field(default="All tests passed successfully", description="Test execution summary")
    tests_passed: bool = Field(default=True, description="Whether acceptance tests passed without error")
    modified_files: list[str] = Field(default_factory=list, description="List of changed source file paths")
    notes: str = Field(default="", description="Release notes or implementation caveats")


class NextIterationPlanDTO(BaseModel):
    """Architecture roadmap, task steps, and spec drafted during Window 2 (Plan)."""

    model_config = ConfigDict(extra="forbid")

    next_objective: str = Field(..., min_length=1, description="Synthesized objective for the next iteration")
    architecture_notes: str = Field(default="", description="High-level architectural evolution notes")
    planned_task_steps: list[str] = Field(default_factory=list, description="Decomposed execution steps for next run")
    estimated_tokens_savings: int = Field(default=0, ge=0, description="Estimated tokens saved by split-session context reset")


class SplitSessionGoalTemplateDTO(BaseModel):
    """Declarative split-session goal template specification supporting English and Chinese."""

    model_config = ConfigDict(extra="forbid")

    template_id: str = Field(..., description="Unique template identifier")
    name_zh: str = Field(..., description="Chinese display name")
    name_en: str = Field(..., description="English display name")
    description_zh: str = Field(..., description="Chinese description")
    description_en: str = Field(..., description="English description")
    window1_prompt_template: str = Field(..., description="Prompt instructions for Window 1: Ship")
    window2_prompt_template: str = Field(..., description="Prompt instructions for Window 2: Plan")
    acceptance_gate: str = Field(..., description="Acceptance criteria required before moving to Window 2")


class SplitSessionGoalInstanceDTO(BaseModel):
    """Full snapshot of an active or completed Split-Session Goal instance."""

    model_config = ConfigDict(extra="forbid")

    instance_id: str = Field(..., description="Unique goal instance ID")
    session_id: str = Field(..., description="Associated chat session ID")
    template_id: str = Field(..., description="Template specification ID")
    title: str = Field(..., description="Goal title")
    current_phase: SplitSessionPhaseLiteral = Field(default="window1_shipping", description="Current lifecycle phase")
    ship_dossier: ShipDossierDTO | None = Field(default=None, description="Window 1 delivery artifact dossier")
    iteration_plan: NextIterationPlanDTO | None = Field(default=None, description="Window 2 forward-looking plan")
    created_at: float = Field(default_factory=time.time, description="Creation epoch timestamp")
    updated_at: float = Field(default_factory=time.time, description="Last updated epoch timestamp")


class CreateSplitSessionGoalRequestDTO(BaseModel):
    """Request payload to initiate a Split-Session Goal."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., min_length=1, description="Associated session ID")
    template_id: str = Field(default="code_ship_architecture_plan", description="Template ID to instantiate")
    title: str = Field(..., min_length=1, description="User-facing goal title")
    custom_window1_objective: str = Field(default="", description="Optional custom instructions for Window 1")
    custom_window2_objective: str = Field(default="", description="Optional custom instructions for Window 2")


class AdvanceSplitSessionRequestDTO(BaseModel):
    """Request payload to advance the split-session state machine."""

    model_config = ConfigDict(extra="forbid")

    target_phase: SplitSessionPhaseLiteral = Field(..., description="Phase to transition into")
    ship_dossier: ShipDossierDTO | None = Field(default=None, description="Required when completing Window 1")
    iteration_plan: NextIterationPlanDTO | None = Field(default=None, description="Required when completing Window 2")
