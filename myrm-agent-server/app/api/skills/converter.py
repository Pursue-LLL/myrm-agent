"""Conversion helpers between Skill models and API schemas.

[INPUT]
- app.core.skills.models::Skill (POS: 统一业务层技能数据模型)
- app.core.skills.store.evolution_store::EvolutionRowIndex, find_primary_evolution_record (POS: core/skills/store 进化 SQLite 入口)

[OUTPUT]
- skill_to_response: 将核心 Skill 实体精确适配转换为 API SkillResponse 强类型响应模型
- skills_to_responses: 一次列表请求的批量转换，其中的本地技能共用一次进化行读取

[POS]
技能模型转换适配器。解耦业务模型与 HTTP 传输模式，负责安全审计摘要、演进指标与使用统计的规整映射；
本地技能的进化锁与回归用例读自存放其 SKILL.md 的进化行，与 /derive、/fix 同一规则。
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING

from app.core.skills.models import Skill
from app.core.storage.types import SkillType

from .schemas import (
    SecurityFindingResponse,
    SecurityScanSummaryResponse,
    SkillRequiresResponse,
    SkillResponse,
    SkillUsageStatsResponse,
)

if TYPE_CHECKING:
    from myrm_agent_harness.agent.skills.evolution import SkillStore

    from app.core.skills.store.evolution_store import EvolutionRowIndex

logger = logging.getLogger(__name__)


def _stat_int(stats: dict[str, object], key: str) -> int:
    value = stats.get(key, 0)
    return int(value) if isinstance(value, (int, float, str)) else 0


def _stat_float(stats: dict[str, object], key: str) -> float:
    value = stats.get(key, 0.0)
    return float(value) if isinstance(value, (int, float, str)) else 0.0


def _evolution_store() -> SkillStore | None:
    """The evolution store when the evolution system is running; the skill pages work without it."""
    try:
        from myrm_agent_harness.agent.skills.evolution.infra.integration import (
            get_global_evolution_integration,
        )

        evolution = get_global_evolution_integration()
        return evolution.store if evolution and evolution.store else None
    except Exception as e:
        logger.debug("Evolution store unavailable: %s", e)
        return None


def _lookup_evolution_data(
    skill: Skill, rows: EvolutionRowIndex | None
) -> tuple[list[dict[str, object]], bool, list[dict[str, object]]]:
    """Best-effort lookup of evolution verification steps, lock status and eval cases."""
    try:
        from app.core.skills.store.evolution_store import find_primary_evolution_record

        store = _evolution_store()
        record = find_primary_evolution_record(store, skill, rows) if store is not None else None
        if record:
            return record.verification_steps, record.evolution_locked, record.eval_cases
    except Exception as e:
        logger.debug("Evolution data lookup failed for %s: %s", skill.name, e)
    return [], False, []


def _evolution_row_index(skills: Sequence[Skill]) -> EvolutionRowIndex | None:
    """One read of the evolution rows for the local skills of a list; ``None`` when there is nothing to look up."""
    if not any(skill.type is SkillType.LOCAL for skill in skills):
        return None
    try:
        from app.core.skills.store.evolution_store import EvolutionRowIndex

        store = _evolution_store()
        return EvolutionRowIndex(store) if store is not None else None
    except Exception as e:
        logger.debug("Evolution row index failed: %s", e)
        return None


def skills_to_responses(skills: Sequence[Skill]) -> list[SkillResponse]:
    """Convert the skills of one list request; its local skills share one read of the evolution rows."""
    rows = _evolution_row_index(skills)
    return [skill_to_response(skill, rows) for skill in skills]


def skill_to_response(skill: Skill, rows: EvolutionRowIndex | None = None) -> SkillResponse:
    """Convert Skill model to SkillResponse; ``rows`` is the evolution row index of the list it belongs to."""
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

    verification_steps, store_evolution_locked, eval_cases = _lookup_evolution_data(skill, rows)
    evolution_locked = skill.evolution_locked or store_evolution_locked

    usage = SkillUsageStatsResponse()
    if skill.usage_stats:
        usage = SkillUsageStatsResponse(
            call_count=_stat_int(skill.usage_stats, "call_count"),
            success_count=_stat_int(skill.usage_stats, "success_count"),
            failure_count=_stat_int(skill.usage_stats, "failure_count"),
            last_used_at=(str(skill.usage_stats["last_used_at"]) if skill.usage_stats.get("last_used_at") else None),
            success_rate=_stat_float(skill.usage_stats, "success_rate"),
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
        oauth_issuer=getattr(skill, "oauth_issuer", None),
        required_oauth_issuers=getattr(skill, "required_oauth_issuers", []),
        required_mcp_server_ids=getattr(skill, "required_mcp_server_ids", []),
        security=security,
        user_trusted=skill.user_trusted,
        evolution_locked=evolution_locked,
        scope_agent_id=skill.scope_agent_id,
        required_permissions=skill.required_permissions,
        config_schema=skill.config_schema,
        has_upstream_update=skill.has_upstream_update,
        installed_from=skill.installed_from,
        last_replace_batch_id=getattr(skill, "last_replace_batch_id", None),
        verification_steps=verification_steps,
        eval_cases=eval_cases,
        created_at=skill.created_at.isoformat(),
        updated_at=skill.updated_at.isoformat(),
    )
