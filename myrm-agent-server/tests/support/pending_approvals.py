"""Builders for the router's open approval requests and the router around them, shared by the channel routing tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol
from unittest.mock import AsyncMock, MagicMock

from app.channels.routing.pending_approvals import PendingApproval, PendingApprovals
from app.channels.routing.router import AgentRouter
from app.channels.types import InboundMessage


class ScriptedAgent(Protocol):
    """The executor side of a router test: what ``execute_stream`` yields for each message it is given."""

    def execute_stream(self, msg: InboundMessage, user_id: str, **kwargs: object) -> AsyncIterator[object]: ...


def inbound_message(content: str = "build it", *, locale: str = "en", group: bool = False) -> InboundMessage:
    """A message of user ``u1`` in chat ``c1`` of the ``telegram`` channel."""
    return InboundMessage(
        channel="telegram",
        sender_id="u1",
        chat_id="c1",
        content=content,
        user_id="u1",
        is_group=group,
        message_id="m1",
        metadata={"locale": locale},
    )


def router_with_agent(agent: ScriptedAgent | None = None, *, record_resumes: bool = False) -> tuple[AgentRouter, MagicMock]:
    """A real router; with ``record_resumes`` its gate only records the messages it is asked to run."""
    bus = MagicMock()
    bus.consume_inbound = AsyncMock(side_effect=TimeoutError)
    bus.publish_outbound = AsyncMock()
    bus.edit_channel_message = AsyncMock(return_value=True)
    bus.send_tracked = AsyncMock(return_value="prompt-1")
    bus.get_channel = MagicMock(return_value=None)
    executor = MagicMock()
    executor.execute_stream = agent.execute_stream if agent is not None else None
    router = AgentRouter(bus=bus, pairing_store=MagicMock(), agent_executor=executor)
    router._resolve_mobile_status_deep_link = AsyncMock(return_value=None)  # type: ignore[method-assign]
    router._resolve_topic = AsyncMock(return_value=None)  # type: ignore[method-assign]
    if record_resumes:
        router._gate.submit = MagicMock()  # type: ignore[method-assign]
    return router, bus


def said_by(bus: MagicMock) -> list[str]:
    """The texts the bot sent as new messages, in order."""
    return [call.args[0].content for call in bus.publish_outbound.call_args_list]


def asked_in(
    channel: str = "telegram",
    chat_id: str = "c1",
    *,
    thread_id: str | None = None,
    sender_id: str = "u1",
    user_id: str = "u1",
    card_message_id: str = "card-1",
    is_group: bool = False,
    locale: str = "en",
) -> PendingApproval:
    """The approval a turn of ``chat_id`` asked, as the router keeps it."""
    message = InboundMessage(
        channel=channel,
        sender_id=sender_id,
        content="run the build",
        chat_id=chat_id,
        thread_id=thread_id,
        is_group=is_group,
        metadata={"locale": locale},
    )
    return PendingApproval(card_message_id=card_message_id, message=message, user_id=user_id)


def empty_registry() -> PendingApprovals:
    """A registry whose expiry reports go nowhere."""
    return PendingApprovals(on_expire=AsyncMock())


def waiting(state_key: str, card_message_id: str = "card-1") -> PendingApprovals:
    """A registry in which the chat behind ``state_key`` waits on an approval without a time limit."""
    registry = empty_registry()
    channel, _, chat_id = state_key.partition(":")
    registry.register(state_key, asked_in(channel, chat_id, card_message_id=card_message_id), None)
    return registry
