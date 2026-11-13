"""Tool-call ordering counter: one series per outcome, and recording needs no metrics backend."""

from __future__ import annotations

from typing import get_args
from unittest.mock import MagicMock, patch

import pytest

from myrm_agent_harness.observability.metrics.tool_order_metrics import ToolOrderOutcome, record_tool_order

COUNTER = "myrm_agent_harness.observability.metrics.tool_order_metrics.tool_call_order_total"


@pytest.mark.parametrize("outcome", get_args(ToolOrderOutcome))
def test_each_outcome_counts_in_its_own_series(outcome: ToolOrderOutcome) -> None:
    counter = MagicMock()

    with patch(COUNTER, counter):
        record_tool_order(outcome)

    counter.labels.assert_called_once_with(outcome=outcome)
    counter.labels.return_value.inc.assert_called_once_with()


def test_recording_is_a_no_op_without_a_metrics_backend() -> None:
    with patch(COUNTER, None):
        record_tool_order("held_for_order")
