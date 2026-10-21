"""Tests for wiki source sync Gmail defaults after Google OAuth."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.wiki.source_sync.defaults import maybe_enable_wiki_gmail_on_google_connect
from app.services.wiki.source_sync.schemas import WikiSourceSyncConfig


@pytest.mark.asyncio
async def test_maybe_enable_gmail_when_google_connected() -> None:
    config = WikiSourceSyncConfig(gmail_enabled=False)
    db = AsyncMock()

    with (
        patch("app.services.wiki.source_sync.defaults.get_session") as session_ctx,
        patch(
            "app.services.wiki.source_sync.defaults.is_oauth_issuer_connected",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "app.services.wiki.source_sync.defaults.wiki_source_sync_config_exists",
            new=AsyncMock(return_value=False),
        ),
        patch(
            "app.services.wiki.source_sync.defaults.load_wiki_source_sync_config",
            new=AsyncMock(return_value=config),
        ),
        patch(
            "app.services.wiki.source_sync.defaults.save_wiki_source_sync_config",
            new=AsyncMock(),
        ) as save_config,
    ):
        session_ctx.return_value.__aenter__ = AsyncMock(return_value=db)
        session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
        enabled = await maybe_enable_wiki_gmail_on_google_connect(respect_existing_config=False)

    assert enabled is True
    save_config.assert_awaited_once()
    saved = save_config.await_args.args[1]
    assert saved.gmail_enabled is True
    assert saved.gmail_label == "ReadLater"


@pytest.mark.asyncio
async def test_maybe_enable_skips_when_respecting_existing_config() -> None:
    db = AsyncMock()
    with (
        patch("app.services.wiki.source_sync.defaults.get_session") as session_ctx,
        patch(
            "app.services.wiki.source_sync.defaults.is_oauth_issuer_connected",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "app.services.wiki.source_sync.defaults.wiki_source_sync_config_exists",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "app.services.wiki.source_sync.defaults.save_wiki_source_sync_config",
            new=AsyncMock(),
        ) as save_config,
    ):
        session_ctx.return_value.__aenter__ = AsyncMock(return_value=db)
        session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
        enabled = await maybe_enable_wiki_gmail_on_google_connect(respect_existing_config=True)

    assert enabled is False
    save_config.assert_not_awaited()
