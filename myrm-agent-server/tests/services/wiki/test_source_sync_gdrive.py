"""Tests for Google Drive wiki source sync (httpx mock)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.toolkits.wiki import WikiStructure
from myrm_agent_harness.toolkits.wiki.pipeline.raw_gate import RawPublishResult

from app.services.wiki.source_sync.gdrive import sync_gdrive_folder_to_wiki

_MIME_MD = "text/markdown"


@pytest.mark.asyncio
async def test_sync_gdrive_not_connected() -> None:
    structure = WikiStructure("/tmp/wiki-test-gdrive-disconnected")

    with patch(
        "app.services.wiki.source_sync.gdrive.is_oauth_issuer_connected",
        new=AsyncMock(return_value=False),
    ):
        result = await sync_gdrive_folder_to_wiki(
            structure,
            folder_id="root",
            max_items=5,
            auto_compile=False,
            compiler_enqueue=None,
        )

    assert result.published == 0
    assert result.errors == ["Google Workspace is not connected"]


@pytest.mark.asyncio
async def test_sync_gdrive_empty_folder() -> None:
    structure = WikiStructure("/tmp/wiki-test-gdrive-empty")
    credential = MagicMock(token="token-abc")

    async def fake_get(url: str, **kwargs: object) -> MagicMock:
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"files": []}
        return resp

    mock_client = MagicMock()
    mock_client.get = fake_get
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch(
            "app.services.wiki.source_sync.gdrive.is_oauth_issuer_connected",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "app.services.wiki.source_sync.gdrive.refresh_oauth_token",
            new=AsyncMock(return_value=credential),
        ),
        patch("app.services.wiki.source_sync.gdrive.httpx.AsyncClient", return_value=mock_client),
    ):
        result = await sync_gdrive_folder_to_wiki(
            structure,
            folder_id="root",
            max_items=5,
            auto_compile=False,
            compiler_enqueue=None,
        )

    assert result.published == 0
    assert result.failed == 0
    assert result.errors == []


@pytest.mark.asyncio
async def test_sync_gdrive_publishes_markdown_file() -> None:
    structure = WikiStructure("/tmp/wiki-test-gdrive-publish")
    credential = MagicMock(token="token-abc")
    file_id = "file-001"

    async def fake_get(url: str, **kwargs: object) -> MagicMock:
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        if url.endswith("/files") and kwargs.get("params", {}).get("q"):
            resp.json.return_value = {
                "files": [
                    {
                        "id": file_id,
                        "name": "notes.md",
                        "mimeType": _MIME_MD,
                        "modifiedTime": "2024-01-15T10:00:00.000Z",
                    }
                ]
            }
        elif url.endswith(f"/files/{file_id}"):
            resp.content = b"# Research notes\n\nDrive body"
        else:
            resp.json.return_value = {}
        return resp

    mock_client = MagicMock()
    mock_client.get = fake_get
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    publish_result = RawPublishResult(
        relative_path="gdrive/2024-01/notes-file-001.md",
        absolute_path=Path("/tmp/wiki-test-gdrive-publish/raw/gdrive/2024-01/notes-file-001.md"),
        content_hash="abc123",
        written=True,
        skipped=False,
        superseded=False,
        created=True,
        conflict_skipped=False,
        security_blocked=False,
    )

    with (
        patch(
            "app.services.wiki.source_sync.gdrive.is_oauth_issuer_connected",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "app.services.wiki.source_sync.gdrive.refresh_oauth_token",
            new=AsyncMock(return_value=credential),
        ),
        patch("app.services.wiki.source_sync.gdrive.httpx.AsyncClient", return_value=mock_client),
        patch(
            "app.services.wiki.source_sync.gdrive.publish_source_markdown",
            new=AsyncMock(return_value=publish_result),
        ),
    ):
        result = await sync_gdrive_folder_to_wiki(
            structure,
            folder_id="root",
            max_items=5,
            auto_compile=False,
            compiler_enqueue=None,
        )

    assert result.published == 1
    assert result.failed == 0
    assert result.errors == []
