"""Guard tests: persist_assistant_message_safe must not interpolate unsafe chat_ids."""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_persist_assistant_message_safe_skips_unsafe_chat_id():
    """Unsafe chat_id must skip usage sync and memory projection (no side effects)."""

    async def _fake_append_message(*args, **kwargs):
        from app.database.dto import MessageDTO

        return MessageDTO(id="msg-1", chat_id=args[0])

    with (
        patch(
            "app.services.chat.chat_message._ChatMessageMixin.append_message",
            new=AsyncMock(side_effect=_fake_append_message),
        ),
        patch(
            "app.services.chat.chat_message.record_memory_influence_event",
            new=AsyncMock(),
        ) as memory_mock,
    ):
        from app.services.chat.chat_message import _ChatMessageMixin

        # 非法 chat_id：is_safe_session_id 拦截，usage sync 与记忆投影均不触达
        await _ChatMessageMixin.persist_assistant_message_safe(
            "../../etc/passwd",
            "hello",
            extra_data=None,
        )

    memory_mock.assert_not_called()


@pytest.mark.asyncio
async def test_persist_assistant_message_safe_stores_request_message_id():
    """request_message_id must be written into extra_data for hydrate-side recovery."""

    captured_extra: list[dict[str, object] | None] = []

    async def _fake_append_message(chat_id, role, content, **kwargs):
        from app.database.dto import MessageDTO

        captured_extra.append(kwargs.get("extra_data"))
        return MessageDTO(id="msg-rid", chat_id=chat_id)

    with (
        patch(
            "app.services.chat.chat_message._ChatMessageMixin.append_message",
            new=AsyncMock(side_effect=_fake_append_message),
        ),
        patch(
            "app.services.chat.chat_message.record_memory_influence_event",
            new=AsyncMock(),
        ),
    ):
        from app.services.chat.chat_message import _ChatMessageMixin

        await _ChatMessageMixin.persist_assistant_message_safe(
            "chat-rid-1",
            "hello",
            extra_data=None,
            request_message_id="r-abc123",
        )
        await _ChatMessageMixin.persist_assistant_message_safe(
            "chat-rid-2",
            "hello",
            extra_data={"existing": True},
            request_message_id="r-def456",
        )
        await _ChatMessageMixin.persist_assistant_message_safe(
            "chat-rid-3",
            "hello",
            extra_data={"existing": True},
        )

    assert captured_extra[0] == {"request_message_id": "r-abc123"}
    assert captured_extra[1] == {"existing": True, "request_message_id": "r-def456"}
    assert captured_extra[2] == {"existing": True}
