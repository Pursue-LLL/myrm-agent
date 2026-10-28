"""Whether a verification call passed or failed: the exit code decides when there is one, the output text otherwise."""

from __future__ import annotations

import pytest

from myrm_agent_harness.agent.security.guards.loop_guard import VerificationOutcome
from tests.support.call_records import EMPTY, EXIT_0, EXIT_1, FAIL, OK, call, shell, unit_tests


class TestNotAVerification:
    def test_a_call_that_is_not_a_verification_neither_passed_nor_failed(self) -> None:
        record = call("file_read_tool", "/w/app.py", FAIL)

        assert not record.verification_passed
        assert not record.verification_failed


class TestExitCodeDecides:
    def test_exit_zero_passes_though_the_output_reads_like_a_failure(self) -> None:
        record = unit_tests(FAIL, EXIT_0)

        assert record.verification_passed
        assert not record.verification_failed

    def test_non_zero_exit_fails_though_the_output_reads_clean(self) -> None:
        record = unit_tests(OK, EXIT_1)

        assert record.verification_failed
        assert not record.verification_passed

    def test_a_run_that_exited_zero_but_executed_nothing_is_not_proof(self) -> None:
        record = unit_tests(EMPTY, EXIT_0)

        assert not record.verification_passed
        assert not record.verification_failed


class TestWithoutAnExitCodeTheOutputDecides:
    @pytest.mark.parametrize(
        ("level", "passed", "failed"),
        [(OK, True, False), (FAIL, False, True), (EMPTY, False, False)],
    )
    def test_output_level_when_the_exit_code_is_not_known(self, level, passed: bool, failed: bool) -> None:
        record = unit_tests(level)

        assert record.verification_passed is passed
        assert record.verification_failed is failed

    def test_the_outcome_is_none_until_something_sets_it(self) -> None:
        assert shell("pytest").verification_outcome is None
        assert VerificationOutcome.PASSED != VerificationOutcome.FAILED
