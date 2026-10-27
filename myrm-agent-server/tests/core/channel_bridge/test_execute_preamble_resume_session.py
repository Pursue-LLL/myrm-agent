"""A resumed run continues the chat of the turn that asked, on a real database.

The turn that asked for the approval ran in a channel session; the card names its key and the resume message carries it.
Working the key out again when the answer arrives goes wrong as soon as the reset policy has moved on: a daily epoch that
rolled over or an idle window that closed names a chat that does not exist, and a first message of the epoch looks like a
fresh conversation, which would tell the member that the session was reset in the middle of their approval.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.i18n import channel_t
from app.channels.types import METADATA_RESUME_SESSION_KEY, InboundMessage, OutboundMessage, SessionPolicy, SessionResetMode
from app.core.channel_bridge.agent_executor.execute_preamble.session import ChannelSessionContext, resolve_channel_session_context
from app.core.channel_bridge.agent_executor.session import resolve_session_key
from app.core.channel_bridge.executor_helpers import persist_and_load_history
from app.core.channel_bridge.executor_helpers.topic_workspace_sync import ChannelWorkspaceSyncError

_SESSION = "app.core.channel_bridge.agent_executor.execute_preamble.session"
_DAILY = SessionPolicy(mode=SessionResetMode.DAILY)
# An epoch long gone: the daily policy resolves another key today.
_ASKED_IN_A_PAST_EPOCH = "telegram:dm:u1:e=2020-01-01"


def _resume(pinned_session: str | None) -> InboundMessage:
    metadata: dict[str, object] = {"locale": "en", "is_resume": True}
    if pinned_session is not None:
        metadata[METADATA_RESUME_SESSION_KEY] = pinned_session
    return InboundMessage(
        channel="telegram",
        sender_id="u1",
        content="",
        chat_id="c1",
        metadata=metadata,
        resume_value={"decisions": [{"type": "approve"}]},
    )


@pytest.fixture(autouse=True)
def _database(db_session: AsyncSession) -> Iterator[None]:
    @asynccontextmanager
    async def session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    with (
        patch("app.database.connection.get_session", session),
        patch(f"{_SESSION}.maybe_backfill_channel_history", AsyncMock()),
        patch(f"{_SESSION}.extract_session_policy_safe", return_value=_DAILY),
    ):
        yield


async def _asked(session_key: str) -> str:
    """The turn that asked: it stores the member's message in the chat of ``session_key``; returns the chat id."""
    chat_id, _history = await persist_and_load_history(
        channel_session_key=session_key,
        source="telegram",
        content="mail the report",
        sent_at=datetime.now(UTC),
        sent_timezone="UTC",
        agent_id=None,
        topic_context=None,
    )
    return chat_id


async def _resumed(msg: InboundMessage) -> ChannelSessionContext:
    return await resolve_channel_session_context(
        MagicMock(),
        msg,
        query="",
        is_resume=True,
        topic_context=None,
        resolved_agent_id=None,
        resolved_profile=None,
        personal_settings_dict=None,
    )


@pytest.mark.asyncio
async def test_a_resume_after_the_epoch_rolled_over_continues_the_chat_that_asked() -> None:
    asked_chat = await _asked(_ASKED_IN_A_PAST_EPOCH)

    context = await _resumed(_resume(_ASKED_IN_A_PAST_EPOCH))

    assert context.chat_id == asked_chat
    assert context.session_key == _ASKED_IN_A_PAST_EPOCH
    assert context.pre_events == ()


@pytest.mark.asyncio
async def test_a_resume_of_the_first_message_of_an_epoch_is_not_a_fresh_conversation() -> None:
    """The asking message is the only one in the chat, which the cold-start check reads as a conversation with no past."""
    current = await resolve_session_key(_resume(None), _DAILY)
    asked_chat = await _asked(current)

    context = await _resumed(_resume(current))

    assert context.chat_id == asked_chat
    assert context.session_was_auto_reset is False
    assert context.pre_events == ()
    assert context.query == ""


@pytest.mark.asyncio
async def test_a_resume_whose_chat_no_longer_exists_says_so() -> None:
    context = await _resumed(_resume(_ASKED_IN_A_PAST_EPOCH))

    assert context.chat_id == ""
    (reply,) = context.pre_events
    assert isinstance(reply, OutboundMessage)
    assert reply.content == channel_t("en", "approval_session_gone")
    assert reply.metadata["error_type"] == "approval_session_gone"


@pytest.mark.asyncio
async def test_a_resume_that_names_no_session_works_its_session_out_when_it_arrives() -> None:
    """An answer the router held no request for names no session: the session of the message's own turn applies."""
    await _asked(_ASKED_IN_A_PAST_EPOCH)

    assert (await _resumed(_resume(None))).chat_id == ""


@pytest.mark.asyncio
async def test_a_resume_whose_workspace_cannot_be_opened_ends_with_a_flagged_reply() -> None:
    failing = AsyncMock(side_effect=ChannelWorkspaceSyncError("sync failed"))
    with patch(f"{_SESSION}.load_history_without_persist", failing):
        context = await _resumed(_resume(_ASKED_IN_A_PAST_EPOCH))

    assert context.chat_id == ""
    (reply,) = context.pre_events
    assert isinstance(reply, OutboundMessage) and reply.metadata["error_type"] == "workspace_unavailable"
