"""A fork finds the pasted texts its history names, in the workspace it will run in."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from myrm_agent_harness.agent.context_guard import KEPT_SPILLOVER_DIR, ContextGuardConfig, SpilloverEngine
from sqlalchemy import select

from app.database.models import Chat, Message
from app.services.agent.params.workspace_resolve import default_chat_workspace_path
from app.services.chat.context_bomb_guard import ContextBombDefenseService, _carry_parked_files
from app.services.chat.conversation_fork_manager import ConversationForkManager
from tests.support.oversized_paste import paste_between_the_limits, paste_over_the_limit

_PASTE = paste_over_the_limit("meeting-line: the decision was to keep watching and review next week\n")


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The default chat workspaces live under the home directory; keep them away from the real one."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    return home


@pytest.fixture(autouse=True)
def no_checkpointer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.chat.conversation_fork_manager.get_checkpointer", lambda: None, raising=False)
    from app import platform_utils

    monkeypatch.setattr(platform_utils, "get_checkpointer", lambda: None)


async def _parent_with_paste(db_session, chat_id: str, workspace: Path, **chat_fields: object) -> str:
    """A chat whose first message is a paste parked in ``workspace``; returns the path its stub names."""
    parked = ContextBombDefenseService.process_incoming_content(_PASTE, workspace_root=workspace, kept=True)
    assert parked.relative_path is not None
    db_session.add(Chat(id=chat_id, title="Parent", **chat_fields))
    db_session.add(
        Message(
            id=str(uuid4()),
            chat_id=chat_id,
            role="user",
            content=parked.processed_content,
            extra_data={"spillover": {"spillover_path": parked.relative_path, "original_char_count": len(_PASTE)}},
            sent_at=datetime.now(UTC),
            sent_timezone="UTC",
        )
    )
    await db_session.commit()
    return parked.relative_path


@pytest.mark.asyncio
async def test_a_fork_of_a_default_workspace_chat_gets_the_pasted_file_of_its_history(db_session, fake_home: Path) -> None:
    del fake_home
    parent_id = str(uuid4())
    relative_path = await _parent_with_paste(db_session, parent_id, default_chat_workspace_path(parent_id))

    result = await ConversationForkManager.fork_conversation(db=db_session, parent_chat_id=parent_id, message_index=0)

    assert result.success and result.new_chat_id is not None
    child_file = default_chat_workspace_path(result.new_chat_id) / relative_path
    assert child_file.read_text(encoding="utf-8") == _PASTE
    child_message = (await db_session.execute(select(Message).where(Message.chat_id == result.new_chat_id))).scalar_one()
    parent_message = (await db_session.execute(select(Message).where(Message.chat_id == parent_id))).scalar_one()
    assert child_message.content == parent_message.content


@pytest.mark.asyncio
async def test_a_fork_of_a_sandbox_chat_gets_the_pasted_file_in_the_repository_root_it_runs_in(
    db_session, tmp_path: Path, fake_home: Path
) -> None:
    del fake_home
    repo, worktree = tmp_path / "repo", tmp_path / "repo" / ".sandboxes" / "sandbox-abc"
    worktree.mkdir(parents=True)
    parent_id = str(uuid4())
    relative_path = await _parent_with_paste(
        db_session, parent_id, worktree, workspace_dir=str(worktree), sandbox_base_dir=str(repo)
    )

    result = await ConversationForkManager.fork_conversation(db=db_session, parent_chat_id=parent_id, message_index=0)

    assert result.success
    assert (repo / relative_path).read_text(encoding="utf-8") == _PASTE
    assert (repo / KEPT_SPILLOVER_DIR / ".gitignore").read_text(encoding="utf-8").strip() == "*"


@pytest.mark.asyncio
async def test_a_fork_that_shares_the_workspace_of_its_parent_copies_nothing(db_session, tmp_path: Path, fake_home: Path) -> None:
    del fake_home
    project = tmp_path / "project"
    parent_id = str(uuid4())
    relative_path = await _parent_with_paste(db_session, parent_id, project, workspace_dir=str(project))
    before = (project / relative_path).stat().st_mtime_ns

    result = await ConversationForkManager.fork_conversation(db=db_session, parent_chat_id=parent_id, message_index=0)

    assert result.success
    assert (project / relative_path).stat().st_mtime_ns == before
    assert len(list((project / KEPT_SPILLOVER_DIR).glob("payload_*.md"))) == 1


@pytest.mark.asyncio
async def test_a_fork_whose_parent_file_is_gone_still_succeeds(db_session, fake_home: Path) -> None:
    del fake_home
    parent_id = str(uuid4())
    relative_path = await _parent_with_paste(db_session, parent_id, default_chat_workspace_path(parent_id))
    (default_chat_workspace_path(parent_id) / relative_path).unlink()

    result = await ConversationForkManager.fork_conversation(db=db_session, parent_chat_id=parent_id, message_index=0)

    assert result.success and result.new_chat_id is not None
    assert not (default_chat_workspace_path(result.new_chat_id) / relative_path).exists()


def test_only_files_directly_under_the_kept_directory_are_carried(tmp_path: Path) -> None:
    source, target = tmp_path / "source", tmp_path / "target"
    parked = ContextBombDefenseService.process_incoming_content(_PASTE, workspace_root=source, kept=True)
    assert parked.relative_path is not None
    secret = source / "secret.md"
    # Other text than the parked one: a copy of it would land under a name of its own and show in the target.
    secret.write_text(_PASTE + " (a different file)", encoding="utf-8")

    carried = _carry_parked_files(
        source,
        target,
        [parked.relative_path, "../source/secret.md", "secret.md", f"{KEPT_SPILLOVER_DIR}/../../secret.md", "/etc/hosts"],
    )

    assert carried == 1
    assert sorted(path.name for path in target.rglob("*.md")) == [Path(parked.relative_path).name]


def test_a_file_parked_under_a_lower_limit_is_carried_all_the_same(tmp_path: Path) -> None:
    """A file parked under a lower limit than a person's is carried as well: the copy depends on no limit."""
    source, target = tmp_path / "source", tmp_path / "target"
    text = paste_between_the_limits("meeting-line: the decision was to keep watching and review next week\n")
    parked = SpilloverEngine(ContextGuardConfig(spillover_dir_name=KEPT_SPILLOVER_DIR)).process_content(text, base_dir=source)
    assert parked.payload is not None
    assert not ContextBombDefenseService.is_oversized(text)

    carried = _carry_parked_files(source, target, [parked.payload.relative_path])

    assert carried == 1
    assert (target / parked.payload.relative_path).read_text(encoding="utf-8") == text
