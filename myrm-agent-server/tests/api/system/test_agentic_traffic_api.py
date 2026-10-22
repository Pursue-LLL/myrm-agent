"""
[INPUT]:
- httpx, ASGITransport
- app.api.system.agentic_traffic_api::router

[OUTPUT]:
- Pytest test cases verifying agent traffic classification, AEO page diagnostics, and funnel conversion APIs.

[POS]:
tests/api/system/test_agentic_traffic_api.py — AI Agent 流量精准解构、跳出归因与静默审判 API 单元测试。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import FastAPI
import httpx
from httpx import ASGITransport
import pytest

from app.api.system.agentic_traffic_api import router as agentic_traffic_router

test_app = FastAPI()
test_app.include_router(agentic_traffic_router, prefix="/api/v1/system")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_record_visit_and_get_analytics(async_client: httpx.AsyncClient) -> None:
    # 1. 记录 Cursor Agent 访问
    payload_cursor = {
        "visit_id": "v-cursor-01",
        "user_agent": "Cursor/0.45.2 (Macintosh; Intel Mac OS X 10_15_7)",
        "target_path": "/docs/sdk-quickstart",
        "duration_ms": 420.0,
        "status_code": 200,
        "page_content": "# Quickstart\n```python\nimport myrm\n```\nllms.txt declared.",
        "has_llms_txt_declared": True,
    }
    resp1 = await async_client.post(
        "/api/v1/system/agentic-traffic/record-visit", json=payload_cursor
    )
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["is_agent"] is True
    assert data1["agent_type"] == "CURSOR"
    assert data1["funnel_stage"] == "CONTEXT_ABSORBED"

    # 2. 记录人类浏览器访问
    payload_human = {
        "visit_id": "v-human-01",
        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/128.0",
        "target_path": "/home",
        "headers": {"Sec-CH-UA": '"Chromium";v="128"'},
        "duration_ms": 3500.0,
    }
    resp2 = await async_client.post(
        "/api/v1/system/agentic-traffic/record-visit", json=payload_human
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["is_agent"] is False
    assert data2["agent_type"] == "HUMAN_BROWSER"

    # 3. 查询聚合流量大盘
    analytics_resp = await async_client.get(
        "/api/v1/system/agentic-traffic/analytics"
    )
    assert analytics_resp.status_code == 200
    summary = analytics_resp.json()
    assert summary["total_visits"] >= 2
    assert summary["agent_visits_count"] >= 1
    assert "CURSOR" in summary["top_agents"]
    assert "DISCOVERED" in summary["funnel_conversion"]
    assert len(summary["recent_visits"]) >= 2


@pytest.mark.asyncio
async def test_diagnose_page_aeo_endpoint(async_client: httpx.AsyncClient) -> None:
    # 诊断一个有缺陷的页面（前 500 Token 无代码，缺失 llms.txt）
    vague_content = "This is a wordy description without any runnable code snippets." * 50
    req_payload = {
        "path": "/docs/vague-guide",
        "content": vague_content,
        "has_llms_txt_declared": False,
    }
    resp = await async_client.post(
        "/api/v1/system/agentic-traffic/diagnose-page", json=req_payload
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["path"] == "/docs/vague-guide"
    assert data["has_llms_txt_declared"] is False
    assert data["has_code_in_first_500_tokens"] is False
    assert data["aeo_score"] < 80
    assert "LLMS_TXT_MISSING" in data["abandonment_reasons"]
    assert "FIRST_500_TOKENS_VAGUE" in data["abandonment_reasons"]
    assert len(data["suggested_actions"]) >= 2
