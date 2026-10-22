"""
[INPUT]:
- httpx, ASGITransport
- app.api.system.memory_backend_metrics_api::router

[OUTPUT]:
- Pytest verification for memory backend metrics and recall phase latency REST endpoints.

[POS]:
tests/api/system/test_memory_backend_metrics_api.py — 记忆多后端与细分阶段指标 API 单元测试。
"""

from collections.abc import AsyncGenerator
from fastapi import FastAPI
import httpx
from httpx import ASGITransport
import pytest

from app.api.system.memory_backend_metrics_api import router as metrics_router

test_app = FastAPI()
test_app.include_router(metrics_router, prefix="/api/v1/system")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_memory_backend_metrics_lifecycle(async_client: httpx.AsyncClient) -> None:
    # 1. Reset state
    reset_resp = await async_client.post("/api/v1/system/memory-backend-metrics/reset")
    assert reset_resp.status_code == 200
    assert reset_resp.json() == {"status": "reset_completed"}

    # 2. Record samples across backends and recall phases
    r1 = await async_client.post(
        "/api/v1/system/memory-backend-metrics/sample",
        json={
            "backend": "sqlite_fts5",
            "operation": "recall",
            "phase": "collect",
            "duration_ms": 12.5,
            "success": True,
            "degraded": False,
        },
    )
    assert r1.status_code == 200
    assert r1.json()["status"] == "recorded"
    assert r1.json()["sample_id"].startswith("mem-")

    r2 = await async_client.post(
        "/api/v1/system/memory-backend-metrics/sample",
        json={
            "backend": "sqlite_fts5",
            "operation": "recall",
            "phase": "collect",
            "duration_ms": 25.0,
            "success": True,
            "degraded": False,
        },
    )
    assert r2.status_code == 200

    r3 = await async_client.post(
        "/api/v1/system/memory-backend-metrics/sample",
        json={
            "backend": "qdrant",
            "operation": "recall",
            "phase": "rerank",
            "duration_ms": 85.0,
            "success": False,
            "degraded": True,
        },
    )
    assert r3.status_code == 200

    # 3. Retrieve report
    report_resp = await async_client.get("/api/v1/system/memory-backend-metrics/report")
    assert report_resp.status_code == 200
    report_data = report_resp.json()
    assert report_data["opt_in_enabled"] is True
    assert report_data["total_samples"] == 3
    assert len(report_data["backend_stats"]) == 2

    # Verify sqlite_fts5 group stats
    sqlite_stats = next(s for s in report_data["backend_stats"] if s["backend"] == "sqlite_fts5")
    assert sqlite_stats["operation"] == "recall"
    assert sqlite_stats["phase"] == "collect"
    assert sqlite_stats["total_operations"] == 2
    assert sqlite_stats["success_count"] == 2
    assert sqlite_stats["success_rate"] == 1.0
    assert sqlite_stats["p50_duration_ms"] == 25.0

    # Verify qdrant group stats
    qdrant_stats = next(s for s in report_data["backend_stats"] if s["backend"] == "qdrant")
    assert qdrant_stats["operation"] == "recall"
    assert qdrant_stats["phase"] == "rerank"
    assert qdrant_stats["total_operations"] == 1
    assert qdrant_stats["success_rate"] == 0.0
    assert qdrant_stats["degraded_count"] == 1

    # 4. Opt-in toggle to disable high-cardinality label collection
    conf_resp = await async_client.post(
        "/api/v1/system/memory-backend-metrics/configure",
        json={"opt_in_enabled": False},
    )
    assert conf_resp.status_code == 200
    assert conf_resp.json() == {"opt_in_enabled": False}

    dropped_resp = await async_client.post(
        "/api/v1/system/memory-backend-metrics/sample",
        json={
            "backend": "in_memory",
            "operation": "retain",
            "phase": "none",
            "duration_ms": 3.0,
        },
    )
    assert dropped_resp.status_code == 200
    assert dropped_resp.json()["status"] == "dropped_opt_in_disabled"
    assert dropped_resp.json()["sample_id"] is None

    # Verify total samples did not increase
    report_resp2 = await async_client.get("/api/v1/system/memory-backend-metrics/report")
    assert report_resp2.json()["opt_in_enabled"] is False
    assert report_resp2.json()["total_samples"] == 3

    # Re-enable opt-in
    await async_client.post(
        "/api/v1/system/memory-backend-metrics/configure",
        json={"opt_in_enabled": True},
    )

    # 5. Invalid parameters validation
    bad_backend = await async_client.post(
        "/api/v1/system/memory-backend-metrics/sample",
        json={
            "backend": "unknown_db",
            "operation": "recall",
            "duration_ms": 10.0,
        },
    )
    assert bad_backend.status_code == 400

    bad_op = await async_client.post(
        "/api/v1/system/memory-backend-metrics/sample",
        json={
            "backend": "sqlite_fts5",
            "operation": "invalid_op",
            "duration_ms": 10.0,
        },
    )
    assert bad_op.status_code == 400
