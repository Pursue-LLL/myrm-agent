"""Persist wiki source sync settings in UserConfig.

[INPUT]
- app.database.models::UserConfig (POS: per-user config persistence)

[OUTPUT]
- load/save/exists helpers for per-agent wikiSourceSync UserConfig key

[POS]
Server SSOT for wiki source sync UserConfig read/write (nested by agent scope).
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
from app.services.wiki.source_sync.agent_scope import normalize_agent_scope
from app.services.wiki.source_sync.schemas import WikiSourceSyncConfig

logger = logging.getLogger(__name__)

CONFIG_KEY = "wikiSourceSync"
_AGENTS_FIELD = "agents"


def _parse_agents_map(raw: object) -> dict[str, dict[str, Any]]:
    if not isinstance(raw, dict):
        return {}
    agents = raw.get(_AGENTS_FIELD)
    if isinstance(agents, dict):
        return {str(key): value for key, value in agents.items() if isinstance(value, dict)}
    if any(
        key in raw
        for key in (
            "gmail_enabled",
            "gdrive_enabled",
            "gdrive_folder_id",
            "rss_feeds",
            "auto_compile",
            "mirror_integrations_to_wiki",
        )
    ):
        return {normalize_agent_scope(None): dict(raw)}
    return {}


def _serialize_agents_map(agents: dict[str, WikiSourceSyncConfig]) -> dict[str, object]:
    return {_AGENTS_FIELD: {scope: cfg.model_dump(mode="json") for scope, cfg in agents.items()}}


async def wiki_source_sync_config_exists(db: AsyncSession, *, agent_id: str | None = None) -> bool:
    row = (
        await db.execute(select(UserConfig).where(UserConfig.config_key == CONFIG_KEY))
    ).scalars().first()
    if row is None:
        return False
    raw = row.config_value
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return False
    agents = _parse_agents_map(raw)
    if agent_id is None:
        return bool(agents)
    return normalize_agent_scope(agent_id) in agents


async def load_wiki_source_sync_config(
    db: AsyncSession,
    *,
    agent_id: str | None = None,
) -> WikiSourceSyncConfig:
    scope = normalize_agent_scope(agent_id)
    row = (
        await db.execute(select(UserConfig).where(UserConfig.config_key == CONFIG_KEY))
    ).scalars().first()
    if row is None:
        return WikiSourceSyncConfig()
    raw = row.config_value
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Invalid wikiSourceSync JSON; using defaults")
            return WikiSourceSyncConfig()
    if not isinstance(raw, dict):
        return WikiSourceSyncConfig()
    agents = _parse_agents_map(raw)
    scoped = agents.get(scope)
    if scoped is None:
        return WikiSourceSyncConfig()
    try:
        return WikiSourceSyncConfig.model_validate(scoped)
    except ValidationError as exc:
        logger.warning("Invalid wikiSourceSync schema for scope %s: %s", scope, exc)
        return WikiSourceSyncConfig()


async def save_wiki_source_sync_config(
    db: AsyncSession,
    config: WikiSourceSyncConfig,
    *,
    agent_id: str | None = None,
) -> WikiSourceSyncConfig:
    scope = normalize_agent_scope(agent_id)
    row = (
        await db.execute(select(UserConfig).where(UserConfig.config_key == CONFIG_KEY))
    ).scalars().first()

    agents: dict[str, WikiSourceSyncConfig] = {}
    if row is not None:
        raw = row.config_value
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                raw = {}
        if isinstance(raw, dict):
            for key, value in _parse_agents_map(raw).items():
                try:
                    agents[key] = WikiSourceSyncConfig.model_validate(value)
                except ValidationError:
                    continue

    agents[scope] = config
    payload = _serialize_agents_map(agents)

    if row:
        row.config_value = payload
        row.is_encrypted = False
        flag_modified(row, "config_value")
    else:
        db.add(
            UserConfig(
                id=str(uuid.uuid4()),
                config_key=CONFIG_KEY,
                config_value=payload,
                is_encrypted=False,
            )
        )
    await db.commit()
    return config
