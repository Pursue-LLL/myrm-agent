"""The rules the verification checklist is made of: what a write needs after it, which failures still stand."""

from __future__ import annotations

from myrm_agent_harness.agent.middlewares.completion.completion_guard.record_rules import (
    code_changed_since_proof,
    failed_verification_types,
    is_code_file,
    unresolved_failures,
)
from myrm_agent_harness.agent.security.guards.loop_guard import VerificationCategory
from tests.support.call_records import EMPTY, FAIL, call, lint, shell, unit_tests, write


class TestCodeFile:
    def test_source_files_count_as_code_whatever_the_case(self) -> None:
        assert is_code_file("/w/app.PY")
        assert is_code_file("src/App.tsx")

    def test_prose_and_data_files_do_not(self) -> None:
        assert not is_code_file("README.md")
        assert not is_code_file("data.json")


class TestCodeChangedSinceProof:
    def test_no_writes_means_nothing_to_prove(self) -> None:
        assert not code_changed_since_proof([])
        assert not code_changed_since_proof([unit_tests()])

    def test_code_written_and_never_verified(self) -> None:
        assert code_changed_since_proof([write("/w/app.py")])

    def test_a_passing_verification_after_the_write_proves_it(self) -> None:
        assert not code_changed_since_proof([write("/w/app.py"), unit_tests()])

    def test_any_verification_category_proves_it(self) -> None:
        assert not code_changed_since_proof([write("/w/app.py"), lint()])

    def test_a_write_after_the_proof_needs_a_new_one(self) -> None:
        assert code_changed_since_proof([write("/w/app.py"), unit_tests(), write("/w/app.py")])

    def test_the_same_check_run_again_after_the_second_write_proves_it(self) -> None:
        assert not code_changed_since_proof([write("/w/app.py"), unit_tests(), write("/w/app.py"), unit_tests()])

    def test_a_verification_that_failed_or_ran_nothing_proves_nothing(self) -> None:
        assert code_changed_since_proof([write("/w/app.py"), unit_tests(FAIL)])
        assert code_changed_since_proof([write("/w/app.py"), unit_tests(EMPTY)])

    def test_a_verification_from_before_the_write_proves_nothing_about_it(self) -> None:
        assert code_changed_since_proof([unit_tests(), write("/w/app.py")])

    def test_prose_written_after_a_proof_does_not_need_one(self) -> None:
        assert not code_changed_since_proof([write("/w/app.py"), unit_tests(), write("/w/README.md")])

    def test_a_write_that_failed_changed_nothing(self) -> None:
        assert not code_changed_since_proof([write("/w/app.py", FAIL)])
        assert not code_changed_since_proof([write("/w/app.py"), unit_tests(), write("/w/app.py", FAIL)])


class TestFailedVerificationTypes:
    def test_the_latest_run_of_a_category_decides(self) -> None:
        assert failed_verification_types([unit_tests(FAIL), unit_tests()]) == frozenset()
        assert failed_verification_types([unit_tests(), unit_tests(FAIL)]) == {VerificationCategory.TEST}

    def test_a_category_that_failed_is_not_cleared_by_another_that_passed(self) -> None:
        assert failed_verification_types([lint(FAIL), unit_tests()]) == {VerificationCategory.LINT}

    def test_failures_of_two_categories_are_both_reported(self) -> None:
        assert failed_verification_types([lint(FAIL), unit_tests(FAIL)]) == {
            VerificationCategory.LINT,
            VerificationCategory.TEST,
        }

    def test_commands_that_are_not_verification_are_ignored(self) -> None:
        assert failed_verification_types([shell("python app.py", FAIL)]) == frozenset()


class TestUnresolvedFailures:
    def test_a_failure_before_the_last_write_was_superseded_by_the_work(self) -> None:
        assert unresolved_failures([shell("ls /nope", FAIL), write("/w/README.md")]) == []

    def test_a_failure_after_the_last_write_stands(self) -> None:
        crash = shell("python app.py", FAIL)

        assert unresolved_failures([write("/w/app.py"), unit_tests(), crash]) == [crash]

    def test_the_same_call_succeeding_later_puts_a_failure_right(self) -> None:
        records = [write("/w/app.py"), shell("python app.py", FAIL), shell("python app.py")]

        assert unresolved_failures(records) == []

    def test_a_different_call_succeeding_does_not(self) -> None:
        crash = shell("python app.py", FAIL)

        assert unresolved_failures([write("/w/app.py"), crash, shell("python other.py")]) == [crash]

    def test_a_success_before_the_failure_does_not_put_it_right(self) -> None:
        crash = shell("python app.py", FAIL)

        assert unresolved_failures([write("/w/app.py"), shell("python app.py"), crash]) == [crash]

    def test_a_missing_file_read_before_writing_it_is_exploration(self) -> None:
        records = [call("file_read_tool", "/w/NOTES.md", FAIL), write("/w/NOTES.md")]

        assert unresolved_failures(records) == []

    def test_a_failed_write_after_the_last_good_write_stands(self) -> None:
        refused = write("/w/b.py", FAIL)

        assert unresolved_failures([write("/w/a.py"), refused]) == [refused]

    def test_a_run_that_wrote_nothing_has_every_failure_standing_in_call_order(self) -> None:
        first, second = shell("ls /nope", FAIL), call("web_fetch_tool", "https://x", FAIL)

        assert unresolved_failures([first, second]) == [first, second]

    def test_a_verification_failure_is_judged_elsewhere(self) -> None:
        assert unresolved_failures([write("/w/app.py"), unit_tests(FAIL)]) == []
