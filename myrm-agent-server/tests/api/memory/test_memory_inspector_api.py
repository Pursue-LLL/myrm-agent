"""Integration and unit tests for Memory Inspector & Epistemic Veracity API endpoints.

[INPUT]
- httpx, ASGITransport
- app.api.memory.memory_inspector_router::router

[OUTPUT]
- Pytest test cases verifying session memory inspection, promotion, in-place correction, and physical deletion.

[POS]
Test suite for Item 30 server layer. Strictly under 200 lines. Zero `Any`.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport

from app.api.memory.memory_inspector_router import router as memory_inspector_router

# Build minimal isolated test app
test_app = FastAPI()
test_app.include_router(memory_inspector_router, prefix="/api/v1/memory")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_get_session_memories_with_epistemic_grading(async_client: httpx.AsyncClient) -> None:
    """Session inspection should return cited memories with epistemic tiers and confidence scores."""
    resp = await async_client.get("/api/v1/memory/inspect/session/session_test_123")
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == "session_test_123"
    assert data["total_count"] >= 3
    memories = data["memories"]
    tiers = {m["epistemic_tier"] for m in memories}
    assert "assertion" in tiers
    assert "observation" in tiers
    assert "belief" in tiers

    # Check structure
    sample = memories[0]
    assert "id" in sample
    assert "content" in sample
    assert "confidence_score" in sample
    assert "similarity_score" in sample
    assert "provenance_chain" in sample


@pytest.mark.asyncio
async def test_promote_belief_to_assertion(async_client: httpx.AsyncClient) -> None:
    """Operator should be able to promote an inferred belief into a hard assertion."""
    promote_payload = {
        "target_tier": "assertion",
        "justification": "Confirmed by user in chat",
    }
    resp = await async_client.post("/api/v1/memory/inspect/mem_mock_3/promote", json=promote_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "mem_mock_3"
    assert data["epistemic_tier"] == "assertion"
    assert data["confidence_score"] == 1.0
    assert any("operator_promoted" in p for p in data["provenance_chain"])


@pytest.mark.asyncio
async def test_correct_memory_content_in_place(async_client: httpx.AsyncClient) -> None:
    """In-place correction should update memory text and append to provenance chain."""
    correct_payload = {
        "new_content": "User explicitly stated dark theme with 14px font size.",
        "reason": "Clarified font size specification",
    }
    resp = await async_client.post("/api/v1/memory/inspect/mem_mock_1/correct", json=correct_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "mem_mock_1"
    assert data["content"] == "User explicitly stated dark theme with 14px font size."
    assert any("operator_corrected" in p for p in data["provenance_chain"])


@pytest.mark.asyncio
async def test_forget_memory_item_lifecycle(async_client: httpx.AsyncClient) -> None:
    """Physical forgetting should delete the record and reject future access."""
    resp = await async_client.delete("/api/v1/memory/inspect/mem_mock_2/forget")
    assert resp.status_code == 204

    # Second delete should return 404
    resp_again = await async_client.delete("/api/v1/memory/inspect/mem_mock_2/forget")
    assert resp_again.status_code == 404
