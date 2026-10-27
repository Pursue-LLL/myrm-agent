"""``get_newest_channel_chat_under`` returns the newest chat of a conversation, not of a peer whose id extends it."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.chat.chat_service import ChatService
from tests.support.channel_chat_rows import seed_channel_chat


@pytest.mark.asyncio
async def test_the_newest_chat_under_a_key_is_the_newest_of_that_conversation(db_session: AsyncSession) -> None:
    older = await seed_channel_chat(db_session, "telegram:dm:u1:e=2026-01-01", idle_minutes=300)
    newer = await seed_channel_chat(db_session, "telegram:dm:u1:agent:a1:e=2026-01-02", idle_minutes=30)
    await seed_channel_chat(db_session, "telegram:dm:u10:e=2026-01-02", idle_minutes=1)

    chat = await ChatService.get_newest_channel_chat_under("telegram:dm:u1")

    assert chat is not None and chat.id == newer != older


@pytest.mark.asyncio
async def test_a_conversation_without_chats_has_no_newest_chat(db_session: AsyncSession) -> None:
    await seed_channel_chat(db_session, "telegram:dm:u10:e=2026-01-02")

    assert await ChatService.get_newest_channel_chat_under("telegram:dm:u1") is None
