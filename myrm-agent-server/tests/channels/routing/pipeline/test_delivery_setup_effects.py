"""A turn sets its processing reaction once, in the turn's ack step; the delivery setup must not set it a second time."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.core.bus import MessageBus
from app.channels.routing.message_effects import MessageEffects
from app.channels.routing.pending_approvals import PendingApprovals
from app.channels.routing.pipeline import RouterDeliveryMixin
from app.channels.routing.placeholder_strategy import DeferredPlaceholder
from app.channels.routing.router_models import ReactionPolicy, _ActiveTask, _CleanupEntry
from app.channels.types import InboundMessage, ReactionLevel, VoiceConfig


class _DeliveryHost(RouterDeliveryMixin):
    """The router attributes ``_setup_message_effects`` reads; the rest of ``AgentRouter`` is not needed."""

    def __init__(self, policy: ReactionPolicy) -> None:
        self._fx: MessageEffects = MagicMock(
            reactions=MagicMock(react=AsyncMock()),
            send_placeholder=AsyncMock(return_value=None),
            set_typing=AsyncMock(),
            start_typing_keepalive=MagicMock(),
        )
        self._bus: MessageBus = MagicMock()
        self._pending_approvals: PendingApprovals = MagicMock()
        self._voice: VoiceConfig | None = None
        self._reaction_policy: ReactionPolicy = policy
        self._active_tasks: dict[str, _ActiveTask] = {}
        self._cleanups: dict[str, _CleanupEntry] = {}


def _message() -> InboundMessage:
    return InboundMessage(channel="telegram", sender_id="u1", chat_id="chat-1", content="hello", message_id="m1")


@pytest.mark.asyncio
async def test_a_new_turn_leaves_the_processing_reaction_to_the_turn_ack() -> None:
    host = _DeliveryHost(ReactionPolicy(level=ReactionLevel.FULL))
    assert host._reaction_policy.should_processing

    deferred = await host._setup_message_effects(_message(), "telegram:chat-1", "chat-1", "m1", is_resume=False)

    try:
        host._fx.reactions.react.assert_not_awaited()  # type: ignore[attr-defined]
        assert isinstance(deferred, DeferredPlaceholder)
        assert "telegram:chat-1" in host._cleanups
    finally:
        if deferred is not None:
            await deferred.cancel()
