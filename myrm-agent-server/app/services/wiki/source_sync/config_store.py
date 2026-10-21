"""Persist wiki source sync settings in UserConfig.

[INPUT]
- app.services.wiki._userconfig_scoped (POS: shared UserConfig scoped persistence)
- app.services.wiki.source_sync.schemas::WikiSourceSyncConfig (POS: source sync config DTO)

[OUTPUT]
- load/save/exists helpers for per-agent wikiSourceSync UserConfig key

[POS]
Server SSOT for wiki source sync UserConfig read/write (nested by agent scope).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.wiki._userconfig_scoped import (
    exists_scoped_userconfig,
    load_scoped_userconfig,
    save_scoped_userconfig,
)
from app.services.wiki.source_sync.schemas import WikiSourceSyncConfig

CONFIG_KEY = "wikiSourceSync"
_LEGACY_KEYS = (
    "gmail_enabled",
    "gdrive_enabled",
    "gdrive_folder_id",
    "rss_feeds",
    "auto_compile",
    "mirror_integrations_to_wiki",
)


async def wiki_source_sync_config_exists(
    db: AsyncSession,
    *,
    agent_id: str | None = None,
) -> bool:
    """Return whether any wiki source sync config exists for the scope."""
    return await exists_scoped_userconfig(
        db,
        config_key=CONFIG_KEY,
        agent_id=agent_id,
        legacy_keys=_LEGACY_KEYS,
    )


async def load_wiki_source_sync_config(
    db: AsyncSession,
    *,
    agent_id: str | None = None,
) -> WikiSourceSyncConfig:
    """Load the scoped wiki source sync config from UserConfig."""
    return await load_scoped_userconfig(
        db,
        config_key=CONFIG_KEY,
        model=WikiSourceSyncConfig,
        agent_id=agent_id,
        legacy_keys=_LEGACY_KEYS,
        invalid_log_label="wikiSourceSync",
    )


async def save_wiki_source_sync_config(
    db: AsyncSession,
    config: WikiSourceSyncConfig,
    *,
    agent_id: str | None = None,
) -> WikiSourceSyncConfig:
    """Merge the config into the scoped UserConfig store."""
    return await save_scoped_userconfig(
        db,
        config_key=CONFIG_KEY,
        model=WikiSourceSyncConfig,
        value=config,
        agent_id=agent_id,
        legacy_keys=_LEGACY_KEYS,
    )
