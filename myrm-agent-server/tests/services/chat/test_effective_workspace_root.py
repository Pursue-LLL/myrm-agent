"""``resolve_chat_workspace_root``: where the runs of a chat wrote their vault objects and artifacts."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.database.dto import ChatDTO
from app.platform_utils.workspace_root import get_workspace_root
from app.services.chat.effective_workspace import find_chat_workspace_root, resolve_chat_workspace_root

_JIT_PATH_TARGET = "app.services.agent.params.workspace_resolve.default_chat_workspace_path"
_METADATA_TARGET = "app.services.chat.chat_service.ChatService.get_chat_metadata"


def _chat(chat_id: str, workspace_dir: str | None = None) -> ChatDTO:
    now = datetime.now(UTC)
    return ChatDTO(id=chat_id, workspace_dir=workspace_dir, created_at=now, updated_at=now)


@pytest.mark.parametrize("chat_id", [None, "", "   "])
async def test_no_chat_means_the_process_workspace_root(chat_id: str | None) -> None:
    assert await resolve_chat_workspace_root(chat_id) == get_workspace_root()


async def test_a_chat_with_a_bound_workspace_resolves_to_it(tmp_path: Path) -> None:
    bound = tmp_path / "bound"
    chat = _chat("c1", str(bound))

    with patch(_METADATA_TARGET, AsyncMock(return_value=chat)):
        assert await resolve_chat_workspace_root("c1") == bound


async def test_a_chat_without_a_bound_workspace_resolves_to_its_jit_path_without_creating_it(tmp_path: Path) -> None:
    jit = tmp_path / "workspaces" / "chat_c2"
    chat = _chat("c2")

    with patch(_METADATA_TARGET, AsyncMock(return_value=chat)), patch(_JIT_PATH_TARGET, return_value=jit):
        assert await resolve_chat_workspace_root("c2") == jit

    assert not jit.exists()


async def test_a_chat_whose_metadata_is_gone_still_resolves_to_its_jit_path(tmp_path: Path) -> None:
    jit = tmp_path / "workspaces" / "chat_gone"

    with patch(_METADATA_TARGET, AsyncMock(return_value=None)), patch(_JIT_PATH_TARGET, return_value=jit):
        assert await resolve_chat_workspace_root("gone") == jit


async def test_a_chat_id_that_cannot_name_a_directory_falls_back_to_the_process_root() -> None:
    with patch(_METADATA_TARGET, AsyncMock(return_value=None)):
        assert await resolve_chat_workspace_root("../escape") == get_workspace_root()


async def test_find_reports_a_chat_id_that_cannot_name_a_directory_as_having_no_workspace() -> None:
    with patch(_METADATA_TARGET, AsyncMock(return_value=None)):
        assert await find_chat_workspace_root("../escape") is None


async def test_find_still_answers_for_such_an_id_when_the_chat_has_a_bound_workspace(tmp_path: Path) -> None:
    chat = _chat("feishu:ou_1", str(tmp_path / "bound"))

    with patch(_METADATA_TARGET, AsyncMock(return_value=chat)):
        assert await find_chat_workspace_root("feishu:ou_1") == tmp_path / "bound"
