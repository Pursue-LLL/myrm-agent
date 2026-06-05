import os

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import get_model_selection


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY environment variable",
)
class TestGatewayHygieneE2E:
    """E2E Test for Gateway Hygiene Block"""

    def test_massive_payload_blocked(self, client: TestClient):
        """Test that a massive text payload is blocked with a 400 status."""
        model_selection = get_model_selection()

        # Create a payload of 360,001 characters
        massive_text = "A" * 360001

        search_request: dict[str, object] = {
            "query": massive_text,
            "message_id": "test-msg-id-hygiene",
            "chat_id": "test-chat-id-hygiene",
            "action_mode": "general",
            "model_selection": model_selection,
            "timezone": "UTC",
        }

        response = client.post("/api/v1/agents/agent-stream", json=search_request)
        assert response.status_code == 400
        error_content = response.json()
        assert "Request exceeds gateway token limits" in error_content.get("detail", "")
