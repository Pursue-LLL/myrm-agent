"""Update contract for agent command_bindings via /api/agents.

The Settings editor persists slash-command bindings with a bindings-only update that never carries the rest of the
agent. These tests lock what that relies on: an omitted key leaves the bindings (and every other field) untouched,
a list replaces them, and an explicit null clears them.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

_BINDINGS = [
    {
        "command_name": "daily-report",
        "skill_ids": ["report_generator"],
        "description": "Daily summary",
        "aliases": ["dr"],
        "instruction": "",
    },
    {
        "command_name": "search-kb",
        "skill_ids": ["kb_search", "summarizer"],
        "description": "",
        "aliases": [],
        "instruction": "Search then summarize",
    },
]


@pytest.fixture
async def async_client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def _create_agent_with_bindings(client: AsyncClient) -> str:
    response = await client.post(
        "/api/agents",
        json={
            "name": "Bindings Contract Agent",
            "description": "Keeps its description",
            "system_prompt": "You are a reporter.",
            "model_selection": {"providerId": "openai", "model": "gpt-4o-mini"},
            "command_bindings": _BINDINGS,
        },
    )
    assert response.status_code == 200
    return response.json()["data"]["id"]


@pytest.mark.asyncio
async def test_update_without_command_bindings_key_keeps_them(async_client: AsyncClient) -> None:
    agent_id = await _create_agent_with_bindings(async_client)

    response = await async_client.put(f"/api/agents/{agent_id}", json={"name": "Renamed"})

    assert response.status_code == 200
    updated = response.json()["data"]
    assert updated["name"] == "Renamed"
    assert updated["command_bindings"] == _BINDINGS

    await async_client.delete(f"/api/agents/{agent_id}")


@pytest.mark.asyncio
async def test_bindings_only_update_replaces_bindings_and_keeps_other_fields(async_client: AsyncClient) -> None:
    agent_id = await _create_agent_with_bindings(async_client)
    replacement = [{"command_name": "weekly", "skill_ids": ["weekly_gen"], "aliases": ["w"]}]

    response = await async_client.put(f"/api/agents/{agent_id}", json={"command_bindings": replacement})

    assert response.status_code == 200
    updated = response.json()["data"]
    assert updated["command_bindings"] == [
        {
            "command_name": "weekly",
            "skill_ids": ["weekly_gen"],
            "description": "",
            "aliases": ["w"],
            "instruction": "",
        }
    ]
    assert updated["name"] == "Bindings Contract Agent"
    assert updated["description"] == "Keeps its description"

    await async_client.delete(f"/api/agents/{agent_id}")


@pytest.mark.asyncio
async def test_explicit_null_clears_command_bindings(async_client: AsyncClient) -> None:
    agent_id = await _create_agent_with_bindings(async_client)

    response = await async_client.put(f"/api/agents/{agent_id}", json={"command_bindings": None})

    assert response.status_code == 200
    assert response.json()["data"]["command_bindings"] is None
    detail = (await async_client.get(f"/api/agents/{agent_id}")).json()["data"]
    assert detail["command_bindings"] is None

    await async_client.delete(f"/api/agents/{agent_id}")
