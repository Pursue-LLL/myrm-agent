"""Tests for wiki ingest SSE stream endpoint."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.dependencies import get_optional_llm_for_user
from app.api.memory.utils import get_optional_memory_manager
from tests.support.minimal_app import build_minimal_app


@pytest.mark.asyncio
async def test_wiki_ingest_stream_route_exists() -> None:
    app = build_minimal_app(preset="wiki")
    mock_archiver = MagicMock()

    async def _override_llm() -> MagicMock:
        return MagicMock()

    async def _override_manager() -> None:
        return None

    app.dependency_overrides[get_optional_llm_for_user] = _override_llm
    app.dependency_overrides[get_optional_memory_manager] = _override_manager

    with (
        patch(
            "app.api.wiki.ingest_stream.wiki_ingest_event_bus.stream_scope",
            new=_fake_stream_scope,
        ),
        patch(
            "app.services.wiki.vault.get_wiki_archiver",
            return_value=mock_archiver,
        ),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/wiki/ingest/stream")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")


async def _fake_stream_scope(*_args: object, **_kwargs: object):
    yield 'event: ingest_snapshot\ndata: {"stats":{"pending":0,"processing":0,"completed":0,"failed":0}}\n\n'
