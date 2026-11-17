"""A failed run has one definition, and a run-history status filter selects by it.

The ``error`` filter is the one that asks for failures, so it selects a circuit break (a failure with a status of
its own) too; every other filter selects exactly its own status. The server's failure badge and the failed run list
read the stores through this filter, which is why both answer the same count.
"""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits.cron import matching_run_statuses
from myrm_agent_harness.toolkits.cron.run_status_filter import FAILED_RUN_STATUSES
from myrm_agent_harness.toolkits.cron.types import RunStatus


def test_a_failed_run_is_an_error_or_a_circuit_break() -> None:
    assert {RunStatus.ERROR, RunStatus.CIRCUIT_BREAK} == FAILED_RUN_STATUSES


def test_a_filter_on_error_selects_every_failed_status() -> None:
    assert matching_run_statuses("error") == FAILED_RUN_STATUSES


@pytest.mark.parametrize("status", [*(s.value for s in RunStatus if s != RunStatus.ERROR), "timed_out", "cancelled"])
def test_every_other_filter_selects_exactly_its_own_status(status: str) -> None:
    assert matching_run_statuses(status) == {status}


def test_a_stored_status_matches_as_the_enum_and_as_its_plain_string() -> None:
    wanted = matching_run_statuses("error")

    assert "circuit_break" in wanted and RunStatus.CIRCUIT_BREAK in wanted
    assert "ok" not in wanted and RunStatus.OK not in wanted
