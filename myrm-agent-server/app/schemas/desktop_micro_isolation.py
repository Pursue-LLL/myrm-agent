"""Pydantic schemas for Desktop Host Auth & Tool Routing Micro-Isolation.

[INPUT]
- None.

[OUTPUT]
- Typed DTO models for environment sanitization, tool route execution requests/responses,
  and micro-isolation status disclosure.

[POS]
- Server schemas. Exposes typed contracts for client desktop/UI and security gateways.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

JsonScalar = str | int | float | bool | None


class SanitizeEnvironmentRequest(BaseModel):
    """Payload to purge sensitive host credentials from an environment dictionary."""

    model_config = ConfigDict(extra="forbid")

    host_env: dict[str, str] = Field(
        ..., description="Raw host environment key-value pairs"
    )


class SanitizeEnvironmentResponse(BaseModel):
    """Sanitized environment safe for passing to micro-isolation sandboxes."""

    model_config = ConfigDict(extra="forbid")

    clean_env: dict[str, str] = Field(
        ..., description="Sanitized environment without secret keys"
    )
    stripped_keys: list[str] = Field(
        ..., description="List of sensitive keys that were purged"
    )


class RouteToolExecutionRequest(BaseModel):
    """Payload to route and execute a tool under micro-isolation policies."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(..., description="Tool name to execute, e.g. bash, file_write, read_file")
    arguments: dict[str, JsonScalar] = Field(
        default_factory=dict, description="Tool invocation arguments"
    )
    host_env: dict[str, str] = Field(
        default_factory=dict, description="Host environment variables"
    )
    target_path: str | None = Field(
        default=None, description="Target workspace file/folder path if applicable"
    )
    allow_unisolated_override: bool = Field(
        default=False,
        description="Explicit user override allowing unisolated execution if provider is missing",
    )


class RouteToolExecutionResponse(BaseModel):
    """Outcome of micro-isolation tool routing execution."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(..., description="Executed tool name")
    destination: str = Field(..., description="Target routing destination (HOST_PROCESS or MICRO_ISOLATION_SANDBOX)")
    isolation_level: str = Field(..., description="Isolation level applied")
    workspace_root: str = Field(..., description="Mounted workspace root path")
    output: str = Field(..., description="Tool execution standard output or return payload")
    stripped_credential_keys: list[str] = Field(
        default_factory=list, description="Purged host credential environment keys"
    )
    is_blocked: bool = Field(
        default=False, description="Whether tool execution was blocked by fail-closed or sandbox rules"
    )
    error_message: str | None = Field(
        default=None, description="Failure reason if execution was blocked"
    )


class IsolationStatusDisclosureDto(BaseModel):
    """System-level disclosure of active tool micro-isolation capabilities."""

    model_config = ConfigDict(extra="forbid")

    provider_available: bool = Field(..., description="Whether micro-isolation provider is available")
    default_isolation_level: str = Field(..., description="Default isolation level (MICRO_SANDBOX or FAIL_CLOSED_BLOCKED)")
    workspace_root: str = Field(..., description="Current workspace root path")
    fail_closed_enforced: bool = Field(..., description="Whether fail-closed contract is enforced")
    disclosure_notice: str = Field(..., description="Human-readable disclosure message describing isolation boundary")
