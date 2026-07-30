"""Integration test for context retention Chrome E2E seed fixture."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.platform_utils.persistent_root import configure_persistent_root_for_local_dev
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="chats")


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_seed_context_retention_fixture(client: TestClient, tmp_path: pytest.TempPathFactory) -> None:
    configure_persistent_root_for_local_dev(str(tmp_path))

    fake_agent = MagicMock()
    fake_agent.id = "agent-e2e-context-retention"
    fake_agent.display_name = "Context Retention E2E Agent"

    with (
        patch("app.api.chats.test_fixtures_context_retention.is_local_mode", return_value=True),
        patch(
            "app.api.chats.test_fixtures_context_retention.AgentService.get_agent_list",
            new_callable=AsyncMock,
            return_value=([fake_agent], 1),
        ),
    ):
        response = client.post("/api/v1/chats/test/seed-context-retention-fixture")

    assert response.status_code == 200, response.text
    body = response.json()
    chat_id = str(body["chat_id"])
    assert chat_id.startswith("e2econtextret")
    assert "E2E context retention summary fixture" in str(body["summary_text"])

    pins_res = client.get(f"/api/v1/chats/{chat_id}/context/pins")
    assert pins_res.status_code == 200, pins_res.text
    assert pins_res.json()["data"]["files"] == ["src/context/retention.py"]

    branches_res = client.get(f"/api/v1/chats/{chat_id}/context/branches")
    assert branches_res.status_code == 200, branches_res.text
    branches = branches_res.json()["data"]["branches"]
    assert len(branches) == 1
    assert branches[0]["label"] == "Before compaction E2E"
