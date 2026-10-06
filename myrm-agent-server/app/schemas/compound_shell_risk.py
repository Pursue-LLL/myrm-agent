"""Pydantic schemas for Compound Shell Risk Interceptor and Edge Auxiliary Suite.

[INPUT]
- pydantic::{BaseModel, Field}
- enum::{StrEnum}

[OUTPUT]
- CommandRiskLevelEnum: risk severity categories.
- FirewallVerdictEnum: firewall enforcement verdicts.
- InspectCommandRequest, CompoundCheckResponse, ScreenCommandRequest, CommandScreeningResponse: command screening schemas.
- GenerateTitleRequest, TitleGenerationResponse, CompactProfileRequest, ProfileCompactionResponse: edge utility schemas.

[POS]
app/schemas/compound_shell_risk defines API schemas for shell command risk inspection and edge utilities.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class CommandRiskLevelEnum(StrEnum):
    """Risk severity categorization."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FirewallVerdictEnum(StrEnum):
    """Enforcement outcome of the compound command firewall."""

    ALLOW = "allow"
    AUDIT_REQUIRED = "audit_required"
    BLOCK = "block"


class InspectCommandRequest(BaseModel):
    """Request payload to inspect a shell command."""

    raw_command: str = Field(..., description="Raw shell command string to inspect")


class CompoundCheckResponse(BaseModel):
    """Outcome of compound shell command inspection."""

    raw_command: str
    is_compound: bool
    operators_found: list[str]
    sub_commands: list[str]
    verdict: FirewallVerdictEnum
    risk_level: CommandRiskLevelEnum
    reason: str | None


class ScreenCommandRequest(BaseModel):
    """Request payload for low-latency command risk screening."""

    command: str = Field(..., description="Shell command string to pre-screen")


class CommandScreeningResponse(BaseModel):
    """Outcome of edge model command pre-screening."""

    command: str
    risk_level: CommandRiskLevelEnum
    is_dangerous: bool
    risk_factors: list[str]
    execution_time_ms: float
    summary: str


class GenerateTitleRequest(BaseModel):
    """Request payload for edge session title extraction."""

    first_turn_text: str = Field(..., description="First user turn text or question")


class TitleGenerationResponse(BaseModel):
    """Outcome of edge model session title generation."""

    title: str
    suggested_tags: list[str]
    execution_time_ms: float


class CompactProfileRequest(BaseModel):
    """Request payload for user preference memory compaction."""

    conversation_snippet: str = Field(..., description="Conversation text snippet")
    existing_profile: dict[str, str] | None = Field(
        default=None, description="Current user preference profile dictionary"
    )


class ProfileCompactionResponse(BaseModel):
    """Outcome of edge model user profile compaction."""

    compacted_profile: dict[str, str]
    extracted_preferences: list[str]
    execution_time_ms: float
