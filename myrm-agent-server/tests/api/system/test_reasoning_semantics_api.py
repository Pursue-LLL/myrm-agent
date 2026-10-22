"""
[INPUT]:
- httpx, ASGITransport
- app.api.system.reasoning_semantics_api::router

[OUTPUT]:
- Pytest test cases verifying provider token normalization, invariant check / auto-healing, and policy list endpoints.

[POS]:
tests/api/system/test_reasoning_semantics_api.py — 推理 Token 计费语义契约与重复计数回归守卫 API 单元测试。
"""

from collections.abc import AsyncGenerator

from fastapi import FastAPI
import httpx
from httpx import ASGITransport
import pytest

from app.api.system.reasoning_semantics_api import router as reasoning_semantics_router

test_app = FastAPI()
test_app.include_router(reasoning_semantics_router, prefix="/api/v1/system")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_normalize_token_usage_openai_and_vllm_api(async_client: httpx.AsyncClient) -> None:
    # 1. 验证 OpenAI o3-mini 归一化 (completion_tokens 包含 reasoning_tokens)
    payload_openai = {
        "provider_or_model": "openai/o3-mini",
        "raw_usage": {
            "prompt_tokens": 1500,
            "completion_tokens": 4000,
            "reasoning_tokens": 2500,
            "total_tokens": 5500,
        },
        "prompt_cost_per_1k": 0.003,
        "completion_cost_per_1k": 0.015,
    }
    resp1 = await async_client.post("/api/v1/system/reasoning-semantics/normalize", json=payload_openai)
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["prompt_tokens"] == 1500
    assert data1["completion_tokens"] == 4000
    assert data1["reasoning_tokens"] == 2500
    assert data1["visible_content_tokens"] == 1500
    assert data1["total_tokens"] == 5500  # 1500 + 4000
    assert data1["is_zero_double_counted"] is True
    assert data1["policy_applied"] == "INCLUDED_IN_COMPLETION"

    # 2. 验证 vLLM Standalone 独立网关归一化 (需合并)
    payload_vllm = {
        "provider_or_model": "vllm_standalone_gateway",
        "raw_usage": {
            "prompt_tokens": 1000,
            "completion_tokens": 800,
            "reasoning_tokens": 1200,
        },
    }
    resp2 = await async_client.post("/api/v1/system/reasoning-semantics/normalize", json=payload_vllm)
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["completion_tokens"] == 2000  # 800 + 1200
    assert data2["total_tokens"] == 3000  # 1000 + 2000
    assert data2["policy_applied"] == "STANDALONE_OUTPUT"


@pytest.mark.asyncio
async def test_verify_token_invariant_and_healing_api(async_client: httpx.AsyncClient) -> None:
    # 1. 验证正常快照
    valid_payload = {
        "prompt_tokens": 1000,
        "completion_tokens": 3000,
        "reasoning_tokens": 1500,
        "total_tokens": 4000,
        "cost_usd": 0.048,
    }
    resp_valid = await async_client.post("/api/v1/system/reasoning-semantics/verify-invariant", json=valid_payload)
    assert resp_valid.status_code == 200
    v_data = resp_valid.json()
    assert v_data["is_valid"] is True
    assert v_data["violation_type"] is None

    # 2. 验证上游重复累加漏洞 (total_tokens 误传 prompt + completion + reasoning = 5500)
    double_counting_payload = {
        "prompt_tokens": 1000,
        "completion_tokens": 3000,
        "reasoning_tokens": 1500,
        "total_tokens": 4000,
        "raw_reported_total": 5500,  # 1000 + 3000 + 1500
    }
    resp_double = await async_client.post("/api/v1/system/reasoning-semantics/verify-invariant", json=double_counting_payload)
    assert resp_double.status_code == 200
    d_data = resp_double.json()
    assert d_data["is_valid"] is False
    assert d_data["violation_type"] == "DOUBLE_COUNTING_TOTAL"
    assert "检测到严重重复计数漏洞" in str(d_data["diagnostic_warning"])


@pytest.mark.asyncio
async def test_list_provider_policies_api(async_client: httpx.AsyncClient) -> None:
    resp = await async_client.get("/api/v1/system/reasoning-semantics/policies")
    assert resp.status_code == 200
    policies = resp.json()
    assert len(policies) >= 4
    keywords = {p["provider_keyword"] for p in policies}
    assert "openai" in keywords
    assert "anthropic" in keywords
    assert "deepseek" in keywords
