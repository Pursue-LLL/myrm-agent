"""Per-skill daily usage and outcome trends.

[INPUT]
- app.api.statistics.skill_growth.ledger::(iter_skill_ledgers, parse_record_time) (POS: usage ledger read path)
- app.api.statistics.skill_growth.models::(SkillTrendPoint, SkillTrendSeries) (POS: response contract)

[OUTPUT]
- fetch_skill_trends: Daily use count and observed success rate for every skill with history, busiest skill first

[POS]
Trend panel data of the growth dashboard; runs without an observed outcome count as uses only. A day is the
viewer's calendar day, so a run lands on the date the viewer lived it, and the chart opens on the skill that ran most.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, tzinfo

from app.api.statistics.skill_growth.ledger import iter_skill_ledgers, parse_record_time
from app.api.statistics.skill_growth.models import SkillTrendPoint, SkillTrendSeries

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _DayBucket:
    total: int = 0
    successes: int = 0
    failures: int = 0


def _total_calls(series: SkillTrendSeries) -> int:
    return sum(point.call_count for point in series.data_points)


async def fetch_skill_trends(tz: tzinfo = UTC) -> list[SkillTrendSeries]:
    """Aggregate per-skill usage_history into daily trend series, with days counted in ``tz``."""
    try:
        result: list[SkillTrendSeries] = []
        for skill_dir, stats in iter_skill_ledgers():
            daily: dict[str, _DayBucket] = defaultdict(_DayBucket)
            for record in stats.usage_history:
                moment = parse_record_time(record.timestamp)
                if moment is None:
                    continue
                bucket = daily[moment.astimezone(tz).date().isoformat()]
                bucket.total += 1
                if record.success is True:
                    bucket.successes += 1
                elif record.success is False:
                    bucket.failures += 1

            if not daily:
                continue

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

        result.sort(key=lambda series: (-_total_calls(series), series.skill_name))
        return result
    except Exception as e:
        logger.warning("Failed to fetch skill trends: %s", e)
        return []
