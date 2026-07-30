"""Tests for wiki source sync config store."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.wiki.source_sync.config_store import CONFIG_KEY, load_wiki_source_sync_config
from app.services.wiki.source_sync.schemas import WikiSourceSyncConfig


@pytest.mark.asyncio
async def test_load_defaults_when_missing() -> None:
    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalars.return_value.first.return_value = None
    db.execute = AsyncMock(return_value=result_mock)

    loaded = await load_wiki_source_sync_config(db)
    assert loaded.gmail_enabled is False
    assert CONFIG_KEY == "wikiSourceSync"


@pytest.mark.asyncio
async def test_load_parses_scoped_config() -> None:
    row = MagicMock()
    row.config_value = {
        "agents": {
            "agent-a": WikiSourceSyncConfig(gmail_enabled=True, rss_feeds=["https://a.test/feed"]).model_dump(),
        }
    }
    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalars.return_value.first.return_value = row
    db.execute = AsyncMock(return_value=result_mock)

    loaded = await load_wiki_source_sync_config(db, agent_id="agent-a")
    assert loaded.gmail_enabled is True
    assert loaded.rss_feeds == ["https://a.test/feed"]
