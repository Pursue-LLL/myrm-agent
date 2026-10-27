"""An oversized user message is parked in a file that lives as long as the chat's workspace, and chat lists show its preview."""

from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from myrm_agent_harness.agent.context_guard import KEPT_SPILLOVER_DIR, ContextGuardConfig
from myrm_agent_harness.agent.security.checks import check_path_policy
from myrm_agent_harness.agent.security.types import PathPolicy, PermissionAction
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.dto import MessageDTO
from app.services.agent.context_guard_service import ContextGuardService
from app.services.agent.params.workspace_resolve import default_chat_workspace_path, resolve_default_chat_workspace_dir
from app.services.chat.chat_service import ChatService
from app.services.chat.context_bomb_guard import ContextBombDefenseService
from tests.support.oversized_paste import paste_between_the_limits, paste_over_the_limit

_PASTE = paste_over_the_limit("meeting-line: the decision was to keep watching and review next week\n")


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The default spill directory lives under the home directory; keep it away from the real one."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    return home


async def _append(chat_id: str, role: str, content: str, *, spill_workspace: Path) -> MessageDTO:
    return await ChatService.append_message(chat_id, role, content, datetime.now(UTC), "UTC", spill_workspace=spill_workspace)


async def _channel_chat_id() -> str:
    return (await ChatService.get_or_create_channel_chat("test:spill-workspace", "test")).id


@pytest.mark.asyncio
async def test_oversized_user_message_is_parked_in_the_named_workspace(
    db_session: AsyncSession, tmp_path: Path, fake_home: Path
) -> None:
    del db_session
    workspace = tmp_path / "agent-workspace"
    message = await _append(await _channel_chat_id(), "user", _PASTE, spill_workspace=workspace)

    (parked,) = list((workspace / ".myrm" / "pastes").glob("payload_*.md"))
    assert parked.read_text(encoding="utf-8") == _PASTE
    assert message.content.startswith("<file_spillover")
    assert f"{KEPT_SPILLOVER_DIR}/{parked.name}" in message.content
    assert str(workspace) not in message.content
    assert "file_read_tool" in message.content
    assert message.extra_data is not None
    spillover = message.extra_data["spillover"]
    assert isinstance(spillover, dict)
    assert spillover["spillover_path"] == f"{KEPT_SPILLOVER_DIR}/{parked.name}"
    assert spillover["original_char_count"] == len(_PASTE)
    assert spillover["preview"] == _PASTE[: len(str(spillover["preview"]))]
    assert 0 < len(str(spillover["preview"])) <= ContextGuardConfig().preview_chars
    assert not (fake_home / ".myrm").exists()


@pytest.mark.asyncio
async def test_small_user_message_is_stored_verbatim_and_writes_nothing(
    db_session: AsyncSession, tmp_path: Path, fake_home: Path
) -> None:
    del db_session
    workspace = tmp_path / "agent-workspace"
    message = await _append(await _channel_chat_id(), "user", "short question", spill_workspace=workspace)

    assert message.content == "short question"
    assert message.extra_data is None
    assert not workspace.exists()
    assert not (fake_home / ".myrm").exists()


@pytest.mark.asyncio
async def test_assistant_message_is_never_spilled(db_session: AsyncSession, tmp_path: Path, fake_home: Path) -> None:
    del db_session
    workspace = tmp_path / "agent-workspace"
    message = await _append(await _channel_chat_id(), "assistant", _PASTE, spill_workspace=workspace)

    assert message.content == _PASTE
    assert not workspace.exists()
    assert not (fake_home / ".myrm").exists()


def _age(path: Path, days: int) -> None:
    then = time.time() - days * 86_400
    os.utime(path, (then, then))


@pytest.mark.asyncio
async def test_a_message_within_the_limit_of_a_person_is_stored_as_it_is(
    db_session: AsyncSession, tmp_path: Path, fake_home: Path
) -> None:
    del db_session, fake_home
    workspace = tmp_path / "agent-workspace"
    text = paste_between_the_limits("meeting-line: the decision was to keep watching and review next week\n")

    message = await _append(await _channel_chat_id(), "user", text, spill_workspace=workspace)

    assert message.content == text
    assert message.extra_data is None or "spillover" not in message.extra_data
    assert not workspace.exists()


@pytest.mark.asyncio
async def test_a_parked_paste_outlives_the_housekeeping_sweep_that_clears_transient_spill(
    db_session: AsyncSession, tmp_path: Path, fake_home: Path
) -> None:
    """The database keeps only a preview of the paste, so the file is the only copy of it."""
    del db_session
    workspaces_root = tmp_path / "workspaces"
    workspace = workspaces_root / "chat_parked"
    await _append(await _channel_chat_id(), "user", _PASTE, spill_workspace=workspace)
    transient = ContextBombDefenseService.process_incoming_content("ephemeral\n" * 3000, workspace_root=workspace)
    (parked,) = list((workspace / ".myrm" / "pastes").glob("payload_*.md"))
    assert transient.spillover_path is not None
    _age(parked, 2)
    _age(Path(transient.spillover_path), 2)

    ContextGuardService.sweep_all_workspaces(workspaces_root)

    assert parked.read_text(encoding="utf-8") == _PASTE
    assert not Path(transient.spillover_path).exists()


@pytest.mark.asyncio
async def test_the_agent_reads_a_parked_paste_without_asking_for_approval(
    db_session: AsyncSession, tmp_path: Path, fake_home: Path
) -> None:
    del db_session
    workspace = tmp_path / "agent-workspace"
    message = await _append(await _channel_chat_id(), "user", _PASTE, spill_workspace=workspace)
    assert message.extra_data is not None
    spillover = message.extra_data["spillover"]
    assert isinstance(spillover, dict)

    action, _ = check_path_policy(str(workspace / str(spillover["spillover_path"])), PathPolicy(), str(workspace))

    assert action is PermissionAction.ALLOW


@pytest.mark.asyncio
async def test_chat_lists_show_the_start_of_the_paste_not_the_pointer(
    db_session: AsyncSession, tmp_path: Path, fake_home: Path
) -> None:
    del db_session
    chat_id = await _channel_chat_id()

    await _append(chat_id, "user", _PASTE, spill_workspace=tmp_path / "agent-workspace")

    chat = await ChatService.get_chat_metadata(chat_id)
    assert chat is not None
    assert chat.title == _PASTE[:50]
    assert chat.last_message == _PASTE[:100]
    assert chat.first_message is not None
    assert chat.first_message.startswith("meeting-line: the decision")
    assert "file_spillover" not in chat.first_message


@pytest.mark.asyncio
async def test_a_web_paste_is_parked_in_the_chat_workspace_not_the_home_directory(
    db_session: AsyncSession, fake_home: Path
) -> None:
    """The Web path names no workspace: the chat's own one is looked up, new chat or not."""
    del db_session
    chat_id = str(uuid4())

    message = await ChatService.ensure_chat_and_append_user_message(chat_id, _PASTE, datetime.now(UTC), "UTC")

    (parked,) = list((default_chat_workspace_path(chat_id) / ".myrm" / "pastes").glob("payload_*.md"))
    assert parked.read_text(encoding="utf-8") == _PASTE
    assert message.content.startswith("<file_spillover")
    assert not (fake_home / ".myrm").exists()
    chat = await ChatService.get_chat_metadata(chat_id)
    assert chat is not None
    assert chat.title == _PASTE[:50]


@pytest.mark.asyncio
async def test_the_sandbox_a_run_creates_adopts_the_directory_that_already_holds_a_paste(
    db_session: AsyncSession, fake_home: Path
) -> None:
    del db_session, fake_home
    chat_id = str(uuid4())
    await ChatService.ensure_chat_and_append_user_message(chat_id, _PASTE, datetime.now(UTC), "UTC")
    (parked,) = list((default_chat_workspace_path(chat_id) / ".myrm" / "pastes").glob("payload_*.md"))

    created = await resolve_default_chat_workspace_dir(chat_id, persist_workspace=False)

    assert created is not None
    assert Path(created).resolve() == default_chat_workspace_path(chat_id).resolve()
    assert parked.read_text(encoding="utf-8") == _PASTE


@pytest.mark.asyncio
async def test_a_short_web_message_costs_no_workspace_lookup_and_writes_nothing(
    db_session: AsyncSession, fake_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del db_session
    from app.services.chat import effective_workspace

    async def forbidden(_chat_id: str) -> Path | None:
        raise AssertionError("a short message has no file to place")

    monkeypatch.setattr(effective_workspace, "find_chat_workspace_root", forbidden)
    chat_id = str(uuid4())

    message = await ChatService.ensure_chat_and_append_user_message(chat_id, "short question", datetime.now(UTC), "UTC")

    assert message.content == "short question"
    assert not default_chat_workspace_path(chat_id).exists()
    assert not (fake_home / ".myrm").exists()


@pytest.mark.asyncio
async def test_a_parked_paste_stays_out_of_the_version_control_of_a_project_workspace(
    db_session: AsyncSession, tmp_path: Path, fake_home: Path
) -> None:
    """The workspace of a chat can be a git project; a parked paste must not show up in its status."""
    del db_session, fake_home
    project = tmp_path / "project"
    project.mkdir()
    subprocess.run(["git", "init", "-q", str(project)], check=True)

    await _append(await _channel_chat_id(), "user", _PASTE, spill_workspace=project)

    assert (project / ".myrm" / "pastes").is_dir()
    status = subprocess.run(["git", "-C", str(project), "status", "--porcelain"], check=True, capture_output=True, text=True)
    assert status.stdout == ""


@pytest.mark.asyncio
async def test_a_paste_sent_with_an_attachment_reaches_neither_the_row_nor_the_replayed_history_in_full(
    db_session: AsyncSession, fake_home: Path
) -> None:
    """A query with an image keeps its blocks in ``original_query``; the text block of it is the paste again."""
    del db_session, fake_home
    chat_id = str(uuid4())
    image = {"type": "image_url", "image_url": {"url": "file:///tmp/shot.png"}}
    query = [{"type": "text", "text": _PASTE}, image]

    message = await ChatService.ensure_chat_and_append_user_message(
        chat_id, _PASTE, datetime.now(UTC), "UTC", extra_data={"original_query": query}
    )
    history = await ChatService.load_web_chat_history(chat_id)

    assert json.dumps(_PASTE)[1:-1] not in json.dumps(message.extra_data)
    (human,) = [entry for entry in history if entry[0] == "human"]
    replayed = human[1]
    assert isinstance(replayed, list)
    assert image in replayed
    texts = [block["text"] for block in replayed if block.get("type") == "text"]
    assert len(texts) == 1
    assert texts[0] == message.content
    assert (default_chat_workspace_path(chat_id) / ".myrm" / "pastes").is_dir()


@pytest.mark.asyncio
async def test_a_message_stays_whole_in_the_conversation_when_its_file_cannot_be_written(
    db_session: AsyncSession, tmp_path: Path, fake_home: Path
) -> None:
    """Losing the person's message is worse than carrying it in the database."""
    del db_session, fake_home
    blocked = tmp_path / "not-a-directory"
    blocked.write_text("a file where the workspace should be", encoding="utf-8")

    message = await _append(await _channel_chat_id(), "user", _PASTE, spill_workspace=blocked)

    assert message.content == _PASTE
    assert message.extra_data is None


@pytest.mark.asyncio
async def test_the_recall_index_gets_the_readable_start_of_a_paste_not_its_stub(
    db_session: AsyncSession, fake_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A search over past conversations can only match words a person could have typed."""
    del db_session, fake_home
    from app.services.chat.conversation_recall_index_service import ConversationRecallIndexService

    indexed: list[str] = []

    async def record(*_args: object, content: str, **_kwargs: object) -> None:
        indexed.append(content)

    monkeypatch.setattr(ConversationRecallIndexService, "append_message", record)

    message = await ChatService.ensure_chat_and_append_user_message(str(uuid4()), _PASTE, datetime.now(UTC), "UTC")

    assert message.content.startswith("<file_spillover")
    (text,) = indexed
    assert text.startswith("meeting-line: the decision")
    assert "file_spillover" not in text


@pytest.mark.asyncio
async def test_a_paste_of_a_chat_without_any_workspace_stays_in_the_database(
    db_session: AsyncSession, fake_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no directory the agent's file tools could read from, a stub would point at nothing."""
    del db_session, fake_home
    from app.services.chat import effective_workspace

    async def no_workspace(_chat_id: str) -> None:
        return None

    monkeypatch.setattr(effective_workspace, "find_chat_workspace_root", no_workspace)

    message = await ChatService.ensure_chat_and_append_user_message(str(uuid4()), _PASTE, datetime.now(UTC), "UTC")

    assert message.content == _PASTE
    assert message.extra_data is None
