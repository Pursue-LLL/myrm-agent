"""HTTP integration tests for migration readiness Chrome E2E seed endpoint."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="memory")


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_seed_migration_readiness_fixture_mcp_warning(client: TestClient) -> None:
    fake_agent = MagicMock()
    fake_agent.id = "agent-e2e-migration"

    with (
        patch("app.api.memory.test_fixtures_migration_readiness.is_local_mode", return_value=True),
        patch(
            "app.api.memory.test_fixtures_migration_readiness.AgentService.get_agent_list",
            new_callable=AsyncMock,
            return_value=([fake_agent], 1),
        ),
        patch(
            "app.services.memory.manager_deps.get_memory_manager",
        ),
        patch(
            "app.api.memory.test_fixtures_migration_readiness.get_session_factory",
        ) as mock_session_factory,
        patch(
            "app.api.memory.test_fixtures_migration_readiness.MemoryImportSessionService"
        ) as mock_service_cls,
    ):
        mock_service = mock_service_cls.return_value
        mock_service.create_dry_run = AsyncMock(return_value=("dry-1", {}, "hash", "expires"))
        confirm = MagicMock()
        confirm.import_batch_id = "memory-import-batch:e2e"
        mock_service.confirm_import = AsyncMock(return_value=confirm)
        mock_service.save_post_import_diagnostic = AsyncMock()
        mock_service.save_post_import_readiness = AsyncMock()

        mock_db = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_db
        mock_session_factory.return_value.__aexit__.return_value = None

        resp = client.post(
            "/api/v1/memory/test/seed-migration-readiness-fixture?variant=mcp_warning",
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["import_batch_id"] == "memory-import-batch:e2e"
    assert body["target_agent_id"] == "agent-e2e-migration"
    assert body["readiness_status"] == "warning"
    assert body["settings_path"] == "/settings/mcp"
    assert body["chat_ui_path"] == "/?agentId=agent-e2e-migration"


def test_seed_migration_readiness_fixture_hidden_outside_local_mode(client: TestClient) -> None:
    with patch("app.api.memory.test_fixtures_migration_readiness.is_local_mode", return_value=False):
        resp = client.post("/api/v1/memory/test/seed-migration-readiness-fixture")
    assert resp.status_code == 404
