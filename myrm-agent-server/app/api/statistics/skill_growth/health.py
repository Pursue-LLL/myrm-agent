"""Per-skill 7-day health verdicts.

[INPUT]
- myrm_agent_harness.observability::(SkillCompoundingMetrics, SkillHealthEvaluator) (POS: pure-rule health evaluator)
- app.core.skills.curator.service::get_curator_config (POS: the observed-outcome minimum the curator itself acts on)
- app.api.statistics.skill_growth.ledger::iter_skill_ledgers (POS: usage ledger read path)

[OUTPUT]
- fetch_skill_health: Health score, status and evidence for every local skill that ran in the window, best first

[POS]
Health panel data of the growth dashboard. Only observed outcomes weigh on a skill; a rate or quality
status needs as many outcomes as the curator requires before it acts on one. A skill with no run in the
window has no health to report: dormancy and archiving belong to the curator's lifecycle, which the
skill library already shows.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from myrm_agent_harness.observability import SkillCompoundingMetrics, SkillHealthEvaluator

from app.api.statistics.skill_growth.ledger import iter_skill_ledgers
from app.api.statistics.skill_growth.models import SkillHealthItem

logger = logging.getLogger(__name__)


def _as_utc(moment: datetime) -> datetime:
    """Ledgers that were edited or imported by hand may carry naive timestamps; read them as UTC."""
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


async def fetch_skill_health() -> list[SkillHealthItem]:
    """Evaluate per-skill health for the last 7 days via harness rules."""
    try:
        from app.core.skills.curator.service import get_curator_config

        now = datetime.now(UTC)
        week_ago = now - timedelta(days=7)
        min_observed = max(1, get_curator_config().min_call_count_for_quality_check)
        items: list[SkillHealthItem] = []

        for skill_dir, stats in iter_skill_ledgers():
            calls_7d = 0
            succ_7d = 0
            fail_7d = 0

            for rec in stats.usage_history:
                try:
                    rec_dt = _as_utc(datetime.fromisoformat(rec.timestamp.replace("Z", "+00:00")))
                except (TypeError, ValueError):
                    continue

                if rec_dt >= week_ago:
                    calls_7d += 1
                    if rec.success is True:
                        succ_7d += 1
                    elif rec.success is False:
                        fail_7d += 1

            # Counters without a history can only be placed in time by ``last_used_at``.
            if (
                not stats.usage_history
                and stats.call_count > 0
                and stats.last_used_at
                and _as_utc(stats.last_used_at) >= week_ago
            ):
                calls_7d = stats.call_count
                succ_7d = stats.success_count
                fail_7d = stats.failure_count

            if calls_7d == 0:
                continue

            evaluated = SkillHealthEvaluator.evaluate(
                SkillCompoundingMetrics(
                    skill_id=skill_dir.name,
                    invocations=calls_7d,
                    successful_invocations=succ_7d,
                    failed_invocations=fail_7d,
                ),
                min_observed=min_observed,
            )
            observed_7d = succ_7d + fail_7d

            items.append(
                SkillHealthItem(
                    skill_name=skill_dir.name,
                    health_score=evaluated.health_score,
                    status=evaluated.status.value,
                    call_count_7d=calls_7d,
                    call_count_total=stats.call_count,
                    observed_count_7d=observed_7d,
                    min_observed_count=min_observed,
                    success_rate_7d=evaluated.success_rate if observed_7d >= min_observed else None,
                    actionable_recommendation=evaluated.actionable_recommendation,
                )
            )

        items.sort(key=lambda item: (item.health_score, item.call_count_7d), reverse=True)
        return items
    except Exception as e:
        logger.warning("Failed to fetch skill health: %s", e)
        return []
