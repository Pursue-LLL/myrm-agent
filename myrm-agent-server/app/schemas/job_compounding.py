"""[POS]: app/schemas/job_compounding.py
[INPUT]: Pydantic BaseModel, Field, datetime, and typing primitives.
[OUTPUT]: Request and response DTOs for 4-pillar job descriptions, compounded rules, and maturity reports.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ApprovalBoundaryDTO(BaseModel):
    """Specification of autonomous vs approval required action boundaries."""

    autonomous_actions: list[str] = Field(
        default_factory=list,
        description="Action patterns or tool names the agent can execute independently",
    )
    requires_approval_actions: list[str] = Field(
        default_factory=list,
        description="High-stakes actions requiring explicit human approval",
    )


class JobDescriptionSpecDTO(BaseModel):
    """Full 4-pillar job description spec DTO."""

    agent_id: str = Field(description="Unique agent identifier")
    job_title: str = Field(description="Domain specific title")
    target_scope: str = Field(description="Pillar 1: Goal and scope")
    tools_and_sources: list[str] = Field(default_factory=list, description="Pillar 2: Bound tools and sources")
    work_style: str = Field(default="rigorous", description="Pillar 3: Tone and delivery style")
    approval_boundary: ApprovalBoundaryDTO = Field(description="Pillar 4: Boundary division")
    created_at: datetime = Field(description="Creation timestamp")
    updated_at: datetime = Field(description="Last update timestamp")


class SaveJobDescriptionRequestDTO(BaseModel):
    """Request payload to create or calibrate an agent's 4-pillar job description."""

    agent_id: str = Field(description="Unique agent identifier")
    job_title: str = Field(description="Domain role title (e.g. Talent Scout, Expense Manager)")
    target_scope: str = Field(description="Business goal, objective, and operational scope")
    tools_and_sources: list[str] | None = Field(default=None, description="Bound tools and data sources")
    work_style: str = Field(default="rigorous", description="Work tone and execution style")
    autonomous_actions: list[str] | None = Field(default=None, description="Actions permitted autonomously")
    requires_approval_actions: list[str] | None = Field(default=None, description="Actions requiring approval")


class CompoundedRuleDTO(BaseModel):
    """Compounded domain rule representation."""

    rule_id: str = Field(description="Unique rule identifier")
    agent_id: str = Field(description="Owner agent identifier")
    rule_type: str = Field(description="Rule type: positive_preference, negative_constraint, inspection_lesson")
    statement: str = Field(description="Actionable guideline statement")
    trigger_condition: str = Field(description="Trigger scenario")
    evidence_source: str = Field(description="Feedback source or audit event")
    hit_count: int = Field(ge=0, description="Usage count")
    created_at: datetime = Field(description="Timestamp of establishment")


class RecordRuleRequestDTO(BaseModel):
    """Request to record a new compounded rule from task feedback."""

    agent_id: str = Field(description="Owner agent identifier")
    rule_type: str = Field(
        default="positive_preference",
        description="Type: positive_preference, negative_constraint, or inspection_lesson",
    )
    statement: str = Field(description="Actionable guideline or lesson")
    trigger_condition: str = Field(description="Trigger condition")
    evidence_source: str = Field(description="Feedback source context")


class CheckApprovalRequestDTO(BaseModel):
    """Request to evaluate whether an upcoming action requires human escalation."""

    agent_id: str = Field(description="Target agent identifier")
    action_name: str = Field(description="Proposed action or tool name to verify")


class CheckApprovalResponseDTO(BaseModel):
    """Evaluation outcome report on action approval boundary."""

    agent_id: str = Field(description="Agent identifier")
    action_name: str = Field(description="Evaluated action name")
    needs_approval: bool = Field(description="True if action must be escalated to human operator")
    reason: str = Field(description="Detailed rationale from approval boundary evaluation")


class CompoundingMaturityReportDTO(BaseModel):
    """Comprehensive compounding growth evaluation report."""

    agent_id: str = Field(description="Agent identifier")
    job_title: str = Field(description="Domain role title")
    total_rules_count: int = Field(ge=0, description="Total active rules")
    positive_preferences_count: int = Field(ge=0, description="Positive preferences")
    negative_constraints_count: int = Field(ge=0, description="Negative constraints")
    inspection_lessons_count: int = Field(ge=0, description="Troubleshooting lessons")
    maturity_score: float = Field(ge=0.0, le=100.0, description="Score between 0.0 and 100.0")
    tier: str = Field(description="Maturity tier: rookie, practitioner, specialist, partner")
    summary: str = Field(description="Human readable progress evaluation summary")
