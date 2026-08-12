import json
import os
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.code_execution import create_workspace_service

from app.config.settings import get_settings
from app.platform_utils.workspace_session import to_workspace_session_id
from tests.api.agent.utils import (
    build_approval_resume_value,
    get_lite_model_selection,
    get_model_selection,
)


def _stream_once(
    client: TestClient,
    request_data: dict[str, object],
) -> list[dict]:
    """Stream one agent turn and collect SSE events."""
    collected: list[dict] = []
    with client.stream("POST", "/api/v1/agents/agent-stream", json=request_data, timeout=120.0) as response:
        assert response.status_code == 200
        for line in response.iter_lines():
            if line.startswith("data: "):
                raw = line[6:]
                if raw == "[DONE]":
                    break
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if isinstance(data, dict):
                    collected.append(data)
    return collected


def perform_agent_stream(
    client: TestClient,
    query: str,
    chat_id: str,
    model_selection: dict[str, object] | None = None,
) -> tuple[str, list[dict], int]:
    request_data: dict[str, object] = {
        "messageId": f"gast-msg-{uuid.uuid4().hex[:12]}",
        "chatId": chat_id,
        "query": query,
        "modelSelection": model_selection or get_model_selection(),
        "actionMode": "agent",
        "memoryRequireConfirmation": False,
        "enableMemoryAutoExtraction": False,
    }

    collected: list[dict] = []
    collected.extend(_stream_once(client, request_data))

    for _ in range(10):
        approval_required = any(
            d.get("type") in ("approval_required", "tool_approval_request")
            for d in reversed(collected)
        )
        if not approval_required:
            break
        resume_request = dict(request_data)
        resume_request["resumeValue"] = build_approval_resume_value()
        collected.extend(_stream_once(client, resume_request))

    message_chunks: list[str] = []
    tool_call_count = 0
    for data in collected:
        event_type = data.get("type", "unknown")
        if event_type in ("message", "reasoning"):
            content = data.get("data", "")
            if content:
                message_chunks.append(content)
        elif event_type == "tasks_steps":
            if data.get("tool_name") is not None:
                tool_call_count += 1

    full_answer = "".join(message_chunks)
    return full_answer, collected, tool_call_count


class TestWorkspaceRulesE2E:
    """E2E tests for workspace rules injection (First-Match-Wins).

    Requires a real LLM (agent-stream), so it is gated behind the ``e2e``
    marker and an API-key skip to keep the default CI suite hermetic.
    """

    async def _harness_workspace(self, chat_id: str) -> Path:
        """Resolve the harness workspace dir bound to ``chat_{chat_id}``.

        Workspace rules are scanned from the harness workspace (set via
        ``run_lifecycle.set_workspace_root``), so rule files must be seeded
        there rather than in a mocked server-side chat workspace dir.
        """
        harness_root = Path(get_settings().database.harness_dir)
        workspace_svc = create_workspace_service(root_dir=harness_root)
        workspace = await workspace_svc.get_or_create(
            session_id=to_workspace_session_id(chat_id)
        )
        return Path(workspace_svc.get_workspace_absolute_path(workspace))

    @pytest.mark.e2e
    @pytest.mark.skipif(
        not os.environ.get("BASIC_API_KEY"),
        reason="E2E test requires BASIC_API_KEY environment variable",
    )
    @pytest.mark.asyncio
    async def test_first_match_wins_e2e(self, client: TestClient) -> None:
        """Test that AGENTS.md overrides .cursorrules due to First-Match-Wins."""
        chat_id = f"wrules-{uuid.uuid4().hex[:10]}"
        create_response = client.post("/api/v1/chats/", json={"chat_id": chat_id})
        assert create_response.status_code == 200

        workspace_path = await self._harness_workspace(chat_id)
        workspace_path.mkdir(parents=True, exist_ok=True)

        # Create a low priority rule file
        (workspace_path / ".cursorrules").write_text(
            "Project Convention: When writing any code, you MUST include the comment '# BAZINGA' at the top."
        )

        # Create a high priority rule file
        (workspace_path / "AGENTS.md").write_text(
            "Project Convention: When writing any code, you MUST include the comment '# WUBBALUBBADUBDUB' at the top."
        )

        query = "Write a simple python script that prints hello world."

        # Workspace-rule adherence depends on the model's instruction-following
        # ability; the default BASIC_MODEL (agnes flash) is too weak to reliably
        # honor injected rules, so this E2E uses the stronger LITE_MODEL.
        full_answer, collected_data, _tool_call_count = perform_agent_stream(
            client,
            query,
            chat_id,
            model_selection=get_lite_model_selection(),
        )

        # The agent should follow the high priority rule (AGENTS.md) and ignore the low priority one (.cursorrules)
        assert "WUBBALUBBADUBDUB" in full_answer.upper()
        assert "BAZINGA" not in full_answer.upper()
