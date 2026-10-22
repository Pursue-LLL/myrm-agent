"""Per-skill usage ledgers of the local skill directories.

[INPUT]
- app.core.skills.curator.service::get_stats_collector (POS: injects the harness stats collector)
- app.core.skills.models::DEFAULT_LOCAL_SKILL_PATHS (POS: local skill roots)

[OUTPUT]
- iter_skill_ledgers: Yields every local skill directory that has a usage ledger, with its usage stats
- as_utc / parse_record_time: Read a ledger timestamp as an aware UTC moment; one unreadable record yields None
- dated_outcomes: A ledger's usage records placed in time as (moment, observed outcome), oldest first
- window_is_clipped: Whether runs of a window may be missing because the ledger's rolling history dropped them

[POS]
Single read path of the trend and health panels onto the curator's ``.stats.json`` ledger. The roots include
folders owned by other tools, so a directory without a ledger is skipped: a directory nobody has run has nothing
to report. Ledgers edited or imported by hand may carry naive or
unparseable timestamps, so both panels place a record in time through the same tolerant reader. A ledger keeps only
its latest runs, so both panels ask the same question of it: did the window outgrow what was kept.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

from myrm_agent_harness.backends.skills.types import SkillUsageStats

_LEDGER_FILENAME = ".stats.json"  # name the harness stats collector persists a skill's ledger under


def as_utc(moment: datetime) -> datetime:
    """A naive timestamp is read as UTC, the clock the collector writes."""
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def parse_record_time(raw: str) -> datetime | None:
    """Parse one usage record's timestamp; ``None`` when it is unreadable, so only that record is skipped."""
    try:
        return as_utc(datetime.fromisoformat(raw))
    except (TypeError, ValueError):
        return None


def dated_outcomes(stats: SkillUsageStats) -> list[tuple[datetime, bool | None]]:
    """Each usage record with a readable timestamp as ``(moment, observed outcome)``, oldest first."""
    dated = [
        (moment, record.success) for record in stats.usage_history if (moment := parse_record_time(record.timestamp)) is not None
    ]
    dated.sort(key=lambda pair: pair[0])
    return dated


def window_is_clipped(stats: SkillUsageStats, dated: list[tuple[datetime, bool | None]], since: datetime) -> bool:
    """Whether runs after ``since`` may be missing: a full history that already starts inside the window may have dropped some."""
    return stats.history_is_full and bool(dated) and dated[0][0] > since


def iter_skill_ledgers() -> Iterator[tuple[Path, SkillUsageStats]]:
    """Yield ``(skill_dir, stats)`` for each non-hidden skill directory that already has a ledger."""
    from app.core.skills.curator.service import get_stats_collector
    from app.core.skills.models import DEFAULT_LOCAL_SKILL_PATHS

    collector = get_stats_collector()
    for skill_root in DEFAULT_LOCAL_SKILL_PATHS:
        expanded = Path(skill_root).expanduser()
        if not expanded.exists():
            continue
        for skill_dir in expanded.iterdir():
            if skill_dir.name.startswith(".") or not (skill_dir / _LEDGER_FILENAME).is_file():
                continue
            yield skill_dir, collector.get_stats(skill_dir)
