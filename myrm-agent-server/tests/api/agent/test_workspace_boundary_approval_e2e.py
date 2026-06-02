import json
import os
import uuid

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import (
    get_model_selection,
    get_search_service_config,
)


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY environment variable",
)
class TestWorkspaceBoundaryApprovalE2E:
    """End-to-End test for Workspace Boundary Approval Interception.

    Verifies that when an agent attempts to access a file outside of its
    workspace boundary, the server emits a TOOL_APPROVAL_REQUEST
    instead of failing silently or proceeding with an error.

    Note: This test depends on LLM behavior and may be flaky if the model
    doesn't use file_write_tool as expected.
    """

    @pytest.mark.flaky(reruns=2)
    def test_out_of_bounds_file_access_triggers_approval(self, client: TestClient):
        chat_id = str(uuid.uuid4())

        request: dict[str, object] = {
            "messageId": str(uuid.uuid4()),
            "query": (
                "You MUST use the file_write_tool to write the text 'hello world' "
                "to exactly this path: /tmp/myrm_out_of_bounds_test.txt "
                "Do not ask questions, just call file_write_tool immediately."
            ),
            "chatId": chat_id,
            "modelSelection": get_model_selection(),
            "searchServiceCfg": get_search_service_config(),
            "actionMode": "agent",
        }

        collected_data: list[dict] = []

        with client.stream("POST", "/api/v1/agents/agent-stream", json=request) as response:
            assert response.status_code == 200

            for line in response.iter_lines():
                if not line or not line.startswith("data: "):
                    continue

                try:
                    data = json.loads(line[6:])
                    collected_data.append(data)
                except json.JSONDecodeError:
                    pass

        approval_events = [d for d in collected_data if d.get("type") in ("tool_approval_request", "approval_required")]

        assert len(approval_events) > 0, (
            f"The out-of-bounds file access should trigger an approval request. "
            f"Collected {len(collected_data)} events, types: "
            f"{[d.get('type') for d in collected_data[:10]]}"
        )

        payload = approval_events[0].get("data") or {}
        action_requests = payload.get("actionRequests", [])

        assert len(action_requests) > 0, "Should contain action requests"

        action_name = action_requests[0].get("action", "")
        assert "file_write" in action_name, f"Expected file_write action, got: {action_name}"

        reason = action_requests[0].get("description", "")
        assert (
            "Path outside allowed zones" in reason or "requires approval" in reason
        ), f"Unexpected reason: {reason}"
