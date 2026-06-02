"""Skill system data models.

SkillType enum is defined in the storage layer (myrm_agent_harness.toolkits.storage.types)
because it determines skill storage path conventions.
SkillRequires is re-exported from the framework layer to avoid duplicate type definitions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from myrm_agent_harness.backends.skills.types import (
    SecurityFindingDetail,
    SecurityScanSummary,
    SkillMetadata,
    SkillRequires,
)
from myrm_agent_harness.toolkits.storage.types import SkillType as SkillType


@dataclass
class Skill:
    """Unified skill model for prebuilt and local skills."""

    id: str
    type: SkillType
    name: str
    description: str
    storage_path: str

    version: str = "1.0.0"
    category: str | None = None
    icon_url: str | None = None
    tags: list[str] = field(default_factory=list)
    is_active: bool = True
    token_cost: int | None = None

    # Dependency and availability
    requires: SkillRequires = field(default_factory=SkillRequires)
    available: bool = True
    unavailable_reason: str | None = None

    # Trust and identity
    trust: str = "installed"
    author: str | None = None
    homepage: str | None = None
    always: bool = False

    # Invocation control
    model_invocable: bool = True
    user_invocable: bool = True

    # Env injection
    primary_env: str | None = None

    # DLP Protection
    allowed_domains: list[str] | None = None

    # Security scan summary
    security: SecurityScanSummary | None = None
    user_trusted: bool = False
    """Whether this skill was manually elevated to TRUSTED by the user."""

    evolution_locked: bool = False
    """If True, this skill is locked from automatic evolution (parsed from SKILL.md)."""

    scope_agent_id: str | None = None
    """Agent ID that owns this skill, for multi-agent scoping."""

    config_schema: dict[str, object] | None = None
    """JSON Schema for skill configuration UI (from SKILL.md frontmatter)."""

    usage_stats: dict[str, object] | None = None
    """Usage statistics for the skill (e.g. last_used_at, call_count)."""

    # Prebuilt skill update tracking (three-way hash)
    origin_hash: str | None = None
    """SHA-256 of bundled source at last sync. Used by prebuilt_sync to detect user modifications."""

    has_upstream_update: bool = False
    """True when upstream changed but user-modified content was preserved during sync."""

    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "type": self.type.value,
            "name": self.name,
            "description": self.description,
            "storage_path": self.storage_path,
            "version": self.version,
            "category": self.category,
            "icon_url": self.icon_url,
            "tags": self.tags,
            "is_active": self.is_active,
            "token_cost": self.token_cost,
            "requires": self.requires.to_dict(),
            "available": self.available,
            "unavailable_reason": self.unavailable_reason,
            "trust": self.trust,
            "author": self.author,
            "homepage": self.homepage,
            "always": self.always,
            "model_invocable": self.model_invocable,
            "user_invocable": self.user_invocable,
            "primary_env": self.primary_env,
            "allowed_domains": self.allowed_domains,
            "security": self.security.to_dict() if self.security else None,
            "evolution_locked": self.evolution_locked,
            "scope_agent_id": self.scope_agent_id,
            "config_schema": self.config_schema,
            "usage_stats": self.usage_stats,
            "origin_hash": self.origin_hash,
            "has_upstream_update": self.has_upstream_update,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_metadata(
        cls,
        meta: SkillMetadata,
        *,
        skill_id: str,
        skill_type: SkillType,
        category: str | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> Skill:
        """Adapt a framework-layer SkillMetadata into a business-layer Skill."""
        now = datetime.utcnow()
        return cls(
            id=skill_id,
            type=skill_type,
            name=meta.name,
            description=meta.description,
            storage_path=meta.storage_path or "",
            version=meta.version or "1.0.0",
            category=category,
            tags=[],
            is_active=True,
            requires=meta.requires or SkillRequires(),
            available=meta.available,
            unavailable_reason=meta.unavailable_reason,
            trust=meta.trust.name.lower(),
            author=meta.metadata.get("author"),
            homepage=meta.metadata.get("homepage"),
            always=meta.always,
            model_invocable=meta.model_invocable,
            user_invocable=meta.user_invocable,
            primary_env=meta.primary_env,
            allowed_domains=meta.allowed_domains,
            security=meta.scan_summary,
            evolution_locked=meta.evolution_locked,
            scope_agent_id=meta.scope_agent_id,
            config_schema=meta.config_schema,
            usage_stats=(
                meta.usage_stats.to_dict()
                if hasattr(meta, "usage_stats") and meta.usage_stats
                else None
            ),
            created_at=created_at or now,
            updated_at=updated_at or now,
        )

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> Skill:
        skill_type = data.get("type")
        if isinstance(skill_type, str):
            skill_type = SkillType(skill_type)
        elif not isinstance(skill_type, SkillType):
            skill_type = SkillType.PREBUILT

        return cls(
            id=str(data.get("id", "")),
            type=skill_type,
            name=str(data.get("name", "")),
            description=str(data.get("description", "")),
            storage_path=str(data.get("storage_path", "")),
            version=str(data.get("version", "1.0.0")),
            category=_opt_str(data.get("category")),
            icon_url=_opt_str(data.get("icon_url")),
            tags=_str_list(data.get("tags")),
            is_active=bool(data.get("is_active", True)),
            token_cost=(
                int(data.get("token_cost"))
                if data.get("token_cost") is not None
                else None
            ),
            requires=SkillRequires.from_dict(data.get("requires")),
            available=bool(data.get("available", True)),
            unavailable_reason=_opt_str(data.get("unavailable_reason")),
            trust=str(data.get("trust", "installed")),
            author=_opt_str(data.get("author")),
            homepage=_opt_str(data.get("homepage")),
            always=bool(data.get("always", False)),
            model_invocable=bool(data.get("model_invocable", True)),
            user_invocable=bool(data.get("user_invocable", True)),
            primary_env=_opt_str(data.get("primary_env")),
            allowed_domains=(
                _str_list(data.get("allowed_domains"))
                if data.get("allowed_domains") is not None
                else None
            ),
            security=_parse_security_summary(data.get("security")),
            evolution_locked=bool(data.get("evolution_locked", False)),
            scope_agent_id=_opt_str(data.get("scope_agent_id")),
            config_schema=data.get("config_schema") if isinstance(data.get("config_schema"), dict) else None,
            usage_stats=_coerce_usage_stats(data.get("usage_stats")),
            origin_hash=_opt_str(data.get("origin_hash")),
            has_upstream_update=bool(data.get("has_upstream_update", False)),
            created_at=_parse_datetime(data.get("created_at")),
            updated_at=_parse_datetime(data.get("updated_at")),
        )


def _coerce_usage_stats(raw: object) -> dict[str, object] | None:
    if not isinstance(raw, dict):
        return None
    return {str(k): v for k, v in raw.items()}


def _opt_str(val: object) -> str | None:
    return str(val) if val else None


def _str_list(val: object) -> list[str]:
    return [str(v) for v in val] if isinstance(val, list) else []


def _parse_security_summary(val: object) -> SecurityScanSummary | None:
    if val is None:
        return None
    if isinstance(val, SecurityScanSummary):
        return val
    if isinstance(val, dict):
        raw_findings = val.get("findings")
        findings: tuple[SecurityFindingDetail, ...] = ()
        if isinstance(raw_findings, (list, tuple)):
            findings = tuple(
                SecurityFindingDetail(
                    threat_type=str(f.get("threat_type", "")),
                    severity=str(f.get("severity", "")),
                    description=str(f.get("description", "")),
                )
                for f in raw_findings
                if isinstance(f, dict)
            )
        fc_raw = val.get("finding_counts")
        finding_counts = (
            {str(k): int(v) for k, v in fc_raw.items()}
            if isinstance(fc_raw, dict)
            else {}
        )
        return SecurityScanSummary(
            score=int(val.get("score", 0)),
            trust_recommendation=str(val.get("trust_recommendation", "installed")),
            finding_counts=finding_counts,
            total_findings=int(val.get("total_findings", 0)),
            findings=findings,
        )
    return None


def _parse_datetime(val: object) -> datetime:
    if isinstance(val, datetime):
        return val
    if isinstance(val, str):
        return datetime.fromisoformat(val)
    return datetime.utcnow()


DEFAULT_LOCAL_SKILL_PATHS: list[str] = ["~/.myrm/skills"]


@dataclass
class UserSkillConfig:
    """Per-user skill preferences.

    - enabled_prebuilt_ids: enabled prebuilt skill IDs
    - local_skill_paths: local filesystem paths to scan for skills (local mode)
    - enabled_local_skill_ids: enabled local skill IDs
    """

    user_id: str
    enabled_prebuilt_ids: list[str] = field(default_factory=list)
    disabled_prebuilt_ids: list[str] = field(default_factory=list)
    """Prebuilt skill IDs the user explicitly disabled (prevents re-enable on seed sync)."""
    local_skill_paths: list[str] = field(default_factory=list)
    enabled_local_skill_ids: list[str] = field(default_factory=list)
    skill_env_vars: dict[str, dict[str, str]] = field(default_factory=dict)
    trusted_skill_ids: list[str] = field(default_factory=list)
    """Skill IDs the user has manually elevated to TRUSTED after security review."""
    evolution_strategy: str = "balanced"
    """Agent's mindset for evolution: balanced, innovate, harden, repair-only."""
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, object]:
        return {
            "user_id": self.user_id,
            "enabled_prebuilt_ids": self.enabled_prebuilt_ids,
            "disabled_prebuilt_ids": self.disabled_prebuilt_ids,
            "local_skill_paths": self.local_skill_paths,
            "enabled_local_skill_ids": self.enabled_local_skill_ids,
            "skill_env_vars": self.skill_env_vars,
            "trusted_skill_ids": self.trusted_skill_ids,
            "evolution_strategy": self.evolution_strategy,
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> UserSkillConfig:
        updated_at = data.get("updated_at")
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)
        elif not isinstance(updated_at, datetime):
            updated_at = datetime.utcnow()

        prebuilt_ids_raw = data.get("enabled_prebuilt_ids", [])
        prebuilt_ids = (
            [str(s) for s in prebuilt_ids_raw]
            if isinstance(prebuilt_ids_raw, list)
            else []
        )

        disabled_prebuilt_raw = data.get("disabled_prebuilt_ids", [])
        disabled_prebuilt_ids = (
            [str(s) for s in disabled_prebuilt_raw]
            if isinstance(disabled_prebuilt_raw, list)
            else []
        )

        local_paths_raw = data.get("local_skill_paths", [])
        local_paths = (
            [str(p) for p in local_paths_raw]
            if isinstance(local_paths_raw, list)
            else []
        )

        enabled_local_ids_raw = data.get("enabled_local_skill_ids", [])
        enabled_local_ids = (
            [str(s) for s in enabled_local_ids_raw]
            if isinstance(enabled_local_ids_raw, list)
            else []
        )

        env_vars_raw = data.get("skill_env_vars", {})
        env_vars: dict[str, dict[str, str]] = {}
        if isinstance(env_vars_raw, dict):
            for skill_id, vars_dict in env_vars_raw.items():
                if isinstance(vars_dict, dict):
                    env_vars[str(skill_id)] = {
                        str(k): str(v) for k, v in vars_dict.items()
                    }

        trusted_ids_raw = data.get("trusted_skill_ids", [])
        trusted_ids = (
            [str(s) for s in trusted_ids_raw]
            if isinstance(trusted_ids_raw, list)
            else []
        )

        return cls(
            user_id=str(data.get("user_id", "")),
            enabled_prebuilt_ids=prebuilt_ids,
            disabled_prebuilt_ids=disabled_prebuilt_ids,
            local_skill_paths=local_paths,
            enabled_local_skill_ids=enabled_local_ids,
            skill_env_vars=env_vars,
            trusted_skill_ids=trusted_ids,
            evolution_strategy=str(data.get("evolution_strategy", "balanced")),
            updated_at=updated_at,
        )


__all__ = [
    "DEFAULT_LOCAL_SKILL_PATHS",
    "Skill",
    "SkillType",
    "UserSkillConfig",
]
