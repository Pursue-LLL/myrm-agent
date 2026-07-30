"""Persist wiki source sync settings in UserConfig.

[INPUT]
- app.database.models::UserConfig (POS: per-user config persistence)

[OUTPUT]
- load/save/exists helpers for wikiSourceSync UserConfig key

[POS]
Server SSOT for wiki source sync UserConfig read/write.
"""

from __future__ import annotations

import json
import logging
import uuid

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.database.models import UserConfig
from app.services.wiki.source_sync.schemas import WikiSourceSyncConfig

logger = logging.getLogger(__name__)

CONFIG_KEY = "wikiSourceSync"


async def wiki_source_sync_config_exists(db: AsyncSession) -> bool:
    row = (
        await db.execute(select(UserConfig).where(UserConfig.config_key == CONFIG_KEY))
    ).scalars().first()
    return row is not None


async def load_wiki_source_sync_config(db: AsyncSession) -> WikiSourceSyncConfig:
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
    try:
        return WikiSourceSyncConfig.model_validate(raw)
    except ValidationError as exc:
        logger.warning("Invalid wikiSourceSync schema: %s", exc)
        return WikiSourceSyncConfig()


async def save_wiki_source_sync_config(db: AsyncSession, config: WikiSourceSyncConfig) -> WikiSourceSyncConfig:
    payload = config.model_dump(mode="json")
    row = (
        await db.execute(select(UserConfig).where(UserConfig.config_key == CONFIG_KEY))
    ).scalars().first()
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
