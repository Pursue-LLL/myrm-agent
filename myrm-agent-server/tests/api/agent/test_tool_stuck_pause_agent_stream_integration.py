"""A loop guard pause ends the turn like any other: the chat stays usable and the pause survives a reload.

Real app, real agent, real persistence. Only the model is scripted (a localhost OpenAI-compatible endpoint), so the
guard really trips on a tool the model keeps calling the wrong way.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.conftest import _build_mock_user_configs
from tests.api.agent.utils import get_lite_model_selection, get_model_selection, get_search_service_config
from tests.support import test_secrets
from tests.support.scripted_openai_endpoint import ChatRequest, Reply, ScriptedOpenAIEndpoint

_FAILING_TOOL = "bash_code_execute_tool"
_CONTINUE_WORD = "continue"
_ANSWER = "Picked up where it paused."
_WAIT_SECONDS = 15.0


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
    """Point every model credential the app tests read at the scripted endpoint."""
    endpoint = ScriptedOpenAIEndpoint(_script)
    env = {
        "BASIC_API_KEY": "scripted-key",
        "BASIC_BASE_URL": endpoint.base_url,
        "BASIC_MODEL": "openai/scripted-model",
        "LITE_API_KEY": "scripted-key",
        "LITE_BASE_URL": endpoint.base_url,
        "LITE_MODEL": "openai/scripted-model",
        "EMBEDDING_API_KEY": "scripted-key",
        "EMBEDDING_BASE_URL": endpoint.base_url,
        "OPENAI_API_KEY": "scripted-key",
        "OPENAI_BASE_URL": endpoint.base_url,
        "OPENAI_API_BASE": endpoint.base_url,
        "SEARCH_SERVICE": "tavily",
        "TAVILY_API_KEY": "scripted-key",
    }
    (tmp_path / ".env.test").write_text("".join(f"{key}={value}\n" for key, value in env.items()))
    monkeypatch.setattr(test_secrets, "_SERVER_ROOT", tmp_path)
    test_secrets.clear_test_secrets_cache()
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    mock_load_user_configs.return_value = _build_mock_user_configs()
    # Whoever asks, the configured search provider is not probed live: this test must not leave the machine.
    monkeypatch.setattr("app.services.integrations.search_verify.verify_search_config_cached", AsyncMock(return_value=False))
    yield endpoint
    endpoint.close()
    test_secrets.clear_test_secrets_cache()


def _send(client: TestClient, chat_id: str, query: str) -> list[dict[str, object]]:
    body: dict[str, object] = {
        "messageId": str(uuid.uuid4()),
        "chatId": chat_id,
        "query": query,
        "action_mode": "agent",
        "modelSelection": get_model_selection(),
        "liteModelSelection": get_lite_model_selection(),
        "searchServiceCfg": get_search_service_config(),
        "enable_memory_auto_extraction": False,
    }
    events: list[dict[str, object]] = []
    with client.stream("POST", "/api/v1/agents/agent-stream", json=body, headers={"X-Chat-ID": chat_id}) as response:
        assert response.status_code == 200
        for line in response.iter_lines():
            if line.startswith("data: "):
                payload = json.loads(line[len("data: ") :])
                if isinstance(payload, dict):
                    events.append(payload)
    return events


def _wait_for(read: Callable[[], object], done: Callable[[object], bool]) -> object:
    deadline = time.monotonic() + _WAIT_SECONDS
    value = read()
    while not done(value) and time.monotonic() < deadline:
        time.sleep(0.2)
        value = read()
    return value


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

    paused = _send(client, chat_id, "run the command for me")
    pauses = [event for event in paused if event.get("type") == "approval_required"]
    assert len(pauses) == 1
    pause = pauses[0]["data"]
    assert isinstance(pause, dict)
    assert pause["action_type"] == "tool_stuck"
    assert "approval_id" not in pause, "a pause nobody can answer must not be filed as a pending approval"

    assert _wait_for(lambda: _run_phase(client, chat_id), lambda phase: phase == "completed") == "completed"
    steps = _wait_for(lambda: _assistant_steps(client, chat_id), bool)
    assert isinstance(steps, list)
    assert steps[-1] == {"step_key": "tool_stuck_paused", "items": [], "status": "error"}

    resumed = _send(client, chat_id, f"please {_CONTINUE_WORD}")
    assert [event for event in resumed if event.get("type") == "error"] == []
    assert "".join(str(e.get("data", "")) for e in resumed if e.get("type") == "message") == _ANSWER
    assert resumed[-1]["type"] == "message_end"
