"""Conversion helpers between Skill models and API schemas.

[INPUT]
- Skill: Core business skill model

[OUTPUT]
- SkillResponse: API schema for single skill details
- SecurityScanSummaryResponse: Security audit summary schema
"""

from __future__ import annotations

import logging

from app.core.skills.models import Skill

from .schemas import (
    SecurityFindingResponse,
    SecurityScanSummaryResponse,
    SkillRequiresResponse,
    SkillResponse,
    SkillUsageStatsResponse,
)

logger = logging.getLogger(__name__)


def _lookup_evolution_data(
    skill_name: str,
) -> tuple[list[dict[str, object]], list[dict[str, object]], bool, list[dict[str, object]]]:
    """Best-effort lookup of evolution traps, verification steps, lock status and eval cases."""
    try:
        from myrm_agent_harness.agent.skills.evolution.infra.integration import (
            get_global_evolution_integration,
        )

        evolution = get_global_evolution_integration()
        if evolution and evolution.store:
            record = evolution.store.get_skill_by_name_version(skill_name)
            if record:
                return (
                    record.traps,
                    record.verification_steps,
                    record.evolution_locked,
                    record.eval_cases,
                )
    except Exception as e:
        logger.debug("Evolution data lookup failed for %s: %s", skill_name, e)
    return [], [], False, []


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
                    line_number=getattr(f, "line_number", None),
                )
                for f in skill.security.findings
            ],
        )

    traps, verification_steps, store_evolution_locked, eval_cases = _lookup_evolution_data(skill.name)
    evolution_locked = skill.evolution_locked or store_evolution_locked

    usage = SkillUsageStatsResponse()
    if skill.usage_stats:
        usage = SkillUsageStatsResponse(
            call_count=int(skill.usage_stats.get("call_count", 0)),
            success_count=int(skill.usage_stats.get("success_count", 0)),
            failure_count=int(skill.usage_stats.get("failure_count", 0)),
            last_used_at=(str(skill.usage_stats["last_used_at"]) if skill.usage_stats.get("last_used_at") else None),
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
        token_cost=skill.token_cost,
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
        scope_chat_id=skill.scope_chat_id,
        subagent_allowed=skill.subagent_allowed,
        blocked=skill.blocked,
        pending_approval=skill.pending_approval,
        required_permissions=skill.required_permissions,
        config_schema=skill.config_schema,
        has_upstream_update=skill.has_upstream_update,
        installed_from=skill.installed_from,
        traps=traps,
        verification_steps=verification_steps,
        eval_cases=eval_cases,
        created_at=skill.created_at.isoformat(),
        updated_at=skill.updated_at.isoformat(),
    )
