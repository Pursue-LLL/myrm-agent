"""
[INPUT]:
- httpx, ASGITransport
- app.api.system.org_spend_limit_api::router

[OUTPUT]:
- Pytest test cases verifying organization spend limits, pre-check gating, spend recording, and attribution endpoints.

[POS]:
tests/api/system/test_org_spend_limit_api.py — 组织级共享 Agent 预算硬限额与 Query 标签归因审计 API 单元测试。
"""

from collections.abc import AsyncGenerator

from fastapi import FastAPI
import httpx
from httpx import ASGITransport
import pytest

from app.api.system.org_spend_limit_api import router as org_spend_limit_router

test_app = FastAPI()
test_app.include_router(org_spend_limit_router, prefix="/api/v1/system")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_org_budget_configuration_and_precheck_lifecycle(
    async_client: httpx.AsyncClient,
) -> None:
    org_id = "org_api_lifecycle_test"

    # 1. 配置组织月度预算 $50，80% 软预警，100% 熔断
    cfg_resp = await async_client.post(
        "/api/v1/system/org-spend-limit/configure",
        json={
            "org_id": org_id,
            "monthly_budget_usd": 50.0,
            "soft_warn_watermark_pct": 80.0,
            "hard_block_limit_usd": 50.0,
            "is_circuit_breaker_enabled": True,
        },
    )
    assert cfg_resp.status_code == 200
    assert cfg_resp.json()["status"] == "ok"

    # 2. 正常群聊预检：应放行 ALLOW
    pre_resp = await async_client.post(
        "/api/v1/system/org-spend-limit/pre-check",
        json={
            "org_id": org_id,
            "estimated_cost_usd": 1.0,
            "label": {
                "org_id": org_id,
                "surface": "CHANNEL",
                "billing_scope": "ORG_SHARED",
                "session_id": "sess_ch_001",
                "requesting_user_id": "ident:alice",
                "query_tags": ["code-review"],
            },
        },
    )
    assert pre_resp.status_code == 200
    pre_data = pre_resp.json()
    assert pre_data["action"] == "ALLOW"
    assert pre_data["is_blocked"] is False

    # 3. 记录群聊实际支出 $42 (达到 84%，进入 WARN_APPROACHING 区间)
    rec_resp = await async_client.post(
        "/api/v1/system/org-spend-limit/record-spend",
        json={
            "org_id": org_id,
            "actual_tokens": 120000,
            "actual_cost_usd": 42.0,
            "label": {
                "org_id": org_id,
                "surface": "CHANNEL",
                "billing_scope": "ORG_SHARED",
                "session_id": "sess_ch_001",
                "requesting_user_id": "ident:alice",
                "query_tags": ["code-review"],
            },
        },
    )
    assert rec_resp.status_code == 200
    rec_data = rec_resp.json()
    assert rec_data["tokens_consumed"] == 120000
    assert rec_data["cost_usd"] == 42.0

    # 4. 再次发起群聊预检：应触发 WARN_APPROACHING
    warn_resp = await async_client.post(
        "/api/v1/system/org-spend-limit/pre-check",
        json={
            "org_id": org_id,
            "estimated_cost_usd": 0.5,
            "label": {
                "org_id": org_id,
                "surface": "CHANNEL",
                "billing_scope": "ORG_SHARED",
                "session_id": "sess_ch_002",
                "requesting_user_id": "ident:bob",
                "query_tags": ["summarize"],
            },
        },
    )
    assert warn_resp.status_code == 200
    warn_data = warn_resp.json()
    assert warn_data["action"] == "WARN_APPROACHING"
    assert warn_data["is_blocked"] is False
    assert warn_data["utilization_pct"] >= 80.0

    # 5. 记录追加支出 $9，使得总支出达到 $51 (超支 > $50)
    rec_resp2 = await async_client.post(
        "/api/v1/system/org-spend-limit/record-spend",
        json={
            "org_id": org_id,
            "actual_tokens": 30000,
            "actual_cost_usd": 9.0,
            "label": {
                "org_id": org_id,
                "surface": "CHANNEL",
                "billing_scope": "ORG_SHARED",
                "session_id": "sess_ch_002",
                "requesting_user_id": "ident:bob",
                "query_tags": ["summarize"],
            },
        },
    )
    assert rec_resp2.status_code == 200

    # 6. 群聊预检应触发 CIRCUIT_BREAKER_BLOCKED 阻断
    block_resp = await async_client.post(
        "/api/v1/system/org-spend-limit/pre-check",
        json={
            "org_id": org_id,
            "estimated_cost_usd": 0.5,
            "label": {
                "org_id": org_id,
                "surface": "CHANNEL",
                "billing_scope": "ORG_SHARED",
                "session_id": "sess_ch_003",
                "requesting_user_id": "ident:charlie",
                "query_tags": ["test"],
            },
        },
    )
    assert block_resp.status_code == 200
    block_data = block_resp.json()
    assert block_data["action"] == "CIRCUIT_BREAKER_BLOCKED"
    assert block_data["is_blocked"] is True

    # 7. 私聊个人预检 (DIRECT_MESSAGE + PERSONAL_DM)：应自动绕过组织熔断放行 ALLOW
    dm_resp = await async_client.post(
        "/api/v1/system/org-spend-limit/pre-check",
        json={
            "org_id": org_id,
            "estimated_cost_usd": 1.0,
            "label": {
                "org_id": org_id,
                "surface": "DIRECT_MESSAGE",
                "billing_scope": "PERSONAL_DM",
                "session_id": "sess_dm_001",
                "requesting_user_id": "ident:alice",
                "query_tags": ["personal-research"],
            },
        },
    )
    assert dm_resp.status_code == 200
    dm_data = dm_resp.json()
    assert dm_data["action"] == "ALLOW"
    assert dm_data["is_blocked"] is False


@pytest.mark.asyncio
async def test_org_summary_and_user_attribution_api(
    async_client: httpx.AsyncClient,
) -> None:
    org_id = "org_api_attribution_test"

    # 配置 $100 预算
    await async_client.post(
        "/api/v1/system/org-spend-limit/configure",
        json={
            "org_id": org_id,
            "monthly_budget_usd": 100.0,
            "soft_warn_watermark_pct": 75.0,
            "hard_block_limit_usd": 100.0,
            "is_circuit_breaker_enabled": True,
        },
    )

    # 记录两条不同用户的消耗
    await async_client.post(
        "/api/v1/system/org-spend-limit/record-spend",
        json={
            "org_id": org_id,
            "actual_tokens": 50000,
            "actual_cost_usd": 20.0,
            "label": {
                "org_id": org_id,
                "surface": "CHANNEL",
                "billing_scope": "ORG_SHARED",
                "session_id": "s1",
                "requesting_user_id": "ident:lead_dev",
                "query_tags": ["refactor"],
            },
        },
    )

    await async_client.post(
        "/api/v1/system/org-spend-limit/record-spend",
        json={
            "org_id": org_id,
            "actual_tokens": 25000,
            "actual_cost_usd": 10.0,
            "label": {
                "org_id": org_id,
                "surface": "REST_API",
                "billing_scope": "ORG_SHARED",
                "session_id": "s2",
                "requesting_user_id": "ident:qa_bot",
                "query_tags": ["automated_e2e"],
            },
        },
    )

    # 1. 验证总结端点
    sum_resp = await async_client.get(f"/api/v1/system/org-spend-limit/summary/{org_id}")
    assert sum_resp.status_code == 200
    sum_data = sum_resp.json()
    assert sum_data["monthly_budget_usd"] == 100.0
    assert sum_data["current_spend_usd"] == 30.0
    assert sum_data["remaining_budget_usd"] == 70.0
    assert sum_data["utilization_pct"] == 30.0
    assert sum_data["total_records_count"] == 2

    # 2. 验证用户对账与归因排行端点
    attr_resp = await async_client.get(f"/api/v1/system/org-spend-limit/attributions/{org_id}")
    assert attr_resp.status_code == 200
    attr_data = attr_resp.json()
    assert len(attr_data) == 2
    # 按支出排序，第一名应该是 lead_dev
    assert attr_data[0]["requesting_user_id"] == "ident:lead_dev"
    assert attr_data[0]["total_spend_usd"] == 20.0
    assert attr_data[0]["primary_surface"] == "CHANNEL"
    # 第二名应该是 qa_bot
    assert attr_data[1]["requesting_user_id"] == "ident:qa_bot"
    assert attr_data[1]["total_spend_usd"] == 10.0
    assert attr_data[1]["primary_surface"] == "REST_API"
