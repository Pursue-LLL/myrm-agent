"""The folder a viewer picked before the chat existed is written together with the chat row."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.chat import Chat
from app.services.agent.params import AgentRequest, workspace_resolve
from app.services.agent.params.conversion.chat_context import resolve_chat_context
from app.services.agent.stream_session.chat_history_bootstrap import persist_user_message
from app.services.agent.stream_session.lazy_session_gate import commit_lazy_session_barrier
from app.services.agent.stream_session.turn_workspace_bind import bind_turn_workspace
from app.services.chat.chat_service import ChatService


async def _row(db: AsyncSession, chat_id: str) -> Chat:
    result = await db.execute(select(Chat).where(Chat.id == chat_id))
    return result.scalar_one()


@pytest.mark.asyncio
async def test_the_first_turn_workspace_is_stored_with_the_new_chat(db_session: AsyncSession, tmp_path: Path) -> None:
    chat_id = f"bind-{uuid4().hex[:8]}"

    await ChatService.ensure_chat_and_append_user_message(
        chat_id=chat_id,
        content="summarise the invoices",
        sent_at=datetime.now(UTC),
        sent_timezone="UTC",
        action_mode="agent",
        agent_id="default",
        workspace_dir=str(tmp_path),
    )

    db_session.expire_all()
    assert (await _row(db_session, chat_id)).workspace_dir == str(tmp_path)


@pytest.mark.asyncio
async def test_a_later_turn_never_overwrites_the_stored_workspace(db_session: AsyncSession, tmp_path: Path) -> None:
    chat_id = f"bind-{uuid4().hex[:8]}"
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()

    for content, folder in (("first", first), ("second", second)):
        await ChatService.ensure_chat_and_append_user_message(
            chat_id=chat_id,
            content=content,
            sent_at=datetime.now(UTC),
            sent_timezone="UTC",
            action_mode="agent",
            agent_id="default",
            workspace_dir=str(folder),
        )

    db_session.expire_all()
    assert (await _row(db_session, chat_id)).workspace_dir == str(first)


@pytest.mark.asyncio
async def test_the_first_turn_draft_carries_the_folder_into_the_chat_row(db_session: AsyncSession, tmp_path: Path) -> None:
    chat_id = f"bind-{uuid4().hex[:8]}"
    request = AgentRequest(
        message_id=f"msg-{uuid4().hex[:8]}",
        chat_id=chat_id,
        query="summarise the invoices",
        workspace_dir=str(tmp_path),
    )

    persisted = await persist_user_message(request, text_content="summarise the invoices")

    assert persisted is not None
    draft = persisted.pending_draft
    assert draft is not None
    assert draft.workspace_dir == str(tmp_path)

    await draft.commit_if_pending()
    db_session.expire_all()
    assert (await _row(db_session, chat_id)).workspace_dir == str(tmp_path)


@pytest.mark.asyncio
async def test_the_picked_folder_is_the_workspace_of_every_turn(
    db_session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Turn one runs in the picked folder, the lazy session barrier makes no private folder, turn two still runs there."""
    picked = tmp_path / "invoices"
    picked.mkdir()
    private_folders: list[str] = []

    class _SessionPrivateWorkspaces:
        async def get_or_create(self, *, session_id: str) -> str:
            return session_id

        def get_workspace_absolute_path(self, workspace: str) -> str:
            private_folders.append(workspace)
            return str(tmp_path / "private" / workspace)

    monkeypatch.setattr(workspace_resolve, "_chat_workspace_service", _SessionPrivateWorkspaces)
    monkeypatch.setattr(workspace_resolve, "_materialize_agent_template_files", AsyncMock())
    monkeypatch.setattr(
        "app.services.memory.shared_context.shared_context.resolve_shared_context_ids", AsyncMock(return_value=[])
    )
    monkeypatch.setattr("app.services.agent.session_access_service.bootstrap_session_access_roots", lambda *_a, **_k: None)

    chat_id = f"bind-{uuid4().hex[:8]}"
    first = AgentRequest(message_id="msg-1", chat_id=chat_id, query="summarise", workspace_dir=str(picked))
    await bind_turn_workspace(first)
    persisted = await persist_user_message(first, text_content="summarise")
    assert persisted is not None
    assert (await resolve_chat_context(first)).chat_workspace_dir == str(picked.resolve())

    await commit_lazy_session_barrier(SimpleNamespace(request=first, pending_session_draft=persisted.pending_draft))

    # The client keeps sending the folder it shows, so the second turn carries it again.
    second = AgentRequest(message_id="msg-2", chat_id=chat_id, query="and the receipts", workspace_dir=str(picked))
    await bind_turn_workspace(second)
    db_session.expire_all()
    assert (await resolve_chat_context(second)).chat_workspace_dir == str(picked.resolve())
    assert (await _row(db_session, chat_id)).workspace_dir == str(picked.resolve())
    assert private_folders == []
