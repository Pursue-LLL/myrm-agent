"""Pydantic schemas for Inherited Identity Protection and Session Resume Guard.

[INPUT]
- None.

[OUTPUT]
- Typed DTO models for terminal environment sanitization, session reference resolution,
  and official agent resume plan generation.

[POS]
- Server schemas for Herdr #4461 clear inherited terminal and agent session identity.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class SessionRefKindDto(StrEnum):
    """Kind of agent session reference."""

    ID = "id"
    PATH = "path"


class AgentSessionRefDto(BaseModel):
    """Data transfer object representing an agent session reference."""

    model_config = ConfigDict(extra="forbid")

    kind: SessionRefKindDto = Field(..., description="Reference kind: id or path")
    value: str = Field(..., description="Session identifier string or absolute file path")


class AgentResumePlanDto(BaseModel):
    """Executable resume instruction plan."""

    model_config = ConfigDict(extra="forbid")

    agent: str = Field(..., description="Target agent binary name")
    argv: list[str] = Field(..., description="Validated command argument array")
    dedupe_key: str = Field(..., description="Unique key for deduplicating resume tasks")


class SanitizeEnvRequest(BaseModel):
    """Request payload for stripping inherited terminal environment variables."""

    model_config = ConfigDict(extra="forbid")

    dirty_env: dict[str, str] = Field(
        default_factory=dict,
        description="Incoming environment dictionary potentially containing inherited identity",
    )
    extra_removals: list[str] | None = Field(
        default=None,
        description="Optional list of additional environment keys to purge",
    )
    extra_overrides: dict[str, str] | None = Field(
        default=None,
        description="Optional explicit child environment values to inject",
    )
    allow_system_only: bool = Field(
        default=False,
        description="Whether to discard all custom non-standard system variables",
    )


class SanitizeEnvResponse(BaseModel):
    """Response containing isolated and sanitized environment."""

    model_config = ConfigDict(extra="forbid")

    sanitized_env: dict[str, str] = Field(
        default_factory=dict, description="Cleaned environment dictionary"
    )
    purged_keys: list[str] = Field(
        default_factory=list, description="List of stripped variable names"
    )
    purged_count: int = Field(
        default=0, description="Number of variables removed"
    )
    is_isolated: bool = Field(
        default=True, description="Indicates if inherited terminal variables are isolated"
    )


class ResolveSessionRefRequest(BaseModel):
    """Request payload to parse and validate an agent session reference."""

    model_config = ConfigDict(extra="forbid")

    source: str = Field(..., description="Origin namespace (e.g., 'myrm:claude', 'herdr:codex')")
    agent: str = Field(..., description="Agent name (e.g., 'claude', 'codex', 'pi')")
    session_id: str | None = Field(
        default=None, description="Optional reported session identifier"
    )
    session_path: str | None = Field(
        default=None, description="Optional reported session file path"
    )


class ResolveSessionRefResponse(BaseModel):
    """Result of resolving an agent session reference."""

    model_config = ConfigDict(extra="forbid")

    resolved: bool = Field(..., description="Whether session reference was successfully resolved")
    session_ref: AgentSessionRefDto | None = Field(
        default=None, description="Resolved session reference object if valid"
    )
    reason: str | None = Field(
        default=None, description="Failure reason if not resolved"
    )


class CreateResumePlanRequest(BaseModel):
    """Request payload to derive and validate an agent resume execution plan."""

    model_config = ConfigDict(extra="forbid")

    source: str = Field(..., description="Origin namespace of the session reference")
    agent: str = Field(..., description="Target agent name")
    session_ref: AgentSessionRefDto = Field(
        ..., description="Session reference containing kind and value"
    )
    cwd: str | None = Field(
        default=None, description="Optional current working directory for deduplication"
    )
    is_windows: bool = Field(
        default=False, description="Whether execution target is Windows environment"
    )


class CreateResumePlanResponse(BaseModel):
    """Result of generating a resume command plan."""

    model_config = ConfigDict(extra="forbid")

    is_valid: bool = Field(..., description="Whether the resume plan is validated and approved")
    plan: AgentResumePlanDto | None = Field(
        default=None, description="Validated resume execution plan"
    )
    reason: str | None = Field(
        default=None, description="Rejection reason if validation failed"
    )
