"""The topic binding that serves one inbound message: the thread's, else the chat's, else the channel's.

[INPUT]
- channels.protocols.topic::TopicManager (POS: Topic/channel-level management protocol. Supports two binding granularities for flexible channel routing.)
- channels.types::InboundMessage (POS: channel message types.)
- channels.types::TopicContext (POS: per-topic configuration for forum-style thread routing)

[OUTPUT]
- resolve_bound_topic(): the binding that governs a message, tagged with the level it was found at

[POS]
The one cascade behind "which binding serves this message". The router resolves it for every inbound turn, and the IM
commands that act on a conversation (``/undo``, ``/retry``, ``/compact``, ``/handoff``) resolve it again to find the
conversation the next turn writes to, so a binding rule changes in this file only. Routing logic only: the storage
stays behind the ``TopicManager`` it is given.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator

from app.channels.protocols.topic import TopicManager
from app.channels.types import InboundMessage, TopicContext

# The chat id under which a binding that covers the whole channel is stored.
_CHANNEL_WIDE_CHAT_ID = "__global__"


def _levels(msg: InboundMessage) -> Iterator[tuple[str, str | None, str]]:
    """The ``(chat_id, thread_id, matched_by)`` lookups for ``msg``, most specific first."""
    chat_id = msg.chat_id or msg.sender_id
    if msg.thread_id:
        yield chat_id, msg.thread_id, "thread_binding"
    yield chat_id, None, "chat_binding"
    yield _CHANNEL_WIDE_CHAT_ID, None, "channel_binding"


async def resolve_bound_topic(resolver: TopicManager, msg: InboundMessage) -> TopicContext | None:
    """The binding that serves ``msg``, or ``None`` when no level binds it.

    The first level with a binding wins even when that binding names no agent, so a thread bound only to a project
    still shadows the chat's agent. ``matched_by`` of the returned context names the level.
    """
    for chat_id, thread_id, matched_by in _levels(msg):
        ctx = await resolver.resolve_topic(msg.channel, chat_id, thread_id)
        if ctx is not None:
            return dataclasses.replace(ctx, matched_by=matched_by)
    return None
