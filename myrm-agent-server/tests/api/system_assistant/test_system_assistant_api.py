"""
[INPUT]
- FastAPI test client
- System assistant router under /api/v1/system-assistant

[OUTPUT]
- Unit test suite verifying XiaoMo system assistant natural language intent dispatch, execution, and telemetry

[POS]
Unit tests for XiaoMo Unified Natural Language Control Center API.
"""

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.system_assistant.routes import router as system_assistant_router


@pytest.fixture
def assistant_client() -> TestClient:
    app = FastAPI()
    app.include_router(system_assistant_router, prefix="/api/v1/system-assistant")
    return TestClient(app)


def test_execute_command_create_project(assistant_client: TestClient):
    payload = {
        "user_prompt": "帮我新建一个 前端重构 项目并绑定沙箱",
    }
    response = assistant_client.post("/api/v1/system-assistant/command", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["command_id"].startswith("cmd-")
    assert data["intent"] == "create_project"
    assert "前端重构" in data["summary"] or "项目" in data["summary"]
    assert data["action"]["action_type"] == "project_created"
    assert data["action"]["status"] == "success"
    assert "project_id" in data["action"]["details"]
    assert len(data["suggested_followups"]) >= 1


def test_execute_command_query_tasks(assistant_client: TestClient):
    payload = {
        "user_prompt": "汇总查一下当前所有进行中的任务进度",
    }
    response = assistant_client.post("/api/v1/system-assistant/command", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["intent"] == "query_tasks"
    assert data["action"]["action_type"] == "tasks_queried"
    assert "running_count" in data["action"]["details"]


def test_execute_command_terminate_tasks(assistant_client: TestClient):
    payload = {
        "user_prompt": "终止所有后台任务并释放资源",
    }
    response = assistant_client.post("/api/v1/system-assistant/command", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["intent"] == "terminate_tasks"
    assert data["action"]["action_type"] == "tasks_terminated"
    assert data["action"]["status"] == "success"


def test_execute_command_health_diagnosis(assistant_client: TestClient):
    payload = {
        "user_prompt": "检查当前系统健康度与水位状态",
    }
    response = assistant_client.post("/api/v1/system-assistant/command", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["intent"] == "system_status"
    assert data["action"]["action_type"] == "health_diagnosed"
    assert "health_score" in data["action"]["details"]


def test_execute_command_general_query(assistant_client: TestClient):
    payload = {
        "user_prompt": "你是谁，你能为我代劳哪些系统操作？",
    }
    response = assistant_client.post("/api/v1/system-assistant/command", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["intent"] == "general_query"
    assert data["action"]["action_type"] == "query_answered"
    assert len(data["suggested_followups"]) >= 1


def test_get_system_assistant_status(assistant_client: TestClient):
    response = assistant_client.get("/api/v1/system-assistant/status")
    assert response.status_code == 200
    data = response.json()

    assert "active_agents_count" in data
    assert "system_health" in data
    assert data["voice_enabled"] is True
    assert "last_heartbeat" in data
