"""
[INPUT]
- collections.abc (Generator)
- pytest
- fastapi (FastAPI)
- starlette.testclient (TestClient)
- app.api.agents.ralph_workflow_router (router, get_ralph_workflow_service)
- app.services.agent.ralph_workflow_service (RalphWorkflowService)
- myrm_agent_harness.agent.sub_agents.ralph_loop (RalphFreshAgentLoopCoordinator)

[OUTPUT]
- test_create_and_get_ralph_session_api: 测试创建会话与状态查询
- test_advance_round_and_min_three_round_downgrade_api: 测试轮次交接与满三轮阻断防御降级
- test_advance_round_completion_api: 测试任务达成全局状态流转为 completed
- test_session_not_found_guard_api: 测试未找到会话 404 守卫

[POS]
Server 业务层 Ralph 式 Fresh-Agent 多轮循环 REST API 自动化测试套件（Topic 12 · 第 15 项）。
通过纯净隔离的 TestClient 验证会话初始化、轮次交接推进、Min-3-Round 阻断拦截与异常边界。
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from myrm_agent_harness.agent.sub_agents.ralph_loop import (
    RalphFreshAgentLoopCoordinator,
)
from starlette.testclient import TestClient

from app.api.agents.ralph_workflow_router import (
    get_ralph_workflow_service,
)
from app.api.agents.ralph_workflow_router import (
    router as ralph_workflow_router,
)
from app.services.agent.ralph_workflow_service import RalphWorkflowService


@pytest.fixture
def ralph_client() -> Generator[TestClient, None, None]:
    """提供隔离的 TestClient fixture 挂载 ralph_workflow_router。"""
    coordinator = RalphFreshAgentLoopCoordinator()
    service = RalphWorkflowService(coordinator=coordinator)

    test_app = FastAPI()
    test_app.include_router(ralph_workflow_router, prefix="/api/agents")
    test_app.dependency_overrides[get_ralph_workflow_service] = lambda: service

    with TestClient(test_app) as client:
        yield client


def test_create_and_get_ralph_session_api(ralph_client: TestClient) -> None:
    """测试创建 Ralph 循环会话与详情获取。"""
    create_payload = {
        "human_goal": "Migrate Redis pubsub to durable NATS streams",
        "workspace_root": "/sandbox/projects/messaging",
        "max_rounds": 6,
        "min_rounds_before_blocked": 3,
    }
    res = ralph_client.post("/api/agents/ralph-loop/sessions", json=create_payload)
    assert res.status_code == 201
    data = res.json()

    assert data["human_goal"] == "Migrate Redis pubsub to durable NATS streams"
    assert data["current_round"] == 1
    assert data["max_rounds"] == 6
    assert data["min_rounds_before_blocked"] == 3
    assert data["status"] == "in_progress"
    assert len(data["rounds"]) == 0
    assert data["next_directive"] is not None
    assert "Migrate Redis pubsub to durable NATS streams" in data["next_directive"]
    assert "Context Status: FRESH" in data["next_directive"]

    session_id = data["session_id"]

    # GET 查询
    get_res = ralph_client.get(f"/api/agents/ralph-loop/sessions/{session_id}")
    assert get_res.status_code == 200
    get_data = get_res.json()
    assert get_data["session_id"] == session_id


def test_advance_round_and_min_three_round_downgrade_api(ralph_client: TestClient) -> None:
    """测试在未满 3 轮时声称 blocked 触发防御降级。"""
    # 1. 创建
    c_res = ralph_client.post(
        "/api/agents/ralph-loop/sessions",
        json={"human_goal": "Refactor parser", "min_rounds_before_blocked": 3},
    )
    session_id = c_res.json()["session_id"]

    # 2. 第 1 轮声称 blocked
    advance_payload = {
        "child_session_id": "child-w1",
        "handoff": {
            "status": "blocked",
            "summary": "AST tree node type unknown",
            "evidence": "parser/ast.py:102",
            "next_steps": "Need spec definition",
            "blocker": "Unknown syntax token @",
        },
        "duration_seconds": 15.2,
        "tokens_consumed": 3800,
    }
    adv_res = ralph_client.post(
        f"/api/agents/ralph-loop/sessions/{session_id}/advance-round",
        json=advance_payload,
    )
    assert adv_res.status_code == 200
    adv_data = adv_res.json()

    # 验证防早衰拦截
    assert adv_data["status"] == "in_progress"
    assert adv_data["current_round"] == 2
    assert len(adv_data["rounds"]) == 1

    r1_record = adv_data["rounds"][0]
    assert r1_record["was_blocked_downgraded"] is True
    assert r1_record["handoff"]["status"] == "in_progress"
    assert "[Ralph Guardrail]" in r1_record["handoff"]["next_steps"]


def test_advance_round_completion_api(ralph_client: TestClient) -> None:
    """测试任务顺利完成时流转为 completed。"""
    c_res = ralph_client.post(
        "/api/agents/ralph-loop/sessions",
        json={"human_goal": "Optimize query index"},
    )
    session_id = c_res.json()["session_id"]

    adv_payload = {
        "child_session_id": "child-w2",
        "handoff": {
            "status": "completed",
            "summary": "Added composite index on (tenant_id, created_at)",
            "evidence": "EXPLAIN ANALYZE: scan time from 850ms to 4ms",
            "next_steps": "Deploy migration",
            "blocker": "",
        },
        "duration_seconds": 8.0,
        "tokens_consumed": 2100,
    }
    adv_res = ralph_client.post(
        f"/api/agents/ralph-loop/sessions/{session_id}/advance-round",
        json=adv_payload,
    )
    assert adv_res.status_code == 200
    adv_data = adv_res.json()

    assert adv_data["status"] == "completed"
    assert len(adv_data["rounds"]) == 1
    assert adv_data["rounds"][0]["handoff"]["status"] == "completed"
    assert adv_data["next_directive"] is None


def test_session_not_found_guard_api(ralph_client: TestClient) -> None:
    """测试 404 守卫。"""
    res = ralph_client.get("/api/agents/ralph-loop/sessions/non-existent-id")
    assert res.status_code == 404
