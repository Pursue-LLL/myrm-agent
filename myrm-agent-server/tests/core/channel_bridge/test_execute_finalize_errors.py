"""A failed turn replies with the harness diagnostic, never the provider's raw error text.

``error_user_message`` / ``error_steps`` come from the ``diagnostic_result`` of the fatal ``error`` event
(see ``test_stream_events``); the raw ``error_message`` is only the fallback for undiagnosable errors.
"""

from __future__ import annotations

import pytest

from app.channels.types import InboundMessage
from app.core.channel_bridge.executor_helpers import StreamAccumulator
from tests.core.channel_bridge.test_execute_finalize import _finalize


@pytest.mark.asyncio
async def test_error_message_becomes_error_reply() -> None:
    acc = StreamAccumulator()
    acc.error_message = "tool crashed"
    _persist_mock, reply = await _finalize(acc, ((), frozenset()))
    assert "[Error] tool crashed" in reply.content


_RAW_PROVIDER_ERROR = (
    "_XaiEntitlementError: Error code: 403 - {'code': 'The caller does not have permission', "
    "'error': 'Your team has either used all available credits or reached its monthly spending limit.'}"
)


def _diagnosed_error_acc() -> StreamAccumulator:
    acc = StreamAccumulator()
    acc.error_message = _RAW_PROVIDER_ERROR
    acc.error_user_message = "Your API account balance is insufficient"
    acc.error_steps = ["Top up your account", "Switch to another model", "Use another API key", "dropped fourth step"]
    return acc


@pytest.mark.asyncio
async def test_diagnosed_error_replies_with_diagnostic_and_hides_raw_provider_text() -> None:
    persist_mock, reply = await _finalize(_diagnosed_error_acc(), ((), frozenset()))

    assert reply.content.startswith("❌ Your API account balance is insufficient\n\nNext steps:\n• Top up your account")
    assert "• Use another API key" in reply.content
    assert "dropped fourth step" not in reply.content
    for leaked in ("403", "_XaiEntitlementError", "monthly spending limit"):
        assert leaked not in reply.content
    assert persist_mock.call_args.args[1] == reply.content


@pytest.mark.asyncio
async def test_diagnosed_error_next_steps_header_follows_member_locale() -> None:
    zh_message = InboundMessage(
        channel="telegram",
        sender_id="user-1",
        content="hi",
        sent_timezone="UTC",
        metadata={"platform_locale": "zh-CN"},
    )
    _persist_mock, reply = await _finalize(_diagnosed_error_acc(), ((), frozenset()), message=zh_message)

    assert "后续步骤" in reply.content
    assert "Next steps:" not in reply.content


@pytest.mark.asyncio
async def test_diagnosed_error_without_steps_has_no_next_steps_block() -> None:
    acc = _diagnosed_error_acc()
    acc.error_steps = []
    _persist_mock, reply = await _finalize(acc, ((), frozenset()))

    assert reply.content == "❌ Your API account balance is insufficient"


@pytest.mark.asyncio
async def test_streamed_text_wins_over_a_later_error() -> None:
    acc = _diagnosed_error_acc()
    acc.chunks.append("Partial answer.")
    _persist_mock, reply = await _finalize(acc, ((), frozenset()))

    assert reply.content == "Partial answer."
