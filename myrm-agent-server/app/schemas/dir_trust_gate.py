"""Schemas for Directory Trust Gate."""

from pydantic import BaseModel, Field


class DirectoryTrustEvaluateRequest(BaseModel):
    """Request to evaluate a directory and its project remote settings."""

    directory: str = Field(..., description="Project workspace directory path")
    remote_url: str | None = Field(
        default=None, description="Configured remote sync/dial URL"
    )
    remote_token: str | None = Field(
        default=None, description="Configured remote token"
    )
    scope: str | None = Field(default=None, description="Configured workspace scope")


class DirectoryTrustEvaluateResponse(BaseModel):
    """Response containing sanitized gated configuration and trust decision."""

    sanitized_directory: str
    is_trusted: bool
    is_remote_allowed: bool
    allowed_remote_url: str | None
    allowed_remote_token: str | None
    effective_scope: str | None
    warning_message: str | None = None


class DirectoryTrustActionRequest(BaseModel):
    """Request to trust or untrust a directory."""

    directory: str = Field(..., description="Project workspace directory path")
    reason: str = Field(
        default="manual_grant", description="Reason or context for trust action"
    )


class DirectoryTrustActionResponse(BaseModel):
    """Response indicating outcome of trust/untrust action."""

    directory: str
    success: bool
    action: str
    is_trusted: bool


class DirectoryTrustListResponse(BaseModel):
    """Response listing all trusted directories."""

    trusted_directories: list[str]
    count: int
