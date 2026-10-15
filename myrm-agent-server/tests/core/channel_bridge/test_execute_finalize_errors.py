"""A failed turn replies with the member-safe wording of its error kind, never the provider's raw text.

``error_kind`` comes from the fatal ``error`` event (see ``test_stream_events``); the raw ``error_message``
only reaches the operator log, under the same reference id the reply carries.
"""

from __future__ import annotations

import logging
import re

import pytest
from myrm_agent_harness.toolkits.llms.errors.classifier import ErrorKind

from app.channels.types import InboundMessage
from app.core.channel_bridge.executor_helpers import StreamAccumulator
from tests.core.channel_bridge.test_execute_finalize import _finalize

_RAW_PROVIDER_ERROR = (
    "_XaiEntitlementError: Error code: 403 - {'code': 'The caller does not have permission', "
    "'error': 'Your team has either used all available credits or reached its monthly spending limit.'}"
)
_REF = re.compile(r" \[ref: ([0-9a-f]{8})\]$")


def _failed_acc(kind: ErrorKind = ErrorKind.BILLING) -> StreamAccumulator:
    acc = StreamAccumulator()
    acc.error_message = _RAW_PROVIDER_ERROR
    acc.error_kind = kind
    return acc


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", list(ErrorKind))
async def test_every_error_kind_replies_with_catalog_wording_and_a_reference(kind: ErrorKind) -> None:
    persist_mock, reply = await _finalize(_failed_acc(kind), ((), frozenset()))

    assert _REF.search(reply.content) is not None
    assert reply.content == reply.content.strip()
    assert not reply.content.startswith("error_")
    assert "_XaiEntitlementError" not in reply.content
    assert persist_mock.call_args.args[1] == reply.content


@pytest.mark.asyncio
async def test_reply_hides_the_provider_text_and_the_billing_state() -> None:
    _persist_mock, reply = await _finalize(_failed_acc(), ((), frozenset()))

    for leaked in ("403", "_XaiEntitlementError", "monthly spending limit", "credits", "balance"):
        assert leaked not in reply.content
    assert "administrator" in reply.content


@pytest.mark.asyncio
async def test_reply_follows_the_member_locale() -> None:
    zh_message = InboundMessage(
        channel="telegram",
        sender_id="user-1",
        content="hi",
        sent_timezone="UTC",
        metadata={"platform_locale": "zh-CN"},
    )
    _persist_mock, reply = await _finalize(_failed_acc(ErrorKind.TIMEOUT), ((), frozenset()), message=zh_message)

    assert "超时" in reply.content
    assert "timed out" not in reply.content


@pytest.mark.asyncio
async def test_raw_error_is_logged_under_the_reference_the_reply_carries(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        _persist_mock, reply = await _finalize(_failed_acc(), ((), frozenset()))

    ref = _REF.search(reply.content)
    assert ref is not None
    logged = [r.getMessage() for r in caplog.records if _RAW_PROVIDER_ERROR in r.getMessage()]
    assert len(logged) == 1
    assert f"[ref: {ref.group(1)}]" in logged[0]


@pytest.mark.asyncio
async def test_streamed_text_wins_over_a_later_error() -> None:
    acc = _failed_acc()
    acc.chunks.append("Partial answer.")
    _persist_mock, reply = await _finalize(acc, ((), frozenset()))

    assert reply.content == "Partial answer."
