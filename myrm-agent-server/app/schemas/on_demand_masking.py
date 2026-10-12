"""Schemas for on-demand credential materialization and multi-encoding secret masking."""

from pydantic import BaseModel, Field


class MaskTextRequest(BaseModel):
    """Request to mask secret values in text."""

    text: str = Field(..., description="Raw text containing potential secrets")
    environment: dict[str, str] = Field(
        default_factory=dict, description="Environment variables with secrets to mask"
    )


class MaskTextResponse(BaseModel):
    """Response containing masked text and redacted key labels."""

    masked_text: str
    redacted_labels: list[str] = Field(default_factory=list)
    has_redactions: bool


class ResolveAndExecuteRequest(BaseModel):
    """Request to resolve selected credentials on demand and execute command safely."""

    command: str = Field(..., description="Command to execute")
    requested_handles: list[str] = Field(
        default_factory=list, description="Explicit credential handles to materialize"
    )
    mock_providers: dict[str, dict[str, str]] = Field(
        default_factory=dict,
        description="Credential handle to env mapping for mock/test resolution",
    )


class ResolveAndExecuteResponse(BaseModel):
    """Result of resolving credentials and executing with multi-encoding masking."""

    command: str
    resolved_env_keys: list[str]
    masked_stdout: str
    masked_stderr: str
    exit_code: int
    redacted_labels: list[str]
