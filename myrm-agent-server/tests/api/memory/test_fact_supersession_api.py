# [POS]: tests/api/memory/test_fact_supersession_api.py
# [INPUT]: app.api.memory.fact_supersession_router, isolated FastAPI app
# [OUTPUT]: Integration API tests for FactSupersessionTemporalValidityAndContradictionLedgerSuite (Item 102)

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.fact_supersession_router import router as fact_supersession_router
from app.services.memory.fact_supersession_service import (
    FactSupersessionService,
    get_fact_supersession_service,
)


@pytest.fixture
def isolated_service() -> FactSupersessionService:
    """Provides an isolated in-memory FactSupersessionService instance."""
    return FactSupersessionService()


@pytest.fixture
def test_app(isolated_service: FactSupersessionService) -> FastAPI:
    """Creates a lightweight test FastAPI application with dependency overrides."""
    app = FastAPI()
    app.include_router(fact_supersession_router, prefix="/api/memory")
    app.dependency_overrides[get_fact_supersession_service] = lambda: isolated_service
    return app


@pytest.mark.asyncio
async def test_fact_registration_and_dialectic_recall_api(test_app: FastAPI) -> None:
    """Validate fact ingestion, automatic supersession, and dialectic explainable recall."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Register fact 1 (Python)
        req1 = {
            "subject": "User",
            "predicate": "primary_language",
            "object_value": "Python",
            "valid_from": "2026-01-01T00:00:00Z",
            "confidence": 1.0,
            "evidence_quote": "Primary code language is Python.",
        }
        res1 = await client.post("/api/memory/supersession/facts", json=req1)
        assert res1.status_code == 200
        data1 = res1.json()
        assert data1["action_taken"] == "RECORDED"
        fact1_id = data1["fact"]["fact_id"]

        # 2. Register fact 2 (Rust) with high confidence (1.0 >= 0.85 threshold)
        req2 = {
            "subject": "User",
            "predicate": "primary_language",
            "object_value": "Rust",
            "valid_from": "2026-09-01T00:00:00Z",
            "confidence": 1.0,
            "evidence_quote": "Switched primary language to Rust in September.",
        }
        res2 = await client.post("/api/memory/supersession/facts", json=req2)
        assert res2.status_code == 200
        data2 = res2.json()
        assert data2["action_taken"] == "SUPERSEDED"
        fact2_id = data2["fact"]["fact_id"]

        # 3. Recall current active facts: should be Rust
        recall_req = {
            "subject": "User",
            "predicate": "primary_language",
        }
        res_recall = await client.post("/api/memory/supersession/recall", json=recall_req)
        assert res_recall.status_code == 200
        recall_data = res_recall.json()
        assert recall_data["total_matched"] == 1
        assert recall_data["active_facts"][0]["object_value"] == "Rust"

        # Verify dialectic lineage contains fact 1
        lineage = recall_data["superseded_lineage"].get(fact2_id, [])
        assert len(lineage) == 1
        assert lineage[0]["fact_id"] == fact1_id
        assert lineage[0]["object_value"] == "Python"

        # 4. Time-travel recall: as of 2026-06-01 -> should return Python
        past_recall_req = {
            "subject": "User",
            "predicate": "primary_language",
            "as_of_time": "2026-06-01T00:00:00Z",
        }
        res_past = await client.post("/api/memory/supersession/recall", json=past_recall_req)
        assert res_past.status_code == 200
        past_data = res_past.json()
        assert past_data["total_matched"] == 1
        assert past_data["active_facts"][0]["object_value"] == "Python"

        # 5. Get history endpoint
        hist_res = await client.get(f"/api/memory/supersession/facts/{fact2_id}/history")
        assert hist_res.status_code == 200
        hist_data = hist_res.json()
        assert hist_data["fact_id"] == fact2_id
        assert len(hist_data["ancestor_facts"]) == 1
        assert hist_data["ancestor_facts"][0]["fact_id"] == fact1_id


@pytest.mark.asyncio
async def test_fact_contradiction_quarantine_and_human_resolve_api(test_app: FastAPI) -> None:
    """Validate low-confidence contradiction quarantine isolation and human resolution."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Base fact
        base_req = {
            "subject": "Org",
            "predicate": "license",
            "object_value": "MIT",
            "valid_from": "2026-01-01T00:00:00Z",
            "confidence": 1.0,
        }
        res_base = await client.post("/api/memory/supersession/facts", json=base_req)
        assert res_base.status_code == 200
        assert res_base.json()["action_taken"] == "RECORDED"

        # 2. Ingest low-confidence contradiction (0.6 < 0.85)
        contra_req = {
            "subject": "Org",
            "predicate": "license",
            "object_value": "Apache-2.0",
            "valid_from": "2026-10-01T00:00:00Z",
            "confidence": 0.6,
        }
        res_contra = await client.post("/api/memory/supersession/facts", json=contra_req)
        assert res_contra.status_code == 200
        contra_data = res_contra.json()
        assert contra_data["action_taken"] == "QUARANTINED"
        q_id = contra_data["quarantine_id"]
        assert q_id is not None

        # 3. List quarantine entries
        q_list_res = await client.get("/api/memory/supersession/quarantine?status=quarantined")
        assert q_list_res.status_code == 200
        q_items = q_list_res.json()
        assert len(q_items) == 1
        assert q_items[0]["quarantine_id"] == q_id

        # 4. Human resolve: Approve override
        resolve_req = {"approve_override": True}
        res_res = await client.post(f"/api/memory/supersession/quarantine/{q_id}/resolve", json=resolve_req)
        assert res_res.status_code == 200
        assert res_res.json()["action_taken"] == "SUPERSEDED"

        # 5. Verify active fact now is Apache-2.0
        recall_res = await client.post(
            "/api/memory/supersession/recall",
            json={"subject": "Org", "predicate": "license"},
        )
        assert recall_res.status_code == 200
        active_list = recall_res.json()["active_facts"]
        assert len(active_list) == 1
        assert active_list[0]["object_value"] == "Apache-2.0"
