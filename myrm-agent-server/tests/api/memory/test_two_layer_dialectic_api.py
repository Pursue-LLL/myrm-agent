# [POS]: tests/api/memory/test_two_layer_dialectic_api.py
# [INPUT]: app.api.memory.two_layer_dialectic_router, FastAPI app
# [OUTPUT]: Integration API tests for Two-Layer Context Injection & Multi-Pass Dialectic Reconciliation Suite (Item 112)

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.two_layer_dialectic_router import (
    router as two_layer_dialectic_router,
)
from app.services.memory.two_layer_dialectic_service import (
    TwoLayerDialecticService,
    get_two_layer_dialectic_service,
)


@pytest.fixture
def isolated_service() -> TwoLayerDialecticService:
    """Provides an isolated TwoLayerDialecticService instance."""
    return TwoLayerDialecticService()


@pytest.fixture
def test_app(isolated_service: TwoLayerDialecticService) -> FastAPI:
    """Creates a lightweight test FastAPI application with dependency overrides."""
    app = FastAPI()
    app.include_router(two_layer_dialectic_router, prefix="/api/memory")
    app.dependency_overrides[get_two_layer_dialectic_service] = lambda: isolated_service
    return app


@pytest.mark.asyncio
async def test_inspect_and_reconcile_api(test_app: FastAPI) -> None:
    """Validate inspecting memory contradictions and executing multi-pass dialectic reconciliation."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        statements = [
            "Storage layer uses PostgreSQL database cluster.",
            "Storage layer switched from PostgreSQL to SQLite embedded engine.",
        ]

        # 1. Inspect conflicts
        inspect_res = await client.post(
            "/api/memory/two-layer-dialectic/inspect",
            json={"statements": statements, "cutoff": 0.4},
        )
        assert inspect_res.status_code == 200
        conflicts = inspect_res.json()
        assert len(conflicts) >= 1
        assert "postgresql" in conflicts[0]["statement_a"].lower()
        assert "sqlite" in conflicts[0]["statement_b"].lower()

        # 2. Reconcile conflicts (depth=3)
        reconcile_res = await client.post(
            "/api/memory/two-layer-dialectic/reconcile",
            json={"statements": statements, "depth": 3},
        )
        assert reconcile_res.status_code == 200
        results = reconcile_res.json()
        assert len(results) >= 1
        top_res = results[0]
        assert "sqlite" in top_res["resolved_statement"].lower()
        assert len(top_res["passes_executed"]) == 3
        assert top_res["confidence"] >= 0.9


@pytest.mark.asyncio
async def test_assemble_and_cache_management_api(test_app: FastAPI) -> None:
    """Validate cadence-governed dual-layer assembly, KV cache preservation, and eviction."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        session_id = "test-dialectic-sess-001"
        statements = [
            "Vector index relies on pgvector extension.",
            "Vector index migrated from pgvector to Qdrant cluster.",
        ]

        # 1. First turn assembly (Turn 0: triggers Layer 1 base compilation & Layer 2 dialectic)
        assemble_res_0 = await client.post(
            "/api/memory/two-layer-dialectic/assemble",
            json={
                "session_id": session_id,
                "turn": 0,
                "session_summary": "Initial vector store configuration",
                "peer_cards": ["PeerPlanner (Architect)"],
                "candidate_memories": statements,
                "context_cadence": 5,
                "dialectic_cadence": 3,
            },
        )
        assert assemble_res_0.status_code == 200
        data_0 = assemble_res_0.json()
        assert data_0["is_cache_safe"] is True
        assert data_0["injected_position"] == "user_message_tail"
        assert "<base_context cache_hash=" in data_0["layer1_base_context"]
        assert "<dialectic_reconciliation>" in data_0["layer2_dialectic_block"]

        # 2. Verify cached Layer 1 payload retrieval
        cache_res = await client.get(f"/api/memory/two-layer-dialectic/cache/{session_id}")
        assert cache_res.status_code == 200
        cache_data = cache_res.json()
        assert cache_data["refreshed_at_turn"] == 0
        assert len(cache_data["cache_control_hash"]) == 16

        # 3. Turn 1 assembly (Turn 1: cadence suppresses Layer 2 dialectic block to save tokens)
        assemble_res_1 = await client.post(
            "/api/memory/two-layer-dialectic/assemble",
            json={
                "session_id": session_id,
                "turn": 1,
                "session_summary": "Initial vector store configuration",
                "peer_cards": ["PeerPlanner (Architect)"],
                "candidate_memories": statements,
                "context_cadence": 5,
                "dialectic_cadence": 3,
            },
        )
        assert assemble_res_1.status_code == 200
        data_1 = assemble_res_1.json()
        assert data_1["layer2_dialectic_block"] == ""

        # 4. Reset cadence and cache
        reset_res = await client.post(f"/api/memory/two-layer-dialectic/reset/{session_id}")
        assert reset_res.status_code == 200
        assert reset_res.json()["ok"] is True

        # 5. Subsequent cache lookup should return 404
        cache_after_reset = await client.get(f"/api/memory/two-layer-dialectic/cache/{session_id}")
        assert cache_after_reset.status_code == 404
