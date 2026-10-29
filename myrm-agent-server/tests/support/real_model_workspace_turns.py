"""What the real-model workspace tests share: the app routes, the trust lookup, the recorders and the project, chat and turn helpers.

[INPUT]
- POST /api/v1/agents/agent-stream with the LITE model (POS: the whole server path, a real provider call, SSE back)
- The project and folder-trust API (POS: what a user does before asking: link a folder, preview it, trust it)
- ChatLiteLLM message building and the run's trust binding (POS: recorded where the request is built and the trust is decided)

[OUTPUT]
- stuck_turn_report, routes_and_trust, sent, applied: fixtures (registered for ``tests/api/agent`` by its conftest)
- new_chat, trusted_project_folder, harness_workspace, turn_request, resume_request, stream_turn, perform_agent_stream, ask, main_request_text: the steps of a turn
- TRUST_API, PROJECT_API, TURN_TIMEOUT_SECONDS: shared constants

[POS]
Server pytest-only. ``tests/api/agent/conftest.py`` imports the fixtures, so ``test_workspace_hostile_folder_e2e.py``,
``test_workspace_subdirectory_rules_e2e.py`` and ``test_workspace_rules_e2e.py`` get them by name; those modules switch ``routes_and_trust`` and
``stuck_turn_report`` on with ``usefixtures``, because the other tests of the directory must not run behind the project and trust routes.
"""

from __future__ import annotations

import copy
import json
import uuid
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.messages import BaseMessage
from myrm_agent_harness.agent.security.workspace_trust import runtime as trust_runtime
from myrm_agent_harness.agent.security.workspace_trust.provider import (
    get_workspace_trust_lookup,
    set_workspace_trust_lookup,
)
from myrm_agent_harness.agent.security.workspace_trust.runtime import clear_workspace_trust_runtime
from myrm_agent_harness.agent.security.workspace_trust.types import WorkspaceTrustLevel
from myrm_agent_harness.toolkits.code_execution import create_workspace_service
from myrm_agent_harness.toolkits.llms.adapters.chat_model.model import ChatLiteLLM

from app.api.projects import router as project_router
from app.api.security import workspace_trust as workspace_trust_module
from app.config.settings import get_settings
from app.platform_utils.workspace_session import to_workspace_session_id
from app.services.security.workspace_trust_store import ConfigWorkspaceTrustLookup, get_workspace_trust_store
from tests.api.agent.utils import (
    build_approval_resume_value,
    check_e2e_errors,
    get_lite_model_selection,
    get_model_selection,
)
from tests.support.pending_task_report import report_pending_tasks_after

TRUST_API = "/api/v1/security/workspace-trust"
PROJECT_API = "/api/v1/projects"
TURN_TIMEOUT_SECONDS = 240
_APPROVAL_EVENT_TYPES = ("approval_required", "tool_approval_request")
_MAX_APPROVAL_ROUNDS = 10


@pytest.fixture
def stuck_turn_report() -> Iterator[None]:
    """The thread stacks of a run ended by the timeout show an idle loop; the tasks parked on an await say which one."""
    with report_pending_tasks_after(TURN_TIMEOUT_SECONDS - 40):
        yield


@pytest.fixture
def routes_and_trust(app: FastAPI) -> Iterator[None]:
    """The agent test app has neither the project and folder-trust routes nor the trust lookup the server registers at startup."""
    app.include_router(project_router, prefix=PROJECT_API)
    app.include_router(workspace_trust_module.router, prefix=TRUST_API)
    previous = get_workspace_trust_lookup()
    set_workspace_trust_lookup(ConfigWorkspaceTrustLookup(get_workspace_trust_store()))
    yield
    set_workspace_trust_lookup(previous)
    clear_workspace_trust_runtime()


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[list[dict[str, object]]]:
    """Every message list ChatLiteLLM sends to a provider, copied where the request is built."""
    requests: list[list[dict[str, object]]] = []
    build = ChatLiteLLM._create_message_dicts

    def record(
        self: ChatLiteLLM, messages: list[BaseMessage], stop: list[str] | None
    ) -> tuple[list[dict[str, object]], dict[str, object]]:
        message_dicts, params = build(self, messages, stop)
        requests.append(copy.deepcopy(message_dicts))
        return message_dicts, params

    monkeypatch.setattr(ChatLiteLLM, "_create_message_dicts", record)
    return requests


@pytest.fixture
def applied(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Path, WorkspaceTrustLevel]]:
    """The workspace root and trust level of every run, recorded where the run binds its trust."""
    runs: list[tuple[Path, WorkspaceTrustLevel]] = []
    apply = trust_runtime.apply_workspace_trust_for_root

    def record(workspace_root: str) -> WorkspaceTrustLevel:
        level = apply(workspace_root)
        runs.append((Path(workspace_root).resolve(), level))
        return level

    monkeypatch.setattr(trust_runtime, "apply_workspace_trust_for_root", record)
    return runs


def main_request_text(requests: Sequence[Sequence[Mapping[str, object]]], prompt: str) -> str:
    """The text of the requests that carry the question of the turn and were built before any tool result existed.

    A model that goes and reads the rule file with a tool puts the codeword into every later request, its own and the extractors' that quote the
    turn, without any rule having been injected; what was sent before that point can only hold what the server put into the prompt.
    The notes updater is left out as well because it quotes the question afterwards.
    """
    before_any_tool_result: list[Sequence[Mapping[str, object]]] = []
    for request in requests:
        if any(message.get("role") == "tool" for message in request):
            break
        before_any_tool_result.append(request)
    texts = [json.dumps(request, ensure_ascii=False) for request in before_any_tool_result]
    return "\n".join(text for text in texts if prompt in text and "Update the session notes" not in text)


async def harness_workspace(chat_id: str) -> Path:
    workspace_service = create_workspace_service(root_dir=Path(get_settings().database.harness_dir))
    workspace = await workspace_service.get_or_create(session_id=to_workspace_session_id(chat_id))
    path = Path(workspace_service.get_workspace_absolute_path(workspace))
    path.mkdir(parents=True, exist_ok=True)
    return path


def new_chat(client: TestClient) -> str:
    chat_id = f"whostile-{uuid.uuid4().hex[:10]}"
    created = client.post("/api/v1/chats/", json={"chat_id": chat_id})
    assert created.status_code == 200, created.text
    return chat_id


@contextmanager
def trusted_project_folder(client: TestClient, folder: Path, trusted_as: Path | None = None) -> Iterator[str]:
    """What a user does: bind ``folder`` to a project, put a chat in it, preview the folder and trust it with the hash that was shown.

    The folder is previewed and trusted under ``trusted_as`` when the user names it by another path than the one the project holds.
    """
    trusted_path = trusted_as or folder
    created = client.post(f"{PROJECT_API}/", json={"name": f"linked-{uuid.uuid4().hex[:8]}"})
    assert created.status_code == 200, created.text
    project_id = created.json()["data"]["project"]["id"]
    try:
        bound = client.put(f"{PROJECT_API}/{project_id}", json={"workspace_path": str(folder)})
        assert bound.status_code == 200, bound.text
        chat_id = new_chat(client)
        moved = client.patch(f"{PROJECT_API}/chats/{chat_id}/project", json={"projectId": project_id})
        assert moved.status_code == 200, moved.text
        shown = client.post(f"{TRUST_API}/manifest", json={"path": str(trusted_path)})
        assert shown.status_code == 200, shown.text
        decided = client.post(
            f"{TRUST_API}/decide",
            json={"path": str(trusted_path), "level": "TRUSTED", "manifest_hash": shown.json()["data"]["manifest_hash"]},
        )
        assert decided.status_code == 200, decided.text
        try:
            yield chat_id
        finally:
            client.delete(TRUST_API, params={"path": str(trusted_path), "remove": "true"})
    finally:
        client.delete(f"{PROJECT_API}/{project_id}")


def stream_turn(client: TestClient, request_data: dict[str, object]) -> list[dict[str, object]]:
    """Stream one agent turn and collect SSE events."""
    collected: list[dict[str, object]] = []
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


def _awaits_approval(events: Sequence[Mapping[str, object]]) -> bool:
    return any(event.get("type") in _APPROVAL_EVENT_TYPES for event in events)


def turn_request(query: str, chat_id: str, model_selection: dict[str, object] | None = None) -> dict[str, object]:
    """The request the UI sends for a question: a message id of its own and no resume."""
    return {
        "messageId": f"gast-msg-{uuid.uuid4().hex[:12]}",
        "chatId": chat_id,
        "query": query,
        "modelSelection": model_selection or get_model_selection(),
        "actionMode": "agent",
        "memoryRequireConfirmation": False,
        "enableMemoryAutoExtraction": False,
    }


def resume_request(stopped: Mapping[str, object]) -> dict[str, object]:
    """The request the UI sends when the user approves: the stopped turn's id and settings, no query, an approving resume value."""
    return {**stopped, "query": "", "resumeValue": build_approval_resume_value()}


def perform_agent_stream(
    client: TestClient,
    query: str,
    chat_id: str,
    model_selection: dict[str, object] | None = None,
) -> tuple[str, list[dict[str, object]], int]:
    """Run a turn to its end: a model that goes for a gated tool stops the turn at an approval, and each approval is approved once.

    Only the latest stream says whether an approval is pending: the events of a stream that was answered stay in ``collected``.
    A resume goes out under the id of the turn it continues, as the UI sends it, and its stream carries the continuation. The server
    refuses a second resume of one approval with 409 once the turn behind the first has ended.
    """
    request_data = turn_request(query, chat_id, model_selection)

    latest = stream_turn(client, request_data)
    collected = list(latest)
    for _ in range(_MAX_APPROVAL_ROUNDS):
        if not _awaits_approval(latest):
            break
        latest = stream_turn(client, resume_request(request_data))
        collected.extend(latest)
    assert not _awaits_approval(latest), f"the turn is still waiting for an approval after {_MAX_APPROVAL_ROUNDS} were answered"

    answer = "".join(
        str(event["data"]) for event in collected if event.get("type") in ("message", "reasoning") and event.get("data")
    )
    tool_call_count = sum(1 for event in collected if event.get("type") == "tasks_steps" and event.get("tool_name") is not None)
    return answer, collected, tool_call_count


def ask(client: TestClient, chat_id: str, prompt: str) -> str:
    """What the model said as its answer; its reasoning is left out because it repeats the question."""
    _, collected, _ = perform_agent_stream(client, prompt, chat_id, model_selection=get_lite_model_selection())
    check_e2e_errors(collected)
    return "".join(str(event.get("data", "")) for event in collected if event.get("type") == "message").upper()
