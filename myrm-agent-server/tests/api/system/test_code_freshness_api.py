"""
[INPUT]:
- httpx, ASGITransport
- app.api.system.code_freshness_api::router

[OUTPUT]:
- Pytest verification for three-state code freshness (fresh/stale/indeterminate) and drain/restart recommendation REST endpoints.

[POS]:
tests/api/system/test_code_freshness_api.py — 运行时代码新鲜度三态判定 API 单元测试。
"""

from collections.abc import AsyncGenerator
from fastapi import FastAPI
import httpx
from httpx import ASGITransport
import pytest

from app.api.system.code_freshness_api import router as cf_router

test_app = FastAPI()
test_app.include_router(cf_router, prefix="/api/v1/system")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_code_freshness_api_flow(async_client: httpx.AsyncClient) -> None:
    # 1. Reset state
    reset_resp = await async_client.post("/api/v1/system/code-freshness/reset")
    assert reset_resp.status_code == 200
    assert reset_resp.json() == {"status": "reset"}

    # 2. Register module
    reg_resp = await async_client.post(
        "/api/v1/system/code-freshness/register",
        json={"module_name": "app.core.sample", "file_path": "/app/sample.py"},
    )
    assert reg_resp.status_code == 200
    assert reg_resp.json()["status"] == "registered"

    # 3. Inspect module with simulated stale mtime (mtime > process start)
    # Using fixed epoch timestamps: process start roughly now, mtime 1 hour in future
    import time
    now_ms = int(time.time() * 1000)
    stale_mtime_ms = now_ms + 3600000

    inspect_stale = await async_client.post(
        "/api/v1/system/code-freshness/inspect-module",
        json={
            "module_name": "app.core.sample",
            "file_path": "/app/sample.py",
            "mock_mtime_ms": stale_mtime_ms,
        },
    )
    assert inspect_stale.status_code == 200
    stale_data = inspect_stale.json()
    assert stale_data["state"] == "stale"
    assert stale_data["time_drift_seconds"] is not None
    assert stale_data["time_drift_seconds"] > 0
    assert "older than disk code" in stale_data["remediation_hint"]

    # 4. Inspect module with simulated fresh mtime (mtime < process start)
    fresh_mtime_ms = now_ms - 3600000
    inspect_fresh = await async_client.post(
        "/api/v1/system/code-freshness/inspect-module",
        json={
            "module_name": "app.core.sample_fresh",
            "file_path": "/app/sample_fresh.py",
            "mock_mtime_ms": fresh_mtime_ms,
        },
    )
    assert inspect_fresh.status_code == 200
    fresh_data = inspect_fresh.json()
    assert fresh_data["state"] == "fresh"

    # 5. Fetch comprehensive report
    report_resp = await async_client.get("/api/v1/system/code-freshness/report")
    assert report_resp.status_code == 200
    report_data = report_resp.json()
    assert report_data["pid"] > 0
    assert "overall_state" in report_data
    assert report_data["total_inspected_modules"] >= 1
    assert "details" in report_data
