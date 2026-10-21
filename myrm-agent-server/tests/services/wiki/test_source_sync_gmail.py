"""Tests for Gmail wiki source sync (httpx mock)."""

from __future__ import annotations

import base64
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.toolkits.wiki import WikiStructure
from myrm_agent_harness.toolkits.wiki.pipeline.raw_gate import RawPublishResult

from app.services.wiki.source_sync.gmail import sync_gmail_label_to_wiki


def _plain_message_payload(*, subject: str, body: str) -> dict[str, object]:
    encoded = base64.urlsafe_b64encode(body.encode()).decode()
    return {
        "payload": {
            "headers": [{"name": "Subject", "value": subject}, {"name": "Date", "value": "Mon, 1 Jan 2024 00:00:00 +0000"}],
            "mimeType": "text/plain",
            "body": {"data": encoded},
        },
        "snippet": body,
    }


@pytest.mark.asyncio
async def test_sync_gmail_not_connected() -> None:
    structure = WikiStructure("/tmp/wiki-test-gmail-disconnected")

    with patch(
        "app.services.wiki.source_sync.gmail.is_oauth_issuer_connected",
        new=AsyncMock(return_value=False),
    ):
        result = await sync_gmail_label_to_wiki(
            structure,
            label="ReadLater",
            max_items=5,
            auto_compile=False,
            compiler_enqueue=None,
        )

    assert result.published == 0
    assert result.errors == ["Google Workspace is not connected"]


@pytest.mark.asyncio
async def test_sync_gmail_label_not_found() -> None:
    structure = WikiStructure("/tmp/wiki-test-gmail-no-label")
    credential = MagicMock(token="token-abc")

    async def fake_get(url: str, **kwargs: object) -> MagicMock:
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        if url.endswith("/labels"):
            resp.json.return_value = {"labels": [{"id": "L1", "name": "Other"}]}
        else:
            resp.json.return_value = {}
        return resp

    mock_client = MagicMock()
    mock_client.get = fake_get
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch(
            "app.services.wiki.source_sync.gmail.is_oauth_issuer_connected",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "app.services.wiki.source_sync.gmail.refresh_oauth_token",
            new=AsyncMock(return_value=credential),
        ),
        patch("app.services.wiki.source_sync.gmail.httpx.AsyncClient", return_value=mock_client),
    ):
        result = await sync_gmail_label_to_wiki(
            structure,
            label="ReadLater",
            max_items=5,
            auto_compile=False,
            compiler_enqueue=None,
        )

    assert result.published == 0
    assert result.errors == ["Gmail label not found: ReadLater"]


@pytest.mark.asyncio
async def test_sync_gmail_publishes_message() -> None:
    structure = WikiStructure("/tmp/wiki-test-gmail-publish")
    credential = MagicMock(token="token-abc")
    message_id = "msg-001"

    async def fake_get(url: str, **kwargs: object) -> MagicMock:
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        if url.endswith("/labels"):
            resp.json.return_value = {"labels": [{"id": "LBL", "name": "ReadLater"}]}
        elif url.endswith("/messages"):
            resp.json.return_value = {"messages": [{"id": message_id}]}
        elif f"/messages/{message_id}" in url:
            resp.json.return_value = _plain_message_payload(subject="Weekly digest", body="Hello wiki")
        else:
            resp.json.return_value = {}
        return resp

    mock_client = MagicMock()
    mock_client.get = fake_get
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    publish_result = RawPublishResult(
        relative_path="gmail/2024-01/msg-001.md",
        absolute_path=Path("/tmp/wiki-test-gmail-publish/raw/gmail/2024-01/msg-001.md"),
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
            "app.services.wiki.source_sync.gmail.is_oauth_issuer_connected",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "app.services.wiki.source_sync.gmail.refresh_oauth_token",
            new=AsyncMock(return_value=credential),
        ),
        patch("app.services.wiki.source_sync.gmail.httpx.AsyncClient", return_value=mock_client),
        patch(
            "app.services.wiki.source_sync.gmail.publish_source_markdown",
            new=AsyncMock(return_value=publish_result),
        ),
    ):
        result = await sync_gmail_label_to_wiki(
            structure,
            label="ReadLater",
            max_items=5,
            auto_compile=False,
            compiler_enqueue=None,
        )

    assert result.published == 1
    assert result.failed == 0
    assert result.errors == []
