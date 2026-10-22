"""
[INPUT]:
- httpx, ASGITransport
- app.api.system.otel_degrade_api::router

[OUTPUT]:
- Pytest verification for OpenTelemetry graceful degrade status, active probe, and simulation endpoints.

[POS]:
tests/api/system/test_otel_degrade_api.py — OpenTelemetry 缺失时优雅降级 API 单元测试。
"""

from collections.abc import AsyncGenerator

from fastapi import FastAPI
import httpx
from httpx import ASGITransport
import pytest

from app.api.system.otel_degrade_api import router as otel_degrade_router

test_app = FastAPI()
test_app.include_router(otel_degrade_router, prefix="/api/v1/system")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_get_status_and_active_probe(async_client: httpx.AsyncClient) -> None:
    # 1. 查询初始探针状态
    status_resp = await async_client.get("/api/v1/system/otel-degrade/status")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert "state" in status_data
    assert status_data["state"] in ["ACTIVE", "DEGRADED_NO_OP", "DISABLED"]
    assert "last_probe_time" in status_data

    # 2. 主动触发一次环境探针自检
    probe_resp = await async_client.post("/api/v1/system/otel-degrade/probe")
    assert probe_resp.status_code == 200
    probe_data = probe_resp.json()
    assert probe_data["state"] == status_data["state"]


@pytest.mark.asyncio
async def test_simulate_dependency_missing_and_recovery(async_client: httpx.AsyncClient) -> None:
    try:
        # 1. 模拟依赖缺失
        sim_resp = await async_client.post(
            "/api/v1/system/otel-degrade/simulate",
            json={"simulate_missing": True},
        )
        assert sim_resp.status_code == 200
        sim_data = sim_resp.json()
        assert sim_data["simulating_missing"] is True
        curr = sim_data["current_status"]
        assert curr["state"] == "DEGRADED_NO_OP"
        assert curr["is_otel_installed"] is False
        assert "Dependency 'opentelemetry' is missing" in (curr["degrade_reason"] or "")

        # 2. 再次通过 GET 验证降级状态生效
        get_resp = await async_client.get("/api/v1/system/otel-degrade/status")
        assert get_resp.status_code == 200
        assert get_resp.json()["state"] == "DEGRADED_NO_OP"
    finally:
        # 3. 恢复依赖模拟
        restore_resp = await async_client.post(
            "/api/v1/system/otel-degrade/simulate",
            json={"simulate_missing": False},
        )
        assert restore_resp.status_code == 200
        assert restore_resp.json()["simulating_missing"] is False
