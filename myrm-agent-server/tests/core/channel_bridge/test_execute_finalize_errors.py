"""A failed turn replies with the member-safe wording of its error kind, never the provider's raw text.

``error_kind`` comes from the fatal ``error`` event (see ``test_stream_events``); the raw ``error_message``
only reaches the operator log, under the same reference id the reply carries.
"""

from __future__ import annotations

import logging
import re
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from myrm_agent_harness.toolkits.llms.errors.classifier import ErrorKind

from app.channels.routing.friendly_errors import ERROR_TYPE_METADATA_KEY, is_error_reply
from app.channels.types import InboundMessage
from app.core.channel_bridge.executor_helpers import StreamAccumulator
from tests.core.channel_bridge.test_execute_finalize import _finalize

_RAW_PROVIDER_ERROR = (
    "_XaiEntitlementError: Error code: 403 - {'code': 'The caller does not have permission', "
    "'error': 'Your team has either used all available credits or reached its monthly spending limit.'}"
)
_REF = re.compile(r" \[ref: ([0-9a-f]{8})\]$")
_CAPABILITIES = "app.channels.routing.friendly_errors.get_deployment_capabilities"


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
async def test_a_cut_off_answer_keeps_its_text_and_says_it_is_incomplete() -> None:
    acc = _failed_acc(ErrorKind.TIMEOUT)
    acc.draft.feed({"type": "message", "data": "The capital of France is Pa"})
    persist_mock, reply = await _finalize(acc, ((), frozenset()))

    assert reply.content.startswith("The capital of France is Pa\n\n")
    assert "timed out" in reply.content
    assert _REF.search(reply.content) is not None
    assert "_XaiEntitlementError" not in reply.content
    assert is_error_reply(reply)
    assert reply.metadata is not None
    assert reply.metadata[ERROR_TYPE_METADATA_KEY] == ErrorKind.TIMEOUT.value
    assert persist_mock.call_args.args[1] == reply.content


@pytest.mark.asyncio
async def test_a_cut_off_answer_logs_the_raw_error_under_the_reply_reference(caplog: pytest.LogCaptureFixture) -> None:
    acc = _failed_acc()
    acc.draft.feed({"type": "message", "data": "Partial answer."})
    with caplog.at_level(logging.WARNING):
        _persist_mock, reply = await _finalize(acc, ((), frozenset()))

    ref = _REF.search(reply.content)
    assert ref is not None
    logged = [r.getMessage() for r in caplog.records if _RAW_PROVIDER_ERROR in r.getMessage()]
    assert len(logged) == 1
    assert f"[ref: {ref.group(1)}]" in logged[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", list(ErrorKind))
async def test_failed_turn_reply_is_flagged_with_its_error_kind(kind: ErrorKind) -> None:
    _persist_mock, reply = await _finalize(_failed_acc(kind), ((), frozenset()))

    assert is_error_reply(reply)
    assert reply.metadata is not None
    assert reply.metadata[ERROR_TYPE_METADATA_KEY] == kind.value


@pytest.mark.asyncio
async def test_an_answer_is_not_flagged_as_a_failed_turn() -> None:
    acc = StreamAccumulator()
    acc.draft.feed({"type": "message", "data": "Here is your answer."})
    _persist_mock, reply = await _finalize(acc, ((), frozenset()))

    assert not is_error_reply(reply)


@pytest.mark.asyncio
async def test_account_guidance_swaps_in_the_owner_wording() -> None:
    _persist_mock, generic = await _finalize(_failed_acc(), ((), frozenset()))
    with patch(_CAPABILITIES, return_value=SimpleNamespace(uses_platform_budget=False)):
        persist_mock, owner = await _finalize(_failed_acc(), ((), frozenset()), account_guidance=True)

    assert "administrator" in generic.content
    assert "balance or quota" in owner.content
    assert _REF.search(owner.content) is not None
    assert "_XaiEntitlementError" not in owner.content
    assert persist_mock.call_args.args[1] == owner.content


@pytest.mark.asyncio
async def test_a_failed_turn_keeps_its_flag_next_to_the_other_reply_metadata() -> None:
    acc = _failed_acc()
    acc.cost_usd = 0.05
    acc.model_name = "m"
    _persist_mock, reply = await _finalize(acc, ((), frozenset()), memory_settings={"enableCostEstimation": True})

    assert reply.metadata is not None
    assert reply.metadata[ERROR_TYPE_METADATA_KEY] == ErrorKind.BILLING.value
    assert "cost_metadata" in reply.metadata
