"""Reusable test base for all channel provider implementations.

Every channel provider test module should subclass ``ChannelTestBase`` and
implement ``create_channel()``. The mixin automatically runs a standard
suite of behavioral tests that verify BaseChannel contract compliance,
capabilities consistency, and lifecycle correctness.

Usage::

    class TestTelegramChannel(ChannelTestBase):
        def create_channel(self) -> TelegramChannel:
            return TelegramChannel(bot_token="test:token")

        @pytest.fixture(autouse=True)
        def _patch_http(self, monkeypatch):
            # patch httpx calls ...
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import pytest

from app.channels.core.base import BaseChannel
from app.channels.types import (
    ChannelCapabilities,
    ChannelStatus,
    InboundMessage,
    OutboundMessage,
    RenderStyle,
)


@dataclass
class SentMessage:
    """Recorded message from MockTransport."""

    recipient_id: str
    content: str
    message_id: str


@dataclass
class MockTransport:
    """In-memory transport for testing channels without real API calls.

    Captures all outbound messages and provides helpers to simulate
    inbound messages. Use ``inject_inbound`` to push a message into
    the channel's inbound handler.
    """

    sent: list[SentMessage] = field(default_factory=list)
    edits: list[tuple[str, str, str]] = field(default_factory=list)
    deletes: list[tuple[str, str]] = field(default_factory=list)
    reactions: list[tuple[str, str, str]] = field(default_factory=list)
    _next_id: int = field(default=1)

    def next_message_id(self) -> str:
        mid = str(self._next_id)
        self._next_id += 1
        return mid

    def record_send(self, recipient_id: str, content: str) -> str:
        mid = self.next_message_id()
        self.sent.append(SentMessage(recipient_id=recipient_id, content=content, message_id=mid))
        return mid

    def record_edit(self, chat_id: str, message_id: str, text: str) -> None:
        self.edits.append((chat_id, message_id, text))

    def record_delete(self, chat_id: str, message_id: str) -> None:
        self.deletes.append((chat_id, message_id))

    def record_reaction(self, chat_id: str, message_id: str, emoji: str) -> None:
        self.reactions.append((chat_id, message_id, emoji))


class ChannelTestBase(ABC):
    """Standard test suite for BaseChannel implementations.

    Subclasses must implement ``create_channel()`` and optionally
    override ``create_test_outbound()`` for channel-specific payloads.
    """

    @abstractmethod
    def create_channel(self) -> BaseChannel:
        """Create a channel instance configured for testing."""
        ...

    def create_test_outbound(self, recipient: str = "test_chat") -> OutboundMessage:
        """Create a minimal OutboundMessage for testing."""
        return OutboundMessage(
            channel=self.create_channel().name,
            recipient_id=recipient,
            content="Hello from test",
            user_id="test_user",
        )

    # -- Contract tests --

    def test_channel_has_name(self) -> None:
        ch = self.create_channel()
        assert isinstance(ch.name, str)
        assert len(ch.name) > 0
        assert ch.name != "base"

    def test_channel_has_capabilities(self) -> None:
        ch = self.create_channel()
        assert isinstance(ch.capabilities, ChannelCapabilities)

    def test_capabilities_text_always_true(self) -> None:
        ch = self.create_channel()
        assert ch.capabilities.text is True

    def test_capabilities_max_text_length_positive(self) -> None:
        ch = self.create_channel()
        assert ch.capabilities.max_text_length > 0

    def test_edit_implies_edit_capability(self) -> None:
        """If channel overrides edit_message, capabilities.edit should be True."""
        ch = self.create_channel()
        has_override = type(ch).edit_message is not BaseChannel.edit_message
        if has_override:
            assert ch.capabilities.edit, f"{type(ch).__name__} overrides edit_message but capabilities.edit=False"

    def test_delete_implies_delete_capability(self) -> None:
        """If channel overrides delete_message, capabilities.delete should be True."""
        ch = self.create_channel()
        has_override = type(ch).delete_message is not BaseChannel.delete_message
        if has_override:
            assert ch.capabilities.delete, f"{type(ch).__name__} overrides delete_message but capabilities.delete=False"

    def test_react_implies_reactions_capability(self) -> None:
        """If channel overrides react_to_message, capabilities.reactions should be True."""
        ch = self.create_channel()
        has_override = type(ch).react_to_message is not BaseChannel.react_to_message
        if has_override:
            assert ch.capabilities.reactions, f"{type(ch).__name__} overrides react_to_message but capabilities.reactions=False"

    def test_initial_status_is_idle(self) -> None:
        ch = self.create_channel()
        assert ch.status == ChannelStatus.IDLE

    def test_health_initially_clean(self) -> None:
        ch = self.create_channel()
        assert ch.health.consecutive_failures == 0
        assert ch.health.last_error == ""

    @pytest.mark.asyncio
    async def test_inbound_handler_default_none(self) -> None:
        ch = self.create_channel()
        assert ch._inbound_handler is None

    @pytest.mark.asyncio
    async def test_set_inbound_handler(self) -> None:
        ch = self.create_channel()
        received: list[InboundMessage] = []

        async def handler(msg: InboundMessage) -> None:
            received.append(msg)

        ch.set_inbound_handler(handler)
        assert ch._inbound_handler is handler

    @pytest.mark.asyncio
    async def test_base_edit_is_noop(self) -> None:
        """BaseChannel.edit_message is a no-op (returns None)."""
        ch = self.create_channel()
        if type(ch).edit_message is BaseChannel.edit_message:
            result = await ch.edit_message("chat", "msg", "text")
            assert result is None

    @pytest.mark.asyncio
    async def test_base_delete_is_noop(self) -> None:
        """BaseChannel.delete_message is a no-op (returns None)."""
        ch = self.create_channel()
        if type(ch).delete_message is BaseChannel.delete_message:
            result = await ch.delete_message("chat", "msg")
            assert result is None

    @pytest.mark.asyncio
    async def test_list_groups_returns_list(self) -> None:
        ch = self.create_channel()
        groups = await ch.list_groups()
        assert isinstance(groups, list)

    def test_collect_issues_returns_list(self) -> None:
        ch = self.create_channel()
        issues = ch.collect_issues()
        assert isinstance(issues, list)

    @pytest.mark.asyncio
    async def test_stop_from_idle_is_safe(self) -> None:
        """Stopping a channel that was never started should not raise."""
        ch = self.create_channel()
        await ch.stop()
        assert ch.status == ChannelStatus.STOPPED

    # -- Capability ↔ method consistency (extended) --

    def test_thread_implies_threads_capability(self) -> None:
        """If channel overrides create_thread, capabilities.threads should be True."""
        ch = self.create_channel()
        has_override = type(ch).create_thread is not BaseChannel.create_thread
        if has_override:
            assert ch.capabilities.threads, f"{type(ch).__name__} overrides create_thread but capabilities.threads=False"

    def test_typing_implies_typing_capability(self) -> None:
        """If channel overrides start_typing, capabilities.typing_indicator should be True."""
        ch = self.create_channel()
        has_override = type(ch).start_typing is not BaseChannel.start_typing
        if has_override:
            assert ch.capabilities.typing_indicator, (
                f"{type(ch).__name__} overrides start_typing but capabilities.typing_indicator=False"
            )

    # -- RenderStyle contract --

    def test_render_style_is_valid_type(self) -> None:
        """render_style should be a RenderStyle instance."""
        ch = self.create_channel()
        if not hasattr(ch, "render_style"):
            pytest.skip(f"{type(ch).__name__} does not implement render_style yet")
        assert isinstance(ch.render_style, RenderStyle), (
            f"{type(ch).__name__}.render_style is {type(ch.render_style).__name__}, expected RenderStyle"
        )

    def test_render_style_max_text_consistent(self) -> None:
        """render_style.max_text_length should match capabilities.max_text_length."""
        ch = self.create_channel()
        if not hasattr(ch, "render_style"):
            pytest.skip(f"{type(ch).__name__} does not implement render_style yet")
        assert ch.render_style.max_text_length == ch.capabilities.max_text_length, (
            f"{type(ch).__name__}: render_style.max_text_length={ch.render_style.max_text_length} "
            f"!= capabilities.max_text_length={ch.capabilities.max_text_length}"
        )

    # -- health_check contract --

    @pytest.mark.asyncio
    async def test_health_check_returns_bool(self) -> None:
        """health_check() should return a bool."""
        ch = self.create_channel()
        result = await ch.health_check()
        assert isinstance(result, bool), f"{type(ch).__name__}.health_check() returned {type(result).__name__}, expected bool"
