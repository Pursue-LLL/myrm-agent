import json
import os
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config.settings import settings
from tests.api.agent.utils import get_model_selection


def perform_agent_stream(
    client: TestClient,
    query: str,
) -> tuple[str, list[dict], int]:
    request_data = {
        "messageId": f"gast-msg-{uuid.uuid4().hex[:12]}",
        "chatId": f"gast-chat-{uuid.uuid4().hex[:10]}",
        "query": query,
        "modelSelection": get_model_selection(),
        "actionMode": "agent",
        "memoryRequireConfirmation": False,
        "enableMemoryAutoExtraction": False,
    }

    collected_data = []
    message_chunks = []
    tool_call_count = 0

    with client.stream("POST", "/api/v1/agents/agent-stream", json=request_data, timeout=120.0) as response:
        assert response.status_code == 200

        for line in response.iter_lines():
            if not line or not line.startswith("data: "):
                continue

            try:
                data = json.loads(line[6:])
                if data is None:
                    continue
                collected_data.append(data)
                event_type = data.get("type", "unknown")

                if event_type in ("message", "reasoning"):
                    content = data.get("data", "")
                    if content:
                        message_chunks.append(content)
                elif event_type == "tasks_steps":
                    tool_name = data.get("tool_name")
                    if tool_name is not None:
                        tool_call_count += 1
            except json.JSONDecodeError:
                continue

    full_answer = "".join(message_chunks)
    return full_answer, collected_data, tool_call_count


class TestWorkspaceRulesE2E:
    """E2E tests for workspace rules injection (First-Match-Wins)."""

    @pytest.fixture
    def temp_workspace(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        """Create a temporary workspace and mock get_workspace_root."""
        monkeypatch.setattr("app.platform_utils.workspace_root.get_workspace_root", lambda: tmp_path)
        yield tmp_path

    def test_first_match_wins_e2e(self, client: TestClient, temp_workspace: Path):
        """Test that AGENTS.md overrides .cursorrules due to First-Match-Wins."""
        
        # Create a low priority rule file
        (temp_workspace / ".cursorrules").write_text(
            "Project Convention: When writing any code, you MUST include the comment '# BAZINGA' at the top."
        )
        
        # Create a high priority rule file
        (temp_workspace / "AGENTS.md").write_text(
            "Project Convention: When writing any code, you MUST include the comment '# WUBBALUBBADUBDUB' at the top."
        )

        query = "Write a simple python script that prints hello world."
        
        full_answer, collected_data, tool_call_count = perform_agent_stream(client, query)
        
        # The agent should follow the high priority rule (AGENTS.md) and ignore the low priority one (.cursorrules)
        assert "WUBBALUBBADUBDUB" in full_answer.upper()
        assert "BAZINGA" not in full_answer.upper()
