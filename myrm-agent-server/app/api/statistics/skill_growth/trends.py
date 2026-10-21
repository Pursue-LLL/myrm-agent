"""Per-skill daily usage and outcome trends.

[INPUT]
- app.api.statistics.skill_growth.ledger::(iter_skill_ledgers, dated_outcomes, window_is_clipped) (POS: usage ledger read path)
- app.api.statistics.skill_growth.models::(SkillTrendPoint, SkillTrendSeries) (POS: response contract)

[OUTPUT]
- fetch_skill_trends: Daily use count and observed success rate of the last N days for every skill that ran in them, busiest skill first

[POS]
Trend panel data of the growth dashboard; runs without an observed outcome count as uses only. The window is the
dashboard's selected range, a rolling one like the health and cost panels. A day is the viewer's calendar day, so a
run lands on the date the viewer lived it, and the chart opens on the skill that ran most. A skill whose ledger no
longer reaches back to the window start is flagged ``truncated`` rather than drawn as if complete.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, tzinfo

from app.api.statistics.skill_growth.ledger import dated_outcomes, iter_skill_ledgers, window_is_clipped
from app.api.statistics.skill_growth.models import SkillTrendPoint, SkillTrendSeries

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _DayBucket:
    total: int = 0
    successes: int = 0
    failures: int = 0


def _total_calls(series: SkillTrendSeries) -> int:
    return sum(point.call_count for point in series.data_points)


async def fetch_skill_trends(days: int, tz: tzinfo = UTC) -> list[SkillTrendSeries]:
    """Aggregate per-skill usage_history of the last ``days`` days into daily trend series, with days counted in ``tz``."""
    try:
        since = datetime.now(UTC) - timedelta(days=days)
        result: list[SkillTrendSeries] = []
        for skill_dir, stats in iter_skill_ledgers():
            daily: dict[str, _DayBucket] = defaultdict(_DayBucket)
            dated = dated_outcomes(stats)
            for moment, success in dated:
                if moment < since:
                    continue
                bucket = daily[moment.astimezone(tz).date().isoformat()]
                bucket.total += 1
                if success is True:
                    bucket.successes += 1
                elif success is False:
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
            result.append(
                SkillTrendSeries(
                    skill_name=skill_dir.name,
                    data_points=data_points,
                    truncated=window_is_clipped(stats, dated, since),
                )
            )

        result.sort(key=lambda series: (-_total_calls(series), series.skill_name))
        return result
    except Exception as e:
        logger.warning("Failed to fetch skill trends: %s", e)
        return []
