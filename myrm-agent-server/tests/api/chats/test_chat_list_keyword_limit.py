"""The sidebar keyword is bounded like the other chat search inputs: a longer one is rejected, not scanned."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from httpx import ASGITransport

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="chats")


@pytest.fixture
async def async_client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver", timeout=60.0) as client:
        yield client


@pytest.mark.parametrize(("length", "status"), [(200, 200), (201, 422)])
@pytest.mark.asyncio
async def test_the_sidebar_keyword_is_capped_at_200_characters(async_client: httpx.AsyncClient, length: int, status: int) -> None:
    response = await async_client.get("/api/v1/chats/", params={"keyword": "x" * length})

    assert response.status_code == status
