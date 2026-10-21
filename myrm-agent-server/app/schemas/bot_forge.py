"""Pydantic V2 DTO schemas for Chat-Driven Agent & Team Factory with Builder Safety Envelope."""

from __future__ import annotations

from enum import StrEnum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class PipelineStageEnum(StrEnum):
    """Pipeline progression stages."""

    PRECHECK = "precheck"
    NAME_OVERLAP_GUARD = "name_overlap_guard"
    PROFILE_DESIGN = "profile_design"
    PERSONA_MEMORY = "persona_memory"
    ROUTINE_BIND = "routine_bind"
    POST_VERIFICATION = "post_verification"
    COMPLETED = "completed"
    ROLLED_BACK = "rolled_back"


class OverlapVerdictEnum(StrEnum):
    """Result of name or duty overlap checks."""

    UNIQUE = "unique"
    DUPLICATE_NAME = "duplicate_name"
    OVERLAPPING_DUTY = "overlapping_duty"


class ReadinessSeverityEnum(StrEnum):
    """Severity level of readiness dry run findings."""

    PASS = "pass"
    WARNING = "warning"
    BLOCKED = "blocked"


class BuilderAuthorityDTO(BaseModel):
    """Permission envelope of the creating builder."""

    builder_name: str = Field(..., description="Identity name of the creator")
    allowed_tools: List[str] = Field(default_factory=list, description="Allowlist of tools builder can grant")
    allowed_skills: List[str] = Field(default_factory=list, description="Allowlist of skills builder can grant")
    allowed_mcps: List[str] = Field(default_factory=list, description="Allowlist of MCP servers builder can grant")
    can_create_agents: bool = Field(default=True, description="Whether builder has authorization to create agents")
    max_team_members: int = Field(default=8, description="Maximum specialists in a created team")


class BotProfileSpecDTO(BaseModel):
    """Specification of a newly requested agent."""

    name: str = Field(..., description="Unique kebab-case name of the agent")
    display_name: str = Field(default="", description="Human-friendly display title")
    description: str = Field(default="", description="Duty and purpose description")
    system_prompt: str = Field(default="", description="Core instruction prompt")
    model: str = Field(default="default-model", description="Underlying LLM model")
    tools: List[str] = Field(default_factory=list, description="Granted tool names")
    skills: List[str] = Field(default_factory=list, description="Granted skill names")
    mcp_servers: List[str] = Field(default_factory=list, description="Granted MCP servers")
    cron_routines: List[str] = Field(default_factory=list, description="Scheduled cron expressions")
    role_type: str = Field(default="specialist", description="Role type (e.g. lead, specialist, assistant)")


class TeamCompositionSpecDTO(BaseModel):
    """Specification of an entire multi-agent squad."""

    team_name: str = Field(..., description="Unique name of the squad")
    team_purpose: str = Field(..., description="High-level mission of the squad")
    lead: BotProfileSpecDTO = Field(..., description="Squad lead agent profile")
    specialists: List[BotProfileSpecDTO] = Field(default_factory=list, description="Specialist agent profiles")


class SingleAgentCreationRequestDTO(BaseModel):
    """Request payload to instantiate a single agent through verified pipeline."""

    spec: BotProfileSpecDTO = Field(..., description="Profile specification of the agent")
    is_sandbox: bool = Field(default=False, description="Whether agent will operate in sandbox")
    allow_overlap: bool = Field(default=False, description="Whether to bypass warning duty overlap")


class TeamCreationRequestDTO(BaseModel):
    """Request payload to instantiate a team through verified pipeline."""

    team_spec: TeamCompositionSpecDTO = Field(..., description="Team composition specification")
    is_sandbox: bool = Field(default=False, description="Whether team runs in sandbox")
    allow_overlap: bool = Field(default=False, description="Whether to bypass warning duty overlap")


class CloneAgentRequestDTO(BaseModel):
    """Request payload to clone an existing agent with prompt sanitization."""

    source_name: str = Field(..., description="Name of the existing agent to clone")
    target_name: str = Field(..., description="Name for the new cloned agent")
    new_display_name: Optional[str] = Field(default=None, description="Optional new display title")
    custom_instructions: Optional[str] = Field(default=None, description="Optional extra prompt instructions")
    allow_overlap: bool = Field(default=True, description="Whether to bypass duty overlap check")


class OverlapCheckRequestDTO(BaseModel):
    """Request payload to check name or duty similarity against existing catalog."""

    candidate_name: str = Field(..., description="Proposed agent name")
    candidate_purpose: str = Field(..., description="Proposed agent duty purpose")
    duty_similarity_threshold: float = Field(default=0.65, ge=0.0, le=1.0, description="Similarity threshold")


class OverlapCheckResponseDTO(BaseModel):
    """Response payload for name or duty similarity check."""

    verdict: OverlapVerdictEnum
    conflicting_name: Optional[str] = None
    recommendation: Optional[str] = None


class VerificationFindingDTO(BaseModel):
    """Individual finding from readiness dry run verification."""

    code: str
    severity: ReadinessSeverityEnum
    message: str
    next_action: Optional[str] = None


class CreationVerificationResultDTO(BaseModel):
    """Overall outcome of post-creation zero-model dry run."""

    passed: bool
    severity: ReadinessSeverityEnum
    findings: List[VerificationFindingDTO] = Field(default_factory=list)
    observed_state: Dict[str, str] = Field(default_factory=dict)


class RollbackRecordDTO(BaseModel):
    """Audit record when transactional rollback is executed."""

    target_name: str
    reason: str
    reverted_agents: List[str] = Field(default_factory=list)
    reverted_crons: List[str] = Field(default_factory=list)
    timestamp: float


class PipelineExecutionStateDTO(BaseModel):
    """Complete execution record of the deterministic creation pipeline."""

    pipeline_id: str
    target_name: str
    is_team: bool = False
    current_stage: PipelineStageEnum
    created_agents: List[str] = Field(default_factory=list)
    rollback: Optional[RollbackRecordDTO] = None
    verification: Optional[CreationVerificationResultDTO] = None
    error: Optional[str] = None
    started_at: float
    completed_at: Optional[float] = None


class BotForgeCatalogResponseDTO(BaseModel):
    """Catalog response containing registered agents."""

    session_id: str
    total_agents: int
    agents: List[BotProfileSpecDTO] = Field(default_factory=list)
