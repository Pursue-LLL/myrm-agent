"""The turn's requested folder is used by the parameter stage, with project and chat folders taking precedence."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.agent.params import AgentRequest
from app.services.agent.params.conversion.chat_context import resolve_chat_context


def _request(workspace_dir: str | None, *, chat_id: str = "chat-1") -> AgentRequest:
    return AgentRequest(message_id="msg-1", chat_id=chat_id, workspace_dir=workspace_dir, action_mode="agent")


@pytest.fixture(autouse=True)
def _no_shared_context() -> AsyncMock:
    """Keep the memory lookups out of this unit test; they are wrapped in try/except but would hit the DB."""
    with patch(
        "app.services.memory.shared_context.shared_context.resolve_shared_context_ids",
        AsyncMock(return_value=[]),
    ) as spy:
        yield spy


@pytest.mark.asyncio
async def test_a_first_turn_uses_the_folder_it_carried(tmp_path: Path) -> None:
    with patch(
        "app.services.chat.chat_service.ChatService.get_chat_metadata",
        AsyncMock(return_value=None),
    ):
        context = await resolve_chat_context(_request(str(tmp_path)))

    assert context.chat_workspace_dir == str(tmp_path)


@pytest.mark.asyncio
async def test_a_chat_that_already_has_a_folder_keeps_it(tmp_path: Path) -> None:
    chat = MagicMock(project_id=None, ephemeral_subagents=None, session_loaded_skill_names=None, session_access_roots=None)
    with (
        patch(
            "app.services.chat.chat_service.ChatService.get_chat_metadata",
            AsyncMock(return_value=chat),
        ),
        patch(
            "app.services.chat.effective_workspace.resolve_effective_chat_workspace",
            AsyncMock(return_value=str(tmp_path / "bound")),
        ),
        patch(
            "app.services.agent.session_access_service.bootstrap_session_access_roots",
        ),
    ):
        context = await resolve_chat_context(_request("/somewhere/else"))

    assert context.chat_workspace_dir == str(tmp_path / "bound")


@pytest.mark.asyncio
async def test_a_project_bound_chat_keeps_the_project_folder(tmp_path: Path) -> None:
    chat = MagicMock(project_id="project-1", ephemeral_subagents=None, session_loaded_skill_names=None, session_access_roots=None)
    with (
        patch(
            "app.services.chat.chat_service.ChatService.get_chat_metadata",
            AsyncMock(return_value=chat),
        ),
        patch(
            "app.services.chat.effective_workspace.resolve_effective_chat_workspace",
            AsyncMock(return_value=str(tmp_path / "project")),
        ),
        patch(
            "app.services.agent.session_access_service.bootstrap_session_access_roots",
        ),
    ):
        context = await resolve_chat_context(_request("/somewhere/else"))

    assert context.chat_workspace_dir == str(tmp_path / "project")


@pytest.mark.asyncio
async def test_without_a_requested_folder_the_session_folder_is_materialized(tmp_path: Path) -> None:
    with (
        patch(
            "app.services.chat.chat_service.ChatService.get_chat_metadata",
            AsyncMock(return_value=None),
        ),
        patch(
            "app.services.agent.params.workspace_resolve.resolve_default_chat_workspace_dir",
            AsyncMock(return_value=str(tmp_path / "session")),
        ) as materialize,
        patch(
            "app.services.agent.session_access_service.bootstrap_session_access_roots",
        ),
    ):
        context = await resolve_chat_context(_request(None))

    materialize.assert_awaited_once()
    assert context.chat_workspace_dir == str(tmp_path / "session")
