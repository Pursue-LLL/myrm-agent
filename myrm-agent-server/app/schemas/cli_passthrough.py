"""Pydantic schemas for External CLI Subagent Passthrough API."""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class CliSubagentTypeEnum(str, Enum):
    CLAUDE_CODE = "claude_code"
    CODEX = "codex"
    CURSOR_CLI = "cursor_cli"
    GENERIC_CLI = "generic_cli"


class SubscriptionStatusEnum(str, Enum):
    ACTIVE_PRO = "active_pro"
    ACTIVE_TEAM = "active_team"
    FREE_TIER = "free_tier"
    UNAUTHENTICATED = "unauthenticated"
    DETECTED = "detected"


class SensitivityLevelEnum(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class CliProfileBundleDTO(BaseModel):
    bundle_id: str
    cli_type: CliSubagentTypeEnum
    display_name: str
    executable_name: str
    subscription_status: SubscriptionStatusEnum
    account_email_masked: Optional[str] = None
    default_flags: List[str] = Field(default_factory=list)
    timeout_seconds: int = 300
    allowed_workspace_root: str = "/workspace"
    is_installed: bool = True


class BundlesListResponse(BaseModel):
    bundles: List[CliProfileBundleDTO]
    total_bundles: int
    probe_installed_count: int


class PrivacyDisclosureCreateRequest(BaseModel):
    cli_type: CliSubagentTypeEnum
    context_summary: str
    sensitivity_level: SensitivityLevelEnum = SensitivityLevelEnum.MEDIUM


class PrivacyDisclosureDTO(BaseModel):
    disclosure_id: str
    cli_type: CliSubagentTypeEnum
    vendor_name: str
    data_handling_terms_url: str
    context_summary: str
    sensitivity_level: SensitivityLevelEnum
    user_acknowledged: bool = False
    created_at_utc: str = ""


class PrivacyDisclosureAcknowledgeRequest(BaseModel):
    disclosure_id: str
    user_acknowledged: bool = True


class CliDelegationExecuteRequest(BaseModel):
    task_id: str
    bundle_id: str
    instruction: str
    workspace_path: str
    disclosure_id: str
    context_files: List[str] = Field(default_factory=list)
    dry_run: bool = False


class CliExecutionResultDTO(BaseModel):
    task_id: str
    bundle_id: str
    exit_code: int
    diff_output: str
    structured_summary: str
    tokens_saved_estimate: int
    tamper_proof_audit_hash: str
    egress_accounting_id: str
    completed_at_utc: str
    file_changes_count: int = 0


class AuditRecordsResponse(BaseModel):
    records: List[CliExecutionResultDTO]
    total_records: int
    total_tokens_saved: int
