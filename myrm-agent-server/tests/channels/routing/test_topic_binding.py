"""The binding that serves a message is the thread's, else the chat's, else the channel's, and the router asks the same question.

``resolve_bound_topic`` is the one cascade: the router resolves it for every inbound turn and the IM commands resolve
it to find the conversation the next turn writes to. A binding that names no agent still wins over a less specific
one, because the executor serves the message with the first binding that exists, not the first that names an agent.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.channels.routing.pipeline.execution import RouterExecutionMixin
from app.channels.routing.topic_binding import resolve_bound_topic
from app.channels.types import InboundMessage, TopicContext

_THREAD = ("g1", "th1")
_CHAT = ("g1", None)
_CHANNEL = ("__global__", None)


def _binding(agent_id: str | None, *, frozen: bool = False) -> TopicContext:
    return TopicContext(topic_id=f"topic-{agent_id}", agent_id=agent_id, identity_revoked=frozen)


class _Topics:
    """A topic store that answers from a ``(chat_id, thread_id)`` table and records every lookup it is asked."""

    def __init__(self, table: dict[tuple[str, str | None], TopicContext]) -> None:
        self._table = table
        self.lookups: list[tuple[str, str, str | None]] = []

    async def resolve_topic(self, channel: str, chat_id: str, thread_id: str | None) -> TopicContext | None:
        self.lookups.append((channel, chat_id, thread_id))
        return self._table.get((chat_id, thread_id))


def _group_message(*, thread_id: str | None = "th1") -> InboundMessage:
    return InboundMessage(channel="telegram", sender_id="u1", chat_id="g1", thread_id=thread_id, content="hi", is_group=True)


# (layout, bindings, thread of the message, (level that serves it, agent it names) or None)
_LAYOUTS = [
    pytest.param({}, "th1", None, id="nothing-binds-it"),
    pytest.param(
        {_THREAD: _binding("t"), _CHAT: _binding("c"), _CHANNEL: _binding("g")}, "th1", ("thread_binding", "t"), id="thread-wins"
    ),
    pytest.param({_CHAT: _binding("c"), _CHANNEL: _binding("g")}, "th1", ("chat_binding", "c"), id="unbound-thread-uses-chat"),
    pytest.param({_THREAD: _binding("t"), _CHAT: _binding("c")}, None, ("chat_binding", "c"), id="no-thread-uses-chat"),
    pytest.param({_THREAD: _binding("t"), _CHAT: _binding("c")}, "", ("chat_binding", "c"), id="empty-thread-uses-chat"),
    pytest.param({_CHANNEL: _binding("g")}, "th1", ("channel_binding", "g"), id="channel-binds-the-rest"),
    pytest.param(
        {_THREAD: _binding(None), _CHAT: _binding("c")}, "th1", ("thread_binding", None), id="thread-without-agent-shadows-chat"
    ),
    pytest.param(
        {_CHAT: _binding(None), _CHANNEL: _binding("g")}, None, ("chat_binding", None), id="chat-without-agent-shadows-channel"
    ),
    pytest.param({_CHAT: _binding(""), _CHANNEL: _binding("g")}, None, ("chat_binding", ""), id="empty-agent-still-binds"),
    pytest.param(
        {_THREAD: _binding("t", frozen=True), _CHAT: _binding("c")},
        "th1",
        ("thread_binding", "t"),
        id="frozen-thread-still-binds",
    ),
]


@pytest.mark.parametrize(("table", "thread_id", "expected"), _LAYOUTS)
async def test_the_first_level_with_a_binding_serves_the_message(
    table: dict[tuple[str, str | None], TopicContext], thread_id: str | None, expected: tuple[str, str | None] | None
) -> None:
    served = await resolve_bound_topic(_Topics(table), _group_message(thread_id=thread_id))

    assert (None if served is None else (served.matched_by, served.agent_id)) == expected


async def test_levels_after_the_first_binding_are_not_asked() -> None:
    topics = _Topics({_THREAD: _binding("t"), _CHAT: _binding("c")})

    await resolve_bound_topic(topics, _group_message())

    assert topics.lookups == [("telegram", "g1", "th1")]


@pytest.mark.parametrize("thread_id", [None, ""])
async def test_a_message_without_a_thread_never_asks_the_thread_level(thread_id: str | None) -> None:
    topics = _Topics({})

    await resolve_bound_topic(topics, _group_message(thread_id=thread_id))

    assert topics.lookups == [("telegram", "g1", None), ("telegram", "__global__", None)]


async def test_a_direct_chat_is_looked_up_by_its_sender() -> None:
    topics = _Topics({("u1", None): _binding("c")})

    served = await resolve_bound_topic(topics, InboundMessage(channel="telegram", sender_id="u1", content="hi"))

    assert served is not None
    assert (served.matched_by, served.agent_id) == ("chat_binding", "c")


async def test_the_stored_binding_keeps_its_own_settings_and_only_gains_the_level() -> None:
    stored = TopicContext(topic_id="t", agent_id="a", project_id="p", identity_revoked=True)

    served = await resolve_bound_topic(_Topics({_CHAT: stored}), _group_message(thread_id=None))

    assert served is not None
    assert (served.topic_id, served.agent_id, served.project_id, served.identity_revoked) == ("t", "a", "p", True)
    assert stored.matched_by is None


@pytest.mark.parametrize(("table", "thread_id", "expected"), _LAYOUTS)
async def test_the_router_resolves_a_message_the_way_the_commands_do(
    table: dict[tuple[str, str | None], TopicContext], thread_id: str | None, expected: tuple[str, str | None] | None
) -> None:
    msg = _group_message(thread_id=thread_id)
    host = SimpleNamespace(_topic_resolver=_Topics(table))

    routed = await RouterExecutionMixin._resolve_topic(host, msg)  # type: ignore[arg-type]

    assert routed == await resolve_bound_topic(_Topics(table), msg)


async def test_a_router_without_a_topic_store_serves_no_binding() -> None:
    host = SimpleNamespace(_topic_resolver=None)

    assert await RouterExecutionMixin._resolve_topic(host, _group_message()) is None  # type: ignore[arg-type]
