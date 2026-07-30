"""Tests for Second Brain preset wiki gmail default on apply."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.wiki.source_sync.schemas import WikiSourceSyncConfig


@pytest.mark.asyncio
async def test_maybe_enable_wiki_gmail_source_when_google_connected() -> None:
    from app.services.onboarding.second_brain_preset import _maybe_enable_wiki_gmail_source

    config = WikiSourceSyncConfig(gmail_enabled=False)
    db = AsyncMock()

    with (
        patch("app.database.connection.get_session") as session_ctx,
        patch(
            "app.services.integrations.oauth_store.is_oauth_issuer_connected",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "app.services.wiki.source_sync.config_store.load_wiki_source_sync_config",
            new=AsyncMock(return_value=config),
        ),
        patch(
            "app.services.wiki.source_sync.config_store.save_wiki_source_sync_config",
            new=AsyncMock(),
        ) as save_config,
    ):
        session_ctx.return_value.__aenter__ = AsyncMock(return_value=db)
        session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
        await _maybe_enable_wiki_gmail_source()

    save_config.assert_awaited_once()
    saved = save_config.await_args.args[1]
    assert saved.gmail_enabled is True
    assert saved.gmail_label == "ReadLater"


@pytest.mark.asyncio
async def test_maybe_enable_wiki_gmail_source_skips_when_disabled_oauth() -> None:
    from app.services.onboarding.second_brain_preset import _maybe_enable_wiki_gmail_source

    db = AsyncMock()
    with (
        patch("app.database.connection.get_session") as session_ctx,
        patch(
            "app.services.integrations.oauth_store.is_oauth_issuer_connected",
            new=AsyncMock(return_value=False),
        ),
        patch(
            "app.services.wiki.source_sync.config_store.save_wiki_source_sync_config",
            new=AsyncMock(),
        ) as save_config,
    ):
        session_ctx.return_value.__aenter__ = AsyncMock(return_value=db)
        session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
        await _maybe_enable_wiki_gmail_source()

    save_config.assert_not_awaited()
