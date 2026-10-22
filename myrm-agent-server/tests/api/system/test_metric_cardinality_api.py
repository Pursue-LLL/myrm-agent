"""
[INPUT]:
- httpx, ASGITransport
- app.api.system.metric_cardinality_api::router

[OUTPUT]:
- Pytest verification for metric cardinality cap guardrails, URL parameter normalization, and overflow diversion REST endpoints.

[POS]:
tests/api/system/test_metric_cardinality_api.py — 热点路径指标基数封顶与溢出桶治理 API 单元测试。
"""

from collections.abc import AsyncGenerator
from fastapi import FastAPI
import httpx
from httpx import ASGITransport
import pytest

from app.api.system.metric_cardinality_api import router as mc_router

test_app = FastAPI()
test_app.include_router(mc_router, prefix="/api/v1/system")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_metric_cardinality_api_lifecycle(async_client: httpx.AsyncClient) -> None:
    # 1. Reset governor
    reset_resp = await async_client.post("/api/v1/system/metric-cardinality/reset")
    assert reset_resp.status_code == 200
    assert reset_resp.json() == {"status": "reset"}

    metric_name = "http_requests_total"

    # 2. Configure a low cap limit of 3 for testing
    cfg_resp = await async_client.post(
        "/api/v1/system/metric-cardinality/configure",
        json={"metric_name": metric_name, "cap_limit": 3},
    )
    assert cfg_resp.status_code == 200
    assert cfg_resp.json()["cap_limit"] == "3"

    # 3. Sample 1: Dynamic session UUID path should normalize to /session/{id}
    s1_resp = await async_client.post(
        "/api/v1/system/metric-cardinality/sample",
        json={
            "metric_name": metric_name,
            "label_value": "/api/v1/session/550e8400-e29b-41d4-a716-446655440000",
        },
    )
    assert s1_resp.status_code == 200
    s1_data = s1_resp.json()
    assert s1_data["resolved_label"] == "/api/v1/session/{id}"
    assert s1_data["is_overflow"] is False

    # 4. Sample 2 & 3: Within capacity of 3
    s2_resp = await async_client.post(
        "/api/v1/system/metric-cardinality/sample",
        json={"metric_name": metric_name, "label_value": "/api/v1/tools/web_search"},
    )
    assert s2_resp.status_code == 200
    assert s2_resp.json()["is_overflow"] is False

    s3_resp = await async_client.post(
        "/api/v1/system/metric-cardinality/sample",
        json={"metric_name": metric_name, "label_value": "/api/v1/chat/completions"},
    )
    assert s3_resp.status_code == 200
    assert s3_resp.json()["is_overflow"] is False

    # 5. Sample 4: 4th distinct label exceeds cap of 3 -> must overflow
    s4_resp = await async_client.post(
        "/api/v1/system/metric-cardinality/sample",
        json={"metric_name": metric_name, "label_value": "/api/v1/unseen_rogue_path"},
    )
    assert s4_resp.status_code == 200
    s4_data = s4_resp.json()
    assert s4_data["resolved_label"] == "_overflow_"
    assert s4_data["is_overflow"] is True

    # 6. Retrieve stats
    stats_resp = await async_client.get("/api/v1/system/metric-cardinality/stats")
    assert stats_resp.status_code == 200
    stats_list = stats_resp.json()
    assert len(stats_list) >= 1
    target_stat = next((s for s in stats_list if s["metric_name"] == metric_name), None)
    assert target_stat is not None
    assert target_stat["cap_limit"] == 3
    assert target_stat["tracked_cardinality"] == 3
    assert target_stat["overflow_count"] == 1
    assert target_stat["status"] == "overflowing"
    assert "_overflow_" in target_stat["top_tracked_labels"]
