"""
[INPUT]:
- httpx, ASGITransport
- app.api.system.deployment_funnel_api::router

[OUTPUT]:
- Pytest test cases verifying funnel event recording, feedback tracking, snapshot analytics, and autonomous goal dispatch endpoints.

[POS]:
tests/api/system/test_deployment_funnel_api.py — 交付物部署漏斗监测与反馈推动闭环 API 单元测试。
"""

from collections.abc import AsyncGenerator

from fastapi import FastAPI
import httpx
from httpx import ASGITransport
import pytest

from app.api.system.deployment_funnel_api import router as deployment_funnel_router

test_app = FastAPI()
test_app.include_router(deployment_funnel_router, prefix="/api/v1/system")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_funnel_event_and_snapshot_lifecycle(async_client: httpx.AsyncClient) -> None:
    dep_id = "dep_test_suite_01"

    # 1. 模拟用户进入漏斗各阶段
    # VIEW: user1, user2, user3, user4, user5 (5人)
    for u in ["user1", "user2", "user3", "user4", "user5"]:
        resp = await async_client.post(
            "/api/v1/system/deployment-funnel/event",
            json={
                "deployment_id": dep_id,
                "stage": "STAGE_1_VIEW",
                "user_ident": u,
                "metadata": {"source": "github_readme"},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["deployment_id"] == dep_id
        assert data["stage"] == "STAGE_1_VIEW"
        assert data["user_ident"] == u

    # ENGAGE: user1, user2, user3 (3人) - 流失 40%
    for u in ["user1", "user2", "user3"]:
        await async_client.post(
            "/api/v1/system/deployment-funnel/event",
            json={"deployment_id": dep_id, "stage": "STAGE_2_ENGAGE", "user_ident": u},
        )

    # ACTION: user1, user2 (2人)
    for u in ["user1", "user2"]:
        await async_client.post(
            "/api/v1/system/deployment-funnel/event",
            json={"deployment_id": dep_id, "stage": "STAGE_3_ACTION", "user_ident": u},
        )

    # COMPLETE: user1 (1人)
    await async_client.post(
        "/api/v1/system/deployment-funnel/event",
        json={"deployment_id": dep_id, "stage": "STAGE_4_COMPLETE", "user_ident": "user1"},
    )

    # 2. 查询 Snapshot
    snap_resp = await async_client.get(f"/api/v1/system/deployment-funnel/snapshot/{dep_id}")
    assert snap_resp.status_code == 200
    snap_data = snap_resp.json()

    assert snap_data["deployment_id"] == dep_id
    assert snap_data["total_visitors"] == 5
    assert len(snap_data["stages"]) == 4

    stage_map = {s["stage"]: s for s in snap_data["stages"]}
    assert stage_map["STAGE_1_VIEW"]["user_count"] == 5
    assert stage_map["STAGE_1_VIEW"]["conversion_rate_pct"] == 100.0

    assert stage_map["STAGE_2_ENGAGE"]["user_count"] == 3
    assert stage_map["STAGE_2_ENGAGE"]["conversion_rate_pct"] == 60.0
    assert stage_map["STAGE_2_ENGAGE"]["dropoff_rate_pct"] == 40.0

    assert stage_map["STAGE_3_ACTION"]["user_count"] == 2
    assert stage_map["STAGE_4_COMPLETE"]["user_count"] == 1

    # 判定热点断点及推动
    assert snap_data["dropoff_hotspot_stage"] in ["STAGE_2_ENGAGE", "STAGE_4_COMPLETE"]
    assert snap_data["nudge_required"] is True
    assert snap_data["nudge_reason"] is not None
    assert snap_data["autonomous_goal_recommendation"] is not None


@pytest.mark.asyncio
async def test_feedback_and_goal_dispatch_api(async_client: httpx.AsyncClient) -> None:
    dep_id = "dep_test_suite_02"

    # 上报初始访问
    await async_client.post(
        "/api/v1/system/deployment-funnel/event",
        json={"deployment_id": dep_id, "stage": "STAGE_1_VIEW", "user_ident": "tester_a"},
    )

    # 上报负面反馈
    fb_resp = await async_client.post(
        "/api/v1/system/deployment-funnel/feedback",
        json={
            "deployment_id": dep_id,
            "sentiment": "NEGATIVE",
            "comment": "Onboarding documentation is confusing and missing quickstart.",
        },
    )
    assert fb_resp.status_code == 200
    fb_data = fb_resp.json()
    assert fb_data["sentiment"] == "NEGATIVE"
    assert fb_data["deployment_id"] == dep_id

    # 查询 Snapshot，确认负面反馈触发 nudge_required
    snap_resp = await async_client.get(f"/api/v1/system/deployment-funnel/snapshot/{dep_id}")
    assert snap_resp.status_code == 200
    snap = snap_resp.json()
    assert snap["feedback_counts"]["NEGATIVE"] == 1
    assert snap["nudge_required"] is True
    assert "负面用户反馈" in (snap["nudge_reason"] or "")

    # 测试一键派发优化目标
    goal_resp = await async_client.post(
        "/api/v1/system/deployment-funnel/dispatch-goal",
        json={
            "deployment_id": dep_id,
            "goal": snap["autonomous_goal_recommendation"],
            "target_agent_id": "agent_autonomous_optimizer",
        },
    )
    assert goal_resp.status_code == 200
    goal_data = goal_resp.json()
    assert goal_data["status"] == "dispatched"
    assert goal_data["deployment_id"] == dep_id
    assert goal_data["target_agent_id"] == "agent_autonomous_optimizer"
