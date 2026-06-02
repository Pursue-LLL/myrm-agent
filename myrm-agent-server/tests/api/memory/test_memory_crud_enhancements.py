from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.memory.types import MemoryStatus, SemanticMemory

from app.api.dependencies import get_deploy_identity
from app.api.memory.utils import get_crud_memory_manager
from app.main import app


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
    
    app.dependency_overrides[get_crud_memory_manager] = lambda: mock_manager
    yield mock_manager
    app.dependency_overrides.pop(get_crud_memory_manager, None)

@pytest.mark.asyncio
async def test_taste_summary_and_status_api(client: TestClient, auth_headers: dict[str, str], override_memory_manager: AsyncMock):
    # 1. 验证 TasteSummary API
    resp = client.get("/api/v1/memory/taste-summary", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["memory_count"] == 0
    assert data["reply_style"] == "concise"
    assert data["technical_depth"] == "expert"
    assert data["proactivity"] == "high"
    override_memory_manager.get_profile_attribute.assert_any_call("reply_style")

    # 2. 验证状态更新 API
    mem_id = "test_id"
    r = client.patch(f"/api/v1/memory/{mem_id}/status", json={"status": "disabled"}, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "disabled"
    override_memory_manager.update_memory.assert_called_once_with(mem_id, status=MemoryStatus.DISABLED)
