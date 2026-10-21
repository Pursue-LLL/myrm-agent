"""Persist wiki source sync run state for UI observability.

[INPUT]
- app.services.wiki.source_sync.schemas (POS: WikiSourceSyncState / run summary DTOs)
- app.services.wiki._userconfig_scoped (POS: shared UserConfig scoped persistence)

[OUTPUT]
- load_wiki_source_sync_state / save_wiki_source_sync_state / state_from_run_summary

[POS]
UserConfig `wikiSourceSyncState` SSOT for last sync timestamp, per-source counts, and errors.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.wiki._userconfig_scoped import (
    load_scoped_userconfig,
    save_scoped_userconfig,
)
from app.services.wiki.source_sync.schemas import (
    WikiSourceSyncRunSummary,
    WikiSourceSyncSourceState,
    WikiSourceSyncState,
)

logger = logging.getLogger(__name__)

STATE_KEY = "wikiSourceSyncState"
_LEGACY_KEYS = ("last_sync_at", "sources", "total_published")


async def load_wiki_source_sync_state(
    db: AsyncSession,
    *,
    agent_id: str | None = None,
) -> WikiSourceSyncState:
    """Load the scoped wiki source sync state from UserConfig."""
    return await load_scoped_userconfig(
        db,
        config_key=STATE_KEY,
        model=WikiSourceSyncState,
        agent_id=agent_id,
        legacy_keys=_LEGACY_KEYS,
        invalid_log_label="wikiSourceSyncState",
    )


async def save_wiki_source_sync_state(
    db: AsyncSession,
    state: WikiSourceSyncState,
    *,
    agent_id: str | None = None,
) -> WikiSourceSyncState:
    """Merge the current run state into the scoped UserConfig store."""
    return await save_scoped_userconfig(
        db,
        config_key=STATE_KEY,
        model=WikiSourceSyncState,
        value=state,
        agent_id=agent_id,
        legacy_keys=_LEGACY_KEYS,
    )


def state_from_run_summary(summary: WikiSourceSyncRunSummary) -> WikiSourceSyncState:
    errors: list[str] = []
    sources: list[WikiSourceSyncSourceState] = []
    for item in summary.results:
        sources.append(
            WikiSourceSyncSourceState(
                source=item.source,
                published=item.published,
                skipped=item.skipped,
                failed=item.failed,
                errors=item.errors[:5],
            )
        )
        for err in item.errors:
            if len(errors) >= 20:
                break
            errors.append(f"{item.source}: {err}")

    return WikiSourceSyncState(
        last_sync_at=datetime.now(UTC),
        last_errors=errors,
        sources=sources,
        total_published=summary.total_published,
        total_skipped=summary.total_skipped,
        total_failed=summary.total_failed,
    )
