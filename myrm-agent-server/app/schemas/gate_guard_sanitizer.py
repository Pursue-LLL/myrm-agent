"""Pydantic schemas for GateGuard invisible Unicode sanitization.

[INPUT]
- None.

[OUTPUT]
- Typed DTO models for path and denial reason sanitization requests/responses.

[POS]
- Server schemas for gate guard denial output sanitization (#3103).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SanitizePathRequest(BaseModel):
    """Payload to sanitize an untrusted path in denial outputs."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(..., description="Raw path string potentially containing malicious Unicode")
    max_length: int = Field(default=500, ge=1, le=5000, description="Maximum allowed path length")


class SanitizeReasonRequest(BaseModel):
    """Payload to sanitize a denial reason or explanation string."""

    model_config = ConfigDict(extra="forbid")

    reason: str = Field(..., description="Raw denial reason string")
    max_length: int = Field(default=1000, ge=1, le=10000, description="Maximum allowed reason length")


class SanitizeResultDto(BaseModel):
    """Result of Unicode sanitization."""

    model_config = ConfigDict(extra="forbid")

    original_text: str = Field(..., description="Input text before sanitization")
    sanitized_text: str = Field(..., description="Cleaned output safe for display and logging")
    characters_removed_count: int = Field(..., description="Count of dangerous characters sanitized")
    categories_detected: list[str] = Field(
        default_factory=list, description="Categories of dangerous Unicode detected"
    )
    was_truncated: bool = Field(..., description="Whether output was truncated to max_length")
    has_modifications: bool = Field(..., description="Whether any modifications were made")


class SanitizeDenialPayloadRequest(BaseModel):
    """Payload to sanitize a full gate guard denial event."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(..., description="Target tool name")
    target_path: str | None = Field(default=None, description="Optional target file path")
    reason: str = Field(..., description="Denial reason description")


class SanitizeDenialPayloadResponse(BaseModel):
    """Sanitized gate guard denial event payload."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(..., description="Sanitized tool name")
    target_path: str | None = Field(default=None, description="Sanitized target path if provided")
    reason: str = Field(..., description="Sanitized denial reason")
    has_modifications: bool = Field(..., description="Whether any field was modified")


class GateGuardSanitizePolicySummary(BaseModel):
    """Summary of active GateGuard sanitization policy configuration."""

    model_config = ConfigDict(extra="forbid")

    replacement_char: str = Field(..., description="Character used to replace dangerous Unicode")
    max_path_length: int = Field(..., description="Default maximum path length")
    max_reason_length: int = Field(..., description="Default maximum reason length")
    supported_categories: list[str] = Field(..., description="List of recognized Unicode categories")
