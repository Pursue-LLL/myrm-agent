"""
[INPUT]:
- httpx, ASGITransport
- app.api.system.rate_limit_split_api::router

[OUTPUT]:
- Pytest verification for rate limit source split endpoints, provider failure attribution, and metric consistency.

[POS]:
tests/api/system/test_rate_limit_split_api.py — 429 限流来源拆分与失败归因 API 单元测试。
"""

from collections.abc import AsyncGenerator

from fastapi import FastAPI
import httpx
from httpx import ASGITransport
import pytest

from app.api.system.rate_limit_split_api import router as rate_limit_split_router

test_app = FastAPI()
test_app.include_router(rate_limit_split_router, prefix="/api/v1/system")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_rate_limit_split_api_flow(async_client: httpx.AsyncClient) -> None:
    # 1. Reset metrics to start from clean state
    reset_resp = await async_client.post("/api/v1/system/rate-limit-split/reset")
    assert reset_resp.status_code == 200
    assert reset_resp.json() == {"ok": True}

    # 2. Check initial metrics snapshot
    metrics_resp = await async_client.get("/api/v1/system/rate-limit-split/metrics")
    assert metrics_resp.status_code == 200
    metrics_data = metrics_resp.json()
    assert metrics_data["total_requests"] == 0
    assert metrics_data["total_rate_limited"] == 0
    assert metrics_data["rate_limited_by_source"] == {"myrm": 0, "upstream": 0}
    assert metrics_data["total_failed"] == 0
    assert metrics_data["failed_by_provider"] == {"unknown": 0}
    assert metrics_data["totals_consistent"] is True

    # 3. Record internal governor (myrm) rate limit
    rl_myrm = await async_client.post(
        "/api/v1/system/rate-limit-split/record-rate-limit",
        json={
            "source": "myrm",
            "provider": "openai",
            "model": "gpt-4o",
            "reason": "Local token rate cap exceeded",
        },
    )
    assert rl_myrm.status_code == 200
    myrm_data = rl_myrm.json()
    assert myrm_data["source"] == "myrm"
    assert myrm_data["provider"] == "openai"

    # 4. Record upstream provider 429
    rl_upstream = await async_client.post(
        "/api/v1/system/rate-limit-split/record-rate-limit",
        json={
            "source": "upstream",
            "provider": "anthropic",
            "model": "claude-3-5-sonnet",
            "reason": "HTTP 429 Too Many Requests from Anthropic",
        },
    )
    assert rl_upstream.status_code == 200
    upstream_data = rl_upstream.json()
    assert upstream_data["source"] == "upstream"
    assert upstream_data["provider"] == "anthropic"

    # 5. Record request failure attributed to deepseek
    fail_resp = await async_client.post(
        "/api/v1/system/rate-limit-split/record-failure",
        json={
            "provider": "deepseek",
            "model": "deepseek-chat",
            "error_code": "PROVIDER_OVERLOADED_503",
            "reason": "Temporary upstream capacity shortage",
        },
    )
    assert fail_resp.status_code == 200
    fail_data = fail_resp.json()
    assert fail_data["provider"] == "deepseek"
    assert fail_data["error_code"] == "PROVIDER_OVERLOADED_503"

    # 6. Record completed request
    comp_resp = await async_client.post(
        "/api/v1/system/rate-limit-split/record-completed",
        json={"provider": "openai", "model": "gpt-4o"},
    )
    assert comp_resp.status_code == 200
    assert comp_resp.json() == {"ok": True}

    # 7. Final snapshot verification
    final_metrics_resp = await async_client.get("/api/v1/system/rate-limit-split/metrics")
    assert final_metrics_resp.status_code == 200
    final_data = final_metrics_resp.json()

    assert final_data["total_requests"] == 4
    assert final_data["total_completed"] == 1
    assert final_data["total_rate_limited"] == 2
    assert final_data["rate_limited_by_source"]["myrm"] == 1
    assert final_data["rate_limited_by_source"]["upstream"] == 1
    assert final_data["total_failed"] == 1
    assert final_data["failed_by_provider"]["deepseek"] == 1
    assert final_data["totals_consistent"] is True
    assert len(final_data["recent_rate_limit_events"]) == 2
    assert len(final_data["recent_failure_events"]) == 1
