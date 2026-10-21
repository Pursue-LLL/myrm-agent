"""
[INPUT]:
- httpx, ASGITransport
- app.api.system.local_sink_api::router

[OUTPUT]:
- Pytest verification for local disk sink configuration, span recording, recent spans retrieval, and status monitoring endpoints.

[POS]:
tests/api/system/test_local_sink_api.py — 本地盘可观测性落盘兜底 API 单元测试。
"""

from collections.abc import AsyncGenerator

from fastapi import FastAPI
import httpx
from httpx import ASGITransport
import pytest

from app.api.system.local_sink_api import router as local_sink_router

test_app = FastAPI()
test_app.include_router(local_sink_router, prefix="/api/v1/system")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_local_sink_lifecycle_and_spans_api(
    async_client: httpx.AsyncClient,
) -> None:
    # 1. 动态开启本地盘 Opt-In 兜底
    cfg_resp = await async_client.post(
        "/api/v1/system/local-sink/config",
        json={"enabled": True},
    )
    assert cfg_resp.status_code == 200
    cfg_data = cfg_resp.json()
    assert cfg_data["is_enabled"] is True

    # 2. 上报第 1 条测试 Span
    span1_resp = await async_client.post(
        "/api/v1/system/local-sink/record-span",
        json={
            "trace_id": "trace_api_001",
            "span_id": "span_api_001",
            "name": "agent_run:subagent_dispatch",
            "duration_ms": 320.5,
            "status": "OK",
            "attributes": {"subagent": "researcher"},
        },
    )
    assert span1_resp.status_code == 200
    s1_data = span1_resp.json()
    assert s1_data["trace_id"] == "trace_api_001"
    assert s1_data["name"] == "agent_run:subagent_dispatch"
    assert s1_data["duration_ms"] == 320.5

    # 3. 上报第 2 条测试 Span
    span2_resp = await async_client.post(
        "/api/v1/system/local-sink/record-span",
        json={
            "trace_id": "trace_api_001",
            "span_id": "span_api_002",
            "name": "tool_execute:bash",
            "duration_ms": 45.2,
            "status": "OK",
            "attributes": {"cmd": "git status"},
        },
    )
    assert span2_resp.status_code == 200

    # 4. 查询最近 Spans 列表
    spans_resp = await async_client.get("/api/v1/system/local-sink/spans?limit=10")
    assert spans_resp.status_code == 200
    spans_list = spans_resp.json()
    assert len(spans_list) >= 2
    assert any(s["span_id"] == "span_api_001" for s in spans_list)
    assert any(s["span_id"] == "span_api_002" for s in spans_list)

    # 5. 查询 Sink 整体运行状态
    status_resp = await async_client.get("/api/v1/system/local-sink/status")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["is_enabled"] is True
    assert status_data["buffered_spans_count"] >= 2
    assert "spans.jsonl" in status_data["sink_path"]
