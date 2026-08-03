"""Integration test: Co-Pilot HTTP API with real RunDigestStore and Tier-0 advisor."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.services.copilot.advisor_thread_store import AdvisorThreadStore
from app.services.copilot.run_digest_store import RunDigestStore
from myrm_agent_harness.agent.streaming.run_digest import RunDigestPhase
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="chats")


@pytest.fixture(autouse=True)
def _reset_copilot_stores() -> None:
    RunDigestStore._digests.clear()
    RunDigestStore._sessions.clear()
    AdvisorThreadStore._threads.clear()
    yield
    RunDigestStore._digests.clear()
    RunDigestStore._sessions.clear()
    AdvisorThreadStore._threads.clear()


@pytest.fixture
def client(init_test_database) -> TestClient:
    return TestClient(app)


class TestCopilotApiIntegration:
    def test_run_digest_and_tier0_advisor_roundtrip(self, client: TestClient) -> None:
        chat_id = f"copilot-int-{uuid.uuid4().hex[:8]}"

        empty_resp = client.get(f"/api/v1/chats/{chat_id}/copilot/run-digest")
        assert empty_resp.status_code == 200
        assert empty_resp.json()["data"]["digest"] is None

        RunDigestStore.begin_run(chat_id)
        RunDigestStore.update_from_progress(
            chat_id,
            [{"tool_name": "web_search", "step_key": "s1", "status": "running"}],
        )

        digest_resp = client.get(f"/api/v1/chats/{chat_id}/copilot/run-digest")
        assert digest_resp.status_code == 200
        digest = digest_resp.json()["data"]["digest"]
        assert digest is not None
        assert digest["phase"] == RunDigestPhase.RUNNING.value
        assert digest["step_count"] == 1
        assert digest["current_tool"] == "web_search"

        ask_resp = client.post(
            f"/api/v1/chats/{chat_id}/copilot/advisor/ask",
            json={"question": "现在在干嘛？"},
            headers={"Accept-Language": "zh-CN"},
        )
        assert ask_resp.status_code == 200
        body = ask_resp.json()["data"]
        assert body["tier"] == "tier0"
        assert "步骤 1" in body["reply"]

        list_resp = client.get(f"/api/v1/chats/{chat_id}/copilot/advisor/messages")
        assert list_resp.status_code == 200
        messages = list_resp.json()["data"]["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "assistant"
        assert messages[1]["tier"] == "tier0"

        clear_resp = client.delete(f"/api/v1/chats/{chat_id}/copilot/advisor/messages")
        assert clear_resp.status_code == 200
        assert client.get(f"/api/v1/chats/{chat_id}/copilot/advisor/messages").json()["data"]["messages"] == []

    def test_advisor_ask_rejects_empty_question(self, client: TestClient) -> None:
        chat_id = f"copilot-int-{uuid.uuid4().hex[:8]}"
        resp = client.post(
            f"/api/v1/chats/{chat_id}/copilot/advisor/ask",
            json={"question": "   "},
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["code"] == 400
