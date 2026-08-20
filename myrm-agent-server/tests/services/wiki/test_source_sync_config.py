"""Tests for wiki source sync config store."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.wiki.source_sync.config_store import (
    CONFIG_KEY,
    load_wiki_source_sync_config,
    save_wiki_source_sync_config,
    wiki_source_sync_config_exists,
)
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


@pytest.mark.asyncio
async def test_load_maps_legacy_bare_payload_to_default_scope() -> None:
    row = MagicMock()
    row.config_value = {
        "gmail_enabled": True,
        "rss_feeds": ["https://legacy.test/feed"],
    }
    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalars.return_value.first.return_value = row
    db.execute = AsyncMock(return_value=result_mock)

    loaded = await load_wiki_source_sync_config(db, agent_id=None)
    assert loaded.gmail_enabled is True
    assert loaded.rss_feeds == ["https://legacy.test/feed"]


@pytest.mark.asyncio
async def test_exists_false_when_row_missing() -> None:
    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalars.return_value.first.return_value = None
    db.execute = AsyncMock(return_value=result_mock)

    assert await wiki_source_sync_config_exists(db) is False


@pytest.mark.asyncio
async def test_exists_false_on_corrupt_json() -> None:
    row = MagicMock()
    row.config_value = "{not-valid-json"
    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalars.return_value.first.return_value = row
    db.execute = AsyncMock(return_value=result_mock)

    assert await wiki_source_sync_config_exists(db) is False


@pytest.mark.asyncio
async def test_exists_false_on_non_dict_payload() -> None:
    row = MagicMock()
    row.config_value = ["not", "a", "dict"]
    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalars.return_value.first.return_value = row
    db.execute = AsyncMock(return_value=result_mock)

    assert await wiki_source_sync_config_exists(db) is False


@pytest.mark.asyncio
async def test_exists_true_for_any_scoped_config() -> None:
    row = MagicMock()
    row.config_value = {"agents": {"agent-a": {"gmail_enabled": True}}}
    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalars.return_value.first.return_value = row
    db.execute = AsyncMock(return_value=result_mock)

    assert await wiki_source_sync_config_exists(db) is True
    assert await wiki_source_sync_config_exists(db, agent_id="agent-a") is True
    assert await wiki_source_sync_config_exists(db, agent_id="agent-b") is False


@pytest.mark.asyncio
async def test_save_merges_preserving_other_scopes() -> None:
    existing = {"agents": {"agent-a": {"gmail_enabled": True}}}
    row = MagicMock()
    row.config_value = existing
    row.is_encrypted = False
    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalars.return_value.first.return_value = row
    db.execute = AsyncMock(return_value=result_mock)

    await save_wiki_source_sync_config(
        db,
        WikiSourceSyncConfig(gdrive_enabled=True),
        agent_id="agent-b",
    )

    written = row.config_value
    assert written["agents"]["agent-a"]["gmail_enabled"] is True
    assert written["agents"]["agent-b"]["gdrive_enabled"] is True
