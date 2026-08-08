"""Persist wiki maintain run state for UI observability.

[INPUT]
- app.services.wiki.maintain.schemas (POS: WikiMaintainState / run result DTOs)
- app.services.wiki._userconfig_scoped (POS: shared UserConfig scoped persistence)

[OUTPUT]
- load_wiki_maintain_state / save_wiki_maintain_state / state_from_run_result

[POS]
UserConfig `wikiMaintainState` SSOT for last maintain timestamp, counts, and skip reasons.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.wiki._userconfig_scoped import (
    load_scoped_userconfig,
    save_scoped_userconfig,
)
from app.services.wiki.maintain.schemas import WikiMaintainRunResult, WikiMaintainState

STATE_KEY = "wikiMaintainState"
_LEGACY_KEYS = ("last_run_at", "last_issues_found", "last_mode")


async def load_wiki_maintain_state(
    db: AsyncSession,
    *,
    agent_id: str | None = None,
) -> WikiMaintainState:
    """Load the scoped wiki maintain state from UserConfig."""
    return await load_scoped_userconfig(
        db,
        config_key=STATE_KEY,
        model=WikiMaintainState,
        agent_id=agent_id,
        legacy_keys=_LEGACY_KEYS,
        invalid_log_label="wikiMaintainState",
    )


async def save_wiki_maintain_state(
    db: AsyncSession,
    state: WikiMaintainState,
    *,
    agent_id: str | None = None,
) -> WikiMaintainState:
    """Merge the current run state into the scoped UserConfig store."""
    return await save_scoped_userconfig(
        db,
        config_key=STATE_KEY,
        model=WikiMaintainState,
        value=state,
        agent_id=agent_id,
        legacy_keys=_LEGACY_KEYS,
    )


def state_from_run_result(result: WikiMaintainRunResult) -> WikiMaintainState:
    return WikiMaintainState(
        last_run_at=datetime.now(UTC),
        last_mode=result.mode,
        last_issues_found=result.issues_found,
        last_issues_fixed=result.issues_fixed,
        last_connections_discovered=result.connections_discovered,
        last_duration_ms=result.duration_ms,
        last_skipped_reason=result.skipped_reason,
        last_output=result.summary_text,
    )
