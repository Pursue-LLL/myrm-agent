"""Pydantic schemas for Slack Rotating Token Classification and Scope Inspection.

[INPUT]
- None.

[OUTPUT]
- Typed DTO models for Slack token classification and scope resolution.

[POS]
- Server schemas for OpenConnector #14c3a6c Slack rotating token recognition.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class SlackTokenTypeDto(StrEnum):
    """Semantic identity associated with a Slack token."""

    BOT = "bot"
    USER = "user"
    REFRESH = "refresh"
    UNKNOWN = "unknown"


class SlackTokenCategoryDto(StrEnum):
    """Lifecycle Category of a Slack token."""

    STATIC = "static"
    ROTATING = "rotating"
    REFRESH = "refresh"
    UNKNOWN = "unknown"


class ClassifySlackTokenRequest(BaseModel):
    """Request payload to classify a Slack token."""

    model_config = ConfigDict(extra="forbid")

    token_or_auth_header: str = Field(
        ...,
        description="Raw Slack token string or Authorization Bearer header",
    )
    raw_token_type_hint: str | None = Field(
        default=None,
        description="Optional hint for token semantic type, e.g. 'bot' or 'user'",
    )


class ClassifySlackTokenResponse(BaseModel):
    """Response payload for classified Slack token."""

    model_config = ConfigDict(extra="forbid")

    token_type: SlackTokenTypeDto = Field(..., description="Semantic identity of token")
    category: SlackTokenCategoryDto = Field(
        ..., description="Lifecycle category of token"
    )
    is_rotating: bool = Field(
        ..., description="True if token is a rotating access token"
    )
    prefix_matched: str | None = Field(
        default=None, description="Matched token prefix if any"
    )
    normalized_token: str = Field(..., description="Token with Bearer prefix stripped")
    is_bearer_wrapped: bool = Field(
        ..., description="True if token had a Bearer prefix"
    )


class InspectSlackScopeRequest(BaseModel):
    """Request payload to inspect OAuth scopes for a Slack token."""

    model_config = ConfigDict(extra="forbid")

    token_type: SlackTokenTypeDto = Field(
        default=SlackTokenTypeDto.BOT,
        description="Target token semantic type (bot or user)",
    )
    metadata: dict[str, object] = Field(
        default_factory=dict,
        description="Slack OAuth metadata dictionary containing scopes",
    )


class InspectSlackScopeResponse(BaseModel):
    """Response payload for inspected Slack OAuth scopes."""

    model_config = ConfigDict(extra="forbid")

    token_type: SlackTokenTypeDto = Field(..., description="Target token semantic type")
    resolved_scopes: list[str] = Field(
        default_factory=list,
        description="Deduplicated and sorted OAuth scope strings",
    )
    source_field: str = Field(
        ...,
        description="Metadata field provenance where scopes were resolved from",
    )
