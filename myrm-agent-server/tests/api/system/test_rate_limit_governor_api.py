"""
[INPUT]:
- httpx, ASGITransport
- app.api.system.rate_limit_governor_api::router

[OUTPUT]:
- Pytest test cases verifying client-side pacing pre-check, header sniffing, live status telemetry, and subagent quota isolation.

[POS]:
tests/api/system/test_rate_limit_governor_api.py — 客户端主动限流预测阀门与自适应配额调度 API 单元测试。
"""

from collections.abc import AsyncGenerator

from fastapi import FastAPI
import httpx
from httpx import ASGITransport
import pytest

from app.api.system.rate_limit_governor_api import router as rate_limit_governor_router

test_app = FastAPI()
test_app.include_router(rate_limit_governor_router, prefix="/api/v1/system")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_pacing_pre_check_and_usage_flow(async_client: httpx.AsyncClient) -> None:
    # 1. 预检请求：低水位健康放行
    pre_check_payload = {
        "model_name": "claude-3-5-sonnet",
        "estimated_prompt_tokens": 1200,
        "fallback_model": "claude-3-5-haiku",
    }
    resp = await async_client.post("/api/v1/system/rate-limit-governor/pre-check", json=pre_check_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["action"] == "IMMEDIATE_PASS"
    assert data["delay_ms"] == 0
    assert data["target_model_or_fallback"] == "claude-3-5-sonnet"

    # 2. 消耗登记
    record_payload = {
        "model_name": "claude-3-5-sonnet",
        "actual_tokens": 1200,
    }
    rec_resp = await async_client.post("/api/v1/system/rate-limit-governor/record-usage", json=record_payload)
    assert rec_resp.status_code == 200
    assert rec_resp.json()["status"] == "ok"

    # 3. 实时状态监控查询
    status_resp = await async_client.get("/api/v1/system/rate-limit-governor/status?model_name=claude-3-5-sonnet")
    assert status_resp.status_code == 200
    statuses = status_resp.json()
    assert len(statuses) == 1
    assert statuses[0]["model_name"] == "claude-3-5-sonnet"
    assert statuses[0]["tpm_watermark_pct"] > 0
    assert statuses[0]["status_label"] == "✓ 绿灯顺畅放行"


@pytest.mark.asyncio
async def test_update_headers_sniffing(async_client: httpx.AsyncClient) -> None:
    headers_payload = {
        "model_name": "gpt-4o",
        "headers": {
            "x-ratelimit-remaining-tokens": "88000",
            "x-ratelimit-reset-tokens": "500ms",
            "x-ratelimit-remaining-requests": "99",
            "x-ratelimit-reset-requests": "60s",
        },
    }
    resp = await async_client.post("/api/v1/system/rate-limit-governor/update-headers", json=headers_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["model_name"] == "gpt-4o"
    assert data["remaining_tokens"] == 88000
    assert data["reset_tokens_seconds"] == 0.5
    assert data["remaining_requests"] == 99


@pytest.mark.asyncio
async def test_subagent_quota_slicing_api(async_client: httpx.AsyncClient) -> None:
    ws_id = "ws-test-rate-limit-01"

    # 1. 为两个子 Agent 分割配额
    alloc_payload_1 = {
        "workspace_id": ws_id,
        "subagent_id": "subagent-crawler",
        "total_available_tpm": 60_000,
        "concurrency_count": 2,
    }
    resp1 = await async_client.post("/api/v1/system/rate-limit-governor/slices/allocate", json=alloc_payload_1)
    assert resp1.status_code == 200
    assert resp1.json()["allocated_tpm_share"] == 30_000

    alloc_payload_2 = {
        "workspace_id": ws_id,
        "subagent_id": "subagent-coder",
        "total_available_tpm": 60_000,
        "concurrency_count": 2,
    }
    resp2 = await async_client.post("/api/v1/system/rate-limit-governor/slices/allocate", json=alloc_payload_2)
    assert resp2.status_code == 200
    assert resp2.json()["allocated_tpm_share"] == 30_000

    # 2. subagent-crawler 消耗达到上限触发限流
    consume_payload = {
        "workspace_id": ws_id,
        "subagent_id": "subagent-crawler",
        "tokens": 35_000,
    }
    c_resp = await async_client.post("/api/v1/system/rate-limit-governor/slices/consume", json=consume_payload)
    assert c_resp.status_code == 200
    assert c_resp.json()["is_throttled"] is True

    # 3. 查看切片列表
    list_resp = await async_client.get(f"/api/v1/system/rate-limit-governor/slices?workspace_id={ws_id}")
    assert list_resp.status_code == 200
    slices = list_resp.json()
    assert len(slices) == 2

    # 4. 重置窗口
    reset_resp = await async_client.post(f"/api/v1/system/rate-limit-governor/slices/reset?workspace_id={ws_id}")
    assert reset_resp.status_code == 200
    assert reset_resp.json()["status"] == "ok"
