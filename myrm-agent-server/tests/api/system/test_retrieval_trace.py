"""[INPUT]
- httpx, ASGITransport
- app.api.system.retrieval_trace_api::router

[OUTPUT]
- Pytest test cases verifying context retrieval decision tree trace retrieval and OpenViking-style simulation.

[POS]
tests/api/system/test_retrieval_trace.py — 上下文检索决策树与剪枝留痕 API 单元测试。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport

from app.api.system.retrieval_trace_api import router as retrieval_trace_router

test_app = FastAPI()
test_app.include_router(retrieval_trace_router, prefix="/api/v1/system")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_get_retrieval_trace_by_id(async_client: httpx.AsyncClient) -> None:
    trace_id = "trace-req-test-999"
    resp = await async_client.get(f"/api/v1/system/retrieval-traces/{trace_id}")
    assert resp.status_code == 200
    data = resp.json()

    assert data["trace_id"] == trace_id
    assert "query" in data
    assert len(data["root_nodes"]) >= 1
    assert data["total_nodes_visited"] >= 1
    assert data["hits_count"] >= 1
    assert data["pruned_nodes_count"] >= 1


@pytest.mark.asyncio
async def test_simulate_retrieval_trace_success(async_client: httpx.AsyncClient) -> None:
    payload = {
        "query": "OpenViking 分层记忆检索与决策树可视化",
        "pruning_threshold": 0.80,
        "top_k": 2,
    }
    resp = await async_client.post("/api/v1/system/retrieval-traces/simulate", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["query"] == payload["query"]
    assert data["hits_count"] <= 2
    assert data["pruned_nodes_count"] >= 1
    assert data["total_nodes_visited"] >= 4

    # 验证根节点结构与剪枝标记
    root_nodes = data["root_nodes"]
    assert len(root_nodes) == 2
    # 查找被剪枝的根节点
    pruned_root = next((n for n in root_nodes if n["is_pruned"]), None)
    assert pruned_root is not None
    assert pruned_root["pruning_reason"] == "score_below_threshold"
    assert "低于阈值" in pruned_root["reason_detail"]


@pytest.mark.asyncio
async def test_simulate_retrieval_trace_validation_error(async_client: httpx.AsyncClient) -> None:
    # 阈值超出合法区间 [0.0, 1.0]
    payload = {
        "query": "test query",
        "pruning_threshold": 1.5,
        "top_k": 3,
    }
    resp = await async_client.post("/api/v1/system/retrieval-traces/simulate", json=payload)
    assert resp.status_code == 422
