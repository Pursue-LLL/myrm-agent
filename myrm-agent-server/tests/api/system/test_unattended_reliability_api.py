"""
[INPUT]:
- httpx, ASGITransport
- app.api.system.unattended_reliability_api::router

[OUTPUT]:
- Pytest verification for unattended reliability triad self-proof endpoints, run recording, and benchmark execution.

[POS]:
tests/api/system/test_unattended_reliability_api.py — 无人值守可靠性三联自证 API 单元测试。
"""

from collections.abc import AsyncGenerator

from fastapi import FastAPI
import httpx
from httpx import ASGITransport
import pytest

from app.api.system.unattended_reliability_api import router as reliability_router

test_app = FastAPI()
test_app.include_router(reliability_router, prefix="/api/v1/system")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_unattended_reliability_api_flow(async_client: httpx.AsyncClient) -> None:
    # 1. Reset evaluator
    reset_resp = await async_client.post("/api/v1/system/unattended-reliability/reset")
    assert reset_resp.status_code == 200
    assert reset_resp.json() == {"ok": True}

    # 2. Check initial clean score
    init_score = await async_client.get("/api/v1/system/unattended-reliability/score")
    assert init_score.status_code == 200
    score_data = init_score.json()
    assert score_data["total_evaluated_runs"] == 0
    assert score_data["composite_triad_score"] == 100.0
    assert score_data["hallucinated_success_count"] == 0
    assert score_data["duplicate_side_effect_count"] == 0
    assert score_data["failed_resume_count"] == 0

    # 3. Record normal run with restart recovery
    r1_resp = await async_client.post(
        "/api/v1/system/unattended-reliability/record",
        json={
            "task_name": "Autonomous code audit",
            "resume_status": "RESUMED_SUCCESS",
            "side_effect_status": "ZERO_DUPLICATE",
            "reporting_status": "GENUINE_SUCCESS",
            "detail": "Cleanly resumed from step 3 checkpoint",
        },
    )
    assert r1_resp.status_code == 200
    r1_data = r1_resp.json()
    assert r1_data["task_name"] == "Autonomous code audit"
    assert r1_data["resume_status"] == "RESUMED_SUCCESS"

    # 4. Record honest blocker run
    r2_resp = await async_client.post(
        "/api/v1/system/unattended-reliability/record",
        json={
            "task_name": "Production deploy gate",
            "resume_status": "NOT_APPLICABLE",
            "side_effect_status": "NO_SIDE_EFFECTS",
            "reporting_status": "HONEST_BLOCKER",
            "detail": "Truthfully reported missing prod secret approval",
        },
    )
    assert r2_resp.status_code == 200
    r2_data = r2_resp.json()
    assert r2_data["reporting_status"] == "HONEST_BLOCKER"

    # 5. Check updated scores
    mid_score = await async_client.get("/api/v1/system/unattended-reliability/score")
    assert mid_score.status_code == 200
    mid_data = mid_score.json()
    assert mid_data["total_evaluated_runs"] == 2
    assert mid_data["resume_rate_pct"] == 100.0
    assert mid_data["zero_duplicate_side_effect_rate_pct"] == 100.0
    assert mid_data["honest_blocker_rate_pct"] == 100.0
    assert mid_data["hallucinated_success_count"] == 0

    # 6. Execute self-proof benchmark scenarios
    bench_resp = await async_client.post("/api/v1/system/unattended-reliability/run-benchmark")
    assert bench_resp.status_code == 200
    bench_data = bench_resp.json()
    assert bench_data["total_evaluated_runs"] == 5  # 2 previous + 3 benchmark runs
    assert bench_data["composite_triad_score"] == 100.0
    assert len(bench_data["recent_records"]) == 5

    # 7. Record hallucinated success and verify penalty
    pen_resp = await async_client.post(
        "/api/v1/system/unattended-reliability/record",
        json={
            "task_name": "Flaky webhook call",
            "resume_status": "NOT_APPLICABLE",
            "side_effect_status": "ZERO_DUPLICATE",
            "reporting_status": "HALLUCINATED_SUCCESS",
            "detail": "Claimed webhook delivered but network dropped",
        },
    )
    assert pen_resp.status_code == 200

    pen_score = await async_client.get("/api/v1/system/unattended-reliability/score")
    assert pen_score.status_code == 200
    pen_data = pen_score.json()
    assert pen_data["hallucinated_success_count"] == 1
    assert pen_data["honest_blocker_rate_pct"] < 100.0
