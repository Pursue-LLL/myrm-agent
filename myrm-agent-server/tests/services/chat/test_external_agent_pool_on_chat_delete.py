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


@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_chat_live_tears_down_registry_pool() -> None:
    """Full ChatService.delete_chat must close registry pool without mocking close helper."""
    import uuid
    from datetime import datetime, timezone

    from app.ai_agents.general_agent.external_agents import ExternalAgentsMixin
    from app.database.models.chat import Chat
    from app.platform_utils import get_session_factory
    from app.services.chat.chat_service import ChatService
    from app.services.external_agents.runtime_pool_registry import get_chat_runtime_pool_registry

    chat_id = f"live-del-{uuid.uuid4().hex[:10]}"
    session_factory = get_session_factory()
    async with session_factory() as db:
        db.add(
            Chat(
                id=chat_id,
                title="delete pool integration",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()

    mixin = ExternalAgentsMixin.__new__(ExternalAgentsMixin)
    mixin.external_agents_config = [
        {"name": "echo-cli", "type": "cli", "command": "echo", "args": []},
    ]
    mixin._runtime_pool_scope_id = chat_id
    mixin._runtime_pool = None
    mixin._runtime_pool_from_registry = False
    mixin._runtime_pool_ephemeral = False
    mixin.agent_id = "general"
    mixin.force_delegate_agent = None
    await mixin._do_setup_external_agents([], [], mount_delegate_tool=False)

    registry = get_chat_runtime_pool_registry()
    assert chat_id in registry._entries  # type: ignore[attr-defined]

    ok = await ChatService.delete_chat(chat_id)
    assert ok is True
    assert chat_id not in registry._entries  # type: ignore[attr-defined]
