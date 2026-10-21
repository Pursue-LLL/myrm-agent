"""Tests for Router-level message deduplication.

Verifies that AgentRouter correctly deduplicates inbound messages based on
channel-scoped message_id with TTL expiration.
"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from app.channels.routing.router import AgentRouter
from app.channels.routing.router_constants import (
    _DEDUP_MAX_SIZE,
    _DEDUP_TTL,
)
from app.channels.types import InboundMessage


def _msg(
    channel: str = "telegram",
    sender_id: str = "user1",
    content: str = "hello",
    message_id: str | None = "msg-001",
) -> InboundMessage:
    return InboundMessage(
        channel=channel,
        sender_id=sender_id,
        content=content,
        message_id=message_id,
    )


@pytest.fixture()
def router() -> AgentRouter:
    """Create a minimal AgentRouter with mock dependencies for dedup testing."""
    from unittest.mock import AsyncMock, MagicMock

    bus = MagicMock()
    pairing = MagicMock()
    executor = AsyncMock()
    return AgentRouter(
        bus=bus,
        pairing_store=pairing,
        agent_executor=executor,
    )


class TestIsDuplicate:
    """Tests for AgentRouter._is_duplicate()."""

    def test_first_message_not_duplicate(self, router: AgentRouter) -> None:
        assert router._is_duplicate(_msg()) is False

    def test_same_message_is_duplicate(self, router: AgentRouter) -> None:
        msg = _msg()
        router._is_duplicate(msg)
        assert router._is_duplicate(msg) is True

    def test_different_message_ids_not_duplicate(self, router: AgentRouter) -> None:
        router._is_duplicate(_msg(message_id="msg-001"))
        assert router._is_duplicate(_msg(message_id="msg-002")) is False

    def test_same_id_different_channels_not_duplicate(self, router: AgentRouter) -> None:
        """Same message_id from different channels should NOT be treated as duplicate."""
        router._is_duplicate(_msg(channel="telegram", message_id="123"))
        assert router._is_duplicate(_msg(channel="whatsapp", message_id="123")) is False

    def test_no_message_id_skips_dedup(self, router: AgentRouter) -> None:
        """Messages without message_id should never be flagged as duplicate."""
        msg1 = _msg(message_id=None)
        msg2 = _msg(message_id=None)
        assert router._is_duplicate(msg1) is False
        assert router._is_duplicate(msg2) is False

    def test_ttl_expiration(self, router: AgentRouter) -> None:
        """After TTL expires, the same message_id should be accepted again."""
        msg = _msg()
        router._is_duplicate(msg)

        now = time.monotonic()
        with patch("time.monotonic", return_value=now + _DEDUP_TTL + 1):
            router._seen_messages = {k: v for k, v in router._seen_messages.items() if (now + _DEDUP_TTL + 1) - v <= _DEDUP_TTL}

        assert router._is_duplicate(msg) is False

    def test_max_size_triggers_cleanup(self, router: AgentRouter) -> None:
        """When cache exceeds max size, old entries should be evicted."""
        now = time.monotonic()

        for i in range(_DEDUP_MAX_SIZE):
            router._seen_messages[f"telegram:old-{i}"] = now - _DEDUP_TTL - 1

        assert len(router._seen_messages) == _DEDUP_MAX_SIZE

        fresh_msg = _msg(message_id="fresh-msg")
        assert router._is_duplicate(fresh_msg) is False

        assert len(router._seen_messages) < _DEDUP_MAX_SIZE

    @pytest.mark.asyncio
    async def test_stop_clears_cache(self, router: AgentRouter) -> None:
        """AgentRouter.stop() should clear the dedup cache."""
        router._is_duplicate(_msg())
        assert len(router._seen_messages) > 0

        await router.stop()
        assert len(router._seen_messages) == 0
