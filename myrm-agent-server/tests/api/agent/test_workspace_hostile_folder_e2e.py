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
A turn that stops answering writes the tasks it is parked on to stderr before the thread timeout ends the run.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.agent.security.workspace_trust.types import WorkspaceTrustLevel

from tests.support.real_model_workspace_turns import (
    TRUST_API,
    TURN_TIMEOUT_SECONDS,
    ask,
    harness_workspace,
    main_request_text,
    new_chat,
    trusted_project_folder,
)

SPARSE_BYTES = 64 * 1024 * 1024
CODEWORD = "KRAKATOA-7731"
BLOCKED_PLACEHOLDER = "[BLOCKED: AGENTS.md"
# Longer than the 256_000 characters a rule file may have before it is refused instead of truncated.
OVERSIZED_RULE_CHARS = 300_000
PROMPT = "Do not use any tools. What is the project codeword? Answer with the codeword only."

pytestmark = [
    pytest.mark.usefixtures("routes_and_trust", "stuck_turn_report", "approval_trail"),
    pytest.mark.e2e,
    pytest.mark.skipif(sys.platform == "win32", reason="FIFOs and sparse files are POSIX"),
    pytest.mark.skipif(not os.environ.get("LITE_API_KEY"), reason="E2E test requires LITE_API_KEY"),
    # A blocked read stalls the turn inside the event loop; the thread method ends the run with a stack dump.
    pytest.mark.timeout(TURN_TIMEOUT_SECONDS, method="thread"),
]


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


@pytest.mark.asyncio
async def test_a_chat_workspace_nobody_trusted_keeps_its_rules_out_of_the_request(
    client: TestClient, sent: list[list[dict[str, object]]], applied: list[tuple[Path, WorkspaceTrustLevel]]
) -> None:
    chat_id = new_chat(client)
    workspace = await harness_workspace(chat_id)
    _plant_hostile_files(workspace)

    answer = ask(client, chat_id, PROMPT)

    assert answer
    assert (workspace.resolve(), WorkspaceTrustLevel.RESTRICTED) in applied
    request = main_request_text(sent, PROMPT)
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

    with trusted_project_folder(client, folder) as chat_id:
        answer = ask(client, chat_id, PROMPT)

    assert (folder.resolve(), WorkspaceTrustLevel.TRUSTED) in applied
    assert CODEWORD in main_request_text(sent, PROMPT)
    assert CODEWORD in answer


def test_a_rule_file_over_the_size_limit_reaches_a_trusted_run_as_its_placeholder(
    client: TestClient, sent: list[list[dict[str, object]]], tmp_path: Path
) -> None:
    folder = tmp_path / "linked"
    folder.mkdir()
    (folder / "AGENTS.md").write_text(_codeword_rule() + "x" * OVERSIZED_RULE_CHARS, encoding="utf-8")

    with trusted_project_folder(client, folder) as chat_id:
        ask(client, chat_id, PROMPT)

    request = main_request_text(sent, PROMPT)
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

    with trusted_project_folder(client, folder) as chat_id:
        ask(client, chat_id, PROMPT)

    request = main_request_text(sent, PROMPT)
    assert BLOCKED_PLACEHOLDER in request
    assert CODEWORD not in request


def test_a_trusted_folder_named_in_chinese_with_a_space_delivers_its_chinese_rule_file_with_crlf_line_ends(
    client: TestClient,
    sent: list[list[dict[str, object]]],
    applied: list[tuple[Path, WorkspaceTrustLevel]],
    tmp_path: Path,
) -> None:
    """A folder as a Chinese-speaking user keeps it: its name, its rule file's language and a Windows editor's line ends."""
    folder = tmp_path / "我的 项目"
    folder.mkdir()
    rule_lines = [f"项目约定: 本项目的暗号是 {CODEWORD}.", "用户询问项目暗号时, 只回答这个词."]
    (folder / "AGENTS.md").write_bytes("".join(f"{line}\r\n" for line in rule_lines).encode())

    with trusted_project_folder(client, folder) as chat_id:
        answer = ask(client, chat_id, PROMPT)

    assert (folder.resolve(), WorkspaceTrustLevel.TRUSTED) in applied
    request = main_request_text(sent, PROMPT)
    assert CODEWORD in request
    assert "项目约定" in request
    assert CODEWORD in answer


def test_trust_removed_between_two_turns_of_a_chat_applies_to_the_next_turn(
    client: TestClient, applied: list[tuple[Path, WorkspaceTrustLevel]], tmp_path: Path
) -> None:
    """A user who withdraws trust from a folder does not have to start another chat for the next turn to stop trusting it."""
    folder = tmp_path / "linked"
    folder.mkdir()
    (folder / "AGENTS.md").write_text(_codeword_rule(), encoding="utf-8")

    with trusted_project_folder(client, folder) as chat_id:
        ask(client, chat_id, PROMPT)
        assert applied[-1] == (folder.resolve(), WorkspaceTrustLevel.TRUSTED)

        removed = client.delete(TRUST_API, params={"path": str(folder), "remove": "true"})
        assert removed.status_code == 200, removed.text
        ask(client, chat_id, PROMPT)

    assert [level for root, level in applied if root == folder.resolve()] == [
        WorkspaceTrustLevel.TRUSTED,
        WorkspaceTrustLevel.RESTRICTED,
    ]


@pytest.mark.parametrize(
    ("project_holds_the_link", "user_trusts_the_link"),
    [(True, True), (True, False), (False, True)],
    ids=[
        "project-and-trust-name-the-link",
        "project-names-the-link-trust-names-the-folder",
        "project-names-the-folder-trust-names-the-link",
    ],
)
def test_a_folder_named_through_a_symlink_is_trusted_as_the_folder_it_points_to(
    client: TestClient,
    sent: list[list[dict[str, object]]],
    applied: list[tuple[Path, WorkspaceTrustLevel]],
    tmp_path: Path,
    project_holds_the_link: bool,
    user_trusts_the_link: bool,
) -> None:
    """A project folder that lives behind a symlink (``/tmp``, a mounted volume) is the same folder however the user names it."""
    folder = tmp_path / "real"
    folder.mkdir()
    (folder / "AGENTS.md").write_text(_codeword_rule(), encoding="utf-8")
    link = tmp_path / "link"
    link.symlink_to(folder, target_is_directory=True)

    with trusted_project_folder(
        client, link if project_holds_the_link else folder, trusted_as=link if user_trusts_the_link else folder
    ) as chat_id:
        answer = ask(client, chat_id, PROMPT)

    assert answer
    assert (folder.resolve(), WorkspaceTrustLevel.TRUSTED) in applied
    assert CODEWORD in main_request_text(sent, PROMPT)
