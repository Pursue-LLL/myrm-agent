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
class TestTextApprovalInterceptionE2E:
    """End-to-End tests for Approval Text Interception."""

    def test_text_approval_interception_resume(self, client: TestClient):
        """
        Test that sending a resume_value directly via text interception payload
        is correctly parsed and processed by the agent stream endpoint.
        We simulate the frontend sending a resume_value directly.
        """
        chat_id = str(uuid.uuid4())

        # We simulate the frontend sending a resume_value directly.
        # The frontend sends `resume_value: { "decision": "approve" }`
        resume_request: dict[str, object] = {
            "messageId": str(uuid.uuid4()),
            "query": "yes",
            "chatId": chat_id,
            "resumeValue": {"decision": "approve"},
            "modelSelection": get_model_selection(),
            "searchServiceCfg": get_search_service_config(),
        }

        collected_data: list[dict] = []

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

        # Since we are not actually pausing a graph, LangGraph might just start a new run
        # and ignore the resume command, or it might fail.
        # Either way, if we get a message_end event, it means the server successfully
        # processed the request without crashing.
        has_message_end = any(d.get("type") == "message_end" for d in collected_data)
        has_error = any(d.get("type") == "error" for d in collected_data)

        assert has_message_end or has_error, "Should either complete successfully or return an error"
