"""Tests for Second Brain preset wiki gmail default on apply."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_second_brain_preset_delegates_to_wiki_gmail_defaults() -> None:
    from app.services.onboarding.second_brain_preset import _maybe_enable_wiki_gmail_source

    with patch(
        "app.services.wiki.source_sync.defaults.maybe_enable_wiki_gmail_on_google_connect",
        new=AsyncMock(return_value=True),
    ) as enable:
        await _maybe_enable_wiki_gmail_source()

    enable.assert_awaited_once()
