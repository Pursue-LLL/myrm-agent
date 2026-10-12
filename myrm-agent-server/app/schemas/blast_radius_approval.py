"""
[POS] app/schemas/blast_radius_approval.py
[INPUT] pydantic
[OUTPUT] Blast radius dry-run impact preview & typed launch code DTOs
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class EvaluateCommandApprovalRequestDTO(BaseModel):
    """Payload to evaluate impact preview and launch code requirements for a single command."""

    command: str = Field(..., description="Bash command string to inspect")
    workspace_dir: str | None = Field(default=None, description="Optional working directory path")
    span_id: str | None = Field(default=None, description="Optional span or step identifier")


class ImpactPreviewTargetDTO(BaseModel):
    """Enumerated file, directory, or ref target affected by the command."""

    path_or_identifier: str = Field(..., description="Path, ref, or table name")
    target_type: str = Field(..., description="Target category: file, directory, git_ref, database_table")
    action: str = Field(default="delete", description="Anticipated action: delete, rewrite, drop")
    estimated_size_bytes: int | None = Field(default=None, description="Estimated byte size if known")


class DryRunImpactPreviewDTO(BaseModel):
    """Enumeration results of blast radius dry-run probe."""

    command: str = Field(..., description="Evaluated command")
    estimated_files_count: int = Field(..., description="Estimated number of affected files")
    estimated_dirs_count: int = Field(..., description="Estimated number of affected directories")
    targets: list[ImpactPreviewTargetDTO] = Field(..., description="Enumerated targets list (capped)")
    is_truncated: bool = Field(..., description="Whether targets list exceeds preview cap")
    probe_duration_ms: float = Field(..., description="Probe execution time in milliseconds")
    is_fallback_static: bool = Field(..., description="Whether probe used static fallback")
    summary: str = Field(..., description="Human readable impact summary")


class LaunchCodeRequirementDTO(BaseModel):
    """One-time challenge code metadata for high-risk irreversible actions."""

    requires_challenge: bool = Field(..., description="Whether typed challenge is required")
    challenge_token: str | None = Field(default=None, description="Issued 6-character challenge token")
    expected_keyword: str | None = Field(default=None, description="Expected confirmation keyword")
    expires_at: float | None = Field(default=None, description="Expiration epoch timestamp")
    is_used: bool = Field(default=False, description="Whether token has been consumed")
    prompt_message: str | None = Field(default=None, description="User instruction prompt")


class ApprovalSpanGroupPolicyDTO(BaseModel):
    """Policy decision and presentation metadata for an approval card."""

    span_id: str = Field(..., description="Unique span identifier")
    command: str = Field(..., description="Full command text")
    is_destructive: bool = Field(..., description="Whether command is destructive")
    never_folded: bool = Field(..., description="Whether command must be kept in standalone group")
    impact_preview: DryRunImpactPreviewDTO | None = Field(default=None, description="Dry-run impact preview")
    launch_code: LaunchCodeRequirementDTO | None = Field(default=None, description="Typed launch challenge")
    allowed_shortcuts: list[str] = Field(..., description="Keyboard shortcuts allowed for this card")


class BatchSpanItemDTO(BaseModel):
    """Item specification in batch approval request."""

    span_id: str = Field(..., description="Span or sub-task ID")
    command: str = Field(..., description="Command string")


class EvaluateBatchSpansRequestDTO(BaseModel):
    """Payload to partition multiple batch spans into never-fold groups."""

    commands: list[BatchSpanItemDTO] = Field(..., description="List of spans to partition")
    workspace_dir: str | None = Field(default=None, description="Optional working directory")


class EvaluateBatchSpansResponseDTO(BaseModel):
    """Batch evaluation response containing policies and isolated decision groups."""

    policies: list[ApprovalSpanGroupPolicyDTO] = Field(..., description="Policies for each span")
    decision_groups: list[list[str]] = Field(..., description="Grouped span IDs for batch decision")


class VerifyLaunchCodeRequestDTO(BaseModel):
    """Payload to verify a typed launch code."""

    token: str = Field(..., description="Issued challenge token")
    user_input: str = Field(..., description="User submitted confirmation input")


class VerifyLaunchCodeResponseDTO(BaseModel):
    """Verification outcome of typed launch challenge."""

    is_valid: bool = Field(..., description="Whether challenge code is verified and consumed")
    reason: str = Field(..., description="Diagnostic result explanation")
