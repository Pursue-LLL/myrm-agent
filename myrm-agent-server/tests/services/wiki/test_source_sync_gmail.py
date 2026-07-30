"""Unit tests for Gmail wiki source sync."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.wiki.source_sync.gmail import sync_gmail_label_to_wiki


@pytest.mark.asyncio
async def test_sync_gmail_fails_when_google_not_connected() -> None:
    structure = MagicMock()
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
    assert result.failed == 0
    assert result.errors == ["Google Workspace is not connected"]


@pytest.mark.asyncio
async def test_sync_gmail_fails_when_label_not_found() -> None:
    structure = MagicMock()
    credential = MagicMock()
    credential.token = "token-abc"

    labels_response = MagicMock()
    labels_response.raise_for_status = MagicMock()
    labels_response.json.return_value = {
        "labels": [{"id": "Label_1", "name": "Inbox"}, {"id": "Label_2", "name": "Newsletter"}],
    }

    client = AsyncMock()
    client.get = AsyncMock(return_value=labels_response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    with patch(
        "app.services.wiki.source_sync.gmail.is_oauth_issuer_connected",
        new=AsyncMock(return_value=True),
    ), patch(
        "app.services.wiki.source_sync.gmail.refresh_oauth_token",
        new=AsyncMock(return_value=credential),
    ), patch("app.services.wiki.source_sync.gmail.httpx.AsyncClient", return_value=client):
        result = await sync_gmail_label_to_wiki(
            structure,
            label="ReadLater",
            max_items=5,
            auto_compile=False,
            compiler_enqueue=None,
        )

    assert result.published == 0
    assert result.failed == 0
    assert result.errors == ["Gmail label not found: ReadLater"]


@pytest.mark.asyncio
async def test_sync_gmail_publishes_message_markdown() -> None:
    structure = MagicMock()
    credential = MagicMock()
    credential.token = "token-abc"

    labels_response = MagicMock()
    labels_response.raise_for_status = MagicMock()
    labels_response.json.return_value = {
        "labels": [{"id": "Label_99", "name": "ReadLater"}],
    }

    messages_response = MagicMock()
    messages_response.raise_for_status = MagicMock()
    messages_response.json.return_value = {"messages": [{"id": "msg-1"}]}

    full_message_response = MagicMock()
    full_message_response.raise_for_status = MagicMock()
    full_message_response.json.return_value = {
        "snippet": "Snippet fallback",
        "payload": {
            "headers": [
                {"name": "Subject", "value": "Weekly digest"},
                {"name": "Date", "value": "Mon, 28 Jul 2026 10:00:00 +0000"},
            ],
            "mimeType": "text/plain",
            "body": {"data": "V2Vla2x5IGRpZ2VzdCBib2R5"},
        },
    }

    client = AsyncMock()
    client.get = AsyncMock(side_effect=[labels_response, messages_response, full_message_response])
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    publish = AsyncMock(
        return_value=MagicMock(written=True, skipped=False, conflict_skipped=False, security_blocked=False)
    )

    with patch(
        "app.services.wiki.source_sync.gmail.is_oauth_issuer_connected",
        new=AsyncMock(return_value=True),
    ), patch(
        "app.services.wiki.source_sync.gmail.refresh_oauth_token",
        new=AsyncMock(return_value=credential),
    ), patch("app.services.wiki.source_sync.gmail.httpx.AsyncClient", return_value=client), patch(
        "app.services.wiki.source_sync.gmail.publish_source_markdown",
        publish,
    ):
        result = await sync_gmail_label_to_wiki(
            structure,
            label="readlater",
            max_items=5,
            auto_compile=False,
            compiler_enqueue=None,
        )

    assert result.published == 1
    assert result.failed == 0
    assert result.errors == []
    publish.assert_awaited_once()
    publish_kwargs = publish.await_args.kwargs
    assert publish_kwargs["relative_path"].startswith("gmail/")
    assert "Weekly digest" in publish_kwargs["content"]
