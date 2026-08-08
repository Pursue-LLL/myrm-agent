"""Shared UserConfig scoped JSON persistence for wiki state / config stores.

[INPUT]
- app.database.models::UserConfig (POS: per-user config persistence)
- app.services.wiki.agent_scope::normalize_agent_scope (POS: per-agent UserConfig scope key)

[OUTPUT]
- load_scoped_userconfig / save_scoped_userconfig / exists_scoped_userconfig:
  generic load/save/exists for an agent-scoped UserConfig key storing a
  ``{agents: {scope: value}}`` payload

[POS]
Reusable persistence core for wiki state stores. Each store keeps its own
Pydantic model, legacy-key probe, and public load/save facade; this module
implements the shared UserConfig read/write/merge mechanics once. A global
lock serializes concurrent agent-scoped writes to the same row (per-agent
cron jobs may fire simultaneously).
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.database.models import UserConfig
from app.services.wiki.agent_scope import normalize_agent_scope

logger = logging.getLogger(__name__)

_AGENTS_FIELD = "agents"

# Serializes read-modify-write of a shared UserConfig row across concurrent
# agents. Without it, two agent-scoped writes (e.g. per-agent wiki cron jobs
# firing at the same time) can silently overwrite each other's scope.
_save_lock = asyncio.Lock()

TModel = TypeVar("TModel", bound=BaseModel)


def parse_agents_map(
    raw: object,
    *,
    legacy_keys: tuple[str, ...],
) -> dict[str, dict[str, Any]]:
    """Parse a ``{agents: {scope: value}}`` payload, falling back to a bare
    legacy payload (keys detected via ``legacy_keys``) under the default scope."""
    if not isinstance(raw, dict):
        return {}
    agents = raw.get(_AGENTS_FIELD)
    if isinstance(agents, dict):
        return {
            str(key): value for key, value in agents.items() if isinstance(value, dict)
        }
    if any(key in raw for key in legacy_keys):
        return {normalize_agent_scope(None): dict(raw)}
    return {}


def serialize_agents_map(agents: dict[str, TModel]) -> dict[str, object]:
    """Serialize a ``{scope: model}`` dict into the stored payload shape."""
    return {
        _AGENTS_FIELD: {
            scope: model.model_dump(mode="json") for scope, model in agents.items()
        }
    }


async def load_scoped_userconfig(
    db: AsyncSession,
    *,
    config_key: str,
    model: type[TModel],
    agent_id: str | None,
    legacy_keys: tuple[str, ...],
    invalid_log_label: str,
) -> TModel:
    """Load the scoped value for ``agent_id`` under ``config_key``."""
    scope = normalize_agent_scope(agent_id)
    row = (
        (
            await db.execute(
                select(UserConfig).where(UserConfig.config_key == config_key)
            )
        )
        .scalars()
        .first()
    )
    if row is None:
        return model()
    raw = row.config_value
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Invalid %s JSON; using defaults", invalid_log_label)
            return model()
    if not isinstance(raw, dict):
        return model()
    agents = parse_agents_map(raw, legacy_keys=legacy_keys)
    scoped = agents.get(scope)
    if scoped is None:
        return model()
    try:
        return model.model_validate(scoped)
    except ValidationError as exc:
        logger.warning(
            "Invalid %s schema for scope %s: %s", invalid_log_label, scope, exc
        )
        return model()


async def exists_scoped_userconfig(
    db: AsyncSession,
    *,
    config_key: str,
    agent_id: str | None,
    legacy_keys: tuple[str, ...],
) -> bool:
    """Return whether any scoped value exists under ``config_key``."""
    row = (
        (
            await db.execute(
                select(UserConfig).where(UserConfig.config_key == config_key)
            )
        )
        .scalars()
        .first()
    )
    if row is None:
        return False
    raw = row.config_value
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return False
    agents = parse_agents_map(raw, legacy_keys=legacy_keys)
    if agent_id is None:
        return bool(agents)
    return normalize_agent_scope(agent_id) in agents


async def save_scoped_userconfig(
    db: AsyncSession,
    *,
    config_key: str,
    model: type[TModel],
    value: TModel,
    agent_id: str | None,
    legacy_keys: tuple[str, ...],
) -> TModel:
    """Merge ``value`` into the agent-scoped store under ``config_key``."""
    async with _save_lock:
        scope = normalize_agent_scope(agent_id)
        row = (
            (
                await db.execute(
                    select(UserConfig).where(UserConfig.config_key == config_key)
                )
            )
            .scalars()
            .first()
        )

        agents: dict[str, TModel] = {}
        if row is not None:
            raw = row.config_value
            if isinstance(raw, str):
                try:
                    raw = json.loads(raw)
                except json.JSONDecodeError:
                    raw = {}
            if isinstance(raw, dict):
                for key, value_map in parse_agents_map(
                    raw, legacy_keys=legacy_keys
                ).items():
                    try:
                        agents[key] = model.model_validate(value_map)
                    except ValidationError:
                        continue

        agents[scope] = value
        payload = serialize_agents_map(agents)

        if row:
            row.config_value = payload
            row.is_encrypted = False
            flag_modified(row, "config_value")
        else:
            db.add(
                UserConfig(
                    id=str(uuid.uuid4()),
                    config_key=config_key,
                    config_value=payload,
                    version="1.0.0",
                    last_device_id="sandbox",
                    is_encrypted=False,
                )
            )
        await db.commit()
        return value
