import json
import os
import uuid

import pytest
from fastapi.testclient import TestClient

# Import all models to ensure relations are resolved
from tests.api.agent.utils import (
    get_model_selection,
    get_search_service_config,
)


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY environment variable",
)
class TestAgentStreamResumeValueE2E:
    """End-to-end tests for resuming through `/agent-stream` with an explicit `resumeValue`."""

    def test_resume_value_without_pending_interrupt_does_not_crash(self, client: TestClient) -> None:
        """
        A `resumeValue` sent to a chat that has no paused graph must not crash the stream.

        The server either starts a fresh run or answers with a structured error; both end the
        stream with a `message_end` or `error` event.
        """
        chat_id = str(uuid.uuid4())

        resume_request: dict[str, object] = {
            "messageId": str(uuid.uuid4()),
            "query": "yes",
            "chatId": chat_id,
            "resumeValue": {"decision": "approve"},
            "modelSelection": get_model_selection(),
            "searchServiceCfg": get_search_service_config(),
        }

        collected_data: list[dict[str, object]] = []

        with client.stream("POST", "/api/v1/agents/agent-stream", json=resume_request) as response:
            assert response.status_code == 200

            for line in response.iter_lines():
                if not line or not line.startswith("data: "):
                    continue

                try:
                    data = json.loads(line[6:])
                    if isinstance(data, dict):
                        collected_data.append(data)
                except json.JSONDecodeError:
                    pass

        has_message_end = any(d.get("type") == "message_end" for d in collected_data)
        has_error = any(d.get("type") == "error" for d in collected_data)

        assert has_message_end or has_error, "Should either complete successfully or return an error"
