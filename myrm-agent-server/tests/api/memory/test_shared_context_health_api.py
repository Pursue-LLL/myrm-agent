from __future__ import annotations

from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.memory.operations import shared_context_health as health_operation
from app.api.memory.router import router as memory_router
from app.services.memory.shared_context_health import SharedContextMemoryHealthResult


def test_shared_context_memory_health_route_is_not_captured_by_context_id(
    monkeypatch,
) -> None:
    async def fake_health(*, probe: bool) -> SharedContextMemoryHealthResult:
        assert probe is True
        return SharedContextMemoryHealthResult(
            ready=True,
            status="ready",
            model="text-embedding-3-small",
            api_base_configured=False,
            api_key_configured=True,
            probed=True,
            reason=None,
            retryable=False,
            checked_at=datetime(2026, 4, 30, tzinfo=UTC),
            vector_dimension=1536,
        )

    monkeypatch.setattr(health_operation, "check_shared_context_memory_health", fake_health)
    app = FastAPI()
    app.include_router(memory_router, prefix="/memory")
    client = TestClient(app)

    response = client.get("/memory/shared-contexts/health/memory?probe=true")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ready"] is True
    assert payload["status"] == "ready"
    assert payload["probed"] is True
    assert payload["vector_dimension"] == 1536
