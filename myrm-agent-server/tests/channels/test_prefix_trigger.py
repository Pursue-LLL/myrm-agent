"""Tests for prefix trigger mechanism and automatic prefix stripping.

Verifies that AgentRouter correctly:
- Matches configured prefixes against group messages
- Strips the matched prefix from the content before passing to Agent
- Handles edge cases (multiple prefixes, case sensitivity, empty content, etc.)
- Gives @mention priority over prefix matching (no stripping on mention)
"""

from __future__ import annotations

import asyncio
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
from app.channels.types import InboundMessage, OutboundMessage, ProgressUpdate

# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


class StubPairingStore:
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


class RecordingExecutor:
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
            content="ok",
            user_id=user_id,
        )


class PrefixPolicyProvider:
    """Policy provider with configurable prefix trigger."""

    def __init__(
        self,
        prefixes: list[str],
        mode: GroupTriggerMode = GroupTriggerMode.PREFIX,
    ) -> None:
        self._prefixes = prefixes
        self._mode = mode

    async def get_dm_policy(self, channel: str) -> DmPolicy:
        return DmPolicy.OPEN

    async def get_group_policy(self, channel: str) -> GroupPolicy:
        return GroupPolicy.OPEN

    async def get_group_trigger(self, channel: str) -> tuple[GroupTriggerMode, list[str]]:
        return self._mode, self._prefixes

    async def get_enabled_groups(self) -> set[str]:
        return {"group@g.us"}

    async def get_guest_mode(self, channel: str) -> bool:
        return False

    async def get_default_user_id(self) -> str | None:
        return "test-user"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _group_msg(content: str, *, mentioned: bool = False) -> InboundMessage:
    return InboundMessage(
        channel="whatsapp",
        sender_id="sender@s.whatsapp.net",
        content=content,
        chat_id="group@g.us",
        is_group=True,
        mentioned=mentioned,
        metadata={"message_id": "m1"},
    )


async def _run_single(
    prefixes: list[str],
    content: str,
    *,
    mentioned: bool = False,
    mode: GroupTriggerMode = GroupTriggerMode.PREFIX,
) -> list[tuple[InboundMessage, str]]:
    """Helper: send one group message through the router and return executor calls."""
    bus = MessageBus()
    executor = RecordingExecutor()
    policy = PrefixPolicyProvider(prefixes, mode)
    router = AgentRouter(bus, StubPairingStore(), executor, policy)

    await router.start()
    try:
        await bus._handle_inbound(_group_msg(content, mentioned=mentioned))
        await asyncio.sleep(0.4)
        return list(executor.calls)
    finally:
        await router.stop()


# ---------------------------------------------------------------------------
# Tests: _prepare_execution_context（不经 MessageBus / SessionGate 全链路与 sleep）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prepare_execution_context_exec_msg_stripped_prefix() -> None:
    """Executor-bound message comes from context.exec_msg with prefix removed."""
    bus = MessageBus()
    policy = PrefixPolicyProvider(["/ask "])
    router = AgentRouter(bus, StubPairingStore(), RecordingExecutor(), policy)
    inbound = _group_msg("/ask stripped body")
    ctx = await router._prepare_execution_context(inbound)
    assert ctx is not None
    assert ctx.user_id == "test-user"
    assert ctx.chat_id == "group@g.us"
    assert ctx.exec_msg.content == "stripped body"
    assert ctx.message_id == "m1"


# ---------------------------------------------------------------------------
# Tests: basic prefix matching
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_single_prefix_match_and_strip() -> None:
    """Basic: '/ask hello' with prefix '/ask ' → content 'hello'."""
    calls = await _run_single(["/ask "], "/ask hello world")
    assert len(calls) == 1
    assert calls[0][0].content == "hello world"


@pytest.mark.asyncio
async def test_second_prefix_matches() -> None:
    """When first prefix doesn't match, second prefix should be tried."""
    calls = await _run_single(["/ask ", "!ai "], "!ai explain Python")
    assert len(calls) == 1
    assert calls[0][0].content == "explain Python"


@pytest.mark.asyncio
async def test_first_matching_prefix_wins() -> None:
    """If multiple prefixes could match, the first one wins."""
    calls = await _run_single(["/a", "/ask "], "/ask something")
    assert len(calls) == 1
    assert calls[0][0].content == "sk something"


@pytest.mark.asyncio
async def test_no_prefix_match_ignored() -> None:
    """Message not starting with any prefix should be ignored."""
    calls = await _run_single(["/ask ", "!ai "], "hello everyone")
    assert len(calls) == 0


# ---------------------------------------------------------------------------
# Tests: stripping behavior
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_strip_trims_whitespace() -> None:
    """After removing prefix, leading/trailing whitespace should be trimmed."""
    calls = await _run_single(["/ask"], "/ask   spaced out   ")
    assert len(calls) == 1
    assert calls[0][0].content == "spaced out"


@pytest.mark.asyncio
async def test_prefix_only_produces_empty_content() -> None:
    """Message that is exactly the prefix → empty string after strip."""
    calls = await _run_single(["/ask"], "/ask")
    assert len(calls) == 1
    assert calls[0][0].content == ""


@pytest.mark.asyncio
async def test_prefix_with_trailing_space_only() -> None:
    """'/ask ' with content '/ask  ' → empty after strip."""
    calls = await _run_single(["/ask "], "/ask  ")
    assert len(calls) == 1
    assert calls[0][0].content == ""


# ---------------------------------------------------------------------------
# Tests: case sensitivity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prefix_is_case_sensitive() -> None:
    """Prefix matching is case-sensitive: '/Ask' should not match '/ask'."""
    calls = await _run_single(["/ask "], "/Ask hello")
    assert len(calls) == 0


@pytest.mark.asyncio
async def test_uppercase_prefix_matches_uppercase_content() -> None:
    """Uppercase prefix matches uppercase content."""
    calls = await _run_single(["/ASK "], "/ASK hello")
    assert len(calls) == 1
    assert calls[0][0].content == "hello"


# ---------------------------------------------------------------------------
# Tests: mention vs prefix interaction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mention_bypasses_prefix_no_stripping() -> None:
    """@mention should trigger without stripping any prefix."""
    calls = await _run_single(["/ask "], "/ask hello", mentioned=True)
    assert len(calls) == 1
    assert calls[0][0].content == "/ask hello"


@pytest.mark.asyncio
async def test_mention_works_without_prefix_match() -> None:
    """@mention triggers even when content doesn't match any prefix."""
    calls = await _run_single(["/ask "], "random message", mentioned=True)
    assert len(calls) == 1
    assert calls[0][0].content == "random message"


# ---------------------------------------------------------------------------
# Tests: edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_prefix_list_falls_through() -> None:
    """PREFIX mode with empty prefix list → no match, message ignored."""
    calls = await _run_single([], "hello")
    assert len(calls) == 0


@pytest.mark.asyncio
async def test_prefix_at_start_only() -> None:
    """Prefix must be at the start; middle occurrence should not match."""
    calls = await _run_single(["/ask "], "I want to /ask something")
    assert len(calls) == 0


@pytest.mark.asyncio
async def test_unicode_prefix() -> None:
    """Unicode prefix should work correctly."""
    calls = await _run_single(["问 "], "问 什么是 Python？")
    assert len(calls) == 1
    assert calls[0][0].content == "什么是 Python？"


@pytest.mark.asyncio
async def test_mention_only_mode_ignores_prefix_content() -> None:
    """MENTION_ONLY mode should ignore messages even if they have a prefix pattern."""
    calls = await _run_single(
        ["/ask "],
        "/ask hello",
        mode=GroupTriggerMode.MENTION_ONLY,
    )
    assert len(calls) == 0


@pytest.mark.asyncio
async def test_all_mode_does_not_strip() -> None:
    """ALL mode should respond to everything without stripping."""
    calls = await _run_single(
        ["/ask "],
        "/ask hello",
        mode=GroupTriggerMode.ALL,
    )
    assert len(calls) == 1
    assert calls[0][0].content == "/ask hello"
