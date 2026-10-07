"""[POS]: tests/api/memory/test_dreaming_pruning_api.py
[INPUT]: AsyncClient, isolated test FastAPI application, and dream_diary router.
[OUTPUT]: Pytest integration tests verifying autonomous dreaming consolidation and memory pruning API.
"""

from collections.abc import AsyncGenerator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.dream_diary import (
    router as dream_diary_router,
)


@pytest.fixture
def test_app() -> FastAPI:
    """Create isolated FastAPI app mounting dream_diary router."""
    api_app = FastAPI()
    api_app.include_router(dream_diary_router, prefix="/api/memory")
    return api_app


@pytest.fixture
async def client(test_app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client fixture bound to isolated test app."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_synthesize_and_prune_api_flow(client: AsyncClient) -> None:
    payload = {
        "fragments": [
            {
                "session_id": "sess_dream_01",
                "memories": [
                    {
                        "id": "mem_01_1",
                        "content": "项目中全面采用 Svelte 5 构建极致高性能前端",
                        "confidence": 0.85,
                        "evidence": [{"quote_snippet": "Always use Svelte 5"}],
                    }
                ],
                "topic_keywords": ["svelte", "frontend"],
                "chat_turn_count": 4,
            },
            {
                "session_id": "sess_dream_02",
                "memories": [
                    {
                        "id": "mem_02_1",
                        "content": "项目中全面采用 Svelte 5 构建极致高性能前端界面",
                        "confidence": 0.90,
                        "evidence": [{"quote_snippet": "Svelte 5 components"}],
                    }
                ],
                "topic_keywords": ["svelte", "frontend"],
                "chat_turn_count": 6,
            },
        ],
        "raw_memories": [
            {
                "id": "mem_old_react",
                "content": "项目中全面使用 React 18 作为核心视图层",
                "confidence": 0.75,
            }
        ],
        "target_project_id": "proj_open_perplexity",
    }

    resp = await client.post("/api/memory/dream-diary/synthesize-and-prune", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert "run_id" in data
    assert data["synthesized_count"] >= 1
    assert any("Svelte" in ins["cognitive_statement"] for ins in data["synthesized_insights"])

    # Verify contradiction pruning was executed
    assert data["pruned_count"] >= 1
    assert any(
        p["memory_id"] == "mem_old_react" and p["decision"] == "contradiction_superseded"
        for p in data["pruned_records"]
    )
