import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import get_model_selection


@pytest.mark.asyncio
async def test_file_diff_stream_e2e(app) -> None:
    """
    E2E test to verify that file_diff events are emitted with correct structure
    when the agent modifies a file.
    """
    import uuid

    from myrm_agent_harness.toolkits.code_execution import create_workspace_service

    from app.config.settings import get_settings

    chat_id = f"test-diff-chat-{uuid.uuid4().hex[:8]}"
    session_id = f"chat_{chat_id}"
    workspace_svc = create_workspace_service(
        root_dir=Path(get_settings().database.harness_dir),
    )
    workspace = await workspace_svc.get_or_create(session_id=session_id)
    workspace_dir = Path(workspace_svc.get_workspace_absolute_path(workspace))

    test_file = workspace_dir / "test_diff.txt"
    test_file.write_text("line1\nline2\nline3\n")

    # The query asks the agent to modify the file (relative path is enough)
    query = "Please replace 'line2' with 'modified_line2' in the file test_diff.txt. Do not do anything else."

    request_data = {
        "messageId": f"test-diff-msg-{uuid.uuid4().hex[:8]}",
        "chatId": chat_id,
        "query": query,
        "modelSelection": get_model_selection(),
    }

    file_diff_events = []

    with TestClient(app) as client:
        with client.stream("POST", "/api/v1/agents/agent-stream", json=request_data) as response:
            assert response.status_code == 200

            for line in response.iter_lines():
                if not line or not line.startswith("data: "):
                    continue

                data_str = line[6:]
                if data_str == "[DONE]":
                    break

                try:
                    event = json.loads(data_str)
                    if event.get("type") == "file_diff":
                        file_diff_events.append(event)
                except json.JSONDecodeError:
                    continue

    # Verify that at least one file_diff event was emitted
    assert len(file_diff_events) > 0, "No file_diff event was emitted"

    # Verify the structure of the last file_diff event
    last_diff_event = file_diff_events[-1]
    assert "data" in last_diff_event
    diff_data = last_diff_event["data"]

    assert "path" in diff_data
    assert "test_diff.txt" in diff_data["path"]
    assert "diff" in diff_data
    assert "is_new" in diff_data
    assert diff_data["is_new"] is False
    assert "lines_added" in diff_data
    assert diff_data["lines_added"] >= 1
    assert "lines_removed" in diff_data
    assert diff_data["lines_removed"] >= 1
    assert "truncated" in diff_data
    assert diff_data["truncated"] is False

    # Verify the actual file content was modified
    final_content = test_file.read_text()
    assert "modified_line2" in final_content
    assert all(line != "line2" for line in final_content.splitlines())
