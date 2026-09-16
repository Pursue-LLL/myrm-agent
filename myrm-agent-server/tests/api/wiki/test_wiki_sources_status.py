"""Tests for wiki sources API status flags and config update roundtrip."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.api.wiki.sources import (
    WikiSourceSyncConfigUpdate,
    _wiki_source_sync_status,
    update_wiki_source_sync_config,
)
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


@pytest.mark.asyncio
async def test_update_config_roundtrips_zotero_fields() -> None:
    """PUT /config 的 zotero_* 字段必须透传进持久化 config（防 update 模型漏字段回归）。

    API update 模型一旦漏字段，exclude_unset 合并会静默丢弃前端提交值，
    连接器将永远拿到空配置——此用例是该断链的防回归锚点。
    """
    saved = WikiSourceSyncConfig(
        zotero_enabled=True,
        zotero_api_key="key-123",
        zotero_user_id="user-456",
        zotero_base_url="https://api.zotero.org",
    )
    db = AsyncMock()
    body = WikiSourceSyncConfigUpdate(
        zotero_enabled=True,
        zotero_api_key="key-123",
        zotero_user_id="user-456",
        zotero_base_url="https://api.zotero.org",
    )

    with (
        patch(
            "app.api.wiki.sources.load_wiki_source_sync_config",
            new=AsyncMock(side_effect=[WikiSourceSyncConfig(), saved]),
        ),
        patch(
            "app.api.wiki.sources.save_wiki_source_sync_config",
            new=AsyncMock(return_value=saved),
        ) as save_mock,
        patch(
            "app.api.wiki.sources.load_wiki_source_sync_state",
            new=AsyncMock(return_value=WikiSourceSyncState()),
        ),
        patch(
            "app.api.wiki.sources.is_oauth_issuer_connected",
            new=AsyncMock(return_value=False),
        ),
        patch(
            "app.api.wiki.sources.is_feishu_wiki_sync_available",
            new=AsyncMock(return_value=False),
        ),
    ):
        response = await update_wiki_source_sync_config(body, db=db)

    merged = save_mock.await_args.args[1]
    assert merged.zotero_enabled is True
    assert merged.zotero_api_key == "key-123"
    assert merged.zotero_user_id == "user-456"
    assert merged.zotero_base_url == "https://api.zotero.org"
    assert response.config == saved


@pytest.mark.asyncio
async def test_update_config_partial_update_keeps_other_fields() -> None:
    """仅提交一个字段时，未提及字段保持原值（exclude_unset 语义锚点）。"""
    current = WikiSourceSyncConfig(zotero_enabled=True, zotero_api_key="k1")
    merged_capture: dict[str, object] = {}

    async def _capture_save(
        _db: AsyncMock, merged: WikiSourceSyncConfig, agent_id: str | None = None
    ) -> WikiSourceSyncConfig:
        merged_capture.update(merged.model_dump())
        return merged

    db = AsyncMock()
    with (
        patch(
            "app.api.wiki.sources.load_wiki_source_sync_config",
            new=AsyncMock(side_effect=[current, current]),
        ),
        patch(
            "app.api.wiki.sources.save_wiki_source_sync_config",
            new=_capture_save,
        ),
        patch(
            "app.api.wiki.sources.load_wiki_source_sync_state",
            new=AsyncMock(return_value=WikiSourceSyncState()),
        ),
        patch(
            "app.api.wiki.sources.is_oauth_issuer_connected",
            new=AsyncMock(return_value=False),
        ),
        patch(
            "app.api.wiki.sources.is_feishu_wiki_sync_available",
            new=AsyncMock(return_value=False),
        ),
    ):
        response = await update_wiki_source_sync_config(
            WikiSourceSyncConfigUpdate(gmail_label="Sent"), db=db
        )

    assert response.config.gmail_label == "Sent"
    assert merged_capture["zotero_enabled"] is True
    assert merged_capture["zotero_api_key"] == "k1"