"""
[INPUT]:
- httpx, ASGITransport
- app.api.system.cross_period_milestone_api::router

[OUTPUT]:
- Pytest verification for multi-agent cross-period pivot reports, gamified competency milestones, and team adoption leaderboard REST endpoints.

[POS]:
tests/api/system/test_cross_period_milestone_api.py — 多智能体跨周期透视报表与游戏化进阶里程碑 API 单元测试。
"""

from collections.abc import AsyncGenerator
from fastapi import FastAPI
import httpx
from httpx import ASGITransport
import pytest

from app.api.system.cross_period_milestone_api import router as cpm_router

test_app = FastAPI()
test_app.include_router(cpm_router, prefix="/api/v1/system")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_cross_period_milestone_api_flow(async_client: httpx.AsyncClient) -> None:
    # 1. Reset state
    reset_resp = await async_client.post("/api/v1/system/cross-period-milestone/reset")
    assert reset_resp.status_code == 200
    assert reset_resp.json() == {"status": "reset"}

    # 2. Ingest first activity
    act1_resp = await async_client.post(
        "/api/v1/system/cross-period-milestone/activity",
        json={
            "user_id": "emp_001",
            "user_name": "Devin Chen",
            "agent_id": "coding_agent",
            "agent_name": "Coding Specialist",
            "tokens_in": 5000,
            "tokens_out": 2500,
            "cost_usd": 0.045,
            "latency_ms": 1100.0,
            "success": True,
            "task_category": "code_review",
            "timestamp_iso": "2026-10-12T09:00:00Z",
        },
    )
    assert act1_resp.status_code == 200
    assert act1_resp.json()["status"] == "recorded"

    # 3. Ingest second activity for a different agent and user
    act2_resp = await async_client.post(
        "/api/v1/system/cross-period-milestone/activity",
        json={
            "user_id": "emp_002",
            "user_name": "Sarah Lin",
            "agent_id": "workbuddy",
            "agent_name": "WorkBuddy Prime",
            "tokens_in": 12000,
            "tokens_out": 4000,
            "cost_usd": 0.088,
            "latency_ms": 1400.0,
            "success": True,
            "task_category": "research",
            "timestamp_iso": "2026-10-12T10:00:00Z",
        },
    )
    assert act2_resp.status_code == 200

    # 4. Fetch cross-period pivot report
    report_resp = await async_client.get(
        "/api/v1/system/cross-period-milestone/pivot-report",
        params={"period_type": "weekly"},
    )
    assert report_resp.status_code == 200
    report_data = report_resp.json()
    assert "current_period" in report_data
    assert report_data["current_period"]["total_tokens"] > 0
    assert len(report_data["current_period"]["agent_breakdowns"]) >= 1

    # 5. Fetch user gamification profile
    gamify_resp = await async_client.get("/api/v1/system/cross-period-milestone/gamification/emp_001")
    assert gamify_resp.status_code == 200
    profile_data = gamify_resp.json()
    assert profile_data["user_id"] == "emp_001"
    assert profile_data["user_name"] == "Devin Chen"
    assert profile_data["total_xp"] > 0
    assert len(profile_data["daily_tasks"]) >= 3
    assert len(profile_data["badges"]) >= 4

    # 6. Claim a daily task manually
    claim_resp = await async_client.post(
        "/api/v1/system/cross-period-milestone/claim-task",
        json={"user_id": "emp_001", "task_id": "task_research_summary"},
    )
    assert claim_resp.status_code == 200
    claimed_profile = claim_resp.json()
    task = next((t for t in claimed_profile["daily_tasks"] if t["id"] == "task_research_summary"), None)
    assert task is not None
    assert task["is_completed"] is True

    # 7. Check team rankings
    rank_resp = await async_client.get("/api/v1/system/cross-period-milestone/team-rankings")
    assert rank_resp.status_code == 200
    rank_data = rank_resp.json()
    assert rank_data["total_active_members"] >= 2
    assert len(rank_data["leaderboard"]) >= 2
    assert len(rank_data["top_task_categories"]) >= 1
