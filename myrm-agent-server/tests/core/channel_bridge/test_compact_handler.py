"""ChannelCompactHandler: a person's /compact reaches the service as their request and comes back in the channel's terms."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

from app.channels.protocols.compact import CompactResult, CompactSkip
from app.channels.types import InboundMessage
from app.core.channel_bridge.compact_handler import ChannelCompactHandler
from app.services.chat.compact_service import CompactReason
from app.services.chat.compact_service import CompactResult as ServiceCompactResult

_MODULE = "app.core.channel_bridge.compact_handler"
_MESSAGE = InboundMessage(channel="telegram", sender_id="u1", chat_id="c1", content="/compact", user_id="uid1")

# Only reasons known to be no failure are worded as such; the rest, and any added later, read as a failure.
_SKIP_BY_REASON: dict[CompactReason, CompactSkip] = {
    CompactReason.NO_COMPACTABLE_MESSAGES: CompactSkip.NOTHING_TO_COMPACT,
    CompactReason.TOO_FEW_MESSAGES: CompactSkip.NOTHING_TO_COMPACT,
    CompactReason.CONCURRENT_COMPACTION: CompactSkip.BUSY,
    CompactReason.SUMMARIZE_CIRCUIT_OPEN: CompactSkip.PAUSED,
    CompactReason.ANTI_THRASH_ACTIVE: CompactSkip.FAILED,
    CompactReason.CHAT_NOT_FOUND: CompactSkip.FAILED,
    CompactReason.TIMEOUT: CompactSkip.FAILED,
    CompactReason.PERSIST_FAILED: CompactSkip.FAILED,
}


@asynccontextmanager
async def _session() -> AsyncIterator[MagicMock]:
    yield MagicMock()


@pytest.fixture
def chat_lookup() -> Iterator[AsyncMock]:
    """The lookup of the conversation to compact, recorded."""
    lookup = AsyncMock(return_value=SimpleNamespace(id="chat-1"))
    with patch(f"{_MODULE}.ChatService.get_or_create_channel_chat", lookup):
        yield lookup


@pytest.fixture
def compaction(chat_lookup: AsyncMock) -> Iterator[AsyncMock]:
    """The compaction service, recorded; whatever the handler looks up on the way to it is stood in for."""
    service = AsyncMock(return_value=ServiceCompactResult(compacted=True, message_count=12, tokens_saved=3400))
    with (
        patch(f"{_MODULE}.resolve_command_session_key", AsyncMock(return_value="telegram:c1")),
        patch(f"{_MODULE}.get_session", _session),
        patch(f"{_MODULE}.compact_chat", service),
    ):
        yield service


async def test_a_command_reaches_the_service_as_a_persons_request(compaction: AsyncMock) -> None:
    await ChannelCompactHandler()(_MESSAGE, "uid1", focus_topic="billing")

    compaction.assert_awaited_once_with(ANY, "chat-1", focus_topic="billing", explicit_request=True)


async def test_the_conversation_compacted_is_the_one_the_command_resolves(compaction: AsyncMock, chat_lookup: AsyncMock) -> None:
    await ChannelCompactHandler()(_MESSAGE, "uid1")

    chat_lookup.assert_awaited_once_with("telegram:c1", "telegram")


async def test_a_compaction_that_happened_carries_its_counts(compaction: AsyncMock) -> None:
    result = await ChannelCompactHandler()(_MESSAGE, "uid1")

    assert result == CompactResult(compacted=True, message_count=12, tokens_saved=3400)


def test_every_reason_the_service_gives_is_covered() -> None:
    assert set(_SKIP_BY_REASON) == set(CompactReason)


@pytest.mark.parametrize(("reason", "skip"), list(_SKIP_BY_REASON.items()), ids=lambda value: str(value))
async def test_a_reason_is_worded_as_one_of_the_channels_outcomes(
    compaction: AsyncMock, reason: CompactReason, skip: CompactSkip
) -> None:
    compaction.return_value = ServiceCompactResult(compacted=False, message_count=3, reason=reason)

    result = await ChannelCompactHandler()(_MESSAGE, "uid1")

    assert result == CompactResult(compacted=False, message_count=3, skip=skip)


@pytest.mark.parametrize("reason", ["a_reason_added_later", None, ""])
async def test_a_reason_the_bridge_does_not_know_is_a_failure(compaction: AsyncMock, reason: str | None) -> None:
    compaction.return_value = ServiceCompactResult(compacted=False, reason=reason)

    result = await ChannelCompactHandler()(_MESSAGE, "uid1")

    assert result.skip is CompactSkip.FAILED
