"""The /compact slash command: how a person's request reaches the handler and what the reply tells them."""

from __future__ import annotations

import re
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.protocols.compact import MAX_FOCUS_TOPIC_LENGTH, CompactResult, CompactSkip
from app.channels.routing.commands import handle_compact
from app.channels.types import InboundMessage, OutboundMessage

_COMPACTED = CompactResult(compacted=True, message_count=10, tokens_saved=500)

# What each locale's reply must say for a compaction that did not happen; the key set is checked against CompactSkip.
_SKIP_WORDING: dict[CompactSkip, dict[str, str]] = {
    CompactSkip.NOTHING_TO_COMPACT: {"en": "Nothing to compact yet", "zh-CN": "暂时无需压缩"},
    CompactSkip.BUSY: {"en": "already running", "zh-CN": "正在压缩中"},
    CompactSkip.PAUSED: {"en": "paused for now", "zh-CN": "暂时停用"},
    CompactSkip.FAILED: {"en": "Compaction failed", "zh-CN": "压缩失败"},
}
_SKIP_CASES = [
    pytest.param(skip, locale, phrase, id=f"{skip.value}-{locale}")
    for skip, phrases in _SKIP_WORDING.items()
    for locale, phrase in phrases.items()
]


def _msg(*, is_group: bool = False, user_id: str | None = None, locale: str | None = None) -> InboundMessage:
    return InboundMessage(
        channel="test",
        sender_id="user1",
        content="",
        is_group=is_group,
        user_id=user_id,
        metadata={"locale": locale} if locale else {},
    )


def _bus() -> MagicMock:
    bus = MagicMock()
    bus.publish_outbound = AsyncMock()
    bus.get_channel = MagicMock(return_value=None)
    return bus


def _dm_resolver() -> MagicMock:
    resolver = MagicMock()
    resolver.resolve_dm_user = AsyncMock(return_value="uid1")
    return resolver


def _reply_of(bus: MagicMock) -> str:
    reply: OutboundMessage = bus.publish_outbound.call_args[0][0]
    return reply.content


async def _reply_to(outcome: CompactResult | Exception, *, locale: str | None = None, focus_topic: str = "") -> str:
    """What /compact answers when the handler returns ``outcome``, or raises it."""
    bus = _bus()
    handler = AsyncMock(side_effect=outcome) if isinstance(outcome, Exception) else AsyncMock(return_value=outcome)
    await handle_compact(_msg(locale=locale), bus, _dm_resolver(), compact_handler=handler, focus_topic=focus_topic)
    return _reply_of(bus)


async def test_no_handler_configured() -> None:
    bus = _bus()

    await handle_compact(_msg(), bus, MagicMock(), compact_handler=None)

    bus.publish_outbound.assert_called_once()
    assert "not configured" in _reply_of(bus)


async def test_dm_compact_success_reports_the_counts() -> None:
    reply = await _reply_to(_COMPACTED)

    assert "compacted" in reply.lower()
    assert "10 messages" in reply
    assert "500 tokens" in reply


async def test_group_compact_success() -> None:
    bus = _bus()
    resolver = MagicMock()
    resolver.resolve_group_user = AsyncMock(return_value=("guser", _msg(is_group=True, user_id="guser")))
    handler = AsyncMock(return_value=CompactResult(compacted=True, message_count=5, tokens_saved=200))

    await handle_compact(_msg(is_group=True), bus, resolver, compact_handler=handler)

    handler.assert_called_once()


async def test_dm_without_a_resolved_user_does_not_compact() -> None:
    resolver = MagicMock()
    resolver.resolve_dm_user = AsyncMock(return_value=None)
    handler = AsyncMock()

    await handle_compact(_msg(), _bus(), resolver, compact_handler=handler)

    handler.assert_not_called()


async def test_group_without_a_resolved_user_does_not_compact() -> None:
    resolver = MagicMock()
    resolver.resolve_group_user = AsyncMock(return_value=None)
    handler = AsyncMock()

    await handle_compact(_msg(is_group=True), _bus(), resolver, compact_handler=handler)

    handler.assert_not_called()


def test_every_way_a_compaction_can_be_skipped_has_wording() -> None:
    assert set(_SKIP_WORDING) == set(CompactSkip)


@pytest.mark.parametrize(("skip", "locale", "phrase"), _SKIP_CASES)
async def test_a_skipped_compaction_is_worded_for_what_happened_in_the_readers_language(
    skip: CompactSkip, locale: str, phrase: str
) -> None:
    reply = await _reply_to(CompactResult(compacted=False, skip=skip), locale=locale)

    assert phrase in reply
    if locale == "zh-CN":
        assert not re.search("[A-Za-z]", reply)


@pytest.mark.parametrize("locale", ["en", "zh-CN"])
async def test_a_handler_that_raises_gets_the_failure_reply_without_the_exception(locale: str) -> None:
    reply = await _reply_to(RuntimeError("db error"), locale=locale)

    assert reply == await _reply_to(CompactResult(compacted=False, skip=CompactSkip.FAILED), locale=locale)
    assert "db error" not in reply


async def test_a_handler_that_gives_no_reason_for_not_compacting_reads_as_a_failure() -> None:
    reply = await _reply_to(CompactResult(compacted=False))

    assert reply == await _reply_to(CompactResult(compacted=False, skip=CompactSkip.FAILED))


async def test_focus_topic_is_passed_to_the_handler() -> None:
    bus = _bus()
    handler = AsyncMock(return_value=_COMPACTED)

    await handle_compact(_msg(), bus, _dm_resolver(), compact_handler=handler, focus_topic="API design")

    assert handler.call_args.kwargs["focus_topic"] == "API design"


async def test_focus_topic_is_truncated_to_the_limit() -> None:
    handler = AsyncMock(return_value=_COMPACTED)

    await handle_compact(_msg(), _bus(), _dm_resolver(), compact_handler=handler, focus_topic="x" * 300)

    assert len(handler.call_args.kwargs["focus_topic"]) == MAX_FOCUS_TOPIC_LENGTH


@pytest.mark.parametrize(
    ("locale", "hint"),
    [("en", "(focus: API design)"), ("zh-CN", "（聚焦主题：API 设计）")],
)
async def test_focus_topic_is_named_in_the_readers_language(locale: str, hint: str) -> None:
    topic = "API design" if locale == "en" else "API 设计"

    reply = await _reply_to(_COMPACTED, locale=locale, focus_topic=topic)

    assert hint in reply


@pytest.mark.parametrize("locale", ["en", "zh-CN"])
async def test_no_focus_topic_leaves_no_hint(locale: str) -> None:
    reply = await _reply_to(_COMPACTED, locale=locale)

    assert "focus" not in reply
    assert "聚焦" not in reply
