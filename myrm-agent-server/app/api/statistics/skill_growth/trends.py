"""Per-skill daily usage and outcome trends.

[INPUT]
- app.api.statistics.skill_growth.ledger::iter_skill_ledgers (POS: usage ledger read path)
- app.api.statistics.skill_growth.models::(SkillTrendPoint, SkillTrendSeries) (POS: response contract)

[OUTPUT]
- fetch_skill_trends: Daily use count and observed success rate for every skill with history

[POS]
Trend panel data of the growth dashboard; runs without an observed outcome count as uses only.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass

from app.api.statistics.skill_growth.ledger import iter_skill_ledgers
from app.api.statistics.skill_growth.models import SkillTrendPoint, SkillTrendSeries

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _DayBucket:
    total: int = 0
    successes: int = 0
    failures: int = 0


async def fetch_skill_trends() -> list[SkillTrendSeries]:
    """Aggregate per-skill usage_history into daily trend series."""
    try:
        result: list[SkillTrendSeries] = []
        for skill_dir, stats in iter_skill_ledgers():
            if not stats.usage_history:
                continue

            daily: dict[str, _DayBucket] = defaultdict(_DayBucket)
            for record in stats.usage_history:
                bucket = daily[record.timestamp[:10]]
                bucket.total += 1
                if record.success is True:
                    bucket.successes += 1
                elif record.success is False:
                    bucket.failures += 1

            data_points: list[SkillTrendPoint] = []
            for date_key in sorted(daily):
                bucket = daily[date_key]
                observed = bucket.successes + bucket.failures
                data_points.append(
                    SkillTrendPoint(
                        date=date_key,
                        success_rate=(bucket.successes / observed if observed > 0 else None),
                        observed_count=observed,
                        call_count=bucket.total,
                    )
                )
            result.append(SkillTrendSeries(skill_name=skill_dir.name, data_points=data_points))
        return result
    except Exception as e:
        logger.warning("Failed to fetch skill trends: %s", e)
        return []
