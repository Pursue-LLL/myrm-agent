"""
[INPUT]:
- httpx, ASGITransport
- app.api.system.context_savings_api::router

[OUTPUT]:
- Pytest test cases verifying tool savings recording, session audit war report retrieval, 7-signal pattern scanning, and role-based engineering insights.

[POS]:
tests/api/system/test_context_savings_api.py — 上下文拦截节流审计器与工程信号七维决策 API 单元测试。
"""

from collections.abc import AsyncGenerator

from fastapi import FastAPI
import httpx
from httpx import ASGITransport
import pytest

from app.api.system.context_savings_api import router as context_savings_router

test_app = FastAPI()
test_app.include_router(context_savings_router, prefix="/api/v1/system")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_record_tool_savings_and_session_audit_flow(async_client: httpx.AsyncClient) -> None:
    session_id = "sess-savings-test-01"

    # 1. 登记 Playwright 网页抓取拦截节流
    payload_1 = {
        "session_id": session_id,
        "tool_name": "playwright_browser_scrape",
        "original_bytes": 200_000,  # ~50,000 tokens
        "optimized_bytes": 4_000,   # ~1,000 tokens
        "cache_hit": False,
    }
    resp1 = await async_client.post("/api/v1/system/context-savings/record-tool", json=payload_1)
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["tool_name"] == "playwright_browser_scrape"
    assert data1["saved_tokens"] == 49_000
    assert data1["savings_rate_pct"] == 98.0
    assert data1["cost_saved_usd"] > 0.1
    assert data1["cost_saved_cny"] > 0.8

    # 2. 登记 Bash 编译命令节流 (带缓存命中)
    payload_2 = {
        "session_id": session_id,
        "tool_name": "bash_build_run",
        "original_bytes": 40_000,
        "optimized_bytes": 2_000,
        "cache_hit": True,
    }
    resp2 = await async_client.post("/api/v1/system/context-savings/record-tool", json=payload_2)
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["cache_hit"] is True

    # 3. 查询单会话节流战报
    audit_resp = await async_client.get(f"/api/v1/system/context-savings/session/{session_id}")
    assert audit_resp.status_code == 200
    audit_data = audit_resp.json()
    assert audit_data["session_id"] == session_id
    assert audit_data["total_tool_calls"] == 2
    assert audit_data["total_saved_tokens"] > 55_000
    assert audit_data["overall_savings_rate_pct"] > 90.0
    assert len(audit_data["tool_breakdown"]) == 2
    assert "🎉 本次会话通过智能上下文拦截为您节省了" in audit_data["summary_headline"]


@pytest.mark.asyncio
async def test_analyze_session_signals_and_role_insights_api(async_client: httpx.AsyncClient) -> None:
    session_id = "sess-signals-test-02"

    # 先塞入一条大体积工具记录 (导致 TOOL_OUTPUT_BLOAT)
    payload_bloat = {
        "session_id": session_id,
        "tool_name": "sql_query_dump",
        "original_bytes": 100_000,  # 25,000 tokens
        "optimized_bytes": 2_000,
        "cache_hit": False,
    }
    await async_client.post("/api/v1/system/context-savings/record-tool", json=payload_bloat)

    # 1. 发起会话工程信号扫描 (带高频重试与长耗时指标)
    scan_payload = {
        "session_id": session_id,
        "tool_retry_counts": {"sql_query_dump": 4},
        "tool_latencies_ms": {"sql_query_dump": 7500.0},
    }
    scan_resp = await async_client.post("/api/v1/system/context-savings/analyze-session", json=scan_payload)
    assert scan_resp.status_code == 200
    signals = scan_resp.json()
    assert len(signals) >= 3

    patterns = {s["signal_pattern"] for s in signals}
    assert "TOOL_OUTPUT_BLOAT" in patterns
    assert "HIGH_RETRY_CHURN" in patterns
    assert "LONG_BLOCKING_IO" in patterns

    # 2. 查询 CTO 角色效能大盘
    cto_resp = await async_client.get("/api/v1/system/context-savings/engineering-insights?role=CTO")
    assert cto_resp.status_code == 200
    cto_data = cto_resp.json()
    assert cto_data["role"] == "CTO"
    assert cto_data["total_saved_tokens_aggregate"] > 0
    assert "CTO 视窗" in cto_data["primary_bottleneck_summary"]

    # 3. 查询 FinOps 角色效能大盘
    finops_resp = await async_client.get("/api/v1/system/context-savings/engineering-insights?role=FINOPS")
    assert finops_resp.status_code == 200
    finops_data = finops_resp.json()
    assert finops_data["role"] == "FINOPS"
    assert finops_data["total_cost_saved_usd_aggregate"] > 0
