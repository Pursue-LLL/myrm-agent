"""A real model reads a file in a subdirectory of its workspace; the rules of that subdirectory reach it only when the workspace is trusted.

[INPUT]
- POST /api/v1/agents/agent-stream with the LITE model and its shell tool (POS: the whole server path, a real provider call, a real tool run)
- A project folder the user trusted, and a chat workspace nobody trusted (POS: the two trust levels the run binds before its first step)

[OUTPUT]
- Evidence that the run which binds its trust at its start still sees it when the tool results are built, which a streaming step that runs
  in a context of its own would not, and that the rules a repository keeps in a subdirectory follow the same trust gate as its top-level rules.

[POS]
Server real-model e2e. Needs LITE_API_KEY; the model is told which tool reads the file so that the read goes through a tool the tracker watches.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.agent.security.workspace_trust.types import WorkspaceTrustLevel

from tests.support.real_model_workspace_turns import (
    TURN_TIMEOUT_SECONDS,
    ask,
    harness_workspace,
    new_chat,
    trusted_project_folder,
)

SUBDIRECTORY_CODEWORD = "SUBDIR-4417"
NOTES = "The notes file says: hello from the notes."
DISCOVERY_MARKER = "Workspace Rules (discovered in accessed directory)"
# The tracker watches two kinds of read: a shell command that names the file, and the batch ``paths`` list of the file read tool.
READS = {
    "bash": "Run exactly this command with the bash tool: cat sub/notes.txt. Then answer with the word DONE and nothing else.",
    "file_read_tool": "Read the file sub/notes.txt with the file_read_tool. Then answer with the word DONE and nothing else.",
}
reads = pytest.mark.parametrize("prompt", list(READS.values()), ids=list(READS))

pytestmark = [
    pytest.mark.usefixtures("routes_and_trust", "stuck_turn_report"),
    pytest.mark.e2e,
    pytest.mark.skipif(sys.platform == "win32", reason="the model is told to run a POSIX shell command"),
    pytest.mark.skipif(not os.environ.get("LITE_API_KEY"), reason="E2E test requires LITE_API_KEY"),
    pytest.mark.timeout(TURN_TIMEOUT_SECONDS, method="thread"),
]


def _plant_subdirectory(workspace: Path) -> None:
    sub = workspace / "sub"
    sub.mkdir()
    (sub / "notes.txt").write_text(NOTES + "\n", encoding="utf-8")
    (sub / "AGENTS.md").write_text(
        f"Subdirectory Convention: the subdirectory codeword is {SUBDIRECTORY_CODEWORD}.\n", encoding="utf-8"
    )


def _tool_results(requests: Sequence[Sequence[Mapping[str, object]]]) -> str:
    """Everything the model was shown as the result of a tool, over all the requests of the turn."""
    return "\n".join(
        json.dumps(message, ensure_ascii=False) for request in requests for message in request if message.get("role") == "tool"
    )


@reads
def test_a_trusted_project_folder_hands_the_rules_of_a_subdirectory_to_the_model_with_the_file_it_read(
    client: TestClient,
    sent: list[list[dict[str, object]]],
    applied: list[tuple[Path, WorkspaceTrustLevel]],
    tmp_path: Path,
    prompt: str,
) -> None:
    folder = tmp_path / "linked"
    folder.mkdir()
    _plant_subdirectory(folder)

    with trusted_project_folder(client, folder) as chat_id:
        ask(client, chat_id, prompt)

    results = _tool_results(sent)
    assert (folder.resolve(), WorkspaceTrustLevel.TRUSTED) in applied
    assert "hello from the notes" in results, "the model never read the file"
    assert DISCOVERY_MARKER in results
    assert SUBDIRECTORY_CODEWORD in results


@reads
@pytest.mark.asyncio
async def test_a_chat_workspace_nobody_trusted_does_not_hand_the_rules_of_a_subdirectory_to_the_model(
    client: TestClient, sent: list[list[dict[str, object]]], applied: list[tuple[Path, WorkspaceTrustLevel]], prompt: str
) -> None:
    chat_id = new_chat(client)
    workspace = await harness_workspace(chat_id)
    _plant_subdirectory(workspace)

    ask(client, chat_id, prompt)

    results = _tool_results(sent)
    assert (workspace.resolve(), WorkspaceTrustLevel.RESTRICTED) in applied
    assert "hello from the notes" in results, "the model never read the file, so nothing was tested"
    assert DISCOVERY_MARKER not in results
    assert SUBDIRECTORY_CODEWORD not in results
