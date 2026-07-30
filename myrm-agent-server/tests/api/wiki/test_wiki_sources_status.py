"""Tests for wiki sources API Google Drive authorization flags."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.api.wiki.sources import _wiki_source_sync_status
from app.services.wiki.source_sync.schemas import WikiSourceSyncConfig, WikiSourceSyncState


@pytest.mark.asyncio
async def test_status_drive_unauthorized_when_scope_missing() -> None:
    db = AsyncMock()
    config = WikiSourceSyncConfig(gdrive_enabled=True)
    state = WikiSourceSyncState()

    with (
        patch(
            "app.api.wiki.sources.is_oauth_issuer_connected",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "app.api.wiki.sources.google_workspace_drive_read_enabled",
            new=AsyncMock(return_value=False),
        ),
    ):
        response = await _wiki_source_sync_status(db, config=config, state=state)

    assert response.google_connected is True
    assert response.google_drive_authorized is False


@pytest.mark.asyncio
async def test_status_drive_authorized_when_scope_present() -> None:
    db = AsyncMock()
    config = WikiSourceSyncConfig(gdrive_enabled=True)
    state = WikiSourceSyncState()

    with (
        patch(
            "app.api.wiki.sources.is_oauth_issuer_connected",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "app.api.wiki.sources.google_workspace_drive_read_enabled",
            new=AsyncMock(return_value=True),
        ),
    ):
        response = await _wiki_source_sync_status(db, config=config, state=state)

    assert response.google_connected is True
    assert response.google_drive_authorized is True
