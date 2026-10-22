"""Pydantic V2 schemas for Orchestrator Scope Guardrails and Safe Team Design Mode (Item 37).

[INPUT]
- AuditTeamScopeRequest, MemberScopeCandidateDTO, and SafeTeamDesignConfigDTO.

[OUTPUT]
- Strongly-typed DTOs for permission boundary audit, tool sanitization,
  and violation inspection.

[POS]
- Server-side typed contracts for orchestrator least-privilege guardrails and safe team design.
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field


class ViolationTypeEnum(enum.StrEnum):
    """Categorized scope guardrail violation types."""

    FORBIDDEN_TOOL = "forbidden_tool"
    ROLE_SCOPE_EXCEEDED = "role_scope_exceeded"
    FANOUT_LIMIT_EXCEEDED = "fanout_limit_exceeded"
    HIGH_RISK_REQUIRE_HITL = "high_risk_require_hitl"


class ViolationSeverityEnum(enum.StrEnum):
    """Severity classification for guardrail violations."""

    BLOCKER = "blocker"
    WARNING = "warning"


class ScopeViolationDTO(BaseModel):
    """Audit finding indicating a tool or fanout scope violation."""

    model_config = ConfigDict(frozen=True)

    role_key: str
    tool_name: str
    violation_type: ViolationTypeEnum
    severity: ViolationSeverityEnum
    recommendation: str


class MemberScopeCandidateDTO(BaseModel):
    """Teammate role and requested tools submitted for guardrails audit."""

    model_config = ConfigDict(frozen=True)

    role_key: str = Field(..., min_length=1, description="Subagent role identifier")
    display_name: str = Field(..., min_length=1, description="Human-readable member label")
    requested_tools: list[str] = Field(default_factory=list, description="Tools requested for this role")


class SafeTeamDesignConfigDTO(BaseModel):
    """Configuration for safe team design mode constraints."""

    model_config = ConfigDict(frozen=True)

    max_fanout_cap: int = Field(default=5, ge=1, le=20, description="Max allowed spawned subagent roles")
    require_hitl_for_high_risk: bool = Field(default=True, description="Require HITL for high risk actions")
    forbidden_tools: list[str] = Field(
        default_factory=lambda: [
            "system_exec",
            "eval_exec",
            "db_drop",
            "credential_export",
            "raw_bash_root",
        ],
        description="Globally forbidden tool IDs",
    )
    role_tool_allowlists: dict[str, list[str]] = Field(
        default_factory=lambda: {
            "orchestrator": ["spawn_subagent", "delegate_task", "steer_subagent", "roster_read"],
            "researcher": ["web_search", "web_fetch", "file_read", "search_directory"],
            "coder": ["file_read", "file_write", "linter_run", "test_runner", "diff_view"],
            "reviewer": ["file_read", "diff_view", "linter_run", "audit_report"],
            "specialist": ["file_read", "diff_view", "specialist_eval", "web_search"],
        },
        description="Allowed tool names indexed by subagent role key",
    )


class AuditTeamScopeRequest(BaseModel):
    """Request payload to evaluate proposed squad members against scope guardrails."""

    model_config = ConfigDict(frozen=True)

    candidates: list[MemberScopeCandidateDTO] = Field(..., description="Proposed team roles and toolsets")
    config_override: SafeTeamDesignConfigDTO | None = Field(
        None,
        description="Optional session-specific guardrail configuration override",
    )


class TeamScopeAuditResponse(BaseModel):
    """Response payload containing sanitized tools, violations, and safety disposition."""

    model_config = ConfigDict(frozen=True)

    is_safe: bool
    sanitized_tools_map: dict[str, list[str]]
    violations: list[ScopeViolationDTO]
    fanout_capped: bool
    original_member_count: int
    approved_member_count: int
    audit_summary: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
