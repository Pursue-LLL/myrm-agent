"""Tests for Three-Domain progressive memory and Hermes migration endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.memory import DomainCategory, MemoryDomain
from myrm_agent_harness.toolkits.memory.types import SemanticMemory

from app.api.dependencies import get_deploy_identity
from app.api.memory.utils import get_memory_manager
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="memory")


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test_token"}


@pytest.fixture(autouse=True)
def override_auth():
    app.dependency_overrides[get_deploy_identity] = lambda: {
        "id": "test_user",
        "username": "test",
    }
    with patch("app.core.security.auth.identity.is_loopback_ip", return_value=True):
        yield
    app.dependency_overrides.pop(get_deploy_identity, None)


@pytest.fixture
def mock_memory_mgr():
    mgr = AsyncMock()
    app.dependency_overrides[get_memory_manager] = lambda: mgr
    yield mgr
    app.dependency_overrides.pop(get_memory_manager, None)


def test_domain_mesh_overview_endpoint(
    client: TestClient, auth_headers: dict[str, str], mock_memory_mgr: AsyncMock
) -> None:
    u_mem = SemanticMemory(
        id="mem-user-1",
        content="Prefers dark mode theme in IDE and WebUI.",
        summary_l0="Dark mode preference",
        overview_l1="Dark mode preference overview.",
        domain=MemoryDomain.USER,
        domain_category=DomainCategory.PREFERENCES.value,
    )
    a_mem = SemanticMemory(
        id="mem-asst-1",
        content="Assistant persona is calm and analytical.",
        summary_l0="Calm persona",
        overview_l1="Persona overview.",
        domain=MemoryDomain.ASSISTANT,
        domain_category=DomainCategory.SOUL.value,
    )
    t_mem = SemanticMemory(
        id="mem-task-1",
        content="Always inspect git log before branching.",
        summary_l0="Git branch inspection",
        overview_l1="Git safety rule.",
        domain=MemoryDomain.TASK,
        domain_category=DomainCategory.EXPERIENCES.value,
    )

    async def mock_list(mtype, limit=2000):
        if str(mtype.value) == "semantic":
            return [u_mem, a_mem, t_mem]
        return []

    mock_memory_mgr.list_memories.side_effect = mock_list

    resp = client.get("/api/v1/memory/domain-mesh/overview", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()

    assert data["total_memories"] == 3
    assert data["user"]["total_count"] == 1
    assert data["user"]["category_counts"]["preferences"] == 1
    assert data["assistant"]["total_count"] == 1
    assert data["task"]["total_count"] == 1
    assert len(data["user"]["highlights"]) == 1
    assert data["user"]["highlights"][0]["l0"] == "Dark mode preference"


def test_domain_mesh_drill_down_endpoint(
    client: TestClient, auth_headers: dict[str, str], mock_memory_mgr: AsyncMock
) -> None:
    mem = SemanticMemory(
        id="mem-drill-1",
        content="Detailed verbatim architectural blueprint with full code snippets.",
        summary_l0="Arch blueprint",
        overview_l1="Blueprint overview.",
        domain=MemoryDomain.TASK,
        domain_category=DomainCategory.EXPERIENCES.value,
    )
    mock_memory_mgr.get_memory.return_value = mem

    resp = client.get(
        "/api/v1/memory/domain-mesh/drill-down/mem-drill-1", headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["id"] == "mem-drill-1"
    assert data["l0"] == "Arch blueprint"
    assert data["l1"] == "Blueprint overview."
    assert (
        data["l2_content"]
        == "Detailed verbatim architectural blueprint with full code snippets."
    )
    assert data["domain"] == "task"


def test_domain_mesh_hermes_migration_endpoint(
    client: TestClient, auth_headers: dict[str, str], mock_memory_mgr: AsyncMock
) -> None:
    mock_memory_mgr.save_memory.return_value = None

    payload = {
        "content": """---
id: hermes-test-1
type: semantic
domain: user
category: preferences
---
User prefers fast response times.
""",
        "format": "markdown",
    }

    resp = client.post(
        "/api/v1/memory/domain-mesh/migrate/hermes",
        headers=auth_headers,
        json=payload,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success_count"] == 1
    assert data["fail_count"] == 0
