"""API integration test: source_chat_id / source_message_id in MemoryItem responses.

Verifies the DTO projection flows through the real FastAPI route layer
using TestClient + mocked MemoryManager.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.memory import MemoryType
from myrm_agent_harness.toolkits.memory.types import EpisodicMemory, SemanticMemory

from app.api.dependencies import get_deploy_identity
from app.api.memory.utils import get_crud_memory_manager
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="memory")


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _override_auth():
    app.dependency_overrides[get_deploy_identity] = lambda: {"id": "test_user", "username": "test"}
    with patch("app.core.security.auth.identity.is_loopback_ip", return_value=True):
        yield
    app.dependency_overrides.pop(get_deploy_identity, None)


def _make_mock_manager(memories_by_type: dict[MemoryType, list[object]]) -> AsyncMock:
    manager = AsyncMock()
    manager.has_vector = True
    manager.has_relational = True

    async def mock_count(mem_type: MemoryType) -> int:
        return len(memories_by_type.get(mem_type, []))

    async def mock_list(mem_type: MemoryType, *, limit: int = 10000, offset: int = 0) -> list[object]:
        return memories_by_type.get(mem_type, [])

    manager.count_memories.side_effect = mock_count
    manager.list_memories.side_effect = mock_list
    return manager


class TestListApiSourceProjection:
    """GET /api/v1/memory/ returns source_chat_id when present."""

    def test_list_semantic_with_source(self, client: TestClient) -> None:
        mem = SemanticMemory(
            content="test fact",
            source_chat_id="conv-api-1",
            source_message_id="msg-api-1",
        )
        mock = _make_mock_manager({MemoryType.SEMANTIC: [mem]})
        app.dependency_overrides[get_crud_memory_manager] = lambda: mock
        try:
            resp = client.get("/api/v1/memory/?type=semantic")
            assert resp.status_code == 200
            items = resp.json()["items"]
            assert len(items) == 1
            assert items[0]["source_chat_id"] == "conv-api-1"
            assert items[0]["source_message_id"] == "msg-api-1"
        finally:
            app.dependency_overrides.pop(get_crud_memory_manager, None)

    def test_list_semantic_without_source(self, client: TestClient) -> None:
        mem = SemanticMemory(content="old fact no source")
        mock = _make_mock_manager({MemoryType.SEMANTIC: [mem]})
        app.dependency_overrides[get_crud_memory_manager] = lambda: mock
        try:
            resp = client.get("/api/v1/memory/?type=semantic")
            assert resp.status_code == 200
            items = resp.json()["items"]
            assert len(items) == 1
            assert items[0]["source_chat_id"] is None
            assert items[0]["source_message_id"] is None
        finally:
            app.dependency_overrides.pop(get_crud_memory_manager, None)

    def test_list_mixed_types_source_projection(self, client: TestClient) -> None:
        sem = SemanticMemory(content="semantic", source_chat_id="c1", source_message_id="m1")
        epi = EpisodicMemory(content="episodic", event_type="action", source_chat_id="c2")
        mock = _make_mock_manager({
            MemoryType.SEMANTIC: [sem],
            MemoryType.EPISODIC: [epi],
        })
        app.dependency_overrides[get_crud_memory_manager] = lambda: mock
        try:
            resp = client.get("/api/v1/memory/")
            assert resp.status_code == 200
            items = resp.json()["items"]
            source_items = [i for i in items if i.get("source_chat_id")]
            assert len(source_items) == 2
            chat_ids = {i["source_chat_id"] for i in source_items}
            assert chat_ids == {"c1", "c2"}
        finally:
            app.dependency_overrides.pop(get_crud_memory_manager, None)


class TestOpenApiSchemaSourceFields:
    """Verify MemoryItem OpenAPI schema includes new fields."""

    def test_schema_has_source_fields(self, client: TestClient) -> None:
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        schemas = resp.json()["components"]["schemas"]
        memory_item = schemas["MemoryItem"]
        props = memory_item["properties"]
        assert "source_chat_id" in props
        assert "source_message_id" in props
        for field_name in ("source_chat_id", "source_message_id"):
            field_schema = props[field_name]
            any_of = field_schema.get("anyOf", [])
            type_names = {t.get("type") for t in any_of}
            assert "string" in type_names, f"{field_name} should accept string"
            assert "null" in type_names, f"{field_name} should accept null"
