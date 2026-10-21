"""Integration tests for Tool Guidance API endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.memory.types import ProceduralMemory

from app.api.dependencies import get_deploy_identity
from app.api.memory.utils import get_crud_memory_manager
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="memory")


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth_headers():
    return {"Authorization": "Bearer test_token"}


@pytest.fixture(autouse=True)
def override_auth():
    app.dependency_overrides[get_deploy_identity] = lambda: {"id": "test_user", "username": "test"}
    with patch("app.core.security.auth.identity.is_loopback_ip", return_value=True):
        yield
    app.dependency_overrides.pop(get_deploy_identity, None)


@pytest.fixture(autouse=True)
def override_memory_manager():
    mock_manager = AsyncMock()
    mock_relational = AsyncMock()
    mock_manager._relational = mock_relational

    # Prepare sample procedural memories for tools
    r1 = ProceduralMemory(
        id="rule-bash-1",
        content="Avoid sed -i without empty quotes on macOS",
        trigger="sed -i",
        action="On macOS sed -i requires empty quotes ''",
        tool_name="bash_code_execute_tool",
        is_user_locked=True,  # pinned
    )
    r2 = ProceduralMemory(
        id="rule-fetch-1",
        content="Always include scheme in url",
        trigger="fetch http",
        action="Always specify full url scheme",
        tool_name="web_fetch_tool",
        is_user_locked=False,
    )

    mock_relational.list_rules.return_value = [r1, r2]
    mock_relational.get_rule.return_value = r1
    mock_relational.update_rule.return_value = r1
    mock_relational.delete_rule.return_value = True

    app.dependency_overrides[get_crud_memory_manager] = lambda: mock_manager
    yield mock_manager
    app.dependency_overrides.pop(get_crud_memory_manager, None)


def test_get_tool_guidance(client, auth_headers):
    response = client.get("/api/v1/memory/tool-guidance", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total_tools"] == 2
    assert data["total_rules"] == 2

    tools = {t["tool_name"]: t for t in data["tools"]}
    assert "bash_code_execute_tool" in tools
    assert tools["bash_code_execute_tool"]["has_pinned"] is True
    assert len(tools["bash_code_execute_tool"]["guidelines"]) == 1

    assert "web_fetch_tool" in tools
    assert tools["web_fetch_tool"]["has_pinned"] is False


def test_pin_tool_guidance(client, auth_headers):
    payload = {"rule_id": "rule-bash-1", "is_pinned": True}
    response = client.post("/api/v1/memory/tool-guidance/pin", json=payload, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["rule_id"] == "rule-bash-1"
    assert data["is_pinned"] is True
    assert data["status"] == "success"


def test_delete_tool_guidance(client, auth_headers):
    response = client.delete("/api/v1/memory/tool-guidance/rule-bash-1", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "deleted"
    assert data["rule_id"] == "rule-bash-1"

