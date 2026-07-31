"""Unit and service tests for context branch snapshot fork."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Chat, Message
from app.services.chat.context_branch_fork import (
    ContextBranchForkService,
    _parse_snapshot_messages,
    _resolve_snapshot_path,
)
from app.services.chat.conversation_recall_index_service import ConversationRecallIndexService


def test_parse_snapshot_messages_skips_meta_and_maps_roles() -> None:
    payload = "\n".join(
        [
            json.dumps({"_meta": True, "message_count": 2}),
            json.dumps({"type": "human", "content": "Hello"}),
            json.dumps({"type": "ai", "content": "Hi there"}),
            json.dumps({"type": "unknown", "content": "skip me"}),
        ]
    )
    parsed = _parse_snapshot_messages(payload)
    assert len(parsed) == 2
    assert parsed[0]["role"] == "user"
    assert parsed[0]["content"] == "Hello"
    assert parsed[1]["role"] == "assistant"


def test_resolve_snapshot_path_finds_relative_context_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import myrm_agent_harness.runtime.context.context_branches as branches_module
    import myrm_agent_harness.runtime.execution_paths as execution_paths

    root = tmp_path / "persistent"
    root.mkdir()
    rel = ".context/chat-1/snapshots/pre.jsonl"
    target = root / ".context" / "chat-1" / "snapshots" / "pre.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("{}", encoding="utf-8")

    root_str = str(root)
    monkeypatch.setattr(execution_paths, "PERSISTENT_ROOT", root_str)
    monkeypatch.setattr(execution_paths, "CONTEXT_ROOT", f"{root_str}/.context")
    monkeypatch.setattr(branches_module, "PERSISTENT_ROOT", root_str)

    resolved = _resolve_snapshot_path("chat-1", rel)
    assert resolved.is_file()


@pytest.mark.asyncio
async def test_fork_from_branch_creates_child_chat(
    db_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import myrm_agent_harness.runtime.context.context_branches as branches_module
    import myrm_agent_harness.runtime.context.context_branches as branches_write
    import myrm_agent_harness.runtime.execution_paths as execution_paths

    async def _noop_rebuild(_db: object, _chat_id: str) -> None:
        return None

    monkeypatch.setattr(ConversationRecallIndexService, "rebuild_chat", _noop_rebuild)

    root = tmp_path / "persistent"
    root.mkdir()
    root_str = str(root)
    monkeypatch.setattr(execution_paths, "PERSISTENT_ROOT", root_str)
    monkeypatch.setattr(execution_paths, "CONTEXT_ROOT", f"{root_str}/.context")
    monkeypatch.setattr(branches_module, "PERSISTENT_ROOT", root_str)
    monkeypatch.setattr(branches_write, "PERSISTENT_ROOT", root_str)

    chat_id = "chat-branch-fork-1"
    db_session.add(
        Chat(
            id=chat_id,
            title="Parent chat",
            action_mode="agent",
            source="web",
        )
    )
    await db_session.commit()

    snapshot_rel = f".context/{chat_id}/snapshots/pre-compact.jsonl"
    snapshot_file = root / ".context" / chat_id / "snapshots" / "pre-compact.jsonl"
    snapshot_file.parent.mkdir(parents=True, exist_ok=True)
    snapshot_file.write_text(
        "\n".join(
            [
                json.dumps({"_meta": True, "message_count": 2}),
                json.dumps({"type": "human", "content": "Question before compact"}),
                json.dumps({"type": "ai", "content": "Answer before compact"}),
            ]
        ),
        encoding="utf-8",
    )

    branch = branches_write.append_context_branch(
        chat_id,
        snapshot_path=snapshot_rel,
        label="Before compact",
    )

    result = await ContextBranchForkService.fork_from_branch(
        db_session,
        chat_id,
        branch.branch_id,
        new_title="Recovered branch",
    )
    assert result.success is True
    assert result.new_chat_id is not None
    assert result.message_count == 2

    child = await db_session.get(Chat, result.new_chat_id)
    assert child is not None
    assert child.title == "Recovered branch"
    assert child.compacted_summary is None

    count_stmt = select(func.count(Message.id)).where(Message.chat_id == result.new_chat_id)
    count = (await db_session.execute(count_stmt)).scalar_one()
    assert count == 2


def test_resolve_snapshot_path_rejects_empty_path() -> None:
    with pytest.raises(ValueError, match="snapshot_path is empty"):
        _resolve_snapshot_path("chat-1", "   ")


def test_resolve_snapshot_path_supports_absolute_path(tmp_path: Path) -> None:
    snapshot = tmp_path / "absolute.jsonl"
    snapshot.write_text("{}", encoding="utf-8")
    resolved = _resolve_snapshot_path("chat-1", str(snapshot))
    assert resolved == snapshot


def test_parse_snapshot_messages_handles_multimodal_and_null_content() -> None:
    payload = "\n".join(
        [
            json.dumps({"type": "human", "content": None}),
            json.dumps(
                {
                    "type": "ai",
                    "content": [{"type": "text", "text": "part-a"}, "part-b"],
                    "tool_calls": [{"id": "call_1"}],
                }
            ),
        ]
    )
    parsed = _parse_snapshot_messages(payload)
    assert len(parsed) == 2
    assert parsed[0]["content"] == ""
    assert parsed[1]["content"] == "part-a\npart-b"
    assert parsed[1]["extra_data"] == {"tool_calls": [{"id": "call_1"}]}


@pytest.mark.asyncio
async def test_fork_from_branch_returns_error_when_bookmark_missing(
    db_session: AsyncSession,
) -> None:
    result = await ContextBranchForkService.fork_from_branch(
        db_session,
        "missing-chat",
        "missing-branch",
    )
    assert result.success is False
    assert result.error == "Bookmark not found"


@pytest.mark.asyncio
async def test_fork_from_branch_returns_error_when_snapshot_has_no_messages(
    db_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import myrm_agent_harness.runtime.context.context_branches as branches_module
    import myrm_agent_harness.runtime.execution_paths as execution_paths

    root = tmp_path / "persistent"
    root.mkdir()
    root_str = str(root)
    monkeypatch.setattr(execution_paths, "PERSISTENT_ROOT", root_str)
    monkeypatch.setattr(execution_paths, "CONTEXT_ROOT", f"{root_str}/.context")
    monkeypatch.setattr(branches_module, "PERSISTENT_ROOT", root_str)

    chat_id = "chat-empty-snapshot"
    db_session.add(
        Chat(
            id=chat_id,
            title="Parent chat",
            action_mode="agent",
            source="web",
        )
    )
    await db_session.commit()

    snapshot_rel = f".context/{chat_id}/snapshots/empty.jsonl"
    snapshot_file = root / ".context" / chat_id / "snapshots" / "empty.jsonl"
    snapshot_file.parent.mkdir(parents=True, exist_ok=True)
    snapshot_file.write_text(json.dumps({"_meta": True, "message_count": 0}), encoding="utf-8")

    branch = branches_module.append_context_branch(
        chat_id,
        snapshot_path=snapshot_rel,
        label="Empty snapshot",
    )

    result = await ContextBranchForkService.fork_from_branch(
        db_session,
        chat_id,
        branch.branch_id,
    )
    assert result.success is False
    assert result.error == "Snapshot contains no messages"
