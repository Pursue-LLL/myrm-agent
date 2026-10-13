"""Per-skill usage ledgers of the local skill directories.

[INPUT]
- app.core.skills.curator.service::get_stats_collector (POS: injects the harness stats collector)
- app.core.skills.models::DEFAULT_LOCAL_SKILL_PATHS (POS: local skill roots)

[OUTPUT]
- iter_skill_ledgers: Yields every local skill directory that has a usage ledger, with its usage stats

[POS]
Single read path of the trend and health panels onto the curator's ``.stats.json`` ledger. The roots include
folders owned by other tools, so a directory without a ledger is skipped: the collector would create one on read,
and a directory nobody has run has nothing to report.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from myrm_agent_harness.backends.skills.types import SkillUsageStats

_LEDGER_FILENAME = ".stats.json"  # name the harness stats collector persists a skill's ledger under


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
