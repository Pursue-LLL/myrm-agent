"""Canonical chat message commits must not wait on the derived recall index."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from time import monotonic
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Message
from app.services.chat.chat_service import ChatService


@pytest.mark.asyncio
async def test_user_message_is_visible_when_recall_index_times_out(
    db_session: AsyncSession,
) -> None:
    started = asyncio.Event()

    async def blocked_recall_index(*args: object, **kwargs: object) -> None:
        del args, kwargs
        started.set()
        await asyncio.Event().wait()

    with (
        patch(
            "app.services.chat.chat_message.ConversationRecallIndexService.append_message",
            new=blocked_recall_index,
        ),
        patch(
            "app.services.chat.chat_message._RECALL_INDEX_TIMEOUT_SECONDS",
            0.01,
        ),
    ):
        started_at = monotonic()
        message = await asyncio.wait_for(
            ChatService.ensure_chat_and_append_user_message(
                chat_id="chat-recall-timeout-boundary",
                content="canonical user row",
                sent_at=datetime.now(timezone.utc),
                sent_timezone="UTC",
                message_id="msg-recall-timeout-boundary",
            ),
            timeout=1.0,
        )

    assert started.is_set()
    assert monotonic() - started_at < 0.5
    await db_session.rollback()
    loaded = await db_session.scalar(select(Message).where(Message.id == message.id))
    assert loaded is not None
    assert loaded.content == "canonical user row"


@pytest.mark.asyncio
async def test_user_message_survives_recall_index_failure(
    db_session: AsyncSession,
) -> None:
    async def failed_recall_index(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise RuntimeError("synthetic recall index failure")

    with patch(
        "app.services.chat.chat_message.ConversationRecallIndexService.append_message",
        new=failed_recall_index,
    ):
        message = await ChatService.ensure_chat_and_append_user_message(
            chat_id="chat-recall-failure-boundary",
            content="canonical user row survives",
            sent_at=datetime.now(timezone.utc),
            sent_timezone="UTC",
            message_id="msg-recall-failure-boundary",
        )

    await db_session.rollback()
    loaded = await db_session.scalar(select(Message).where(Message.id == message.id))
    assert loaded is not None
    assert loaded.content == "canonical user row survives"
