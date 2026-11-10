"""Tests for THINKING_SIGNATURE error classification."""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits.llms.errors.classifier import (
    ErrorKind,
    classify_error,
    classify_failover_reason,
)
from myrm_agent_harness.toolkits.llms.errors.error_types import FailoverReason


class _FakeError(Exception):
    def __init__(self, msg: str, status_code: int | None = None) -> None:
        super().__init__(msg)
        self.status_code = status_code


# The provider's three wordings for a refused replay of signed reasoning.
_REFUSALS = [
    "messages.1.content.0: Invalid `signature` in `thinking` block",
    "messages.3.content.0: Invalid `signature` in `thinking` block: the block was written for a different conversation",
    (
        "messages.5.content.0.type: Expected `thinking` or `redacted_thinking`, but found `text`. When `thinking` is "
        "enabled, a final `assistant` message must start with a thinking block (preceding the lastmost set of "
        "`tool_use` and `tool_result` blocks)."
    ),
    (
        "messages.1.content.0: `thinking` or `redacted_thinking` blocks in the latest assistant message cannot be "
        "modified. These blocks must remain as they were in the original response."
    ),
]


class TestThinkingSignatureClassification:
    @pytest.mark.parametrize("msg", _REFUSALS)
    def test_each_wording_is_a_refused_replay(self, msg: str) -> None:
        exc = _FakeError(msg, status_code=400)
        assert classify_failover_reason(exc) == FailoverReason.THINKING_SIGNATURE
        assert classify_error(exc) == ErrorKind.FORMAT_ERROR

    @pytest.mark.parametrize("msg", _REFUSALS)
    def test_only_a_400_is_a_refused_replay(self, msg: str) -> None:
        assert classify_failover_reason(_FakeError(msg, status_code=500)) != FailoverReason.THINKING_SIGNATURE

    @pytest.mark.parametrize(
        "msg",
        [
            "messages.0.content: Input should be a valid list",
            "thinking.budget_tokens: must be less than max_tokens",
            "Thinking is mandatory for this model and cannot be disabled.",
        ],
    )
    def test_other_400s_are_not_a_refused_replay(self, msg: str) -> None:
        assert classify_failover_reason(_FakeError(msg, status_code=400)) != FailoverReason.THINKING_SIGNATURE
