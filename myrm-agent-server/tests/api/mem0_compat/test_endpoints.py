"""Tests for the mem0-compatible API deletion endpoints."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.memory.types import MemoryStatus, MemoryType

from app.schemas.memory.crud import MemoryItem
from app.services.memory.command_center.command_center import ALL_MEMORY_TYPES
from app.services.memory.manager_deps import get_crud_memory_manager
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(mem0_compat=True)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def override_manager() -> AsyncMock:
    mock_manager = AsyncMock()
    app.dependency_overrides[get_crud_memory_manager] = lambda: mock_manager
    yield mock_manager
    app.dependency_overrides.pop(get_crud_memory_manager, None)


def _item(memory_id: str, memory_type: str) -> MemoryItem:
    now = datetime.now(UTC)
    return MemoryItem(
        id=memory_id,
        memory_type=memory_type,
        content="content",
        created_at=now,
        updated_at=now,
    )


def test_delete_all_routes_every_type_to_delete_by_type(client: TestClient, override_manager: AsyncMock) -> None:
    """DELETE /v1/memories/ must delete every memory type via delete_by_type.

    ``delete_all`` takes no per-type argument, so delete_by_type is the only
    correct route for a per-type full clear.
    """
    resp = client.delete("/mem0/v1/memories/")

    assert resp.status_code == 200
    assert override_manager.delete_by_type.await_count == len(ALL_MEMORY_TYPES)
    override_manager.delete_all.assert_not_called()


def test_delete_semantic_memory_soft_deletes(client: TestClient, override_manager: AsyncMock) -> None:
    """Semantic memories are soft-deleted via status=archived."""
    with patch(
        "app.api.mem0_compat.endpoints._find_memory_by_id",
        return_value=_item("mem-1", MemoryType.SEMANTIC.value),
    ):
        resp = client.delete("/mem0/v1/memories/mem-1/")

    assert resp.status_code == 200
    override_manager.update_memory.assert_awaited_once_with("mem-1", status=MemoryStatus.ARCHIVED)


def test_delete_procedural_memory_success(client: TestClient, override_manager: AsyncMock) -> None:
    """Procedural rules are hard-deleted through delete_rule."""
    override_manager.delete_rule.return_value = True
    with patch(
        "app.api.mem0_compat.endpoints._find_memory_by_id",
        return_value=_item("rule-1", MemoryType.PROCEDURAL.value),
    ):
        resp = client.delete("/mem0/v1/memories/rule-1/")

    assert resp.status_code == 200
    override_manager.delete_rule.assert_awaited_once_with("rule-1")


def test_delete_procedural_memory_not_found_returns_404(client: TestClient, override_manager: AsyncMock) -> None:
    """A failed delete_rule (missing/out-of-scope) must surface as 404."""
    override_manager.delete_rule.return_value = False
    with patch(
        "app.api.mem0_compat.endpoints._find_memory_by_id",
        return_value=_item("rule-1", MemoryType.PROCEDURAL.value),
    ):
        resp = client.delete("/mem0/v1/memories/rule-1/")

    assert resp.status_code == 404
    override_manager.delete_rule.assert_awaited_once_with("rule-1")


def test_delete_unsupported_type_returns_400(client: TestClient, override_manager: AsyncMock) -> None:
    """Derived/system memory types are not deletable via the mem0 API."""
    with patch(
        "app.api.mem0_compat.endpoints._find_memory_by_id",
        return_value=_item("mem-9", MemoryType.CONVERSATION.value),
    ):
        resp = client.delete("/mem0/v1/memories/mem-9/")

    assert resp.status_code == 400
