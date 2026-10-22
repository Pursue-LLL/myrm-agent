"""
[INPUT]:
- httpx, ASGITransport
- app.api.system.sandbox_hardware_telemetry_api::router

[OUTPUT]:
- Pytest verification for sandbox hardware telemetry and three-tier runaway circuit breaker REST endpoints.

[POS]:
tests/api/system/test_sandbox_hardware_telemetry_api.py — 沙箱硬件遥测与三级熔断 API 单元测试。
"""

from collections.abc import AsyncGenerator

from fastapi import FastAPI
import httpx
from httpx import ASGITransport
import pytest

from app.api.system.sandbox_hardware_telemetry_api import router as hw_router

test_app = FastAPI()
test_app.include_router(hw_router, prefix="/api/v1/system")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_sandbox_hardware_telemetry_api_flow(async_client: httpx.AsyncClient) -> None:
    # 1. Reset circuit breaker to clean state
    reset_resp = await async_client.post("/api/v1/system/sandbox-hardware/reset")
    assert reset_resp.status_code == 200
    assert reset_resp.json() == {"ok": True}

    # 2. Check initial snapshot
    init_snap = await async_client.get("/api/v1/system/sandbox-hardware/snapshot")
    assert init_snap.status_code == 200
    snap_data = init_snap.json()
    assert snap_data["current_level"] == "normal"
    assert snap_data["consecutive_violations"] == 0
    assert len(snap_data["incident_history"]) == 0

    # 3. Ingest normal sample
    s1_resp = await async_client.post(
        "/api/v1/system/sandbox-hardware/sample",
        json={
            "cpu_percent": 35.0,
            "memory_used_bytes": 4294967296,
            "memory_total_bytes": 17179869184,
            "memory_percent": 25.0,
            "disk_used_bytes": 53687091200,
            "disk_total_bytes": 107374182400,
            "disk_percent": 50.0,
        },
    )
    assert s1_resp.status_code == 200
    s1_data = s1_resp.json()
    assert s1_data["level"] == "normal"
    assert s1_data["triggered_metric"] == "none"

    # 4. Ingest high-load sample triggering WARNING
    s2_resp = await async_client.post(
        "/api/v1/system/sandbox-hardware/sample",
        json={
            "cpu_percent": 84.0,
            "memory_used_bytes": 8589934592,
            "memory_total_bytes": 17179869184,
            "memory_percent": 50.0,
            "disk_used_bytes": 53687091200,
            "disk_total_bytes": 107374182400,
            "disk_percent": 50.0,
        },
    )
    assert s2_resp.status_code == 200
    s2_data = s2_resp.json()
    assert s2_data["level"] == "warning"
    assert s2_data["triggered_metric"] == "CPU"
    assert s2_data["current_value"] == 84.0

    # 5. Verify snapshot reflects incident
    warn_snap = await async_client.get("/api/v1/system/sandbox-hardware/snapshot")
    assert warn_snap.status_code == 200
    w_data = warn_snap.json()
    assert w_data["current_level"] == "warning"
    assert len(w_data["incident_history"]) == 1

    # 6. Dynamically configure thresholds
    cfg_resp = await async_client.post(
        "/api/v1/system/sandbox-hardware/configure",
        json={"warning_cpu_threshold": 70.0},
    )
    assert cfg_resp.status_code == 200
    assert cfg_resp.json()["warning_cpu_threshold"] == 70.0

    # 7. Reset state
    reset_again = await async_client.post("/api/v1/system/sandbox-hardware/reset")
    assert reset_again.status_code == 200
    clean_snap = await async_client.get("/api/v1/system/sandbox-hardware/snapshot")
    assert clean_snap.json()["current_level"] == "normal"
