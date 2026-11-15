"""A loop guard pause ends the turn like any other: the chat stays usable and the pause survives a reload.

Real app, real agent, real persistence. Only the model is scripted (a localhost OpenAI-compatible endpoint), so the
guard really trips on a tool the model keeps calling the wrong way.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.scripted_model import scripted_model_environment, stream_agent_turn, wait_for
from tests.support.scripted_openai_endpoint import ChatRequest, Reply, ScriptedOpenAIEndpoint

_FAILING_TOOL = "bash_code_execute_tool"
_CONTINUE_WORD = "continue"
_ANSWER = "Picked up where it paused."


def _script(request: ChatRequest) -> Reply:
    if _CONTINUE_WORD in request.last_user_text:
        return Reply(text=_ANSWER)
    if _FAILING_TOOL in request.tool_names:
        # The required ``command`` is missing, so every call fails the same way.
        return Reply(tool_name=_FAILING_TOOL, tool_args={"reason": "run the command the user asked for"})
    return Reply(text="ok")


@pytest.fixture
def scripted_model(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, mock_load_user_configs: AsyncMock
) -> Iterator[ScriptedOpenAIEndpoint]:
    endpoint = ScriptedOpenAIEndpoint(_script)
    with scripted_model_environment(endpoint, monkeypatch, tmp_path, mock_load_user_configs):
        yield endpoint
    endpoint.close()


def _run_phase(client: TestClient, chat_id: str) -> object:
    digest = client.get(f"/api/v1/chats/{chat_id}/copilot/run-digest").json()["data"]["digest"]
    return digest["phase"] if isinstance(digest, dict) else None


def _assistant_steps(client: TestClient, chat_id: str) -> list[dict[str, object]]:
    messages = client.get(f"/api/v1/chats/{chat_id}/messages").json()["data"]["messages"]
    assistant = [m for m in messages if m["role"] == "assistant"]
    return assistant[0]["metadata"]["progressSteps"] if assistant else []


@pytest.mark.integration
@pytest.mark.usefixtures("scripted_model")
def test_the_chat_continues_after_a_loop_guard_pause_and_the_pause_survives_a_reload(client: TestClient) -> None:
    chat_id = f"stuck-pause-{uuid.uuid4().hex[:8]}"

    paused = stream_agent_turn(client, chat_id, query="run the command for me")
    assert paused.status == 200
    pauses = paused.of_type("approval_required")
    assert len(pauses) == 1
    pause = pauses[0]["data"]
    assert isinstance(pause, dict)
    assert pause["action_type"] == "tool_stuck"
    assert "approval_id" not in pause, "a pause nobody can answer must not be filed as a pending approval"

    assert wait_for(lambda: _run_phase(client, chat_id), lambda phase: phase == "completed") == "completed"
    steps = wait_for(lambda: _assistant_steps(client, chat_id), bool)
    assert isinstance(steps, list)
    assert steps[-1] == {"step_key": "tool_stuck_paused", "items": [], "status": "error"}

    resumed = stream_agent_turn(client, chat_id, query=f"please {_CONTINUE_WORD}")
    assert resumed.status == 200
    assert resumed.of_type("error") == []
    assert resumed.text == _ANSWER
    assert resumed.events[-1]["type"] == "message_end"
