"""Persist wiki maintain run state for UI observability.

[INPUT]
- app.services.wiki.maintain_schemas (POS: WikiMaintainState / run result DTOs)
- app.services.wiki.source_sync.agent_scope (POS: per-agent UserConfig scope key)

[OUTPUT]
- load_wiki_maintain_state / save_wiki_maintain_state / state_from_run_result

[POS]
UserConfig `wikiMaintainState` SSOT for last maintain timestamp, counts, and skip reasons.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.database.models import UserConfig
from app.services.wiki.maintain_schemas import WikiMaintainRunResult, WikiMaintainState
from app.services.wiki.source_sync.agent_scope import normalize_agent_scope

logger = logging.getLogger(__name__)

STATE_KEY = "wikiMaintainState"
_AGENTS_FIELD = "agents"


def _parse_agents_state_map(raw: object) -> dict[str, dict[str, Any]]:
    if not isinstance(raw, dict):
        return {}
    agents = raw.get(_AGENTS_FIELD)
    if isinstance(agents, dict):
        return {str(key): value for key, value in agents.items() if isinstance(value, dict)}
    if any(key in raw for key in ("last_run_at", "last_issues_found", "last_mode")):
        return {normalize_agent_scope(None): dict(raw)}
    return {}


def _serialize_agents_state_map(agents: dict[str, WikiMaintainState]) -> dict[str, object]:
    return {_AGENTS_FIELD: {scope: state.model_dump(mode="json") for scope, state in agents.items()}}


async def load_wiki_maintain_state(
    db: AsyncSession,
    *,
    agent_id: str | None = None,
) -> WikiMaintainState:
    scope = normalize_agent_scope(agent_id)
    row = (
        await db.execute(select(UserConfig).where(UserConfig.config_key == STATE_KEY))
    ).scalars().first()
    if row is None:
        return WikiMaintainState()
    raw = row.config_value
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Invalid wikiMaintainState JSON; using defaults")
            return WikiMaintainState()
    if not isinstance(raw, dict):
        return WikiMaintainState()
    agents = _parse_agents_state_map(raw)
    scoped = agents.get(scope)
    if scoped is None:
        return WikiMaintainState()
    try:
        return WikiMaintainState.model_validate(scoped)
    except ValidationError as exc:
        logger.warning("Invalid wikiMaintainState schema for scope %s: %s", scope, exc)
        return WikiMaintainState()


async def save_wiki_maintain_state(
    db: AsyncSession,
    state: WikiMaintainState,
    *,
    agent_id: str | None = None,
) -> WikiMaintainState:
    scope = normalize_agent_scope(agent_id)
    row = (
        await db.execute(select(UserConfig).where(UserConfig.config_key == STATE_KEY))
    ).scalars().first()

    agents: dict[str, WikiMaintainState] = {}
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
                    agents[key] = WikiMaintainState.model_validate(value)
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


def state_from_run_result(result: WikiMaintainRunResult) -> WikiMaintainState:
    from datetime import UTC, datetime

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
