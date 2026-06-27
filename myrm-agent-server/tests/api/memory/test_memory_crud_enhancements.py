from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.memory.types import MemoryStatus, SemanticMemory

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
    mock_manager.has_vector = True
    mock_manager.has_relational = True

    # Mock get_profile_attribute for TasteSummary
    async def mock_get_profile(key):
        if key == "reply_style":
            return "concise"
        if key == "cognitive_depth":
            return "expert"
        if key == "proactivity":
            return "high"
        return None

    mock_manager.get_profile_attribute.side_effect = mock_get_profile

    # Mock update_memory for status patch
    mock_updated_mem = SemanticMemory(content="test", metadata={"status": "disabled"})
    mock_updated_mem.id = "test_id"
    mock_updated_mem.status = MemoryStatus.DISABLED
    mock_manager.update_memory.return_value = mock_updated_mem

    # Mock search for get memories
    mock_manager.search.return_value = []

    # Mock preference strategy for taste summary facets aggregation
    mock_manager._preference_strategy = None

    app.dependency_overrides[get_crud_memory_manager] = lambda: mock_manager
    yield mock_manager
    app.dependency_overrides.pop(get_crud_memory_manager, None)


@pytest.mark.asyncio
async def test_taste_summary_and_status_api(client: TestClient, auth_headers: dict[str, str], override_memory_manager: AsyncMock):
    # 1. 验证 TasteSummary API (no strategy → profile only)
    resp = client.get("/api/v1/memory/taste-summary", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["memory_count"] == 0
    assert data["reply_style"] == "concise"
    assert data["technical_depth"] == "expert"
    assert data["proactivity"] == "high"
    assert data["style_keywords"] == []
    assert data["preference_keywords"] == []
    assert data["avoid_keywords"] == []
    assert data["current_goals"] == []
    override_memory_manager.get_profile_attribute.assert_any_call("reply_style")

    # 2. 验证状态更新 API
    mem_id = "test_id"
    r = client.patch(f"/api/v1/memory/{mem_id}/status", json={"status": "disabled"}, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "disabled"
    override_memory_manager.update_memory.assert_called_once_with(mem_id, status=MemoryStatus.DISABLED)


@pytest.mark.asyncio
async def test_taste_summary_with_facets(auth_headers: dict[str, str]):
    """Integration test: taste-summary with active preference facets."""
    from dataclasses import dataclass, field
    from datetime import UTC, datetime

    from myrm_agent_harness.toolkits.memory.strategies.preference_stability import (
        CueFamily,
        PreferenceCategory,
        PreferenceLifecycle,
    )

    @dataclass
    class MockFacet:
        key: str = ""
        value: str = ""
        category: PreferenceCategory = PreferenceCategory.STYLE
        lifecycle: PreferenceLifecycle = PreferenceLifecycle.ACTIVE
        user_forgotten: bool = False
        id: str = "f1"
        stability: float = 0.9
        cue: CueFamily = CueFamily.IMPLICIT
        evidence_count: int = 2
        memory_ids: list[str] = field(default_factory=list)
        first_seen: datetime = field(default_factory=lambda: datetime.now(UTC))
        last_seen: datetime = field(default_factory=lambda: datetime.now(UTC))
        user_pinned: bool = False

    facets = [
        MockFacet(key="style", value="concise code", category=PreferenceCategory.STYLE, lifecycle=PreferenceLifecycle.ACTIVE),
        MockFacet(key="tool", value="Python", category=PreferenceCategory.TOOLING, lifecycle=PreferenceLifecycle.PROVISIONAL),
        MockFacet(key="veto", value="no any type", category=PreferenceCategory.VETO, lifecycle=PreferenceLifecycle.ACTIVE),
        MockFacet(key="goal", value="ship v2", category=PreferenceCategory.GOAL, lifecycle=PreferenceLifecycle.ACTIVE),
    ]

    mock_manager = AsyncMock()
    mock_manager.get_profile_attribute.return_value = None

    store_mock = AsyncMock()
    store_mock.list_all.return_value = facets
    strategy_mock = AsyncMock()
    strategy_mock._store = store_mock
    mock_manager._preference_strategy = strategy_mock

    app.dependency_overrides[get_crud_memory_manager] = lambda: mock_manager
    app.dependency_overrides[get_deploy_identity] = lambda: {"id": "test_user", "username": "test"}

    try:
        with patch("app.core.security.auth.identity.is_loopback_ip", return_value=True):
            client = TestClient(app)
            resp = client.get("/api/v1/memory/taste-summary", headers=auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert "concise code" in data["style_keywords"]
        assert "Python" in data["preference_keywords"]
        assert "no any type" in data["avoid_keywords"]
        assert "ship v2" in data["current_goals"]
        assert data["memory_count"] == 4
        assert "Style: concise code" in data["summary"]
    finally:
        app.dependency_overrides.pop(get_crud_memory_manager, None)
        app.dependency_overrides.pop(get_deploy_identity, None)
