"""
[INPUT]:
- httpx, ASGITransport
- app.api.system.stream_metrics_api::router

[OUTPUT]:
- Pytest verification for streamed call sessions, chunk anti-pollution guarantees, and aggregate endpoints.

[POS]:
tests/api/system/test_stream_metrics_api.py — 流式调用按最终结果计量 API 单元测试。
"""

from collections.abc import AsyncGenerator

from fastapi import FastAPI
import httpx
from httpx import ASGITransport
import pytest

from app.api.system.stream_metrics_api import router as stream_metrics_router

test_app = FastAPI()
test_app.include_router(stream_metrics_router, prefix="/api/v1/system")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_streamed_call_lifecycle_and_chunk_anti_pollution(
    async_client: httpx.AsyncClient,
) -> None:
    call_id = "call_api_test_stream_01"

    # 1. 启动流式调用生命周期跟踪
    start_resp = await async_client.post(
        "/api/v1/system/stream-metrics/session/start",
        json={
            "call_id": call_id,
            "model_name": "claude-3-7-sonnet-20250219",
            "provider": "anthropic",
        },
    )
    assert start_resp.status_code == 200
    start_data = start_resp.json()
    assert start_data["call_id"] == call_id
    assert start_data["chunk_count"] == 0
    assert start_data["is_finalized"] is False

    # 2. 上报首字 chunk（标记 is_first_token=True）
    chunk_1 = await async_client.post(
        "/api/v1/system/stream-metrics/session/chunk",
        json={"call_id": call_id, "chunk_tokens": 5, "is_first_token": True},
    )
    assert chunk_1.status_code == 200
    assert chunk_1.json()["chunk_count"] == 1
    assert chunk_1.json()["ttft_ms"] is not None

    # 3. 模拟连续上报 99 个中间 chunk
    for _ in range(99):
        await async_client.post(
            "/api/v1/system/stream-metrics/session/chunk",
            json={"call_id": call_id, "chunk_tokens": 2, "is_first_token": False},
        )

    # 4. 终态结算为 SUCCESS
    finalize_resp = await async_client.post(
        "/api/v1/system/stream-metrics/session/finalize",
        json={"call_id": call_id, "outcome": "SUCCESS"},
    )
    assert finalize_resp.status_code == 200
    fin_data = finalize_resp.json()
    assert fin_data["is_finalized"] is True
    assert fin_data["outcome"] == "SUCCESS"
    assert fin_data["chunk_count"] == 100
    assert fin_data["total_tokens"] == (5 + 99 * 2)

    # 5. 查询聚合大盘，核心防污染断言：total_calls 严格为当前独立调用数，而非 100！
    agg_resp = await async_client.get(
        "/api/v1/system/stream-metrics/aggregate?model_name=claude-3-7-sonnet-20250219"
    )
    assert agg_resp.status_code == 200
    agg = agg_resp.json()
    assert agg["total_calls"] == 1
    assert agg["success_calls"] == 1
    assert agg["total_chunks"] == 100
    assert agg["chunk_inflation_ratio"] == 100.0
    assert agg["success_rate_pct"] == 100.0

    # 6. 查询单次调用详情
    detail_resp = await async_client.get(f"/api/v1/system/stream-metrics/session/{call_id}")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["call_id"] == call_id
    assert detail["chunk_count"] == 100


@pytest.mark.asyncio
async def test_cancelled_and_error_outcome_attribution_api(
    async_client: httpx.AsyncClient,
) -> None:
    # 场景 1: 用户主动取消
    c_cancel = "call_api_cancel_02"
    await async_client.post(
        "/api/v1/system/stream-metrics/session/start",
        json={"call_id": c_cancel, "model_name": "gpt-4o", "provider": "openai"},
    )
    await async_client.post(
        "/api/v1/system/stream-metrics/session/chunk",
        json={"call_id": c_cancel, "chunk_tokens": 10, "is_first_token": True},
    )
    cancel_resp = await async_client.post(
        "/api/v1/system/stream-metrics/session/finalize",
        json={"call_id": c_cancel, "outcome": "CANCELLED"},
    )
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["outcome"] == "CANCELLED"

    # 场景 2: 流式超时
    c_timeout = "call_api_timeout_03"
    await async_client.post(
        "/api/v1/system/stream-metrics/session/start",
        json={"call_id": c_timeout, "model_name": "gpt-4o", "provider": "openai"},
    )
    timeout_resp = await async_client.post(
        "/api/v1/system/stream-metrics/session/finalize",
        json={
            "call_id": c_timeout,
            "outcome": "TIMEOUT",
            "error_message": "Stream idle for 30s",
        },
    )
    assert timeout_resp.status_code == 200
    assert timeout_resp.json()["outcome"] == "TIMEOUT"

    # 聚合验证 gpt-4o 维度
    agg_resp = await async_client.get("/api/v1/system/stream-metrics/aggregate?model_name=gpt-4o")
    assert agg_resp.status_code == 200
    agg = agg_resp.json()
    assert agg["total_calls"] == 2
    assert agg["cancelled_calls"] == 1
    assert agg["timeout_calls"] == 1
    assert agg["success_calls"] == 0
