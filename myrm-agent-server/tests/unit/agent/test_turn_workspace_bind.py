"""Unit tests for the one-shot workspace bind a first turn can carry."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.agent.params import AgentRequest
from app.services.agent.stream_session.turn_workspace_bind import (
    TurnWorkspaceRefused,
    bind_turn_workspace,
)

GET_CHAT = "app.services.chat.chat_service.ChatService.get_chat_metadata"
UPDATE_CHAT = "app.services.chat.chat_service.ChatService.update_chat_fields"


def _request(*, workspace_dir: str | None, chat_id: str | None = "chat-1", resume: bool = False) -> AgentRequest:
    return AgentRequest(
        message_id="msg-1",
        chat_id=chat_id,
        workspace_dir=workspace_dir,
        resume_value={"approved": True} if resume else None,
    )


@pytest.fixture
def update_chat() -> Iterator[AsyncMock]:
    with patch(UPDATE_CHAT, AsyncMock()) as update:
        yield update


@pytest.mark.asyncio
async def test_returns_none_without_a_requested_folder() -> None:
    assert await bind_turn_workspace(_request(workspace_dir=None)) is None


@pytest.mark.asyncio
async def test_a_resumed_turn_drops_the_folder_it_was_sent(tmp_path: Path) -> None:
    request = _request(workspace_dir=str(tmp_path), resume=True)

    assert await bind_turn_workspace(request) is None
    assert request.workspace_dir is None


@pytest.mark.asyncio
async def test_new_chat_keeps_the_canonical_path_on_the_request(tmp_path: Path, update_chat: AsyncMock) -> None:
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    request = _request(workspace_dir=str(link))

    with patch(GET_CHAT, AsyncMock(return_value=None)):
        resolved = await bind_turn_workspace(request)

    assert resolved == str(real.resolve())
    # The lazy session draft reads it back when the chat row is written with the first message.
    assert request.workspace_dir == str(real.resolve())
    update_chat.assert_not_awaited()


@pytest.mark.asyncio
async def test_chat_without_a_workspace_is_bound_and_persisted(tmp_path: Path, update_chat: AsyncMock) -> None:
    chat = MagicMock(id="chat-1", project_id=None, workspace_dir=None)
    canonical = str(tmp_path.resolve())

    with patch(GET_CHAT, AsyncMock(return_value=chat)):
        assert await bind_turn_workspace(_request(workspace_dir=str(tmp_path))) == canonical

    update_chat.assert_awaited_once_with("chat-1", {"workspace_dir": canonical})


@pytest.mark.asyncio
async def test_project_bound_chat_ignores_the_requested_folder(tmp_path: Path, update_chat: AsyncMock) -> None:
    chat = MagicMock(id="chat-1", project_id="project-1", workspace_dir=None)
    request = _request(workspace_dir=str(tmp_path / "never-judged"))

    with patch(GET_CHAT, AsyncMock(return_value=chat)):
        assert await bind_turn_workspace(request) is None

    assert request.workspace_dir is None
    update_chat.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_stored_folder_that_has_vanished_does_not_block_the_chat(tmp_path: Path, update_chat: AsyncMock) -> None:
    """The client re-sends the chat's own folder with every message; the stored folder decides, not the copy."""
    gone = str(tmp_path / "unplugged-drive")
    chat = MagicMock(id="chat-1", project_id=None, workspace_dir=gone)
    request = _request(workspace_dir=gone)

    with patch(GET_CHAT, AsyncMock(return_value=chat)):
        assert await bind_turn_workspace(request) is None

    assert request.workspace_dir is None
    update_chat.assert_not_awaited()


@pytest.mark.asyncio
async def test_chat_that_already_owns_a_workspace_keeps_it(tmp_path: Path, update_chat: AsyncMock) -> None:
    other = tmp_path / "other"
    other.mkdir()
    chat = MagicMock(id="chat-1", project_id=None, workspace_dir=str(other))
    request = _request(workspace_dir=str(tmp_path))

    with patch(GET_CHAT, AsyncMock(return_value=chat)):
        assert await bind_turn_workspace(request) is None

    assert request.workspace_dir is None
    update_chat.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_folder_is_refused_for_a_chat_that_would_run_in_it(tmp_path: Path) -> None:
    request = _request(workspace_dir=str(tmp_path / "deleted-before-send"))

    with patch(GET_CHAT, AsyncMock(return_value=None)), pytest.raises(TurnWorkspaceRefused) as refused:
        await bind_turn_workspace(request)

    assert refused.value.issue.value == "not_a_directory"


@pytest.mark.asyncio
async def test_a_request_without_a_chat_is_still_judged_and_never_persisted(tmp_path: Path, update_chat: AsyncMock) -> None:
    with patch(GET_CHAT, AsyncMock()) as get_chat:
        assert await bind_turn_workspace(_request(workspace_dir=str(tmp_path), chat_id=None)) == str(tmp_path.resolve())
        with pytest.raises(TurnWorkspaceRefused):
            await bind_turn_workspace(_request(workspace_dir=str(tmp_path / "missing"), chat_id=None))

    get_chat.assert_not_awaited()
    update_chat.assert_not_awaited()
