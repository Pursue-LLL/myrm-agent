"""Tests for Agent progress streaming through AgentRouter.

Verifies that ProgressUpdate events from execute_stream are forwarded
to Placeholder edits with proper throttling.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from unittest.mock import patch

import pytest

from app.channels.core.bus import MessageBus
from app.channels.protocols.pairing import (
    DmPolicy,
    GroupPolicy,
    GroupTriggerMode,
    PairingStatus,
)
from app.channels.reliability.retry import (
    RetryConfig,
    default_extract_retry_after,
    default_should_retry,
)
from app.channels.routing.router import AgentRouter
from app.channels.routing.session_gate import SessionGateConfig
from app.channels.types import (
    ChannelActivity,
    ChannelHealth,
    ChannelStatus,
    InboundMessage,
    OutboundMessage,
    ProgressUpdate,
)

_PATCH_STREAM_INTERVAL = patch(
    "app.channels.routing.router_stream._MIN_PROGRESS_INTERVAL",
    0.0,
)
_PATCH_EXEC_INTERVAL = patch(
    "app.channels.routing.router_execution._MIN_PROGRESS_INTERVAL",
    0.0,
)

_NO_DEBOUNCE = SessionGateConfig(debounce_window_ms=0)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakePairingStore:
    async def resolve(self, channel: str, sender_id: str) -> str | None:
        return "user-1"

    async def bind(
        self,
        channel: str,
        sender_id: str,
        user_id: str,
        *,
        status: PairingStatus = PairingStatus.ACTIVE,
    ) -> None:
        pass

    async def unbind(self, channel: str, sender_id: str) -> None:
        pass

    async def get_status(self, channel: str, sender_id: str) -> PairingStatus | None:
        return PairingStatus.ACTIVE


class _FakePolicyProvider:
    async def get_dm_policy(self, channel: str) -> DmPolicy:
        return DmPolicy.OPEN

    async def get_group_policy(self, channel: str) -> GroupPolicy:
        return GroupPolicy.DISABLED

    async def get_group_trigger(self, channel: str) -> tuple[GroupTriggerMode, list[str]]:
        return GroupTriggerMode.MENTION_ONLY, []

    async def get_enabled_groups(self) -> set[str]:
        return set()

    async def get_guest_mode(self, channel: str) -> bool:
        return False

    async def get_default_user_id(self) -> str | None:
        return "user-1"


class _ProgressExecutor:
    """Yields configurable ProgressUpdate events before the final OutboundMessage."""

    def __init__(
        self,
        progress_labels: list[str],
        *,
        final_content: str = "Final answer",
    ) -> None:
        self._labels = progress_labels
        self._final_content = final_content

    async def execute_stream(
        self,
        msg: InboundMessage,
        user_id: str,
        **_kwargs: object,
    ) -> AsyncGenerator[ProgressUpdate | OutboundMessage]:
        for label in self._labels:
            yield ProgressUpdate(label=label)
        recipient = msg.chat_id or msg.sender_id
        content = self._final_content
        yield OutboundMessage(
            channel=msg.channel,
            recipient_id=recipient,
            content=content,
            user_id=user_id,
        )


class _RecordingChannel:
    """Fake channel that records placeholder sends, edits, and outbound sends.

    Implements the BaseChannel interface subset needed by MessageBus and AgentRouter.
    """

    retry_config = RetryConfig()
    should_retry = staticmethod(default_should_retry)
    extract_retry_after = staticmethod(default_extract_retry_after)

    def __init__(self) -> None:
        self.placeholder_sends: list[tuple[str, str]] = []
        self.edits: list[tuple[str, str, str]] = []
        self.sent_messages: list[OutboundMessage] = []
        self._counter = 0
        self.activity = ChannelActivity()
        self.health = ChannelHealth()

    @property
    def name(self) -> str:
        return "test"

    @property
    def status(self) -> ChannelStatus:
        return ChannelStatus.RUNNING

    @property
    def capabilities(self):
        from app.channels.types import ChannelCapabilities

        return ChannelCapabilities()

    def set_inbound_handler(self, handler: object) -> None:
        pass

    def extract_sender_locale(self, msg: InboundMessage) -> str | None:
        return None

    async def send_placeholder(self, chat_id: str, text: str, *, thread_id: str | None = None) -> str | None:
        self._counter += 1
        mid = f"ph-{self._counter}"
        self.placeholder_sends.append((chat_id, text))
        return mid

    async def edit_message(self, chat_id: str, message_id: str, text: str) -> None:
        self.edits.append((chat_id, message_id, text))

    async def edit_placeholder_message(
        self,
        chat_id: str,
        message_id: str,
        msg: OutboundMessage,
    ) -> None:
        self.edits.append((chat_id, message_id, msg.content))

    async def send(self, msg: OutboundMessage) -> str | None:
        self.sent_messages.append(msg)

    async def start_typing(self, chat_id: str) -> None:
        pass

    async def stop_typing(self, chat_id: str) -> None:
        pass

    async def react_to_message(self, chat_id: str, message_id: str, emoji: str) -> None:
        pass


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.fixture
def bus() -> MessageBus:
    return MessageBus()


@pytest.fixture
def channel() -> _RecordingChannel:
    return _RecordingChannel()


def _make_msg(content: str = "hello") -> InboundMessage:
    return InboundMessage(
        channel="test",
        sender_id="sender-1",
        content=content,
    )


async def _run_scenario(
    bus: MessageBus,
    channel: _RecordingChannel,
    executor: _ProgressExecutor,
) -> None:
    """Start bus + router, push one message, wait, then stop both."""
    router = AgentRouter(
        bus,
        _FakePairingStore(),
        executor,
        _FakePolicyProvider(),
        session_gate_config=_NO_DEBOUNCE,
    )
    await bus.start()
    await router.start()
    await bus._handle_inbound(_make_msg())
    await asyncio.sleep(1.0)
    await router.stop()
    await bus.stop()


@pytest.mark.asyncio
@_PATCH_STREAM_INTERVAL
@_PATCH_EXEC_INTERVAL
async def test_progress_updates_edit_placeholder(bus: MessageBus, channel: _RecordingChannel) -> None:
    """ProgressUpdate events should trigger placeholder edits, final answer edits placeholder."""
    executor = _ProgressExecutor([" Searching...", " Reviewing..."])
    bus.register_channel(channel)
    await _run_scenario(bus, channel, executor)

    assert len(channel.placeholder_sends) == 1
    edit_texts = [text for _, _, text in channel.edits]
    assert " Searching..." in edit_texts
    assert "Final answer" in edit_texts


@pytest.mark.asyncio
async def test_progress_throttling(bus: MessageBus, channel: _RecordingChannel) -> None:
    """Rapid ProgressUpdate events should be throttled by min_progress_interval."""
    labels = [f"Step {i}" for i in range(10)]
    executor = _ProgressExecutor(labels)
    bus.register_channel(channel)

    with (
        patch("app.channels.routing.router_stream._MIN_PROGRESS_INTERVAL", 0.1),
        patch("app.channels.routing.router_execution._MIN_PROGRESS_INTERVAL", 0.1),
    ):
        await _run_scenario(bus, channel, executor)

    final_edits = [text for _, _, text in channel.edits if text == "Final answer"]
    assert len(final_edits) == 1


@pytest.mark.asyncio
@_PATCH_STREAM_INTERVAL
@_PATCH_EXEC_INTERVAL
async def test_no_progress_still_works(bus: MessageBus, channel: _RecordingChannel) -> None:
    """An executor that yields no ProgressUpdate should still deliver via placeholder edit."""
    long_final = "Final answer " + ("x" * 400)
    executor = _ProgressExecutor([], final_content=long_final)
    bus.register_channel(channel)
    with patch(
        "app.channels.routing.placeholder_strategy.DEFER_SECONDS",
        0.0,
    ):
        await _run_scenario(bus, channel, executor)

    edit_texts = [text for _, _, text in channel.edits]
    assert long_final in edit_texts
