"""
[INPUT]:
- httpx, ASGITransport
- app.api.system.turn_usage_api::router

[OUTPUT]:
- Pytest verification for turn round usage recording, billed vs freeze dual-count query, and gateway shape rewriting.

[POS]:
tests/api/system/test_turn_usage_api.py — 回合级 Billed Usage 双计数 API 单元测试。
"""

from collections.abc import AsyncGenerator

from fastapi import FastAPI
import httpx
from httpx import ASGITransport
import pytest

from app.api.system.turn_usage_api import router as turn_usage_router

test_app = FastAPI()
test_app.include_router(turn_usage_router, prefix="/api/v1/system")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_record_turn_rounds_and_dual_count_api(
    async_client: httpx.AsyncClient,
) -> None:
    session_id = "sess_api_turn_01"
    turn_id = "turn_api_01"

    # 1. 记录 Round 1 (初始请求)
    round1_resp = await async_client.post(
        "/api/v1/system/turn-usage/record-round",
        json={
            "session_id": session_id,
            "turn_id": turn_id,
            "input_tokens": 1200,
            "output_tokens": 150,
            "cache_read": 300,
            "cache_write": 900,
        },
    )
    assert round1_resp.status_code == 200
    r1_data = round1_resp.json()
    assert r1_data["rounds_count"] == 1
    assert r1_data["billed"]["input_tokens"] == 1200
    assert r1_data["billed"]["cache_read"] == 300
    assert r1_data["freeze_usage"]["cache_read"] == 300

    # 2. 记录 Round 2 (内部重试/工具循环再驱动)
    round2_resp = await async_client.post(
        "/api/v1/system/turn-usage/record-round",
        json={
            "session_id": session_id,
            "turn_id": turn_id,
            "input_tokens": 200,
            "output_tokens": 250,
            "cache_read": 1100,
            "cache_write": 0,
        },
    )
    assert round2_resp.status_code == 200
    r2_data = round2_resp.json()
    assert r2_data["rounds_count"] == 2

    # 核心断言：billed 必须是绝对累加；freeze_usage 必须仅保留最新有效缓存
    billed = r2_data["billed"]
    freeze = r2_data["freeze_usage"]

    assert billed["input_tokens"] == 1200 + 200
    assert billed["output_tokens"] == 150 + 250
    assert billed["cache_read"] == 300 + 1100  # 1400 实际结算
    assert billed["cache_write"] == 900 + 0

    assert freeze["input_tokens"] == 1200 + 200
    assert freeze["output_tokens"] == 150 + 250
    assert freeze["cache_read"] == 1100  # 严格等于 Round 2 的当前有效缓存，未虚增至 1400！
    assert freeze["cache_write"] == 0

    assert r2_data["cache_divergence_tokens"] == 1200  # (1400 + 900) - (1100 + 0) = 1200

    # 3. GET 查询验证
    summary_resp = await async_client.get(
        f"/api/v1/system/turn-usage/summary/{session_id}/{turn_id}"
    )
    assert summary_resp.status_code == 200
    sum_data = summary_resp.json()
    assert sum_data["rounds_count"] == 2
    assert sum_data["billed"]["cache_read"] == 1400
    assert sum_data["freeze_usage"]["cache_read"] == 1100


@pytest.mark.asyncio
async def test_rewrite_usage_shape_api(
    async_client: httpx.AsyncClient,
) -> None:
    # 模拟将 billed 累加值回写至 OpenAI 响应形状
    resp = await async_client.post(
        "/api/v1/system/turn-usage/rewrite-shape",
        json={
            "existing_shape": {
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "total_tokens": 150,
                "prompt_tokens_details": {"cached_tokens": 20},
            },
            "billed": {
                "input_tokens": 1500,
                "output_tokens": 400,
                "cache_read": 800,
                "cache_write": 200,
            },
        },
    )
    assert resp.status_code == 200
    data = resp.json()["rewritten"]
    assert data["prompt_tokens"] == 1500
    assert data["completion_tokens"] == 400
    assert data["total_tokens"] == 1900
    assert data["prompt_tokens_details"]["cached_tokens"] == 800
