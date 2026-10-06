"""Pydantic schemas for Sensitive Vault and Credential File Overwrite Deny Guard API.

[INPUT]
- Pydantic BaseModel and Field from pydantic.

[OUTPUT]
- DTO schemas for inspecting file write operations, unlock grants, and security alerts.

[POS]
Schema definitions for sensitive credential and vault file protection gates.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class InspectFileOperationRequest(BaseModel):
    """Payload to evaluate a file write/mutation operation against sensitive protection rules."""

    target_path: str = Field(..., description="Target file path to be created, edited, or deleted")
    operation_type: str = Field(
        default="overwrite",
        description="Operation kind: 'write', 'overwrite', 'append', 'replace', 'delete', 'truncate'",
    )
    tool_name: str = Field(default="file_write", description="Name of the tool invoking the operation")
    session_id: str = Field(default="default_session", description="Agent session ID")
    unlock_token: str | None = Field(default=None, description="Temporary explicit user unlock token")


class InspectFileOperationResponse(BaseModel):
    """Evaluation decision for sensitive file operation."""

    allowed: bool = Field(..., description="Whether mutation operation is authorized")
    matched_rule_id: str | None = Field(default=None, description="Matched sensitive rule ID if blocked")
    category: str | None = Field(default=None, description="Sensitive file category classification")
    reason: str = Field(..., description="Detailed rationale or security violation description")
    is_unlocked: bool = Field(default=False, description="Whether write was permitted via explicit unlock grant")


class IssueUnlockGrantRequest(BaseModel):
    """Request payload to issue a temporary user authorization token for a sensitive file."""

    target_path: str = Field(..., description="Path to sensitive file to temporarily unlock")
    ttl_seconds: int = Field(default=300, ge=1, le=86400, description="Grant time-to-live in seconds")
    granted_by: str = Field(default="user_explicit_dialog", description="User confirmation context")


class FileUnlockGrantResponse(BaseModel):
    """Issued temporary authorization token granting single-file write access."""

    canonical_path: str
    unlock_token: str
    expires_at: datetime
    granted_by: str


class RevokeUnlockGrantRequest(BaseModel):
    """Request to revoke an active unlock authorization token."""

    unlock_token: str = Field(..., description="Token to revoke")


class SensitiveFileAlertResponse(BaseModel):
    """Security violation audit alert for blocked file overwrite attempts."""

    alert_id: str
    session_id: str
    target_path: str
    category: str
    operation_type: str
    tool_name: str
    reason: str
    timestamp: datetime
