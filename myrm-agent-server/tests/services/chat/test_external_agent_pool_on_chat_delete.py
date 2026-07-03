"""Chat delete paths must tear down chat-scoped external agent RuntimePools."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.chat.chat_crud import _ChatCrudMixin
from app.services.chat.chat_service import ChatService


@pytest.mark.asyncio
async def test_delete_chat_closes_external_agent_pool() -> None:
    mock_close = AsyncMock()
    mock_uow = MagicMock()
    mock_repo = MagicMock()
    mock_repo.soft_delete_chat = AsyncMock(return_value=True)
    mock_uow.__aenter__ = AsyncMock(return_value=mock_uow)
    mock_uow.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("app.services.chat.chat_crud.UnitOfWork", return_value=mock_uow),
        patch("app.services.chat.chat_crud._ChatServiceBase._cr", return_value=mock_repo),
        patch(
            "app.services.chat.chat_crud.ConversationRecallIndexService.set_chat_excluded",
            AsyncMock(),
        ),
        patch(
            "app.services.chat.chat_crud.close_external_agent_pool_for_chat",
            mock_close,
        ),
    ):
        ok = await ChatService.delete_chat("chat-del-1")

    assert ok is True
    mock_close.assert_awaited_once_with("chat-del-1")


@pytest.mark.asyncio
async def test_permanently_delete_chat_closes_external_agent_pool() -> None:
    mock_close = AsyncMock()
    mock_uow = MagicMock()
    mock_repo = MagicMock()
    mock_repo.get_chat_by_id = AsyncMock(return_value=None)
    mock_repo.permanently_delete_chat = AsyncMock(return_value=True)
    mock_uow.session = MagicMock()
    mock_uow.__aenter__ = AsyncMock(return_value=mock_uow)
    mock_uow.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("app.services.chat.chat_crud.UnitOfWork", return_value=mock_uow),
        patch("app.services.chat.chat_crud._ChatServiceBase._cr", return_value=mock_repo),
        patch(
            "app.services.chat.chat_crud.ConversationRecallIndexService.delete_chat",
            AsyncMock(),
        ),
        patch("app.services.chat.chat_crud._delete_widget_kv_for_chat", AsyncMock()),
        patch("app.services.chat.chat_crud._cascade_delete_memories", AsyncMock()),
        patch.object(_ChatCrudMixin, "_cleanup_checkpointer", AsyncMock()),
        patch(
            "app.services.chat.chat_crud.close_external_agent_pool_for_chat",
            mock_close,
        ),
    ):
        ok = await ChatService.permanently_delete_chat("chat-perm-1")

    assert ok is True
    mock_close.assert_awaited_once_with("chat-perm-1")
