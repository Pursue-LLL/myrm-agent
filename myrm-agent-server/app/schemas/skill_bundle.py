"""Pydantic V2 schemas for Skill Bundles Batch Manifest & Lifecycle Warmup Manager (Item 41).

[INPUT]
- RegisterBundleRequest, WarmupBundleRequest, ActivateBundleRequest, DeactivateBundleRequest.

[OUTPUT]
- Strongly-typed DTOs for batch skill bundles, dependency warmup diagnostics,
  and session-scoped activation records.

[POS]
- Server-side typed schemas for skill bundle APIs.
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field


class WarmupStatusEnum(enum.StrEnum):
    """Runtime lifecycle pre-flight warmup and readiness status."""

    READY = "ready"
    WARNING = "warning"
    BLOCKED = "blocked"


class BundleCategoryEnum(enum.StrEnum):
    """Business vertical category of the skill bundle."""

    CODING = "coding"
    WRITING = "writing"
    MARKETING = "marketing"
    FINANCE = "finance"
    SECURITY = "security"
    CUSTOM = "custom"


class BundleSkillSpecDTO(BaseModel):
    """Individual skill definition within a packaged bundle manifest."""

    model_config = ConfigDict(frozen=True)

    skill_id: str = Field(..., min_length=1, description="Unique skill identifier")
    name: str = Field(..., min_length=1, description="Human-readable skill name")
    description: str = Field(..., description="Skill capability summary")
    required_env_vars: list[str] = Field(
        default_factory=list, description="Required environment variable names"
    )
    required_tools: list[str] = Field(
        default_factory=list, description="Required system or meta tool IDs"
    )
    is_optional: bool = Field(
        default=False, description="Whether skill missing causes blocked or warning"
    )


class BundleWarmupCheckDTO(BaseModel):
    """Diagnostic check item evaluated during bundle pre-flight warmup."""

    model_config = ConfigDict(frozen=True)

    check_name: str = Field(..., min_length=1, description="Diagnostic check key")
    status: WarmupStatusEnum = Field(..., description="Check outcome status")
    message: str = Field(..., description="Detailed diagnostic or error message")
    is_resolved: bool = Field(default=True, description="Whether check resolved cleanly")


class BundleWarmupReportDTO(BaseModel):
    """Consolidated readiness report produced after probe warmup."""

    model_config = ConfigDict(frozen=True)

    bundle_id: str = Field(..., min_length=1, description="Target bundle ID")
    overall_status: WarmupStatusEnum = Field(..., description="Overall warmup verdict")
    checks: list[BundleWarmupCheckDTO] = Field(
        default_factory=list, description="List of individual checks"
    )
    checked_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=UTC), description="Check timestamp"
    )


class SkillBundleManifestDTO(BaseModel):
    """Standardized batch manifest packaging scenario-tailored skills."""

    model_config = ConfigDict(frozen=True)

    bundle_id: str = Field(..., min_length=1, description="Unique bundle identifier")
    name: str = Field(..., min_length=1, description="Scenario bundle name")
    description: str = Field(..., description="Bundle business purpose")
    category: BundleCategoryEnum = Field(
        default=BundleCategoryEnum.CUSTOM, description="Vertical category"
    )
    skills: list[BundleSkillSpecDTO] = Field(
        ..., min_length=1, description="Packaged skills specification"
    )
    author: str = Field(default="system", description="Author or team")
    version: str = Field(default="1.0.0", description="Semantic version string")
    tags: list[str] = Field(default_factory=list, description="Search and categorization tags")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=UTC), description="Creation timestamp"
    )


class BundleActivationRecordDTO(BaseModel):
    """Record of an activated skill bundle mounted into a session or agent profile."""

    model_config = ConfigDict(frozen=True)

    session_id: str = Field(..., min_length=1, description="Target chat session ID")
    bundle_id: str = Field(..., min_length=1, description="Activated bundle ID")
    activated_skills: list[str] = Field(
        default_factory=list, description="List of activated skill IDs"
    )
    warmup_status: WarmupStatusEnum = Field(
        default=WarmupStatusEnum.READY, description="Warmup status at activation"
    )
    activated_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=UTC), description="Activation timestamp"
    )


class RegisterBundleRequest(BaseModel):
    """Request to register or update a scenario-based skill bundle manifest."""

    model_config = ConfigDict(frozen=True)

    manifest: SkillBundleManifestDTO = Field(..., description="Complete bundle manifest")


class WarmupBundleRequest(BaseModel):
    """Request to execute pre-flight warmup diagnostic probes on a bundle."""

    model_config = ConfigDict(frozen=True)

    available_skills: list[str] = Field(
        default_factory=list, description="Explicit available skill IDs override"
    )
    env_vars: dict[str, str] = Field(
        default_factory=dict, description="Environment variables dictionary"
    )
    available_tools: list[str] = Field(
        default_factory=list, description="Optional available tool IDs"
    )


class ActivateBundleRequest(BaseModel):
    """Request to atomically activate all skills in a bundle for a chat session."""

    model_config = ConfigDict(frozen=True)

    bundle_id: str = Field(..., min_length=1, description="Target bundle ID to activate")
    available_skills: list[str] = Field(
        default_factory=list, description="Available skills override"
    )
    env_vars: dict[str, str] = Field(
        default_factory=dict, description="Environment variables dictionary"
    )
    force: bool = Field(
        default=False, description="Whether to bypass BLOCKED status"
    )


class DeactivateBundleRequest(BaseModel):
    """Request to deactivate a bundle from a chat session."""

    model_config = ConfigDict(frozen=True)

    bundle_id: str = Field(..., min_length=1, description="Target bundle ID to deactivate")
