"""Integration and unit tests for Command Matrix & Context-Aware Suggestion API.

[INPUT]
- httpx, ASGITransport
- app.api.chats.chat.command_matrix::router

[OUTPUT]
- Pytest test cases verifying catalog retrieval, category/fuzzy search filtering, and contextual chip suggestions.

[POS]
Server-side integration test suite for Item 38 P0. Strictly under 160 lines. Zero `Any`.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport

from app.api.chats.chat.command_matrix import router as command_matrix_router

test_app = FastAPI()
test_app.include_router(command_matrix_router, prefix="/api/v1/chats")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_get_command_matrix_catalog_all(async_client: httpx.AsyncClient) -> None:
    resp = await async_client.get("/api/v1/chats/commands/matrix")
    assert resp.status_code == 200
    data = resp.json()["data"]
    items = data["items"]
    assert len(items) >= 15
    commands = [it["command"] for it in items]
    assert "/btw" in commands
    assert "/bg" in commands
    assert "/pykernel" in commands
    assert "/sop" in commands
    assert "/scratchpad" in commands


@pytest.mark.asyncio
async def test_get_command_matrix_catalog_filtered(async_client: httpx.AsyncClient) -> None:
    # 1. Filter by category
    resp_cat = await async_client.get(
        "/api/v1/chats/commands/matrix",
        params={"category": "data_science"},
    )
    assert resp_cat.status_code == 200
    items_cat = resp_cat.json()["data"]["items"]
    assert len(items_cat) >= 2
    for it in items_cat:
        assert it["category"] == "data_science"

    # 2. Filter by fuzzy query
    resp_query = await async_client.get(
        "/api/v1/chats/commands/matrix",
        params={"q": "barge-in"},
    )
    assert resp_query.status_code == 200
    items_query = resp_query.json()["data"]["items"]
    assert len(items_query) >= 1
    assert any(it["command"] == "/btw" for it in items_query)


@pytest.mark.asyncio
async def test_suggest_context_commands_running(async_client: httpx.AsyncClient) -> None:
    chat_id = f"test_chat_{uuid.uuid4().hex[:8]}"
    body = {
        "status": "running",
        "running_step_count": 3,
        "recent_tools": ["web_search"],
        "mastered_commands": [],
        "max_results": 3,
    }

    resp = await async_client.post(f"/api/v1/chats/{chat_id}/commands/suggest", json=body)
    assert resp.status_code == 200
    data = resp.json()["data"]
    chips = data["chips"]
    assert len(chips) >= 2
    commands = [c["command"] for c in chips]
    assert "/btw" in commands
    assert "/bg" in commands


@pytest.mark.asyncio
async def test_suggest_context_commands_with_mastery_filter(async_client: httpx.AsyncClient) -> None:
    chat_id = f"test_chat_{uuid.uuid4().hex[:8]}"
    body = {
        "status": "running",
        "running_step_count": 3,
        "recent_tools": ["bash"],
        "mastered_commands": ["/btw", "/bg"],  # User already mastered
        "max_results": 3,
    }

    resp = await async_client.post(f"/api/v1/chats/{chat_id}/commands/suggest", json=body)
    assert resp.status_code == 200
    chips = resp.json()["data"]["chips"]
    commands = [c["command"] for c in chips]
    assert "/btw" not in commands
    assert "/bg" not in commands
    # Should still recommend /pykernel and /steer
    assert "/pykernel" in commands or "/steer" in commands
