"""[INPUT]
- myrm_agent_harness.observability.diagnostics.protocols::HealthReport (POS: 健康状态报告结构)
- myrm_agent_harness.observability.diagnostics.protocols::DiagnosticProtocol (POS: 诊断接口)
- pathlib, logging, typing

[OUTPUT]
- SkillHoardingHealthDiagnostic: 技能库囤积（Hoarding）与错但高频（Wrong-But-Frequent）低质技能诊断探针。

[POS]
Server 层技能生态与 Curator 质量专项健康诊断探针。
"""

from __future__ import annotations

import logging
from pathlib import Path

from myrm_agent_harness.observability.diagnostics.protocols import (
    DiagnosticProtocol,
    HealthReport,
)

logger = logging.getLogger(__name__)


class SkillHoardingHealthDiagnostic(DiagnosticProtocol):
    """Diagnose skill catalog hoarding and wrong-but-frequent skill degradations.

    Checks:
    1. Active skill count vs configured maximum threshold (preventing tool/skill explosion).
    2. Wrong-but-frequent skills (call_count >= min_threshold and success_rate < min_rate).
    3. Exemption/protection status for pinned, evolution_locked, or installed skills.
    """

    async def check_health(self) -> HealthReport:
        try:
            from myrm_agent_harness.backends.skills.local import LocalSkillBackend
            from myrm_agent_harness.backends.skills.types import (
                SkillLifecycleStatus,
                SkillTrust,
            )

            from app.core.skills.curator.service import (
                get_curator_config,
            )
            from app.core.skills.models import DEFAULT_LOCAL_SKILL_PATHS

            config = get_curator_config()

            all_skills = []
            for p in DEFAULT_LOCAL_SKILL_PATHS:
                expanded = Path(p).expanduser()
                if not expanded.exists():
                    continue
                backend = LocalSkillBackend(expanded, use_snapshot=False)
                all_skills.extend(await backend.list_skills())

            total_skills = len(all_skills)
            active_skills = []
            wrong_but_frequent_skills: list[dict[str, object]] = []
            protected_wrong_count: int = 0

            for skill in all_skills:
                stats = skill.usage_stats
                is_active = (stats.lifecycle_status == SkillLifecycleStatus.ACTIVE)
                if is_active:
                    active_skills.append(skill)

                if (
                    stats.call_count >= config.min_call_count_for_quality_check
                    and stats.success_rate < config.min_success_rate
                ):
                    is_pinned = bool(stats.pinned)
                    is_locked = bool(skill.evolution_locked)
                    is_installed_protected = bool(
                        config.protect_installed_skills
                        and skill.trust == SkillTrust.INSTALLED
                    )
                    is_system_protected = False
                    if config.protect_system_skills and skill.storage_path:
                        normalized = skill.storage_path.replace("\\", "/")
                        if "/prebuilt/" in normalized:
                            is_system_protected = True

                    is_exempt = (
                        is_pinned
                        or is_locked
                        or is_installed_protected
                        or is_system_protected
                    )
                    if is_exempt:
                        protected_wrong_count += 1

                    exemption_reasons: list[str] = []
                    if is_pinned:
                        exemption_reasons.append("pinned")
                    if is_locked:
                        exemption_reasons.append("evolution_locked")
                    if is_installed_protected:
                        exemption_reasons.append("installed_protected")
                    if is_system_protected:
                        exemption_reasons.append("system_protected")

                    lifecycle_str = (
                        stats.lifecycle_status.value
                        if hasattr(stats.lifecycle_status, "value")
                        else str(stats.lifecycle_status)
                    )

                    wrong_but_frequent_skills.append({
                        "skill_name": skill.name,
                        "call_count": stats.call_count,
                        "success_count": stats.success_count,
                        "failure_count": stats.failure_count,
                        "success_rate": round(stats.success_rate, 3),
                        "lifecycle_status": lifecycle_str,
                        "is_exempt_from_curator": is_exempt,
                        "exemption_reasons": exemption_reasons,
                    })

            active_count = len(active_skills)
            max_limit = config.max_skills
            wrong_count = len(wrong_but_frequent_skills)

            meta_data: dict[str, object] = {
                "total_skills": total_skills,
                "active_skills_count": active_count,
                "max_skills_limit": max_limit,
                "wrong_but_frequent_count": wrong_count,
                "protected_wrong_count": protected_wrong_count,
                "wrong_but_frequent_skills": wrong_but_frequent_skills,
                "min_call_threshold": config.min_call_count_for_quality_check,
                "min_success_rate_threshold": config.min_success_rate,
            }
            metrics: dict[str, float] = {
                "active_skills_count": float(active_count),
                "max_skills_limit": float(max_limit),
                "wrong_but_frequent_count": float(wrong_count),
                "protected_wrong_count": float(protected_wrong_count),
            }

            if active_count > max_limit or protected_wrong_count >= 3:
                return HealthReport(
                    component_name="SkillEcosystem",
                    status="fail",
                    code="ERR_SKILL_HOARDING_CRITICAL",
                    message=f"Skill hoarding critical: {active_count}/{max_limit} active skills, {protected_wrong_count} protected faulty skill(s).",
                    detail=(
                        f"Active skills ({active_count}) exceed configured limit ({max_limit}). "
                        f"Found {wrong_count} wrong-but-frequent skill(s) ({protected_wrong_count} protected from auto-curator). "
                        "Overcrowded skill catalog degrades retrieval accuracy and increases prompt token overhead."
                    ),
                    fix_suggestion="Run Curator sweep in Settings -> Skills -> Curator, or unpin/archive failing skills.",
                    meta_data=meta_data,
                    metrics=metrics,
                )

            if active_count >= int(max_limit * 0.8) or wrong_count > 0:
                issues: list[str] = []
                if active_count >= int(max_limit * 0.8):
                    issues.append(f"{active_count}/{max_limit} active skills (near capacity)")
                if wrong_count > 0:
                    issues.append(f"{wrong_count} wrong-but-frequent skill(s) (<{config.min_success_rate:.0%} success rate)")

                detail_msg = f"Detected skill health issues: {', '.join(issues)}."
                if protected_wrong_count > 0:
                    detail_msg += f" Note: {protected_wrong_count} faulty skill(s) are pinned or protected and require manual review."

                return HealthReport(
                    component_name="SkillEcosystem",
                    status="warn",
                    code="WARN_SKILL_HOARDING_OR_FAULTY",
                    message=f"Skill health alert: {', '.join(issues)}.",
                    detail=detail_msg,
                    fix_suggestion="Review skill performance in Settings -> Skills -> Curator and trigger a curation sweep.",
                    meta_data=meta_data,
                    metrics=metrics,
                )

            return HealthReport(
                component_name="SkillEcosystem",
                status="pass",
                code="OK_SKILL_ECOSYSTEM_HEALTHY",
                message=f"Skill ecosystem healthy ({active_count}/{max_limit} active skills, 0 wrong-but-frequent skills).",
                detail=f"Scanned {total_skills} local skill(s). All active skills satisfy quality and capacity thresholds.",
                meta_data=meta_data,
                metrics=metrics,
            )
        except Exception as exc:
            logger.warning("Skill ecosystem health check failed: %s", exc)
            return HealthReport(
                component_name="SkillEcosystem",
                status="pass",
                code="OK_SKILL_ECOSYSTEM_SKIPPED",
                message="Skill ecosystem health check skipped or initialized with default status.",
            )
