"""
[INPUT]:
- httpx, ASGITransport
- app.api.system.knowledge_compounding_api::router

[OUTPUT]:
- Pytest test cases verifying knowledge compounding scoreboard and evaluate API endpoints.

[POS]:
tests/api/system/test_knowledge_compounding_api.py — 知识复利健康度记分板与五大指标闭环 API 单元测试。
"""

from collections.abc import AsyncGenerator

from fastapi import FastAPI
import httpx
from httpx import ASGITransport
import pytest

from app.api.system.knowledge_compounding_api import router as knowledge_compounding_router

test_app = FastAPI()
test_app.include_router(knowledge_compounding_router, prefix="/api/v1/system")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_get_compounding_scoreboard_default_endpoint(
    async_client: httpx.AsyncClient,
) -> None:
    resp = await async_client.get("/api/v1/system/knowledge-compounding/scoreboard?window_days=30")
    assert resp.status_code == 200
    data = resp.json()

    assert "overall_score" in data
    assert "compounding_tier" in data
    assert "metrics" in data
    assert data["window_days"] == 30

    metrics = data["metrics"]
    assert len(metrics) == 5
    assert "repeated_error_rate" in metrics
    assert "knowledge_hit_rate" in metrics
    assert "human_corrections_count" in metrics
    assert "first_pass_success_rate" in metrics
    assert "stale_knowledge_ratio" in metrics

    # 验证单项指标字段契约
    hit_metric = metrics["knowledge_hit_rate"]
    assert hit_metric["unit"] == "%"
    assert hit_metric["benchmark_threshold"] == 60.0
    assert "data_source_origin" in hit_metric


@pytest.mark.asyncio
async def test_evaluate_compounding_health_healthy_growth(
    async_client: httpx.AsyncClient,
) -> None:
    payload = {
        "repeated_error_rate_pct": 1.5,
        "knowledge_hit_rate_pct": 75.0,
        "human_corrections_count": 2,
        "first_pass_success_rate_pct": 92.0,
        "stale_knowledge_ratio_pct": 5.0,
        "window_days": 14,
    }

    resp = await async_client.post("/api/v1/system/knowledge-compounding/evaluate", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["overall_score"] >= 85.0
    assert data["compounding_tier"] == "HIGHLY_COMPOUNDING"
    assert data["window_days"] == 14
    assert len(data["regression_alerts"]) == 0

    metrics = data["metrics"]
    assert metrics["repeated_error_rate"]["status"] == "HEALTHY"
    assert metrics["first_pass_success_rate"]["status"] == "HEALTHY"


@pytest.mark.asyncio
async def test_evaluate_compounding_health_regressing_and_alerts(
    async_client: httpx.AsyncClient,
) -> None:
    payload = {
        "repeated_error_rate_pct": 20.0,
        "knowledge_hit_rate_pct": 18.0,
        "human_corrections_count": 25,
        "first_pass_success_rate_pct": 45.0,
        "stale_knowledge_ratio_pct": 40.0,
        "window_days": 7,
    }

    resp = await async_client.post("/api/v1/system/knowledge-compounding/evaluate", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["overall_score"] < 50.0
    assert data["compounding_tier"] == "REGRESSING"
    assert data["window_days"] == 7
    assert len(data["regression_alerts"]) == 5

    alerts_str = " ".join(data["regression_alerts"])
    assert "重复错误率偏高" in alerts_str
    assert "跨会话知识命中率偏低" in alerts_str
    assert "人工纠正与打回重做频次过高" in alerts_str
    assert "任务一次通过率低于基线" in alerts_str
    assert "过期与被忽视知识占比达到" in alerts_str
