"""Integration test for capture_case_from_chat HTTP endpoint.

[INPUT]
- /api/v1/eval/cases/from-chat/{chat_id}
- tests.support.minimal_app

[OUTPUT]
- Verifies POST /api/v1/eval/cases/from-chat/{chat_id} status codes, dataset_id param handling,
  and end-to-end routing into capture_case_from_chat.
"""

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="eval")


@pytest.fixture(scope="module")
def client() -> Generator[TestClient, None, None]:
    with patch("app.core.security.auth.identity.is_loopback_ip", return_value=True):
        with TestClient(app) as test_client:
            yield test_client


def test_capture_from_chat_success_and_query_param(client: TestClient):
        with patch("app.api.eval.router.capture_case_from_chat", new_callable=AsyncMock) as mock_capture:
            mock_capture.return_value = True

            # Default dataset_id
            res = client.post("/api/v1/eval/cases/from-chat/chat-abc")
            assert res.status_code == 200
            assert res.json() == {"status": "success"}
            mock_capture.assert_called_with("chat-abc", None)

            # Custom dataset_id
            res2 = client.post("/api/v1/eval/cases/from-chat/chat-abc?dataset_id=custom-regressions")
            assert res2.status_code == 200
            assert res2.json() == {"status": "success"}
            mock_capture.assert_called_with("chat-abc", "custom-regressions")


def test_capture_from_chat_failure_returns_500(client: TestClient):
    with patch("app.api.eval.router.capture_case_from_chat", new_callable=AsyncMock) as mock_capture:
        mock_capture.return_value = False

        res = client.post("/api/v1/eval/cases/from-chat/chat-failed")
        assert res.status_code == 500
        assert "Failed to capture" in res.json()["detail"]


def test_capture_from_chat_real_pipeline(client: TestClient):
    from app.services.chat.chat_service import ChatService

    class MockMsg:
        def __init__(self, role, content, extra_data=None):
            self.role = role
            self.content = content
            self.extra_data = extra_data

    fake_msgs = [
        MockMsg("user", "Summarize quarterly report in pipeline."),
        MockMsg("assistant", "Quarterly profit up 20%."),
    ]
    with patch.object(ChatService, "get_all_messages", new_callable=AsyncMock) as mock_msgs:
        mock_msgs.return_value = fake_msgs
        cap_res = client.post("/api/v1/eval/cases/from-chat/chat-pipeline-test?dataset_id=pipeline-pack")
        assert cap_res.status_code == 200
        assert cap_res.json() == {"status": "success"}

        pack_res = client.get("/api/v1/eval/datasets/pipeline-pack")
        assert pack_res.status_code == 200
        assert "Summarize quarterly report in pipeline." in pack_res.json()["content"]
        assert "chat-pipeline-test" in pack_res.json()["content"]

