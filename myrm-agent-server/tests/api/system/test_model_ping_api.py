"""Unit and API integration tests for model instant latency and health ping endpoint.

[INPUT]
- httpx, ASGITransport
- app.api.system.model_ping_api::router
- app.services.system.model_ping_service

[OUTPUT]
- Pytest test cases verifying model connection testing, TTFT, TPS, and fallback handling.

[POS]
tests/api/system/test_model_ping_api.py: 模型即时测速验证接口测试套件。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport

from app.api.system.model_ping_api import router as model_ping_router

test_app = FastAPI()
test_app.include_router(model_ping_router, prefix="/api/v1")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_ping_model_success(async_client: httpx.AsyncClient) -> None:
    payload = {
        "model_id": "claude-3-7-sonnet",
        "provider": "anthropic",
        "timeout_seconds": 5.0,
    }
    resp = await async_client.post("/api/v1/system/model-ping", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["model_id"] == "claude-3-7-sonnet"
    assert data["provider"] == "anthropic"
    assert data["status"] in ("healthy", "degraded")
    assert data["ttft_ms"] > 0
    assert data["auth_verified"] is True
    assert data["tokens_per_second"] > 0


@pytest.mark.asyncio
async def test_ping_model_fast_preset(async_client: httpx.AsyncClient) -> None:
    payload = {
        "model_id": "gemini-2.5-flash",
        "provider": "google",
    }
    resp = await async_client.post("/api/v1/system/model-ping", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["model_id"] == "gemini-2.5-flash"
    assert data["tokens_per_second"] >= 40.0


@pytest.mark.asyncio
async def test_ping_model_offline_or_error(async_client: httpx.AsyncClient) -> None:
    payload = {
        "model_id": "offline-model-test",
        "provider": "custom",
    }
    resp = await async_client.post("/api/v1/system/model-ping", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "unreachable"
    assert data["auth_verified"] is False
    assert data["error_message"] is not None


@pytest.mark.asyncio
async def test_ping_model_validation_error(async_client: httpx.AsyncClient) -> None:
    # Missing required model_id
    resp = await async_client.post("/api/v1/system/model-ping", json={})
    assert resp.status_code == 422
