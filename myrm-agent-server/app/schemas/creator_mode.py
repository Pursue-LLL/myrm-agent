"""Pydantic V2 schemas for Creator Mode Guardrailed Preset Synthesizer and Defensive Sandbox (Item 39).

[INPUT]
- SynthesizePresetRequest, VerifyInSandboxRequest, RoamingSyncRequest.

[OUTPUT]
- Strongly-typed DTOs for synthesized agent drafts, defensive sandbox verification reports,
  and multi-platform roaming records.

[POS]
- Server-side typed contracts for creator mode metaprogramming and defense battery governance.
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field


class CaseVerdictEnum(enum.StrEnum):
    """Authorization verdict for sandbox defense tests."""

    ALLOW = "allow"
    BLOCK = "block"


class RoamingPlatformEnum(enum.StrEnum):
    """Target platform for unified profile roaming."""

    WEBUI = "webui"
    DESKTOP_TAURI = "desktop_tauri"
    CLOUD = "cloud"


class AgentPresetDraftDTO(BaseModel):
    """Compiled agent preset draft with least-privilege tool specifications."""

    model_config = ConfigDict(frozen=True)

    preset_id: str = Field(..., description="Unique generated preset identifier")
    name: str = Field(..., min_length=1, description="Synthesized agent display name")
    role: str = Field(..., min_length=1, description="Categorized functional role")
    description: str = Field(..., description="Brief summary of agent scope")
    system_prompt: str = Field(..., description="Compiled prompt with strict boundary clauses")
    allowed_tools: list[str] = Field(default_factory=list, description="Whitelist of authorized tools")
    denied_tools: list[str] = Field(default_factory=list, description="Blacklist of prohibited tools")
    guardrails: dict[str, bool | int | str] = Field(default_factory=dict, description="Active guardrail flags")
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC), description="Synthesis timestamp")


class SynthesizePresetRequest(BaseModel):
    """Request payload for natural language preset synthesis in creator mode."""

    model_config = ConfigDict(frozen=True)

    intent: str = Field(..., min_length=1, description="Natural language prompt describing agent scope and rules")
    name: str | None = Field(default=None, description="Optional custom agent name override")
    role: str | None = Field(default=None, description="Optional role category override")
    custom_forbidden_tools: list[str] = Field(default_factory=list, description="Explicit blacklist tools")


class DefensiveTestCaseDTO(BaseModel):
    """Individual defensive or positive capability test case."""

    model_config = ConfigDict(frozen=True)

    case_id: str = Field(..., description="Unique test case identifier")
    name: str = Field(..., description="Human-readable test purpose label")
    is_exploit: bool = Field(..., description="Whether test represents a negative penetration attempt")
    prompt_input: str = Field(..., description="User prompt simulating the action")
    target_tool: str = Field(..., description="Tool targeted by this action")
    expected_verdict: CaseVerdictEnum = Field(..., description="Expected access control decision")


class CaseEvaluationResultDTO(BaseModel):
    """Outcome for an executed sandbox test case."""

    model_config = ConfigDict(frozen=True)

    case_id: str = Field(..., description="Referenced test case identifier")
    name: str = Field(..., description="Test name")
    is_exploit: bool = Field(..., description="Whether test was an exploit test")
    passed: bool = Field(..., description="Whether outcome met safety expectation")
    actual_verdict: CaseVerdictEnum = Field(..., description="Actual policy verdict rendered")
    reason: str = Field(..., description="Diagnostic justification or breach explanation")


class SandboxVerificationResponse(BaseModel):
    """Consolidated defensive sandbox verification report."""

    model_config = ConfigDict(frozen=True)

    is_safe: bool = Field(..., description="Whether all exploits were blocked and capabilities certified")
    total_cases: int = Field(..., ge=0, description="Total number of evaluated test cases")
    passed_cases: int = Field(..., ge=0, description="Number of passed test cases")
    blocked_exploits: int = Field(..., ge=0, description="Number of successfully blocked exploit attempts")
    results: list[CaseEvaluationResultDTO] = Field(default_factory=list, description="Detailed test case results")
    summary: str = Field(..., description="Executive safety evaluation summary")
    verified_at: datetime = Field(..., description="Verification timestamp")


class VerifyInSandboxRequest(BaseModel):
    """Request payload to execute defensive sandbox verification battery."""

    model_config = ConfigDict(frozen=True)

    draft: AgentPresetDraftDTO = Field(..., description="Target preset draft to evaluate")
    custom_cases: list[DefensiveTestCaseDTO] | None = Field(default=None, description="Optional custom test battery")


class RoamingSyncRecordDTO(BaseModel):
    """Record of multi-platform roaming synchronization and self-healing."""

    model_config = ConfigDict(frozen=True)

    preset_id: str = Field(..., description="Target preset ID")
    platform: RoamingPlatformEnum = Field(..., description="Platform target")
    target_path: str = Field(..., description="Canonical file system or cloud URI")
    status: str = Field(..., description="Synchronization outcome status")
    healed: bool = Field(default=False, description="Whether path was self-healed from broken legacy location")
    timestamp: datetime = Field(..., description="Sync event timestamp")


class RoamingSyncRequest(BaseModel):
    """Request payload to broadcast preset to multi-platform roaming storage."""

    model_config = ConfigDict(frozen=True)

    draft: AgentPresetDraftDTO = Field(..., description="Preset to synchronize")
    target_platforms: list[RoamingPlatformEnum] | None = Field(
        default=None,
        description="Target platforms (defaults to WebUI, Desktop Tauri, and Cloud)",
    )
    legacy_broken_path: str | None = Field(default=None, description="Optional legacy broken path to heal")


class RoamingSyncResponse(BaseModel):
    """Response payload with multi-platform synchronization outcomes."""

    model_config = ConfigDict(frozen=True)

    records: list[RoamingSyncRecordDTO] = Field(default_factory=list, description="Platform sync receipts")
