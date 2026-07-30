"""Persist wiki source sync run state for UI observability.

[INPUT]
- app.services.wiki.source_sync.schemas (POS: WikiSourceSyncState / run summary DTOs)
- app.database.models::UserConfig (POS: UserConfig key-value persistence)

[OUTPUT]
- load_wiki_source_sync_state / save_wiki_source_sync_state / state_from_run_summary

[POS]
UserConfig `wikiSourceSyncState` SSOT for last sync timestamp, per-source counts, and errors.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.database.models import UserConfig
from app.services.wiki.source_sync.agent_scope import normalize_agent_scope
from app.services.wiki.source_sync.schemas import (
    WikiSourceSyncRunSummary,
    WikiSourceSyncSourceState,
    WikiSourceSyncState,
)

logger = logging.getLogger(__name__)

STATE_KEY = "wikiSourceSyncState"
_AGENTS_FIELD = "agents"


def _parse_agents_state_map(raw: object) -> dict[str, dict[str, Any]]:
    if not isinstance(raw, dict):
        return {}
    agents = raw.get(_AGENTS_FIELD)
    if isinstance(agents, dict):
        return {str(key): value for key, value in agents.items() if isinstance(value, dict)}
    if any(key in raw for key in ("last_sync_at", "sources", "total_published")):
        return {normalize_agent_scope(None): dict(raw)}
    return {}


def _serialize_agents_state_map(agents: dict[str, WikiSourceSyncState]) -> dict[str, object]:
    return {_AGENTS_FIELD: {scope: state.model_dump(mode="json") for scope, state in agents.items()}}


async def load_wiki_source_sync_state(
    db: AsyncSession,
    *,
    agent_id: str | None = None,
) -> WikiSourceSyncState:
    scope = normalize_agent_scope(agent_id)
    row = (
        await db.execute(select(UserConfig).where(UserConfig.config_key == STATE_KEY))
    ).scalars().first()
    if row is None:
        return WikiSourceSyncState()
    raw = row.config_value
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Invalid wikiSourceSyncState JSON; using defaults")
            return WikiSourceSyncState()
    if not isinstance(raw, dict):
        return WikiSourceSyncState()
    agents = _parse_agents_state_map(raw)
    scoped = agents.get(scope)
    if scoped is None:
        return WikiSourceSyncState()
    try:
        return WikiSourceSyncState.model_validate(scoped)
    except ValidationError as exc:
        logger.warning("Invalid wikiSourceSyncState schema for scope %s: %s", scope, exc)
        return WikiSourceSyncState()


async def save_wiki_source_sync_state(
    db: AsyncSession,
    state: WikiSourceSyncState,
    *,
    agent_id: str | None = None,
) -> WikiSourceSyncState:
    scope = normalize_agent_scope(agent_id)
    row = (
        await db.execute(select(UserConfig).where(UserConfig.config_key == STATE_KEY))
    ).scalars().first()

    agents: dict[str, WikiSourceSyncState] = {}
    if row is not None:
        raw = row.config_value
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                raw = {}
        if isinstance(raw, dict):
            for key, value in _parse_agents_state_map(raw).items():
                try:
                    agents[key] = WikiSourceSyncState.model_validate(value)
                except ValidationError:
                    continue

    agents[scope] = state
    payload = _serialize_agents_state_map(agents)

    if row:
        row.config_value = payload
        row.is_encrypted = False
        flag_modified(row, "config_value")
    else:
        db.add(
            UserConfig(
                id=str(uuid.uuid4()),
                config_key=STATE_KEY,
                config_value=payload,
                is_encrypted=False,
            )
        )
    await db.commit()
    return state


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
