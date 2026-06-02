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
    config_schema: dict[str, object] | None = None
    has_upstream_update: bool = False

    traps: list[dict[str, object]] = []
    verification_steps: list[dict[str, object]] = []

    created_at: str
    updated_at: str


class SkillListResponse(BaseModel):
    """Paginated skill list."""

    skills: list[SkillResponse]
    total: int


class UserSkillConfigResponse(BaseModel):
    """User skill configuration."""

    enabled_prebuilt_ids: list[str]
    disabled_prebuilt_ids: list[str] = []
    local_skill_paths: list[str] = []
    enabled_local_skill_ids: list[str] = []
    updated_at: str


class UpdateUserSkillConfigRequest(BaseModel):
    """Update enabled prebuilt skill IDs."""

    enabled_prebuilt_ids: list[str]


class LocalSkillPathsRequest(BaseModel):
    paths: list[str]


class LocalSkillPathsResponse(BaseModel):
    paths: list[str]
    default_paths: list[str]


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


class UploadSkillResponse(BaseModel):
    success: bool
    skill_id: str | None
    skill_name: str | None
    error: str | None


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


def _lookup_evolution_data(
    skill_name: str,
) -> tuple[list[dict[str, object]], list[dict[str, object]], bool]:
    """Best-effort lookup of evolution traps and lock status for a skill.

    Returns:
        Tuple of (traps, verification_steps, evolution_locked)
    """
    try:
        from myrm_agent_harness.agent.skills.evolution.infra.integration import (
            get_global_evolution_integration,
        )

        evolution = get_global_evolution_integration()
        if evolution and evolution.store:
            record = evolution.store.get_skill_by_name_version(skill_name)
            if record:
                return record.traps, record.verification_steps, record.evolution_locked
    except Exception as e:
        logger.debug("Evolution data lookup failed for %s: %s", skill_name, e)
    return [], [], False


def skill_to_response(skill: Skill) -> SkillResponse:
    """Convert Skill model to SkillResponse."""
    security = None
    if skill.security is not None:
        security = SecurityScanSummaryResponse(
            score=skill.security.score,
            trust_recommendation=skill.security.trust_recommendation,
            finding_counts=skill.security.finding_counts,
            total_findings=skill.security.total_findings,
            findings=[
                SecurityFindingResponse(
                    threat_type=f.threat_type,
                    severity=f.severity,
                    description=f.description,
                )
                for f in skill.security.findings
            ],
        )

    traps, verification_steps, store_evolution_locked = _lookup_evolution_data(
        skill.name
    )
    evolution_locked = skill.evolution_locked or store_evolution_locked

    usage = SkillUsageStatsResponse()
    if skill.usage_stats:
        usage = SkillUsageStatsResponse(
            call_count=int(skill.usage_stats.get("call_count", 0)),
            success_count=int(skill.usage_stats.get("success_count", 0)),
            failure_count=int(skill.usage_stats.get("failure_count", 0)),
            last_used_at=(
                str(skill.usage_stats["last_used_at"])
                if skill.usage_stats.get("last_used_at")
                else None
            ),
            success_rate=float(skill.usage_stats.get("success_rate", 0.0)),
            avg_duration_ms=float(skill.usage_stats.get("avg_duration_ms", 0.0)),
            lifecycle_status=str(skill.usage_stats.get("lifecycle_status", "active")),
            pinned=bool(skill.usage_stats.get("pinned", False)),
        )

    return SkillResponse(
        id=skill.id,
        type=skill.type.value,
        name=skill.name,
        description=skill.description,
        storage_path=skill.storage_path,
        version=skill.version,
        category=skill.category,
        icon_url=skill.icon_url,
        tags=skill.tags,
        is_active=skill.is_active,
        requires=SkillRequiresResponse(
            bins=skill.requires.bins,
            env=skill.requires.env,
            config=skill.requires.config,
        ),
        available=skill.available,
        unavailable_reason=skill.unavailable_reason,
        trust=skill.trust,
        author=skill.author,
        homepage=skill.homepage,
        usage_stats=usage,
        always=skill.always,
        model_invocable=skill.model_invocable,
        user_invocable=skill.user_invocable,
        primary_env=skill.primary_env,
        security=security,
        user_trusted=skill.user_trusted,
        evolution_locked=evolution_locked,
        scope_agent_id=skill.scope_agent_id,
        config_schema=skill.config_schema,
        has_upstream_update=skill.has_upstream_update,
        traps=traps,
        verification_steps=verification_steps,
        created_at=skill.created_at.isoformat(),
        updated_at=skill.updated_at.isoformat(),
    )
