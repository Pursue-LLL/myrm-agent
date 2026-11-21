"""An IM command acts on the conversation the executor stores the sending chat's next turn in.

The executor serves a message with the first binding that exists (thread, chat, channel) and the agent that binding names,
unless its identity is frozen; that agent and the reset policy decide the session key. A command that resolved the key any
other way, ``/undo`` for one, would delete the turns of a conversation the user is no longer talking in.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.types import InboundMessage, SessionPolicy, SessionResetMode, TopicContext
from app.core.channel_bridge.agent_executor import resolve_session_key
from app.core.channel_bridge.command_session import resolve_command_session_key
from app.core.channel_bridge.turn_handler import ChannelUndoHandler, RevertMessagesOutcome
from app.database.dto import MessageDTO
from app.database.models import Message
from app.database.repositories.chat_repo import ChatRepository
from app.services.chat.chat_service import ChatService

_MODULE = "app.core.channel_bridge.command_session"
_THREAD = ("g1", "th1")
_CHAT = ("g1", None)
_CHANNEL = ("__global__", None)
_MESSAGE = InboundMessage(
    channel="telegram", sender_id="u1", chat_id="g1", thread_id="th1", content="/undo", user_id="uid1", is_group=True
)
_PERSISTENT = SessionPolicy(mode=SessionResetMode.PERSISTENT)
_PERSON_KEEPS_ONE_CONVERSATION = {"sessionPolicy": {"mode": "persistent"}}
_PERSON_RESETS_DAILY = {"sessionPolicy": {"mode": "daily"}}


def _topic(agent_id: str | None, *, frozen: bool = False) -> TopicContext:
    return TopicContext(topic_id="t", agent_id=agent_id, identity_revoked=frozen)


class _Topics:
    """``SqlTopicManager`` standing in: answers from a ``(chat_id, thread_id)`` table."""

    def __init__(self, table: dict[tuple[str, str | None], TopicContext]) -> None:
        self._table = table

    async def resolve_topic(self, channel: str, chat_id: str, thread_id: str | None) -> TopicContext | None:
        return self._table.get((chat_id, thread_id))


@contextmanager
def _stubbed(
    bindings: dict[tuple[str, str | None], TopicContext],
    *,
    personal: dict[str, object] | None,
    agent_policies: dict[str, dict[str, object] | None] | None = None,
) -> Iterator[AsyncMock]:
    """Stand in for the stores the key is resolved from; yields the agent-profile lookup, recorded."""
    profiles = {agent_id: SimpleNamespace(session_policy=policy) for agent_id, policy in (agent_policies or {}).items()}
    lookup = AsyncMock(side_effect=profiles.get)
    with (
        patch(f"{_MODULE}.SqlTopicManager", return_value=_Topics(bindings)),
        patch(f"{_MODULE}.load_user_configs", AsyncMock(return_value=SimpleNamespace(personal_settings_dict=personal))),
        patch(f"{_MODULE}.get_agent_profile_resolver", return_value=SimpleNamespace(resolve=lookup)),
    ):
        yield lookup


# (bindings of the chat, agent that serves the message)
_LAYOUTS = [
    pytest.param({}, None, id="no-binding"),
    pytest.param({_THREAD: _topic("agent-t"), _CHAT: _topic("agent-c")}, "agent-t", id="thread-binding-names-agent"),
    pytest.param({_CHAT: _topic("agent-c")}, "agent-c", id="chat-binding-names-agent"),
    pytest.param({_CHANNEL: _topic("agent-g")}, "agent-g", id="channel-binding-names-agent"),
    pytest.param({_CHAT: _topic("agent-c", frozen=True)}, None, id="frozen-identity"),
    pytest.param(
        {_THREAD: _topic("agent-t", frozen=True), _CHAT: _topic("agent-c")}, None, id="frozen-thread-binding-stops-the-search"
    ),
    pytest.param({_THREAD: _topic(None), _CHAT: _topic("agent-c")}, None, id="thread-binding-without-agent"),
    pytest.param({_CHAT: _topic(None), _CHANNEL: _topic("agent-g")}, None, id="chat-binding-without-agent"),
]


@pytest.mark.parametrize(("bindings", "serving_agent"), _LAYOUTS)
async def test_the_key_names_the_agent_that_serves_the_message(
    bindings: dict[tuple[str, str | None], TopicContext], serving_agent: str | None
) -> None:
    with _stubbed(bindings, personal=_PERSON_KEEPS_ONE_CONVERSATION):
        key = await resolve_command_session_key(_MESSAGE)

    assert key == await resolve_session_key(_MESSAGE, _PERSISTENT, agent_id=serving_agent)


async def test_the_persons_policy_applies_to_a_message_no_agent_serves() -> None:
    with _stubbed({}, personal=_PERSON_KEEPS_ONE_CONVERSATION) as profile_lookup:
        key = await resolve_command_session_key(_MESSAGE)

    assert ":e=" not in key
    profile_lookup.assert_not_awaited()


async def test_a_conversation_resets_daily_until_a_policy_says_otherwise() -> None:
    with _stubbed({}, personal=None):
        key = await resolve_command_session_key(_MESSAGE)

    assert ":e=" in key


@pytest.mark.parametrize(
    ("personal", "agent_policy", "resets"),
    [
        pytest.param(_PERSON_KEEPS_ONE_CONVERSATION, {"mode": "daily"}, True, id="agent-resets-person-keeps"),
        pytest.param(_PERSON_RESETS_DAILY, {"mode": "persistent"}, False, id="agent-keeps-person-resets"),
        pytest.param(_PERSON_KEEPS_ONE_CONVERSATION, None, False, id="agent-without-policy"),
        pytest.param(_PERSON_KEEPS_ONE_CONVERSATION, {}, False, id="agent-with-empty-policy"),
    ],
)
async def test_the_serving_agents_own_policy_replaces_the_persons(
    personal: dict[str, object], agent_policy: dict[str, object] | None, resets: bool
) -> None:
    with _stubbed({_CHAT: _topic("agent-c")}, personal=personal, agent_policies={"agent-c": agent_policy}):
        key = await resolve_command_session_key(_MESSAGE)

    assert (":e=" in key) is resets


async def test_an_agent_whose_profile_cannot_be_resolved_leaves_the_persons_policy() -> None:
    with _stubbed({_CHAT: _topic("agent-c")}, personal=_PERSON_KEEPS_ONE_CONVERSATION) as profile_lookup:
        key = await resolve_command_session_key(_MESSAGE)

    profile_lookup.assert_awaited_once_with("agent-c")
    assert ":e=" not in key


async def test_a_frozen_identity_does_not_apply_its_agents_policy() -> None:
    bindings = {_CHAT: _topic("agent-c", frozen=True)}
    with _stubbed(
        bindings, personal=_PERSON_KEEPS_ONE_CONVERSATION, agent_policies={"agent-c": {"mode": "daily"}}
    ) as profile_lookup:
        key = await resolve_command_session_key(_MESSAGE)

    assert ":e=" not in key
    profile_lookup.assert_not_awaited()


def _turn(chat_id: str, number: int) -> list[MessageDTO]:
    asked = datetime(2026, 1, 1, 12, 0, 0) + timedelta(minutes=number)
    answered = asked + timedelta(seconds=1)
    return [
        MessageDTO(
            id=f"{chat_id}-u{number}",
            chat_id=chat_id,
            role="user",
            content=f"Q{number}",
            sent_at=asked,
            sent_timezone="UTC",
            created_at=asked,
        ),
        MessageDTO(
            id=f"{chat_id}-a{number}",
            chat_id=chat_id,
            role="assistant",
            content=f"A{number}",
            sent_at=answered,
            sent_timezone="UTC",
            created_at=answered,
        ),
    ]


async def _seed_conversation(db: AsyncSession, key: str, agent_id: str | None) -> str:
    """A stored conversation of two turns under ``key``; returns its chat id."""
    chat = await ChatService.get_or_create_channel_chat(key, "telegram", agent_id=agent_id)
    await ChatRepository.add_messages(db, _turn(chat.id, 1) + _turn(chat.id, 2))
    await db.commit()
    return chat.id


async def _message_ids(db: AsyncSession, chat_id: str) -> list[str]:
    rows = await db.execute(select(Message.id).where(Message.chat_id == chat_id).order_by(Message.created_at))
    return [row[0] for row in rows.all()]


@pytest.fixture
def undo_collaborators() -> Iterator[None]:
    """Checkpoint sync and file-snapshot revert are not under test: the turns' removal from the chat is."""
    with (
        patch("app.services.chat.chat_turn._ChatTurnMixin._invalidate_checkpoint_after_mutation", new_callable=AsyncMock),
        patch("app.core.channel_bridge.turn_handler._revert_messages", AsyncMock(return_value=RevertMessagesOutcome(0, 0))),
    ):
        yield


# (bindings of the chat, agent that serves the message, agent of the conversation a command could wrongly pick instead)
_UNDO_LAYOUTS = [
    pytest.param({_CHAT: _topic("agent-c", frozen=True)}, None, "agent-c", id="frozen-identity"),
    pytest.param({_THREAD: _topic(None), _CHAT: _topic("agent-c")}, None, "agent-c", id="thread-binding-without-agent"),
    pytest.param(
        {_THREAD: _topic("agent-t", frozen=True), _CHAT: _topic("agent-c")}, None, "agent-t", id="frozen-thread-binding"
    ),
    pytest.param({_CHAT: _topic("agent-c")}, "agent-c", None, id="chat-binding-names-agent"),
    pytest.param({_CHANNEL: _topic("agent-g")}, "agent-g", None, id="channel-binding-names-agent"),
]


@pytest.mark.parametrize(("bindings", "serving_agent", "other_agent"), _UNDO_LAYOUTS)
async def test_undo_removes_the_last_turn_of_the_conversation_the_executor_writes_to(
    db_session: AsyncSession,
    undo_collaborators: None,
    bindings: dict[tuple[str, str | None], TopicContext],
    serving_agent: str | None,
    other_agent: str | None,
) -> None:
    served_key = await resolve_session_key(_MESSAGE, _PERSISTENT, agent_id=serving_agent)
    other_key = await resolve_session_key(_MESSAGE, _PERSISTENT, agent_id=other_agent)
    served_chat = await _seed_conversation(db_session, served_key, serving_agent)
    other_chat = await _seed_conversation(db_session, other_key, other_agent)

    with _stubbed(bindings, personal=_PERSON_KEEPS_ONE_CONVERSATION):
        result = await ChannelUndoHandler()(_MESSAGE, "uid1")

    assert (result.success, result.deleted_count) == (True, 2)
    assert await _message_ids(db_session, served_chat) == [f"{served_chat}-u1", f"{served_chat}-a1"]
    assert len(await _message_ids(db_session, other_chat)) == 4
