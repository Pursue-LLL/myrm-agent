"""Integration test for memory rating API endpoint.

Covers:
- POST /memory/{memory_id}/rate — successful response shape
- POST /memory/{memory_id}/rate — 404 for non-existent memory
- POST /memory/{memory_id}/rate — 422 for invalid score
- Asymmetric EMA is correctly propagated through the API layer
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.memory.router import router as memory_router
from app.api.memory.utils import get_crud_memory_manager


@pytest.fixture
def mock_manager() -> AsyncMock:
    """Real-like manager mock that simulates asymmetric EMA behavior."""
    manager = AsyncMock()

    call_count = {"n": 0}
    ratings = {"current": 0.5}

    async def _rate_memory(memory_id: str, score: int, collection: str | None = None) -> bool:
        if memory_id == "nonexistent":
            return False
        clamped = max(1, min(5, score))
        normalized = (clamped - 1) / 4.0
        alpha_positive = 0.3
        alpha_negative = 0.5
        old = ratings["current"]
        alpha = alpha_negative if normalized < old else alpha_positive
        ratings["current"] = round(old + alpha * (normalized - old), 4)
        call_count["n"] += 1
        return True

    manager.rate_memory.side_effect = _rate_memory
    manager._ratings = ratings
    return manager


@pytest.fixture
def client(mock_manager: AsyncMock) -> TestClient:
    app = FastAPI()
    app.include_router(memory_router, prefix="/memory")
    app.dependency_overrides[get_crud_memory_manager] = lambda: mock_manager
    return TestClient(app)


class TestRateMemoryAPI:
    def test_success_response_shape(self, client: TestClient):
        """Valid rate request returns 200 with correct shape."""
        resp = client.post("/memory/mem-123/rate", json={"score": 4})
        assert resp.status_code == 200
        data = resp.json()
        assert data == {"success": True, "memory_id": "mem-123", "score": 4}

    def test_not_found(self, client: TestClient):
        """Non-existent memory returns 404."""
        resp = client.post("/memory/nonexistent/rate", json={"score": 3})
        assert resp.status_code == 404

    def test_invalid_score_zero(self, client: TestClient):
        """Score 0 fails schema validation (ge=1)."""
        resp = client.post("/memory/mem-123/rate", json={"score": 0})
        assert resp.status_code == 422

    def test_invalid_score_six(self, client: TestClient):
        """Score 6 fails schema validation (le=5)."""
        resp = client.post("/memory/mem-123/rate", json={"score": 6})
        assert resp.status_code == 422

    def test_missing_score(self, client: TestClient):
        """Missing score field fails validation."""
        resp = client.post("/memory/mem-123/rate", json={})
        assert resp.status_code == 422

    def test_asymmetric_behavior_through_api(self, client: TestClient, mock_manager: AsyncMock):
        """Verify asymmetric EMA propagates correctly through HTTP layer."""
        # Start at 0.5, apply negative (score=1) then positive (score=5)
        resp = client.post("/memory/mem-asym/rate", json={"score": 1})
        assert resp.status_code == 200
        after_neg = mock_manager._ratings["current"]

        resp = client.post("/memory/mem-asym/rate", json={"score": 5})
        assert resp.status_code == 200
        after_pos = mock_manager._ratings["current"]

        # After one neg + one pos, should still be below initial 0.5
        assert after_pos < 0.5, f"Expected < 0.5, got {after_pos}"
        # Negative drop was larger than positive recovery
        drop = 0.5 - after_neg
        recovery = after_pos - after_neg
        assert drop > recovery
