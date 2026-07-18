from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient


class TestApprovalsSeedMock:
    """HTTP tests for local-only push deeplink seed-mock endpoint (no LLM)."""

    def test_seed_mock_http_endpoint(self, client: TestClient) -> None:
        with (
            patch("app.config.deploy_mode.is_local_mode", return_value=True),
            patch(
                "app.services.chat.chat_service.ChatService.create_or_update_chat",
                new_callable=AsyncMock,
            ),
        ):
            resp = client.post("/api/v1/approvals/test/seed-mock")

        assert resp.status_code == 200
        body = resp.json()
        chat_id = body["chat_id"]
        approval_id = body["approval_id"]
        assert chat_id.startswith("e2epush")
        assert len(chat_id) >= 8
        assert approval_id
        assert body["push_url"] == f"/{chat_id}?approval={approval_id}"
        assert body["ui_url"] == body["push_url"]

        list_resp = client.get("/api/v1/approvals?limit=100&offset=0")
        assert list_resp.status_code == 200
        ids = {item["id"] for item in list_resp.json()["approvals"]}
        assert approval_id in ids

    def test_seed_mock_hidden_outside_local_mode(self, client: TestClient) -> None:
        with patch("app.config.deploy_mode.is_local_mode", return_value=False):
            resp = client.post("/api/v1/approvals/test/seed-mock")
        assert resp.status_code == 404
