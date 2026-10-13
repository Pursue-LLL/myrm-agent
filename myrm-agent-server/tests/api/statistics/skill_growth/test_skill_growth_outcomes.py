"""Growth dashboard skill panels read uses and observed outcomes from the real ``.stats.json`` ledger."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta, tzinfo
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from myrm_agent_harness.backends.skills.forgetting_strategy import CuratorConfig
from myrm_agent_harness.backends.skills.stats_collector import SkillStatsCollector
from myrm_agent_harness.backends.skills.types import SkillUsageStats

from app.api.statistics.skill_growth import SkillTrendSeries, fetch_skill_health, fetch_skill_trends


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
async def test_skill_without_a_run_this_week_is_not_on_the_panel(skills_root: Path) -> None:
    """Uses older than the window say nothing about this week's health; the active neighbour stays."""
    _write_stats(skills_root, "old", [True, True], days_ago=20)
    _write_stats(skills_root, "active", [True] * 5)

    assert [item.skill_name for item in await fetch_skill_health()] == ["active"]


@pytest.mark.asyncio
async def test_never_used_archived_and_pinned_idle_skills_are_not_reported_stale(skills_root: Path) -> None:
    """The curator owns dormancy: the panel neither flags a fresh install nor a pinned or archived skill."""
    long_ago = datetime.now(UTC) - timedelta(days=60)
    ledgers = {
        "fresh-install": SkillUsageStats(created_at=datetime.now(UTC) - timedelta(days=12)),
        "pinned-idle": SkillUsageStats(call_count=3, success_count=3, last_used_at=long_ago, pinned=True),
        "archived": SkillUsageStats(call_count=3, success_count=3, last_used_at=long_ago, lifecycle_status="archived"),
    }
    for name, stats in ledgers.items():
        (skills_root / name).mkdir()
        (skills_root / name / ".stats.json").write_text(json.dumps(stats.to_dict()))
    _write_stats(skills_root, "active", [True, None])

    assert [item.skill_name for item in await fetch_skill_health()] == ["active"]


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

    assert await fetch_skill_health() == []


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


def _write_history(root: Path, name: str, records: list[tuple[str, bool | None]]) -> None:
    """Persist a ledger holding exactly the given ``(timestamp, outcome)`` records."""
    skill_dir = root / name
    skill_dir.mkdir()
    stats = SkillUsageStats(call_count=len(records), created_at=datetime.now(UTC))
    for timestamp, outcome in records:
        stats.append_usage(timestamp, outcome)
    (skill_dir / ".stats.json").write_text(json.dumps(stats.to_dict()))


def _dates(series_list: list[SkillTrendSeries], name: str) -> list[str]:
    (series,) = (series for series in series_list if series.skill_name == name)
    return [point.date for point in series.data_points]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("timestamp", "timezone", "expected_day"),
    [
        ("2026-10-12T23:30:00+00:00", UTC, "2026-10-12"),
        ("2026-10-12T23:30:00+00:00", ZoneInfo("Asia/Shanghai"), "2026-10-13"),
        ("2026-10-12T05:30:00+00:00", ZoneInfo("America/Los_Angeles"), "2026-10-11"),
    ],
    ids=["utc", "ahead-of-utc", "behind-utc"],
)
async def test_trend_day_is_the_viewers_calendar_day(
    skills_root: Path, timestamp: str, timezone: tzinfo, expected_day: str
) -> None:
    """07:30 in Shanghai is 23:30 UTC the evening before; the chart must show the day the user lived it."""
    _write_history(skills_root, "morning-run", [(timestamp, True)])

    assert _dates(await fetch_skill_trends(timezone), "morning-run") == [expected_day]


@pytest.mark.asyncio
async def test_trend_days_default_to_utc(skills_root: Path) -> None:
    _write_history(skills_root, "morning-run", [("2026-10-12T23:30:00+00:00", True)])

    assert _dates(await fetch_skill_trends(), "morning-run") == ["2026-10-12"]


@pytest.mark.asyncio
async def test_trend_series_list_the_busiest_skill_first(skills_root: Path) -> None:
    """The chart opens on the first series, so ledger directory order must not decide which skill that is."""
    when = datetime.now(UTC).isoformat()
    for name, runs in {"quiet": 1, "busy": 5, "alpha-tie": 3, "beta-tie": 3}.items():
        _write_history(skills_root, name, [(when, True)] * runs)

    assert [series.skill_name for series in await fetch_skill_trends()] == ["busy", "alpha-tie", "beta-tie", "quiet"]


@pytest.mark.asyncio
async def test_unreadable_timestamp_skips_only_that_record(skills_root: Path) -> None:
    _write_history(
        skills_root,
        "hand-edited",
        [("not-a-time", True), ("2026-10-12T08:00:00Z", True), ("2026-10-12T09:00:00", False)],
    )
    _write_history(skills_root, "neighbour", [("2026-10-12T08:00:00+00:00", True)])

    series = {s.skill_name: s for s in await fetch_skill_trends()}

    (point,) = series["hand-edited"].data_points
    assert (point.date, point.call_count, point.observed_count) == ("2026-10-12", 2, 2)
    assert "neighbour" in series


@pytest.mark.asyncio
async def test_skill_whose_records_are_all_unreadable_has_no_trend(skills_root: Path) -> None:
    _write_history(skills_root, "garbled", [("never", True)])

    assert await fetch_skill_trends() == []


@pytest.mark.asyncio
async def test_reading_the_panels_never_creates_a_ledger_in_a_directory_without_one(skills_root: Path) -> None:
    """The skill roots include folders of other tools; a read-only dashboard must leave them as it found them."""
    _write_stats(skills_root, "used", [True])
    foreign = skills_root / "installed-by-another-tool"
    foreign.mkdir()

    assert [item.skill_name for item in await fetch_skill_health()] == ["used"]
    assert [series.skill_name for series in await fetch_skill_trends()] == ["used"]

    assert list(foreign.iterdir()) == []
