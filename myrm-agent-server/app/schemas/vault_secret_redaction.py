"""Schemas for always-on vault secret dynamic redaction endpoints.

[INPUT]
- Text, tool outputs, user messages, stream chunks, secret registrations, and config.

[OUTPUT]
- Pydantic models validating serialization and request/response structures.

[POS]
- Server schemas in app/schemas/vault_secret_redaction.py.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RedactTextRequest(BaseModel):
    """Request payload for redacting secrets from raw text."""

    text: str = Field(..., description="Raw text containing potential secrets")


class RedactTextResponse(BaseModel):
    """Response payload for text redaction."""

    clean_content: str = Field(..., description="Scrubbed text")
    redacted_count: int = Field(..., description="Total count of replaced secrets")
    matched_secrets: list[str] = Field(
        default_factory=list, description="Names of secrets detected and replaced"
    )


class RedactToolReturnRequest(BaseModel):
    """Request payload for redacting tool execution output."""

    tool_name: str = Field(..., description="Name of the executed tool")
    output_text: str = Field(..., description="Captured stdout, stderr, or result text")
    metadata: dict[str, str] = Field(
        default_factory=dict, description="Metadata dictionary associated with tool call"
    )


class RedactToolReturnResponse(BaseModel):
    """Response payload for tool return redaction."""

    tool_name: str
    clean_output: str
    clean_metadata: dict[str, str]
    redacted_count: int
    matched_secrets: list[str]


class RedactUserMessageRequest(BaseModel):
    """Request payload for redacting inbound user messages."""

    user_id: str = Field(default="user_default", description="ID of sender")
    content: str = Field(..., description="User message content")


class RedactUserMessageResponse(BaseModel):
    """Response payload for inbound user message redaction."""

    user_id: str
    clean_content: str
    redacted_count: int
    matched_secrets: list[str]


class StreamScrubPushRequest(BaseModel):
    """Request payload to push a chunk through the stream scrubber."""

    session_id: str = Field(..., description="Unique streaming session identifier")
    chunk: str = Field(..., description="Incremental streaming text chunk")


class StreamScrubFlushRequest(BaseModel):
    """Request payload to flush remaining held-back bytes in a stream session."""

    session_id: str = Field(..., description="Unique streaming session identifier")


class StreamScrubResponse(BaseModel):
    """Response payload for stream scrubbing chunk evaluation."""

    session_id: str
    emitted_chunk: str
    held_back_len: int


class RegisterSecretRequest(BaseModel):
    """Request payload to register a secret for redaction."""

    name: str = Field(..., description="Label or name of the secret")
    value: str = Field(..., description="Sensitive secret value (min 8 chars)")
    source: str = Field(
        default="dynamic_captured",
        description="Origin: vault, ambient_env, or dynamic_captured",
    )
    mask: str | None = Field(
        default=None, description="Optional custom mask string"
    )


class RegisterSecretResponse(BaseModel):
    """Response payload for secret registration."""

    name: str
    registered: bool
    message: str


class SecretListResponse(BaseModel):
    """Response payload listing registered secret names."""

    secret_names: list[str]
    total_count: int


class UnregisterSecretResponse(BaseModel):
    """Response payload for unregistering a secret."""

    name: str
    unregistered: bool


class RedactionStatsResponse(BaseModel):
    """Response payload returning match statistics per secret."""

    stats: dict[str, int]
    total_matches: int


class RedactionConfigSchema(BaseModel):
    """Configuration model for redaction engine."""

    min_secret_length: int = Field(default=8, ge=3)
    mask_template: str = Field(default="{name}=<REDACTED>")
    strip_ansi: bool = True
    case_sensitive: bool = True


class RedactionConfigUpdateRequest(BaseModel):
    """Update payload for redaction engine configuration."""

    min_secret_length: int | None = None
    mask_template: str | None = None
    strip_ansi: bool | None = None
    case_sensitive: bool | None = None
