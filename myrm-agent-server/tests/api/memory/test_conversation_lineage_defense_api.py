# [POS]: tests/api/memory/test_conversation_lineage_defense_api.py
# [INPUT]: FastAPI test app, AsyncClient, lineage defense router and schemas
# [OUTPUT]: Integration tests verifying search and stats endpoints for Item 97

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.conversation_lineage_defense_router import (
    router as conversation_lineage_defense_router,
)


@pytest.fixture
def app() -> FastAPI:
    test_app = FastAPI()
    test_app.include_router(conversation_lineage_defense_router, prefix="/api/memory")
    return test_app


@pytest.mark.asyncio
async def test_search_with_defense_endpoint(app: FastAPI) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "query": "authentication token validation",
            "limit": 5,
            "include_internal": False,
            "window_size": 3,
            "cron_weight_multiplier": 0.45,
        }
        res = await client.post("/api/memory/lineage-defense/search", json=payload)
        assert res.status_code == 200
        data = res.json()

        assert "hits" in data
        assert "audit_report" in data
        hits = data["hits"]
        assert len(hits) >= 2

        # Top 1 hit must be interactive
        assert hits[0]["source_kind"] == "interactive"
        assert hits[0]["detail_level"] == "expanded_window"
        assert len(hits[0]["window_messages"]) > 0

        # Subsequent hits must be compact card
        for subsequent_hit in hits[1:]:
            assert subsequent_hit["detail_level"] == "compact_card"
            assert len(subsequent_hit["window_messages"]) == 0

        # Audit report metrics
        audit = data["audit_report"]
        assert audit["hidden_internal_count"] == 1
        assert audit["demoted_cron_count"] == 1
        assert audit["interactive_top1_ratio"] == 1.0
        assert audit["token_saving_percent"] > 0


@pytest.mark.asyncio
async def test_stats_endpoint(app: FastAPI) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/memory/lineage-defense/stats")
        assert res.status_code == 200
        data = res.json()

        assert data["total_inspected_sessions"] > 0
        assert data["interactive_sessions_count"] > 0
        assert data["cron_sessions_count"] > 0
        assert data["recall_blindness_defense_active"] is True
