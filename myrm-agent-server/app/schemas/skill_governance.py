"""Pydantic schemas for Agent Skill Engineering Governance and Privilege Verification.

[INPUT]
- None.

[OUTPUT]
- Typed DTO models for skill permission contracts, contract parsing,
  drift & privilege escalation diffing, and runtime mounting validation.

[POS]
- Server schemas. Exposes typed contracts for client UI and Skill marketplace governance.
"""

from __future__ import annotations

import time

from pydantic import BaseModel, ConfigDict, Field


class SkillPermissionContractDto(BaseModel):
    """Specification of an Agent Skill's declared capabilities and security boundary."""

    model_config = ConfigDict(extra="forbid")

    skill_name: str = Field(..., description="Unique skill name identifier")
    version: str = Field(default="1.0.0", description="Semantic version string")
    declared_tools: list[str] = Field(default_factory=list, description="Tool names required by this skill")
    network_egress: bool = Field(default=False, description="Whether skill requests outbound HTTP/socket access")
    filesystem_scope: str = Field(
        default="task_workspace",
        description="Filesystem access level: read_only, task_workspace, full_access",
    )
    requires_admin_review: bool = Field(
        default=False, description="True if elevated capabilities require human security sign-off"
    )
    registered_at: float = Field(default_factory=time.time, description="Unix timestamp of contract registration")


class ParseSkillContractRequest(BaseModel):
    """Payload to parse and infer a permission contract from raw SKILL.md content."""

    model_config = ConfigDict(extra="forbid")

    content: str = Field(..., description="Raw Markdown/YAML content of the SKILL.md file")
    skill_name: str = Field(..., description="Target skill name")
    version: str = Field(default="1.0.0", description="Semantic version")


class DiffSkillContractsRequest(BaseModel):
    """Payload to compare baseline and target skill versions for privilege escalation."""

    model_config = ConfigDict(extra="forbid")

    base_contract: SkillPermissionContractDto | None = Field(
        default=None, description="Baseline contract (None if initial registration)"
    )
    target_contract: SkillPermissionContractDto = Field(
        ..., description="Target or candidate contract being evaluated for merge/update"
    )


class SkillDriftAnalysisDto(BaseModel):
    """Analysis result identifying added tools and potential privilege escalation."""

    model_config = ConfigDict(extra="forbid")

    skill_name: str = Field(..., description="Skill name analyzed")
    base_version: str | None = Field(default=None, description="Baseline version (None if new)")
    target_version: str = Field(..., description="Target version under review")
    added_tools: list[str] = Field(default_factory=list, description="Tools newly added in target version")
    removed_tools: list[str] = Field(default_factory=list, description="Tools removed in target version")
    escalated_permissions: list[str] = Field(
        default_factory=list, description="Specific privilege escalation flags triggered"
    )
    has_privilege_escalation: bool = Field(..., description="True if any dangerous capability was escalated")
    review_required: bool = Field(..., description="True if human security approval is mandated")
    audit_findings: list[str] = Field(default_factory=list, description="Detailed explanatory findings")
    analyzed_at: float = Field(default_factory=time.time, description="Timestamp of analysis")


class ValidateSkillMountingRequest(BaseModel):
    """Payload to check whether a skill contract satisfies runtime security gates before mounting."""

    model_config = ConfigDict(extra="forbid")

    contract: SkillPermissionContractDto = Field(..., description="Skill permission contract to validate")
    is_approved: bool = Field(default=False, description="Whether human administrator has signed off")


class ValidateSkillMountingResponse(BaseModel):
    """Result of runtime skill mounting validation."""

    model_config = ConfigDict(extra="forbid")

    skill_name: str = Field(..., description="Skill name validated")
    permitted: bool = Field(..., description="Whether mounting is allowed")
    message: str = Field(..., description="Status explanation or denial rationale")
