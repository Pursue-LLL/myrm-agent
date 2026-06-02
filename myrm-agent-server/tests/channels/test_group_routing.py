"""Tests for group chat routing in AgentRouter.

Verifies that the AgentRouter correctly handles group messages based on
GroupPolicy and mention gating, without requiring real WhatsApp connections.
"""

from __future__ import annotations

import asyncio
import itertools
from collections.abc import AsyncGenerator

import pytest

from app.channels.core.bus import MessageBus
from app.channels.protocols.pairing import (
    DmPolicy,
    GroupPolicy,
    GroupTriggerMode,
    PairingStatus,
)
from app.channels.routing.router import AgentRouter
from app.channels.routing.session_gate import SessionGateConfig
from app.channels.types import InboundMessage, OutboundMessage, ProgressUpdate

_NO_DEBOUNCE = SessionGateConfig(debounce_window_ms=0)


class FakePairingStore:
    """Minimal PairingStore that never resolves any pairing."""

    async def resolve(self, channel: str, sender_id: str) -> str | None:
        return None

    async def bind(
        self, channel: str, sender_id: str, user_id: str, *, status: PairingStatus = PairingStatus.ACTIVE
    ) -> None:
        pass

    async def unbind(self, channel: str, sender_id: str) -> None:
        pass

    async def get_status(self, channel: str, sender_id: str) -> PairingStatus | None:
        return None


class FakeAgentExecutor:
    """Records execute_stream calls for assertion."""

    def __init__(self) -> None:
        self.calls: list[tuple[InboundMessage, str]] = []

    async def execute_stream(
        self,
        msg: InboundMessage,
        user_id: str,
        **_kwargs: object,
    ) -> AsyncGenerator[ProgressUpdate | OutboundMessage]:
        self.calls.append((msg, user_id))
        recipient = msg.chat_id if msg.is_group and msg.chat_id else msg.sender_id
        yield OutboundMessage(
            channel=msg.channel,
            recipient_id=recipient,
            content=f"Reply to: {msg.content}",
            user_id=user_id,
        )


_TEST_GROUP_JID = "group456@g.us"


class FakePolicyProvider:
    """Configurable policy provider for testing."""

    def __init__(
        self,
        dm_policy: DmPolicy = DmPolicy.OPEN,
        group_policy: GroupPolicy = GroupPolicy.OPEN,
        trigger_mode: GroupTriggerMode = GroupTriggerMode.MENTION_ONLY,
        trigger_prefixes: list[str] | None = None,
        enabled_groups: set[str] | None = None,
    ) -> None:
        self._dm_policy = dm_policy
        self._group_policy = group_policy
        self._trigger_mode = trigger_mode
        self._trigger_prefixes = trigger_prefixes or []
        # Default: enable the standard test group so existing tests pass
        self._enabled_groups = enabled_groups if enabled_groups is not None else {_TEST_GROUP_JID}

    async def get_dm_policy(self, channel: str) -> DmPolicy:
        return self._dm_policy

    async def get_group_policy(self, channel: str) -> GroupPolicy:
        return self._group_policy

    async def get_group_trigger(self, channel: str) -> tuple[GroupTriggerMode, list[str]]:
        return self._trigger_mode, self._trigger_prefixes

    async def get_enabled_groups(self) -> set[str]:
        return self._enabled_groups

    async def get_guest_mode(self, channel: str) -> bool:
        return False

    async def get_default_user_id(self) -> str | None:
        return "local-user"


_msg_counter = itertools.count(1)


def _make_group_msg(mentioned: bool, content: str = "Hello from group") -> InboundMessage:
    return InboundMessage(
        channel="whatsapp",
        sender_id="user123@s.whatsapp.net",
        content=content,
        chat_id="group456@g.us",
        is_group=True,
        mentioned=mentioned,
        metadata={"message_id": f"msg-{next(_msg_counter):04d}"},
    )


def _make_dm_msg(content: str = "Hello DM") -> InboundMessage:
    return InboundMessage(
        channel="whatsapp",
        sender_id="user123@s.whatsapp.net",
        content=content,
        chat_id="user123@s.whatsapp.net",
        is_group=False,
        mentioned=False,
    )


async def _drain_outbound(bus: MessageBus, timeout: float = 0.5) -> list[OutboundMessage]:
    """Collect all outbound messages from the internal queue within timeout."""
    results: list[OutboundMessage] = []
    try:
        while True:
            item = await asyncio.wait_for(bus._outbound.get(), timeout=timeout)
            results.append(item[2] if isinstance(item, tuple) else item)
    except (TimeoutError, Exception):
        pass
    return results


@pytest.mark.asyncio
async def test_group_mentioned_open_policy_routes_to_agent() -> None:
    """Group message with mention + open policy should be routed to Agent."""
    bus = MessageBus()
    executor = FakeAgentExecutor()
    policy = FakePolicyProvider(group_policy=GroupPolicy.OPEN)
    router = AgentRouter(bus, FakePairingStore(), executor, policy, session_gate_config=_NO_DEBOUNCE)

    await router.start()
    try:
        msg = _make_group_msg(mentioned=True, content="@bot what is AI?")
        await bus._handle_inbound(msg)
        await asyncio.sleep(0.3)

        assert len(executor.calls) == 1
        called_msg, called_uid = executor.calls[0]
        assert called_msg.is_group is True
        assert called_msg.mentioned is True
        assert called_uid == "local-user"
        assert called_msg.content == "@bot what is AI?"

        outbound = await _drain_outbound(bus)
        assert len(outbound) == 1
        assert outbound[0].recipient_id == "group456@g.us"
    finally:
        await router.stop()


@pytest.mark.asyncio
async def test_group_not_mentioned_open_policy_ignored() -> None:
    """Group message without mention should be silently ignored (mention gate)."""
    bus = MessageBus()
    executor = FakeAgentExecutor()
    policy = FakePolicyProvider(group_policy=GroupPolicy.OPEN)
    router = AgentRouter(bus, FakePairingStore(), executor, policy, session_gate_config=_NO_DEBOUNCE)

    await router.start()
    try:
        msg = _make_group_msg(mentioned=False, content="random chat")
        await bus._handle_inbound(msg)
        await asyncio.sleep(0.3)

        assert len(executor.calls) == 0
    finally:
        await router.stop()


@pytest.mark.asyncio
async def test_group_mentioned_disabled_policy_ignored() -> None:
    """Group message with mention but disabled policy should be ignored."""
    bus = MessageBus()
    executor = FakeAgentExecutor()
    policy = FakePolicyProvider(group_policy=GroupPolicy.DISABLED)
    router = AgentRouter(bus, FakePairingStore(), executor, policy, session_gate_config=_NO_DEBOUNCE)

    await router.start()
    try:
        msg = _make_group_msg(mentioned=True, content="@bot hello")
        await bus._handle_inbound(msg)
        await asyncio.sleep(0.3)

        assert len(executor.calls) == 0
    finally:
        await router.stop()


@pytest.mark.asyncio
async def test_group_allowlist_with_mention_routes() -> None:
    """Group message with mention + allowlist policy should route (allowlist behaves like open for now)."""
    bus = MessageBus()
    executor = FakeAgentExecutor()
    policy = FakePolicyProvider(group_policy=GroupPolicy.ALLOWLIST)
    router = AgentRouter(bus, FakePairingStore(), executor, policy, session_gate_config=_NO_DEBOUNCE)

    await router.start()
    try:
        msg = _make_group_msg(mentioned=True, content="@bot search something")
        await bus._handle_inbound(msg)
        await asyncio.sleep(0.3)

        assert len(executor.calls) == 1
        assert executor.calls[0][1] == "local-user"
    finally:
        await router.stop()


@pytest.mark.asyncio
async def test_dm_still_works_with_group_support() -> None:
    """DM messages should continue to work normally alongside group support."""
    bus = MessageBus()
    executor = FakeAgentExecutor()
    policy = FakePolicyProvider(dm_policy=DmPolicy.OPEN, group_policy=GroupPolicy.OPEN)
    router = AgentRouter(bus, FakePairingStore(), executor, policy, session_gate_config=_NO_DEBOUNCE)

    await router.start()
    try:
        msg = _make_dm_msg(content="Hello from DM")
        await bus._handle_inbound(msg)
        await asyncio.sleep(0.3)

        assert len(executor.calls) == 1
        called_msg, called_uid = executor.calls[0]
        assert called_msg.is_group is False
        assert called_uid == "local-user"
    finally:
        await router.stop()


@pytest.mark.asyncio
async def test_error_reply_routes_to_group_chat_id() -> None:
    """Error replies for group messages should go to chat_id, not sender_id."""
    bus = MessageBus()

    class FailingExecutor:
        async def execute_stream(
            self,
            msg: InboundMessage,
            user_id: str,
            **_kwargs: object,
        ) -> AsyncGenerator[ProgressUpdate | OutboundMessage]:
            raise RuntimeError("Test error")
            yield  # pragma: no cover — makes this a generator

    policy = FakePolicyProvider(group_policy=GroupPolicy.OPEN)
    router = AgentRouter(bus, FakePairingStore(), FailingExecutor(), policy)

    await router.start()
    try:
        msg = _make_group_msg(mentioned=True, content="@bot trigger error")
        await bus._handle_inbound(msg)
        await asyncio.sleep(0.3)

        outbound = await _drain_outbound(bus)
        assert len(outbound) == 1
        assert outbound[0].recipient_id == "group456@g.us"
        assert "" in outbound[0].content
    finally:
        await router.stop()


@pytest.mark.asyncio
async def test_prefix_trigger_routes_and_strips_prefix() -> None:
    """Group message with prefix trigger should route and strip the prefix from content."""
    bus = MessageBus()
    executor = FakeAgentExecutor()
    policy = FakePolicyProvider(
        group_policy=GroupPolicy.OPEN,
        trigger_mode=GroupTriggerMode.PREFIX,
        trigger_prefixes=["/ask ", "!ai "],
    )
    router = AgentRouter(bus, FakePairingStore(), executor, policy, session_gate_config=_NO_DEBOUNCE)

    await router.start()
    try:
        msg = _make_group_msg(mentioned=False, content="/ask what is Python?")
        await bus._handle_inbound(msg)
        await asyncio.sleep(0.3)

        assert len(executor.calls) == 1
        called_msg, _ = executor.calls[0]
        assert called_msg.content == "what is Python?"
    finally:
        await router.stop()


@pytest.mark.asyncio
async def test_prefix_trigger_no_match_ignored() -> None:
    """Group message without matching prefix should be ignored."""
    bus = MessageBus()
    executor = FakeAgentExecutor()
    policy = FakePolicyProvider(
        group_policy=GroupPolicy.OPEN,
        trigger_mode=GroupTriggerMode.PREFIX,
        trigger_prefixes=["/ask "],
    )
    router = AgentRouter(bus, FakePairingStore(), executor, policy, session_gate_config=_NO_DEBOUNCE)

    await router.start()
    try:
        msg = _make_group_msg(mentioned=False, content="random chat message")
        await bus._handle_inbound(msg)
        await asyncio.sleep(0.3)

        assert len(executor.calls) == 0
    finally:
        await router.stop()


@pytest.mark.asyncio
async def test_all_trigger_mode_responds_to_everything() -> None:
    """Group message with ALL trigger mode should respond to all messages."""
    bus = MessageBus()
    executor = FakeAgentExecutor()
    policy = FakePolicyProvider(
        group_policy=GroupPolicy.OPEN,
        trigger_mode=GroupTriggerMode.ALL,
    )
    router = AgentRouter(bus, FakePairingStore(), executor, policy, session_gate_config=_NO_DEBOUNCE)

    await router.start()
    try:
        msg = _make_group_msg(mentioned=False, content="just chatting")
        await bus._handle_inbound(msg)
        await asyncio.sleep(0.3)

        assert len(executor.calls) == 1
    finally:
        await router.stop()


@pytest.mark.asyncio
async def test_mention_always_overrides_trigger_mode() -> None:
    """@mention should always trigger regardless of trigger mode."""
    bus = MessageBus()
    executor = FakeAgentExecutor()
    policy = FakePolicyProvider(
        group_policy=GroupPolicy.OPEN,
        trigger_mode=GroupTriggerMode.PREFIX,
        trigger_prefixes=["/ask "],
    )
    router = AgentRouter(bus, FakePairingStore(), executor, policy, session_gate_config=_NO_DEBOUNCE)

    await router.start()
    try:
        msg = _make_group_msg(mentioned=True, content="no prefix but mentioned")
        await bus._handle_inbound(msg)
        await asyncio.sleep(0.3)

        assert len(executor.calls) == 1
        assert executor.calls[0][0].content == "no prefix but mentioned"
    finally:
        await router.stop()


@pytest.mark.asyncio
async def test_enabled_groups_allows_listed_group() -> None:
    """Group message from an enabled group should be processed."""
    bus = MessageBus()
    executor = FakeAgentExecutor()
    policy = FakePolicyProvider(
        group_policy=GroupPolicy.OPEN,
        trigger_mode=GroupTriggerMode.ALL,
        enabled_groups={"group456@g.us"},
    )
    router = AgentRouter(bus, FakePairingStore(), executor, policy, session_gate_config=_NO_DEBOUNCE)

    await router.start()
    try:
        msg = _make_group_msg(mentioned=False, content="hello")
        await bus._handle_inbound(msg)
        await asyncio.sleep(0.3)

        assert len(executor.calls) == 1
    finally:
        await router.stop()


@pytest.mark.asyncio
async def test_enabled_groups_blocks_unlisted_group() -> None:
    """Group message from a non-enabled group should be silently ignored."""
    bus = MessageBus()
    executor = FakeAgentExecutor()
    policy = FakePolicyProvider(
        group_policy=GroupPolicy.OPEN,
        trigger_mode=GroupTriggerMode.ALL,
        enabled_groups={"other-group@g.us"},
    )
    router = AgentRouter(bus, FakePairingStore(), executor, policy, session_gate_config=_NO_DEBOUNCE)

    await router.start()
    try:
        msg = _make_group_msg(mentioned=True, content="@bot hello")
        await bus._handle_inbound(msg)
        await asyncio.sleep(0.3)

        assert len(executor.calls) == 0
    finally:
        await router.stop()


@pytest.mark.asyncio
async def test_enabled_groups_empty_blocks_all() -> None:
    """When enabled_groups is empty set, no groups should be processed (explicit opt-in)."""
    bus = MessageBus()
    executor = FakeAgentExecutor()
    policy = FakePolicyProvider(
        group_policy=GroupPolicy.OPEN,
        trigger_mode=GroupTriggerMode.ALL,
        enabled_groups=set(),
    )
    router = AgentRouter(bus, FakePairingStore(), executor, policy, session_gate_config=_NO_DEBOUNCE)

    await router.start()
    try:
        msg = _make_group_msg(mentioned=True, content="@bot hello")
        await bus._handle_inbound(msg)
        await asyncio.sleep(0.3)

        assert len(executor.calls) == 0
    finally:
        await router.stop()


# ─── Context Accumulation Tests ──────────────────────────────────────


@pytest.mark.asyncio
async def test_non_trigger_messages_accumulate_context() -> None:
    """Non-trigger messages should not invoke Agent but accumulate in buffer."""
    bus = MessageBus()
    executor = FakeAgentExecutor()
    policy = FakePolicyProvider(group_policy=GroupPolicy.OPEN)
    router = AgentRouter(bus, FakePairingStore(), executor, policy, session_gate_config=_NO_DEBOUNCE)

    await router.start()
    try:
        for i in range(3):
            msg = _make_group_msg(mentioned=False, content=f"chat msg {i}")
            await bus._handle_inbound(msg)
        await asyncio.sleep(0.3)

        assert len(executor.calls) == 0
    finally:
        await router.stop()


@pytest.mark.asyncio
async def test_trigger_message_includes_accumulated_context() -> None:
    """Trigger message should carry accumulated non-trigger messages as context."""
    bus = MessageBus()
    executor = FakeAgentExecutor()
    policy = FakePolicyProvider(group_policy=GroupPolicy.OPEN)
    router = AgentRouter(bus, FakePairingStore(), executor, policy, session_gate_config=_NO_DEBOUNCE)

    await router.start()
    try:
        for i in range(3):
            msg = _make_group_msg(mentioned=False, content=f"background msg {i}")
            await bus._handle_inbound(msg)
        await asyncio.sleep(0.2)

        trigger = _make_group_msg(mentioned=True, content="@bot summarize")
        await bus._handle_inbound(trigger)
        await asyncio.sleep(0.3)

        assert len(executor.calls) == 1
        called_msg, _ = executor.calls[0]
        assert len(called_msg.context_messages) == 3
        assert called_msg.context_messages[0].content == "background msg 0"
        assert called_msg.context_messages[2].content == "background msg 2"
    finally:
        await router.stop()


@pytest.mark.asyncio
async def test_context_cleared_after_trigger() -> None:
    """After a trigger drains the buffer, subsequent trigger has no context."""
    bus = MessageBus()
    executor = FakeAgentExecutor()
    policy = FakePolicyProvider(group_policy=GroupPolicy.OPEN)
    router = AgentRouter(bus, FakePairingStore(), executor, policy, session_gate_config=_NO_DEBOUNCE)

    await router.start()
    try:
        msg = _make_group_msg(mentioned=False, content="pre-context")
        await bus._handle_inbound(msg)
        await asyncio.sleep(0.1)

        trigger1 = _make_group_msg(mentioned=True, content="@bot first")
        await bus._handle_inbound(trigger1)
        await asyncio.sleep(0.3)

        trigger2 = _make_group_msg(mentioned=True, content="@bot second")
        await bus._handle_inbound(trigger2)
        await asyncio.sleep(0.3)

        assert len(executor.calls) == 2
        assert len(executor.calls[0][0].context_messages) == 1
        assert len(executor.calls[1][0].context_messages) == 0
    finally:
        await router.stop()


@pytest.mark.asyncio
async def test_prefix_trigger_with_context() -> None:
    """Prefix trigger should also carry accumulated context."""
    bus = MessageBus()
    executor = FakeAgentExecutor()
    policy = FakePolicyProvider(
        group_policy=GroupPolicy.OPEN,
        trigger_mode=GroupTriggerMode.PREFIX,
        trigger_prefixes=["/ask "],
    )
    router = AgentRouter(bus, FakePairingStore(), executor, policy, session_gate_config=_NO_DEBOUNCE)

    await router.start()
    try:
        bg = _make_group_msg(mentioned=False, content="discussing topic X")
        await bus._handle_inbound(bg)
        await asyncio.sleep(0.1)

        trigger = _make_group_msg(mentioned=False, content="/ask what about X?")
        await bus._handle_inbound(trigger)
        await asyncio.sleep(0.3)

        assert len(executor.calls) == 1
        called_msg, _ = executor.calls[0]
        assert called_msg.content == "what about X?"
        assert len(called_msg.context_messages) == 1
        assert called_msg.context_messages[0].content == "discussing topic X"
    finally:
        await router.stop()
