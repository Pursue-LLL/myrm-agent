"""Communication style catalog API tests.

`GET /agents/personalities` must serve the SSOT catalog (one entry per preset, bilingual
copy, GUI icon id) and must never leak prompt-internal fields.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.ai_agents.personality_templates import PERSONALITY_TEMPLATES
from app.api.agents.personalities import router


@pytest.fixture()
def app() -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/agents")
    return app


@pytest.fixture()
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _catalog(client: AsyncClient) -> list[dict[str, object]]:
    response = await client.get("/agents/personalities")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    entries = payload["data"]
    assert isinstance(entries, list)
    return entries


async def test_catalog_lists_every_preset_in_ssot_order(client: AsyncClient) -> None:
    entries = await _catalog(client)
    assert [entry["id"] for entry in entries] == list(PERSONALITY_TEMPLATES.keys())


async def test_catalog_entries_match_templates(client: AsyncClient) -> None:
    entries = await _catalog(client)
    for entry in entries:
        style = str(entry["id"])
        template = PERSONALITY_TEMPLATES[style]  # type: ignore[index]
        assert entry["displayName"] == template.display_name
        assert entry["displayNameZh"] == template.display_name_zh
        assert entry["description"] == template.description
        assert entry["descriptionZh"] == template.description_zh
        assert entry["exampleResponse"] == template.example_response
        assert entry["exampleResponseZh"] == template.example_response_zh
        assert entry["iconId"] == template.icon_id
        assert entry["category"] == template.category


async def test_catalog_never_exposes_prompt_internals(client: AsyncClient) -> None:
    entries = await _catalog(client)
    for entry in entries:
        assert "systemPromptSuffix" not in entry
        assert "system_prompt_suffix" not in entry
        # GUI 禁止原生 emoji；服务端 emoji 仅供 IM 文本列表使用，不进目录响应。
        assert "emoji" not in entry


async def test_catalog_preview_copy_is_bilingual(client: AsyncClient) -> None:
    entries = await _catalog(client)
    for entry in entries:
        assert str(entry["descriptionZh"]).strip()
        assert str(entry["exampleResponseZh"]).strip()
        assert str(entry["exampleResponse"]).strip()
