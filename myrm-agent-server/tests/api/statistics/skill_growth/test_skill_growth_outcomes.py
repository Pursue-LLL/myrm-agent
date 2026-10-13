"""Growth dashboard skill panels read uses and observed outcomes from the real ``.stats.json`` ledger."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from myrm_agent_harness.backends.skills.forgetting_strategy import CuratorConfig
from myrm_agent_harness.backends.skills.stats_collector import SkillStatsCollector
from myrm_agent_harness.backends.skills.types import SkillUsageStats

from app.api.statistics.skill_growth import fetch_skill_health, fetch_skill_trends


@pytest.fixture
def skills_root(tmp_path: Path) -> Iterator[Path]:
    root = tmp_path / "skills"
    root.mkdir()
    with (
        patch("app.core.skills.curator.service.get_stats_collector", return_value=SkillStatsCollector(root)),
        patch("app.core.skills.curator.service.get_curator_config", return_value=CuratorConfig()),
        patch("app.core.skills.models.DEFAULT_LOCAL_SKILL_PATHS", [str(root)]),
    ):
        yield root


def _write_stats(root: Path, name: str, outcomes: list[bool | None], *, days_ago: float = 0.5) -> None:
    """Persist one use per outcome, all ``days_ago`` days back."""
    skill_dir = root / name
    skill_dir.mkdir()
    when = datetime.now(UTC) - timedelta(days=days_ago)
    stats = SkillUsageStats(call_count=len(outcomes), last_used_at=when, created_at=when)
    for outcome in outcomes:
        stats.append_usage(when.isoformat(), outcome)
        stats.success_count += outcome is True
        stats.failure_count += outcome is False
    (skill_dir / ".stats.json").write_text(json.dumps(stats.to_dict()))


@pytest.mark.asyncio
async def test_skill_without_observed_outcomes_is_unproven_not_failing(skills_root: Path) -> None:
    """Uses that never ran a tool still count as use, and they carry neither a rate nor a verdict."""
    _write_stats(skills_root, "advisory", [None] * 5)

    (item,) = await fetch_skill_health()

    assert item.call_count_7d == 5
    assert item.observed_count_7d == 0
    assert item.success_rate_7d is None
    assert item.status == "UNPROVEN"


@pytest.mark.asyncio
async def test_success_rate_counts_only_observed_outcomes(skills_root: Path) -> None:
    _write_stats(skills_root, "mixed", [True, True, True, True, False, False, None])

    (item,) = await fetch_skill_health()

    assert item.call_count_7d == 7
    assert (item.observed_count_7d, item.min_observed_count) == (6, 5)
    assert item.success_rate_7d == pytest.approx(2 / 3, abs=1e-3)
    assert item.status == "HEALTHY"
    assert item.actionable_recommendation


@pytest.mark.asyncio
async def test_quality_verdict_waits_for_enough_observed_outcomes(skills_root: Path) -> None:
    """A perfect rate over two runs is not evidence: no rate, no STAR."""
    _write_stats(skills_root, "fresh", [True, True])

    (item,) = await fetch_skill_health()

    assert item.call_count_7d == 2
    assert item.observed_count_7d == 2
    assert item.success_rate_7d is None
    assert item.status == "UNPROVEN"


@pytest.mark.asyncio
async def test_enough_clean_outcomes_earn_star(skills_root: Path) -> None:
    _write_stats(skills_root, "reliable", [True] * 5)

    (item,) = await fetch_skill_health()

    assert item.status == "STAR"
    assert item.health_score == 100.0
    assert item.success_rate_7d == 1.0


@pytest.mark.asyncio
async def test_observed_failures_lower_the_health_status(skills_root: Path) -> None:
    _write_stats(skills_root, "broken", [False, False, False, False, True])

    (item,) = await fetch_skill_health()

    assert item.status == "AT_RISK"
    assert item.success_rate_7d == pytest.approx(0.2, abs=1e-3)


@pytest.mark.asyncio
async def test_better_evidenced_skills_rank_first(skills_root: Path) -> None:
    _write_stats(skills_root, "one-lucky-run", [True])
    _write_stats(skills_root, "proven", [True] * 6)
    _write_stats(skills_root, "failing", [False] * 6)

    names = [item.skill_name for item in await fetch_skill_health()]

    assert names == ["proven", "one-lucky-run", "failing"]


@pytest.mark.asyncio
async def test_uses_outside_the_week_are_not_counted(skills_root: Path) -> None:
    _write_stats(skills_root, "old", [True, True], days_ago=20)

    (item,) = await fetch_skill_health()

    assert item.call_count_7d == 0
    assert item.call_count_total == 2
    assert item.success_rate_7d is None
    assert item.status == "STALE"


@pytest.mark.asyncio
async def test_skill_reset_from_legacy_counters_keeps_its_use_count(skills_root: Path) -> None:
    """Legacy files keep ``call_count`` but lose their history; the panel must not report them as unused."""
    skill_dir = skills_root / "legacy"
    skill_dir.mkdir()
    (skill_dir / ".stats.json").write_text(
        json.dumps({"call_count": 12, "success_count": 12, "last_used_at": datetime.now(UTC).isoformat()})
    )

    (item,) = await fetch_skill_health()

    assert item.call_count_7d == 12
    assert item.success_rate_7d is None
    assert item.status == "UNPROVEN"


@pytest.mark.asyncio
async def test_legacy_counters_of_a_long_idle_skill_are_not_reported_as_this_weeks_uses(skills_root: Path) -> None:
    skill_dir = skills_root / "legacy-idle"
    skill_dir.mkdir()
    long_ago = datetime.now(UTC) - timedelta(days=58)
    (skill_dir / ".stats.json").write_text(
        json.dumps({"call_count": 3, "success_count": 3, "last_used_at": long_ago.isoformat()})
    )

    (item,) = await fetch_skill_health()

    assert item.call_count_7d == 0
    assert item.call_count_total == 3
    assert item.status == "STALE"


@pytest.mark.asyncio
async def test_timestamp_without_timezone_does_not_blank_the_panel(skills_root: Path) -> None:
    _write_stats(skills_root, "healthy-neighbour", [True] * 5)
    skill_dir = skills_root / "naive-clock"
    skill_dir.mkdir()
    naive_now = datetime.now(UTC).replace(tzinfo=None).isoformat()
    (skill_dir / ".stats.json").write_text(
        json.dumps(
            {
                "call_count": 1,
                "success_count": 1,
                "last_used_at": naive_now,
                "usage_history": [{"timestamp": naive_now, "success": True}],
            }
        )
    )

    items = {item.skill_name: item for item in await fetch_skill_health()}

    assert set(items) == {"healthy-neighbour", "naive-clock"}
    assert items["naive-clock"].call_count_7d == 1


@pytest.mark.asyncio
async def test_trend_points_count_uses_and_leave_unobserved_days_without_a_rate(skills_root: Path) -> None:
    _write_stats(skills_root, "observed", [True, False, None])
    _write_stats(skills_root, "advisory", [None, None])

    series = {s.skill_name: s for s in await fetch_skill_trends()}

    (observed_point,) = series["observed"].data_points
    assert observed_point.call_count == 3
    assert observed_point.observed_count == 2
    assert observed_point.success_rate == 0.5
    (advisory_point,) = series["advisory"].data_points
    assert advisory_point.call_count == 2
    assert advisory_point.observed_count == 0
    assert advisory_point.success_rate is None
