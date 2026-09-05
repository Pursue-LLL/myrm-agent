"""Skills API request/response schemas."""

import logging

from pydantic import BaseModel

from app.core.skills.models import Skill

logger = logging.getLogger(__name__)


class SkillRequiresResponse(BaseModel):
    """Skill dependency requirements."""

    bins: list[str] = []
    env: list[str] = []
    config: list[str] = []


class SecurityFindingResponse(BaseModel):
    """A single security finding for frontend display."""

    threat_type: str
    severity: str
    description: str
    line_number: int | None = None


class SecurityScanSummaryResponse(BaseModel):
    """Security scan summary for frontend visualization."""

    score: int
    trust_recommendation: str
    finding_counts: dict[str, int] = {}
    total_findings: int = 0
    findings: list[SecurityFindingResponse] = []


class SkillUsageStatsResponse(BaseModel):
    """Skill usage statistics."""

    call_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    last_used_at: str | None = None
    success_rate: float = 0.0
    avg_duration_ms: float = 0.0
    lifecycle_status: str = "active"
    pinned: bool = False


class SkillResponse(BaseModel):
    """Skill detail response including availability and trust information."""

    id: str
    type: str
    name: str
    description: str
    storage_path: str
    version: str
    category: str | None = None
    icon_url: str | None = None
    tags: list[str] = []
    is_active: bool = True
    token_cost: int | None = None

    requires: SkillRequiresResponse = SkillRequiresResponse()
    available: bool = True
    unavailable_reason: str | None = None

    trust: str = "installed"
    author: str | None = None
    homepage: str | None = None

    usage_stats: SkillUsageStatsResponse = SkillUsageStatsResponse()
    """Usage statistics for forgetting mechanism"""
    always: bool = False
    model_invocable: bool = True
    user_invocable: bool = True
    primary_env: str | None = None
    allowed_domains: list[str] | None = None

    security: SecurityScanSummaryResponse | None = None
    user_trusted: bool = False

    evolution_locked: bool = False
    scope_agent_id: str | None = None
    required_permissions: list[str] = []
    config_schema: dict[str, object] | None = None
    has_upstream_update: bool = False
    installed_from: dict[str, object] | None = None

    traps: list[dict[str, object]] = []
    verification_steps: list[dict[str, object]] = []
    eval_cases: list[dict[str, object]] = []

    created_at: str
    updated_at: str


class SkillListResponse(BaseModel):
    """Paginated skill list."""

    skills: list[SkillResponse]
    total: int


class RegistryPresetResponse(BaseModel):
    id: str
    url: str


class UserSkillConfigResponse(BaseModel):
    """User skill configuration."""

    enabled_prebuilt_ids: list[str]
    disabled_prebuilt_ids: list[str] = []
    local_skill_paths: list[str] = []
    enabled_local_skill_ids: list[str] = []
    evolution_strategy: str = "balanced"
    clawhub_registry_url: str = ""
    registry_presets: list[RegistryPresetResponse] = []
    updated_at: str


class UpdateUserSkillConfigRequest(BaseModel):
    """Update user skill configuration fields."""

    enabled_prebuilt_ids: list[str] | None = None
    evolution_strategy: str | None = None
    clawhub_registry_url: str | None = None


class LocalSkillPathsRequest(BaseModel):
    paths: list[str]


class LocalSkillPathsResponse(BaseModel):
    paths: list[str]
    default_paths: list[str]


class LocalSkillPathPreviewRequest(BaseModel):
    """Payload for dry-run previewing a local skill path."""

    path: str


class LocalSkillPreviewItem(BaseModel):
    """Preview metadata for a single skill discovered in the target path."""

    name: str
    description: str
    version: str = "1.0.0"
    author: str | None = None
    category: str | None = None
    tags: list[str] = []
    required_tools: list[str] = []
    relative_path: str
    skill_id: str = ""
    is_conflicted: bool = False
    conflict_reason: str | None = None
    is_safe: bool = True
    threat_summary: str | None = None


class LocalSkillPathPreviewResponse(BaseModel):
    """Dry-run preview result for a local skill path."""

    resolved_path: str
    exists: bool
    is_directory: bool
    total_discovered: int
    skills: list[LocalSkillPreviewItem]
    warning_message: str | None = None


class LocalSkillPathAdoptRequest(BaseModel):
    """Payload for adopting a local skill path and enabling selected skills."""

    path: str
    selected_skill_ids: list[str] = []
    agent_id: str | None = None


class LocalSkillPathAdoptResponse(BaseModel):
    """Response returned upon adopting a local skill path."""

    status: str = "ok"
    path: str
    added_to_paths: bool = True
    adopted_skills_count: int = 0
    adopted_skill_ids: list[str] = []
    agent_adopted: bool = False
    agent_id: str | None = None


class ToggleLocalSkillRequest(BaseModel):
    skill_id: str


class ToggleLocalSkillResponse(BaseModel):
    skill_id: str
    enabled: bool


class SkillPackageInfoResponse(BaseModel):
    name: str
    description: str
    version: str
    author: str | None
    files: list[str]
    is_valid: bool
    validation_errors: list[str]


class RedactionResponse(BaseModel):
    """A single redaction for frontend diff preview."""

    line_number: int
    original: str
    redacted: str
    reason: str


class PackagePreviewResponse(BaseModel):
    """Preview of skill packaging, including any redactions."""

    success: bool
    is_safe: bool
    error: str | None = None
    redactions: dict[str, list[RedactionResponse]] | None = None
    eval_cases_count: int = 0


class UploadSkillResponse(BaseModel):
    success: bool
    skill_id: str | None
    skill_name: str | None
    error: str | None
    restored_eval_cases: int = 0


class ScanFindingResponse(BaseModel):
    threat_type: str
    severity: int
    description: str
    line_number: int | None = None


class EnableSkillResponse(BaseModel):
    """Response for enable skill endpoint.

    blocked=True means scan found critical issues and enablement was prevented.
    pending_approval=True means skill requires permissions that haven't been granted yet.
    """

    skill_id: str
    enabled: bool
    blocked: bool = False
    pending_approval: bool = False
    required_permissions: list[str] = []
    scan_findings: list[ScanFindingResponse] = []


class UpdateSkillEnvVarsRequest(BaseModel):
    """Update env vars for a specific skill."""

    env_vars: dict[str, str]


class SkillEnvVarsResponse(BaseModel):
    skill_id: str
    env_vars: dict[str, str]
    required_env: list[str]
    primary_env: str | None = None


class SkillConfigVersionResponse(BaseModel):
    """Skill config version for hot-reload detection."""

    version: float


def skill_to_response(skill: Skill) -> SkillResponse:
    """Forwarding wrapper to converter.skill_to_response."""
    from .converter import skill_to_response as _skill_to_response

    return _skill_to_response(skill)


class SkillFileUpdateRequest(BaseModel):
    """Payload for updating a skill source file."""

    content: str


class SkillFileUpdateResponse(BaseModel):
    """Response returned upon successfully saving and scanning a skill file."""

    status: str = "ok"
    skill_id: str
    filename: str
    is_clean: bool = True
    trust_recommendation: str = "trusted"
    findings_count: int = 0

