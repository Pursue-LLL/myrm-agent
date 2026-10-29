"""Real-model agent turns in workspaces that also hold the files of a hostile repository.

[INPUT]
- POST /api/v1/agents/agent-stream with the LITE model (POS: the whole server path, a real provider call, SSE back)
- A folder the user links to a project, previews and trusts through the project and folder-trust API (POS: the workspace root of the turn;
  it may also hold a FIFO ``SKILL.md``, sparse config files, an oversized rule file or a rule file that links out of the folder)
- The workspace trust each run applies and the messages ChatLiteLLM sends to the provider (POS: recorded where they are decided and built)

[OUTPUT]
- Fails when the folder preview does not return, when the stream reports an error event, when a turn does not finish or does not answer,
  when a run does not apply the trust the user decided for its folder, when the rules of a trusted folder do not reach the provider
  request (or an oversized or linked-out rule file reaches it as content instead of its placeholder), or when the rules of a chat
  workspace nobody trusted do.

[POS]
Trusting a folder of hostile files starts with its preview, which reads the folder's skills, rules and config: on a source without the
bounded reads that preview never returns. The turn that follows has to run at the level the user decided, and that level has to still
hold where the rules are put into the request. The chat workspace nobody trusted is the contrast: its rules stay out of the request.
"""

from __future__ import annotations

import copy
import json
import os
import sys
import uuid
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
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
from tests.api.agent.test_workspace_rules_e2e import perform_agent_stream
from tests.api.agent.utils import check_e2e_errors, get_lite_model_selection

SPARSE_BYTES = 64 * 1024 * 1024
CODEWORD = "KRAKATOA-7731"
TRUST_API = "/api/v1/security/workspace-trust"
PROJECT_API = "/api/v1/projects"
BLOCKED_PLACEHOLDER = "[BLOCKED: AGENTS.md"
# Longer than the 256_000 characters a rule file may have before it is refused instead of truncated.
OVERSIZED_RULE_CHARS = 300_000
PROMPT = "Do not use any tools. What is the project codeword? Answer with the codeword only."

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(sys.platform == "win32", reason="FIFOs and sparse files are POSIX"),
    pytest.mark.skipif(not os.environ.get("LITE_API_KEY"), reason="E2E test requires LITE_API_KEY"),
    # A blocked read stalls the turn inside the event loop; the thread method ends the run with a stack dump.
    pytest.mark.timeout(240, method="thread"),
]


@pytest.fixture(autouse=True)
def _routes_and_trust(app: FastAPI) -> Iterator[None]:
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
        self: ChatLiteLLM, messages: list[object], stop: list[str] | None
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


def _main_request_text(requests: Sequence[Sequence[Mapping[str, object]]]) -> str:
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
    return "\n".join(text for text in texts if PROMPT in text and "Update the session notes" not in text)


async def _harness_workspace(chat_id: str) -> Path:
    workspace_service = create_workspace_service(root_dir=Path(get_settings().database.harness_dir))
    workspace = await workspace_service.get_or_create(session_id=to_workspace_session_id(chat_id))
    path = Path(workspace_service.get_workspace_absolute_path(workspace))
    path.mkdir(parents=True, exist_ok=True)
    return path


def _codeword_rule() -> str:
    return (
        f"Project Convention: the project codeword is {CODEWORD}. When the user asks for the project codeword, "
        "answer with exactly that word.\n"
    )


def _plant_hostile_files(workspace: Path) -> None:
    (workspace / "AGENTS.md").write_text(_codeword_rule(), encoding="utf-8")
    honest = workspace / "skills" / "honest"
    honest.mkdir(parents=True)
    (honest / "SKILL.md").write_text(
        "---\nname: honest\ndescription: A skill the folder really ships.\n---\n\nBody.\n", encoding="utf-8"
    )
    hostile = workspace / "skills" / "hostile"
    hostile.mkdir()
    os.mkfifo(hostile / "SKILL.md")
    (workspace / ".myrm").mkdir()
    for sparse in (workspace / "mcp.json", workspace / ".myrm" / "config.toml"):
        with sparse.open("wb") as handle:
            handle.truncate(SPARSE_BYTES)


def _new_chat(client: TestClient) -> str:
    chat_id = f"whostile-{uuid.uuid4().hex[:10]}"
    created = client.post("/api/v1/chats/", json={"chat_id": chat_id})
    assert created.status_code == 200, created.text
    return chat_id


@contextmanager
def _trusted_project_folder(client: TestClient, folder: Path) -> Iterator[str]:
    """What a user does: bind ``folder`` to a project, put a chat in it, preview the folder and trust it with the hash that was shown."""
    created = client.post(f"{PROJECT_API}/", json={"name": f"linked-{uuid.uuid4().hex[:8]}"})
    assert created.status_code == 200, created.text
    project_id = created.json()["data"]["project"]["id"]
    try:
        bound = client.put(f"{PROJECT_API}/{project_id}", json={"workspace_path": str(folder)})
        assert bound.status_code == 200, bound.text
        chat_id = _new_chat(client)
        moved = client.patch(f"{PROJECT_API}/chats/{chat_id}/project", json={"projectId": project_id})
        assert moved.status_code == 200, moved.text
        shown = client.post(f"{TRUST_API}/manifest", json={"path": str(folder)})
        assert shown.status_code == 200, shown.text
        decided = client.post(
            f"{TRUST_API}/decide",
            json={"path": str(folder), "level": "TRUSTED", "manifest_hash": shown.json()["data"]["manifest_hash"]},
        )
        assert decided.status_code == 200, decided.text
        try:
            yield chat_id
        finally:
            client.delete(TRUST_API, params={"path": str(folder), "remove": "true"})
    finally:
        client.delete(f"{PROJECT_API}/{project_id}")


def _ask(client: TestClient, chat_id: str) -> str:
    """What the model said as its answer; its reasoning is left out because it repeats the question."""
    _, collected, _ = perform_agent_stream(client, PROMPT, chat_id, model_selection=get_lite_model_selection())
    check_e2e_errors(collected)
    return "".join(str(event.get("data", "")) for event in collected if event.get("type") == "message").upper()


@pytest.mark.asyncio
async def test_a_chat_workspace_nobody_trusted_keeps_its_rules_out_of_the_request(
    client: TestClient, sent: list[list[dict[str, object]]], applied: list[tuple[Path, WorkspaceTrustLevel]]
) -> None:
    chat_id = _new_chat(client)
    workspace = await _harness_workspace(chat_id)
    _plant_hostile_files(workspace)

    answer = _ask(client, chat_id)

    assert answer
    assert (workspace.resolve(), WorkspaceTrustLevel.RESTRICTED) in applied
    request = _main_request_text(sent)
    assert request, "the question of the turn never reached a provider"
    assert CODEWORD not in request


def test_a_trusted_project_folder_with_hostile_files_delivers_its_rules_and_finishes_its_turn(
    client: TestClient,
    sent: list[list[dict[str, object]]],
    applied: list[tuple[Path, WorkspaceTrustLevel]],
    tmp_path: Path,
) -> None:
    folder = tmp_path / "linked"
    folder.mkdir()
    _plant_hostile_files(folder)

    with _trusted_project_folder(client, folder) as chat_id:
        answer = _ask(client, chat_id)

    assert (folder.resolve(), WorkspaceTrustLevel.TRUSTED) in applied
    assert CODEWORD in _main_request_text(sent)
    assert CODEWORD in answer


def test_a_rule_file_over_the_size_limit_reaches_a_trusted_run_as_its_placeholder(
    client: TestClient, sent: list[list[dict[str, object]]], tmp_path: Path
) -> None:
    folder = tmp_path / "linked"
    folder.mkdir()
    (folder / "AGENTS.md").write_text(_codeword_rule() + "x" * OVERSIZED_RULE_CHARS, encoding="utf-8")

    with _trusted_project_folder(client, folder) as chat_id:
        _ask(client, chat_id)

    request = _main_request_text(sent)
    assert BLOCKED_PLACEHOLDER in request
    assert CODEWORD not in request


def test_a_rule_file_that_links_out_of_the_folder_reaches_a_trusted_run_as_its_placeholder(
    client: TestClient, sent: list[list[dict[str, object]]], tmp_path: Path
) -> None:
    outside = tmp_path / "outside.md"
    outside.write_text(_codeword_rule(), encoding="utf-8")
    folder = tmp_path / "linked"
    folder.mkdir()
    os.symlink(outside, folder / "AGENTS.md")

    with _trusted_project_folder(client, folder) as chat_id:
        _ask(client, chat_id)

    request = _main_request_text(sent)
    assert BLOCKED_PLACEHOLDER in request
    assert CODEWORD not in request
