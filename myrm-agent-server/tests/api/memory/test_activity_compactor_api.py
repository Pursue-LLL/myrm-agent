"""[POS]: tests/api/memory/test_activity_compactor_api.py
[INPUT]: None.
[OUTPUT]: Comprehensive integration tests for hierarchical activity compactor API endpoints.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.activity_compactor_router import (
    router as activity_compactor_router,
)
from app.services.memory.activity_compactor_service import (
    get_activity_compactor_service,
)


@pytest.fixture
def test_app() -> FastAPI:
    """Create isolated FastAPI app mounting activity compactor router."""
    api_app = FastAPI()
    api_app.include_router(activity_compactor_router, prefix="/api/memory")
    return api_app


@pytest.fixture(autouse=True)
def reset_service() -> None:
    """Reset activity compactor pipeline state between tests."""
    service = get_activity_compactor_service()
    service.pipeline.reset()


@pytest.mark.asyncio
async def test_ingest_activity_event_api(test_app: FastAPI) -> None:
    """Verify single event ingestion into the activity compactor buffer."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "app_name": "VSCode",
            "window_title": "models.py",
            "action_type": "window_focus",
            "event_payload": "",
            "duration_seconds": 15.0,
        }
        resp = await client.post("/api/memory/activity-compactor/ingest", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "ok"
        assert data["app_name"] == "VSCode"


@pytest.mark.asyncio
async def test_trigger_micro_fold_api(test_app: FastAPI) -> None:
    """Verify 10-minute micro window fold produces algorithmic slice."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Ingest an event first
        ingest_payload = {
            "app_name": "PyCharm",
            "window_title": "app.py",
            "action_type": "keystroke_burst",
            "event_payload": "print('hello')",
            "duration_seconds": 30.0,
        }
        await client.post("/api/memory/activity-compactor/ingest", json=ingest_payload)

        # 2. Trigger micro fold
        resp = await client.post("/api/memory/activity-compactor/micro-fold")
        assert resp.status_code == 200
        data = resp.json()
        assert data["primary_app"] == "PyCharm"
        assert data["raw_event_count"] == 1
        assert data["is_idle"] is False
        assert "PyCharm" in data["folded_summary"]


@pytest.mark.asyncio
async def test_trigger_macro_distill_api(test_app: FastAPI) -> None:
    """Verify 6-hour macro milestone distillation consolidates micro slices."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Ingest and fold
        ingest_payload = {
            "app_name": "VSCode",
            "window_title": "test_suite.py",
            "action_type": "terminal_cmd",
            "event_payload": "pytest -v",
            "duration_seconds": 20.0,
        }
        await client.post("/api/memory/activity-compactor/ingest", json=ingest_payload)
        await client.post("/api/memory/activity-compactor/micro-fold")

        # Distill macro
        resp = await client.post("/api/memory/activity-compactor/macro-distill")
        assert resp.status_code == 200
        data = resp.json()
        assert data["micro_slices_count"] == 1
        assert "development" in data["tags"] or "testing" in data["tags"]
        assert len(data["key_activities"]) >= 1


@pytest.mark.asyncio
async def test_synthesize_daily_archive_and_telemetry_api(test_app: FastAPI) -> None:
    """Verify 24-hour daily archive synthesis and telemetry querying."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Ingest, fold, and distill
        ingest_payload = {
            "app_name": "Chrome",
            "window_title": "docs.python.org",
            "action_type": "browser_nav",
            "event_payload": "https://docs.python.org",
            "duration_seconds": 10.0,
        }
        await client.post("/api/memory/activity-compactor/ingest", json=ingest_payload)
        await client.post("/api/memory/activity-compactor/micro-fold")
        await client.post("/api/memory/activity-compactor/macro-distill")

        # 1. Synthesize daily archive
        resp_daily = await client.post("/api/memory/activity-compactor/daily-archive", json={"date_str": "2026-10-08"})
        assert resp_daily.status_code == 200
        daily_data = resp_daily.json()
        assert daily_data["date_str"] == "2026-10-08"
        assert daily_data["total_raw_events_processed"] == 1

        # 2. Query telemetry
        resp_telemetry = await client.get("/api/memory/activity-compactor/telemetry")
        assert resp_telemetry.status_code == 200
        tel_data = resp_telemetry.json()
        assert tel_data["total_raw_events"] == 1
        assert tel_data["total_micro_slices"] == 1
        assert tel_data["total_macro_folds"] == 1
        assert tel_data["compression_ratio"] > 0.0

        # 3. Query lists
        resp_slices = await client.get("/api/memory/activity-compactor/slices?limit=5")
        assert resp_slices.status_code == 200
        assert len(resp_slices.json()) == 1

        resp_folds = await client.get("/api/memory/activity-compactor/folds?limit=5")
        assert resp_folds.status_code == 200
        assert len(resp_folds.json()) == 1
