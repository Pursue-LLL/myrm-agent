"""Unit tests for RSS wiki source sync."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.wiki.source_sync.rss import sync_rss_feeds_to_wiki


@pytest.mark.asyncio
async def test_sync_rss_skips_invalid_url() -> None:
    structure = MagicMock()
    result = await sync_rss_feeds_to_wiki(
        structure,
        feed_urls=["ftp://bad.example/feed"],
        max_items=5,
        auto_compile=False,
        compiler_enqueue=None,
    )
    assert result.failed == 1
    assert result.published == 0


@pytest.mark.asyncio
async def test_sync_rss_publishes_atom_entry() -> None:
    atom = """<?xml version="1.0"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <title>Hello</title>
        <id>entry-1</id>
        <summary>Body text</summary>
        <link href="https://example.com/a"/>
      </entry>
    </feed>
    """
    structure = MagicMock()
    publish = AsyncMock(return_value=MagicMock(written=True, skipped=False, conflict_skipped=False, security_blocked=False))
    with patch("app.services.wiki.source_sync.rss.httpx.AsyncClient") as client_cls:
        client = AsyncMock()
        response = MagicMock()
        response.text = atom
        response.raise_for_status = MagicMock()
        client.get = AsyncMock(return_value=response)
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client_cls.return_value = client
        with patch("app.services.wiki.source_sync.rss.publish_source_markdown", publish):
            result = await sync_rss_feeds_to_wiki(
                structure,
                feed_urls=["https://example.com/feed.xml"],
                max_items=5,
                auto_compile=False,
                compiler_enqueue=None,
            )
    assert result.published == 1
    publish.assert_awaited_once()
