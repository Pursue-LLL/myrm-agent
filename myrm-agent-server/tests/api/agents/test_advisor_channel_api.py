"""
[INPUT]
- collections.abc (Generator)
- pytest
- fastapi (FastAPI)
- starlette.testclient (TestClient)
- app.api.agents.advisor_channel_router (router, get_advisor_channel_service)
- app.services.agent.advisor_channel_service (AdvisorChannelService)
- myrm_agent_harness.agent.sub_agents.advisor_channel (DualModelAdvisorEngine)

[OUTPUT]
- test_review_step_benign_passed_api: 测试合规操作平稳放行
- test_review_step_dangerous_blocker_api: 测试高危破坏性操作触发 blocker 硬阻断
- test_review_step_concern_api: 测试敏感操作触发 concern 预警
- test_get_and_clear_session_reviews_api: 测试会话审查历史查询与清空重置

[POS]
Server 业务层双模型实时旁路军师评审通道 REST API 自动化测试套件（Topic 12 · 第 17 项）。
基于隔离 TestClient 验证单步动作审查、aside/concern/blocker 分级判定、历史干预追溯与清理。
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from myrm_agent_harness.agent.sub_agents.advisor_channel import (
    DualModelAdvisorEngine,
)
from starlette.testclient import TestClient

from app.api.agents.advisor_channel_router import (
    get_advisor_channel_service,
)
from app.api.agents.advisor_channel_router import (
    router as advisor_channel_router,
)
from app.services.agent.advisor_channel_service import AdvisorChannelService


@pytest.fixture
def advisor_client() -> Generator[TestClient, None, None]:
    """提供纯净隔离的 TestClient fixture 挂载 advisor_channel_router。"""
    engine = DualModelAdvisorEngine()
    service = AdvisorChannelService(engine=engine)

    test_app = FastAPI()
    test_app.include_router(advisor_channel_router, prefix="/api/agents")
    test_app.dependency_overrides[get_advisor_channel_service] = lambda: service

    with TestClient(test_app) as client:
        yield client


def test_review_step_benign_passed_api(advisor_client: TestClient) -> None:
    """测试常规合规操作平稳放行。"""
    payload = {
        "session_id": "sess-alpha-01",
        "task_goal": "Refactor React state management",
        "tool_name": "view_file",
        "tool_args": {"path": "src/App.tsx"},
        "turn_index": 1,
    }
    res = advisor_client.post("/api/agents/advisor-channel/review", json=payload)
    assert res.status_code == 200
    data = res.json()

    assert data["is_blocked"] is False
    assert data["highest_level"] is None
    assert len(data["interventions"]) == 0
    assert "平稳放行" in data["summary"]


def test_review_step_dangerous_blocker_api(advisor_client: TestClient) -> None:
    """测试高危操作触发 blocker 硬阻断熔断。"""
    payload = {
        "session_id": "sess-beta-02",
        "task_goal": "Clean project directory",
        "tool_name": "bash",
        "tool_args": {"command": "rm -rf / --no-preserve-root"},
        "turn_index": 2,
    }
    res = advisor_client.post("/api/agents/advisor-channel/review", json=payload)
    assert res.status_code == 200
    data = res.json()

    assert data["is_blocked"] is True
    assert data["highest_level"] == "blocker"
    assert len(data["interventions"]) == 1

    intv = data["interventions"][0]
    assert intv["level"] == "blocker"
    assert "高危破坏性指令" in intv["title"]
    assert "已触发硬性阻断" in intv["message"]
    assert intv["suggested_action"] is not None


def test_review_step_concern_api(advisor_client: TestClient) -> None:
    """测试敏感指令触发 concern 预警。"""
    payload = {
        "session_id": "sess-gamma-03",
        "task_goal": "Stop background worker",
        "tool_name": "bash",
        "tool_args": {"command": "kill -9 1234"},
        "turn_index": 3,
    }
    res = advisor_client.post("/api/agents/advisor-channel/review", json=payload)
    assert res.status_code == 200
    data = res.json()

    assert data["is_blocked"] is False
    assert data["highest_level"] == "concern"
    assert len(data["interventions"]) == 1
    assert data["interventions"][0]["level"] == "concern"


def test_get_and_clear_session_reviews_api(advisor_client: TestClient) -> None:
    """测试历史审查汇总查询与清理重置。"""
    sess = "sess-delta-04"

    # 1. 提交一次 blocker
    advisor_client.post(
        "/api/agents/advisor-channel/review",
        json={
            "session_id": sess,
            "task_goal": "Purge database",
            "tool_name": "sql_exec",
            "tool_args": {"query": "DROP TABLE users;"},
            "turn_index": 1,
        },
    )

    # 2. 提交一次 concern
    advisor_client.post(
        "/api/agents/advisor-channel/review",
        json={
            "session_id": sess,
            "task_goal": "Set API key",
            "tool_name": "bash",
            "tool_args": {"cmd": "export token=secret_value"},
            "turn_index": 2,
        },
    )

    # 3. 查询历史
    get_res = advisor_client.get(f"/api/agents/advisor-channel/sessions/{sess}")
    assert get_res.status_code == 200
    hist_data = get_res.json()

    assert hist_data["session_id"] == sess
    assert hist_data["total_reviews"] == 2
    assert hist_data["blocked_count"] == 1
    assert len(hist_data["interventions"]) == 2

    # 4. 清理
    del_res = advisor_client.delete(f"/api/agents/advisor-channel/sessions/{sess}")
    assert del_res.status_code == 204

    # 5. 验证清理后为空
    empty_res = advisor_client.get(f"/api/agents/advisor-channel/sessions/{sess}")
    assert empty_res.status_code == 200
    assert empty_res.json()["total_reviews"] == 0
    assert len(empty_res.json()["interventions"]) == 0
