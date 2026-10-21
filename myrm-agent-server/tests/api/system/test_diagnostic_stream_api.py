"""
[INPUT]:
- httpx, ASGITransport
- app.api.system.diagnostic_stream_api::router

[OUTPUT]:
- Pytest test cases for diagnostic event emission, filtering by session/severity, and aggregate stats.

[POS]:
tests/api/system/test_diagnostic_stream_api.py — 诊断事件双轨流解耦 API 单元测试。
"""

from collections.abc import AsyncGenerator

from fastapi import FastAPI
import httpx
from httpx import ASGITransport
import pytest

from app.api.system.diagnostic_stream_api import router as diagnostic_stream_router

test_app = FastAPI()
test_app.include_router(diagnostic_stream_router, prefix="/api/v1/system")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_emit_and_retrieve_diagnostic_events_api(
    async_client: httpx.AsyncClient,
) -> None:
    session_id = "sess_api_diag_001"
    run_id = "run_api_diag_101"

    # 1. 派发重试告警诊断事件
    resp_retry = await async_client.post(
        "/api/v1/system/diagnostic-stream/emit",
        json={
            "session_id": session_id,
            "run_id": run_id,
            "category": "RETRY",
            "severity": "WARNING",
            "code": "DIAG_RETRY_BACKOFF",
            "message": "LLM 429 速率限制触发第 2 次重试，退避 1500ms",
            "details": {"attempt": "2", "delay_ms": "1500"},
        },
    )
    assert resp_retry.status_code == 200
    retry_data = resp_retry.json()
    assert retry_data["session_id"] == session_id
    assert retry_data["category"] == "RETRY"
    assert retry_data["severity"] == "WARNING"
    assert retry_data["code"] == "DIAG_RETRY_BACKOFF"
    assert retry_data["details"]["attempt"] == "2"

    # 2. 派发上下文滑窗截断诊断事件
    resp_trunc = await async_client.post(
        "/api/v1/system/diagnostic-stream/emit",
        json={
            "session_id": session_id,
            "run_id": run_id,
            "category": "CONTEXT_TRUNCATION",
            "severity": "INFO",
            "code": "DIAG_CTX_TRUNCATE",
            "message": "上下文接近上限，滑窗剔除历史 8 轮",
            "details": {"evicted_turns": "8"},
        },
    )
    assert resp_trunc.status_code == 200
    assert resp_trunc.json()["category"] == "CONTEXT_TRUNCATION"

    # 3. 派发沙箱高压诊断事件
    resp_press = await async_client.post(
        "/api/v1/system/diagnostic-stream/emit",
        json={
            "session_id": "sess_api_diag_002",
            "run_id": "run_api_diag_102",
            "category": "SANDBOX_PRESSURE",
            "severity": "CRITICAL",
            "code": "DIAG_SANDBOX_OOM",
            "message": "沙箱内存占用突破 92% 告警阈值",
            "details": {"mem_usage": "92.4%"},
        },
    )
    assert resp_press.status_code == 200
    assert resp_press.json()["severity"] == "CRITICAL"

    # 4. 按 session_id 过滤检索
    sess_query = await async_client.get(
        f"/api/v1/system/diagnostic-stream/events?session_id={session_id}"
    )
    assert sess_query.status_code == 200
    sess_events = sess_query.json()
    assert len(sess_events) >= 2
    assert all(e["session_id"] == session_id for e in sess_events)

    # 5. 按 severity=CRITICAL 过滤检索
    crit_query = await async_client.get(
        "/api/v1/system/diagnostic-stream/events?severity=CRITICAL"
    )
    assert crit_query.status_code == 200
    crit_events = crit_query.json()
    assert len(crit_events) >= 1
    assert any(e["code"] == "DIAG_SANDBOX_OOM" for e in crit_events)

    # 6. 获取全局统计
    stats_resp = await async_client.get("/api/v1/system/diagnostic-stream/stats")
    assert stats_resp.status_code == 200
    stats = stats_resp.json()
    assert stats["total_events"] >= 3
    assert stats["by_severity"]["WARNING"] >= 1
    assert stats["by_severity"]["CRITICAL"] >= 1
    assert stats["by_category"]["RETRY"] >= 1
    assert stats["by_category"]["SANDBOX_PRESSURE"] >= 1
