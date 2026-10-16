"""[INPUT]
- myrm_agent_harness.observability.diagnostics.protocols::HealthReport (POS: 健康状态报告结构)
- myrm_agent_harness.observability.diagnostics.protocols::DiagnosticProtocol (POS: 诊断接口)
- app.core.skills.curator.local_skills::scan_local_skills (POS: 全部技能根目录扫描与已安装技能标记，与 sweep 同源)
- logging

[OUTPUT]
- SkillQualityHealthDiagnostic: 错但高频（Wrong-But-Frequent）低质技能诊断探针。

[POS]
Server 层技能生态与 Curator 质量专项健康诊断探针。
"""

from __future__ import annotations

import logging

from myrm_agent_harness.observability.diagnostics.protocols import (
    DiagnosticProtocol,
    HealthReport,
)

logger = logging.getLogger(__name__)

# Faulty skills the curator is not allowed to touch (pinned / locked / installed) pile up unnoticed;
# from this many on, the probe fails instead of warning.
_PROTECTED_FAULTY_FAIL_THRESHOLD = 3


class SkillQualityHealthDiagnostic(DiagnosticProtocol):
    """Diagnose wrong-but-frequent skills: run often, but keep failing.

    Checks:
    1. Wrong-but-frequent skills (observed run outcomes >= min_threshold and success_rate < min_rate).
    2. Exemption/protection status for pinned, evolution_locked, or installed skills: the curator
       never archives those, so they need a manual review.
    """

    async def check_health(self) -> HealthReport:
        try:
            from myrm_agent_harness.backends.skills.types import SkillLifecycleStatus

            from app.core.skills.curator.local_skills import scan_local_skills
            from app.core.skills.curator.service import (
                get_curator_config,
            )

            config = get_curator_config()

            scan = await scan_local_skills()
            all_skills = scan.skills

            total_skills = len(all_skills)
            active_count = 0
            wrong_but_frequent_skills: list[dict[str, object]] = []
            protected_wrong_count: int = 0

            for skill in all_skills:
                stats = skill.usage_stats
                if stats.lifecycle_status == SkillLifecycleStatus.ACTIVE:
                    active_count += 1

                if (
                    stats.observed_count >= config.min_call_count_for_quality_check
                    and stats.success_rate < config.min_success_rate
                ):
                    exemption_reasons: list[str] = []
                    if stats.pinned:
                        exemption_reasons.append("pinned")
                    if skill.evolution_locked:
                        exemption_reasons.append("evolution_locked")
                    if config.protect_installed_skills and skill.name in scan.installed_names:
                        exemption_reasons.append("installed_protected")

                    is_exempt = bool(exemption_reasons)
                    if is_exempt:
                        protected_wrong_count += 1

                    lifecycle_str = (
                        stats.lifecycle_status.value if hasattr(stats.lifecycle_status, "value") else str(stats.lifecycle_status)
                    )

                    wrong_but_frequent_skills.append(
                        {
                            "skill_name": skill.name,
                            "call_count": stats.call_count,
                            "observed_count": stats.observed_count,
                            "success_count": stats.success_count,
                            "failure_count": stats.failure_count,
                            "success_rate": round(stats.success_rate, 3),
                            "lifecycle_status": lifecycle_str,
                            "is_exempt_from_curator": is_exempt,
                            "exemption_reasons": exemption_reasons,
                        }
                    )

            wrong_count = len(wrong_but_frequent_skills)

            meta_data: dict[str, object] = {
                "total_skills": total_skills,
                "active_skills_count": active_count,
                "wrong_but_frequent_count": wrong_count,
                "protected_wrong_count": protected_wrong_count,
                "wrong_but_frequent_skills": wrong_but_frequent_skills,
                "min_call_threshold": config.min_call_count_for_quality_check,
                "min_success_rate_threshold": config.min_success_rate,
            }
            metrics: dict[str, float] = {
                "active_skills_count": float(active_count),
                "wrong_but_frequent_count": float(wrong_count),
                "protected_wrong_count": float(protected_wrong_count),
            }

            if protected_wrong_count >= _PROTECTED_FAULTY_FAIL_THRESHOLD:
                return HealthReport(
                    component_name="SkillEcosystem",
                    status="fail",
                    code="ERR_SKILL_PROTECTED_FAULTY",
                    message=f"{protected_wrong_count} faulty skill(s) are exempt from automatic cleanup.",
                    detail=(
                        f"Found {wrong_count} wrong-but-frequent skill(s) ({protected_wrong_count} exempt from the curator "
                        "because they are pinned, evolution-locked or installed). The curator never archives them, "
                        "so they keep failing until they are reviewed."
                    ),
                    fix_suggestion="Review these skills in Settings -> Skills: unpin, fix or archive the failing ones.",
                    meta_data=meta_data,
                    metrics=metrics,
                )

            if wrong_count > 0:
                detail_msg = f"Detected {wrong_count} wrong-but-frequent skill(s) (<{config.min_success_rate:.0%} success rate)."
                if protected_wrong_count > 0:
                    detail_msg += (
                        f" Note: {protected_wrong_count} faulty skill(s) are pinned or protected and require manual review."
                    )

                return HealthReport(
                    component_name="SkillEcosystem",
                    status="warn",
                    code="WARN_SKILL_FAULTY",
                    message=f"Skill health alert: {wrong_count} wrong-but-frequent skill(s) (<{config.min_success_rate:.0%} success rate).",
                    detail=detail_msg,
                    fix_suggestion="Review the failing skills in Settings -> Skills -> Curator and fix or archive them.",
                    meta_data=meta_data,
                    metrics=metrics,
                )

            return HealthReport(
                component_name="SkillEcosystem",
                status="pass",
                code="OK_SKILL_ECOSYSTEM_HEALTHY",
                message=f"Skill ecosystem healthy ({active_count} active skills, 0 wrong-but-frequent skills).",
                detail=f"Scanned {total_skills} local skill(s). No skill with enough observed runs is below the success-rate threshold.",
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
