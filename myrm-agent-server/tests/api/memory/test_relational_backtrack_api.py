# [POS]: tests/api/memory/test_relational_backtrack_api.py
# [INPUT]: app.api.memory.relational_backtrack_router, isolated FastAPI app
# [OUTPUT]: Integration API tests for TemporalRelationalAnchorAndCrossSessionEntityBacktrackingSuite (Item 100)

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.relational_backtrack_router import router as relational_backtrack_router
from app.services.memory.relational_backtrack_service import (
    RelationalBacktrackService,
    get_relational_backtrack_service,
)


@pytest.fixture
def isolated_service() -> RelationalBacktrackService:
    """Provides an isolated in-memory RelationalBacktrackService instance."""
    return RelationalBacktrackService()


@pytest.fixture
def test_app(isolated_service: RelationalBacktrackService) -> FastAPI:
    """Creates a lightweight test FastAPI application with dependency overrides."""
    app = FastAPI()
    app.include_router(relational_backtrack_router, prefix="/api/memory")
    app.dependency_overrides[get_relational_backtrack_service] = lambda: isolated_service
    return app


@pytest.mark.asyncio
async def test_record_triplet_and_cross_session_backtrack_api(test_app: FastAPI) -> None:
    """Validate registering triplets and querying cross-session backtracking for dialect cues."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Record triplet 1: Eat hotpot with client Li
        t1_payload = {
            "subject": "user",
            "predicate_action": "eat_hotpot",
            "target_entity": "李总",
            "target_entity_type": "client",
            "temporal_anchor": "2026-10-02",
            "session_id": "sess-past-hotpot",
            "message_id": "msg-001",
            "verbatim_quote": "下周四带客户李总去吃火锅，预订了川味观。",
            "action_synonyms": ["吃火锅", "打边炉", "涮火锅"],
            "confidence": 1.0,
        }
        res1 = await client.post("/api/memory/backtrack/record", json=t1_payload)
        assert res1.status_code == 200
        data1 = res1.json()
        assert data1["is_success"] is True
        assert data1["triplet"]["target_entity"] == "李总"
        assert data1["triplet"]["target_entity_type"] == "client"

        # 2. Record triplet 2: Meeting with engineer Wang
        t2_payload = {
            "subject": "user",
            "predicate_action": "online_meeting",
            "target_entity": "王工",
            "target_entity_type": "person",
            "temporal_anchor": "2026-10-05",
            "session_id": "sess-past-meeting",
            "message_id": "msg-002",
            "verbatim_quote": "下午和技术顾问王工开了线上技术评审会。",
            "action_synonyms": ["开会", "语音沟通"],
            "confidence": 1.0,
        }
        res2 = await client.post("/api/memory/backtrack/record", json=t2_payload)
        assert res2.status_code == 200

        # 3. List all triplets
        list_res = await client.get("/api/memory/backtrack/list")
        assert list_res.status_code == 200
        all_triplets = list_res.json()
        assert len(all_triplets) == 2

        # 4. Query backtracking with dialect cue: "打边炉"
        query_payload = {
            "action_cue": "打边炉",
            "target_entity_type": "client",
            "min_confidence": 0.5,
        }
        query_res = await client.post("/api/memory/backtrack/query", json=query_payload)
        assert query_res.status_code == 200
        query_data = query_res.json()

        assert query_data["total_found"] == 1
        assert len(query_data["hits"]) == 1

        top_hit = query_data["hits"][0]
        assert top_hit["triplet"]["target_entity"] == "李总"
        assert top_hit["triplet"]["temporal_anchor"] == "2026-10-02"
        assert "川味观" in top_hit["triplet"]["verbatim_quote"]
        assert top_hit["match_score"] >= 0.9

        # Inferred synthesized answer verification
        assert query_data["inferred_answer"] is not None
        assert "李总" in query_data["inferred_answer"]
        assert "2026-10-02" in query_data["inferred_answer"]


@pytest.mark.asyncio
async def test_backtrack_unmatched_cue_returns_empty(test_app: FastAPI) -> None:
    """Validate query with unknown action cue returns 0 hits safely."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        query_payload = {
            "action_cue": "太空漫步",
            "min_confidence": 0.5,
        }
        query_res = await client.post("/api/memory/backtrack/query", json=query_payload)
        assert query_res.status_code == 200
        query_data = query_res.json()
        assert query_data["total_found"] == 0
        assert len(query_data["hits"]) == 0
        assert query_data["inferred_answer"] is None
