import json
import os
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.services.agent.params.workspace_resolve import default_chat_workspace_path
from tests.api.agent.utils import check_e2e_errors, get_model_selection


def _agent_stream_request(query: str, chat_id: str) -> dict[str, object]:
    return {
        "query": query,
        "message_id": str(uuid4()),
        "chat_id": chat_id,
        "action_mode": "general",
        "model_selection": get_model_selection(),
        "timezone": "UTC",
    }


def _sse_events(body: str) -> list[dict[str, object]]:
    payloads = (json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: "))
    return [payload for payload in payloads if isinstance(payload, dict)]


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY environment variable",
)
class TestGatewayHygieneE2E:
    """Oversized prompts: spilled to the chat workspace, rejected only as a last resort."""

    def test_oversized_prompt_of_a_new_chat_is_read_back_by_the_agent(self, client: TestClient) -> None:
        """The task sits in the preview; the code that answers it lives only in the spilled file."""
        secret_code = f"ZEBRA-{uuid4().hex[:8].upper()}"
        filler = "\n".join(f"Log entry {i}: nothing of interest happened here." for i in range(400))
        document = (
            "TASK: find the line that starts with 'SECRET CODE:' in this document "
            "and reply with only the code.\n"
            f"{filler}\nSECRET CODE: {secret_code}\n"
        )
        assert len(document) > 16_000
        chat_id = f"hygiene-{uuid4().hex[:12]}"

        response = client.post("/api/v1/agents/agent-stream", json=_agent_stream_request(document, chat_id))

        assert response.status_code == 200
        events = _sse_events(response.text)
        check_e2e_errors(events)
        answer = "".join(str(event["data"]) for event in events if event.get("type") == "message" and event.get("data"))
        assert secret_code in answer

        spilled_files = list((default_chat_workspace_path(chat_id) / ".myrm" / "spillover").glob("payload_*.md"))
        assert len(spilled_files) == 1
        assert secret_code in spilled_files[0].read_text(encoding="utf-8")

    def test_massive_payload_is_rejected_when_the_guard_cannot_spill_it(self, client: TestClient) -> None:
        """Last-resort gateway backstop: only reachable when the Context Guard itself fails."""
        massive_text = "A" * 360_001
        unavailable_guard = AsyncMock(side_effect=OSError("workspace unavailable"))

        with patch(
            "app.services.agent.context_guard_service.ContextGuardService.guard_inbound_prompt",
            unavailable_guard,
        ):
            response = client.post(
                "/api/v1/agents/agent-stream",
                json=_agent_stream_request(massive_text, f"hygiene-{uuid4().hex[:12]}"),
            )

        assert response.status_code == 400
        assert "Request exceeds gateway token limits" in response.json().get("detail", "")
