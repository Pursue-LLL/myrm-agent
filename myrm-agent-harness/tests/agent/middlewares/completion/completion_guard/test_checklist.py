"""The verification checklist, the last successful verification command and the temporal order of writes and checks."""

from __future__ import annotations

from pathlib import Path

from myrm_agent_harness.agent.meta_tools.progress.storage import todos_path
from myrm_agent_harness.agent.middlewares.completion.completion_guard.checklist import (
    CriticalCause,
    assess_checklist,
    build_checklist,
    find_last_successful_verification_command,
)
from myrm_agent_harness.agent.security.guards.loop_guard import (
    CallRecord,
    SuccessLevel,
    VerificationCategory,
)
from tests.support.call_records import (
    FAIL,
    call,
    lint,
    shell,
    unit_tests,
    write,
)


class TestBuildChecklist:
    """Test build_checklist generates correct verification items."""

    def test_empty_records(self) -> None:
        checklist, _ = build_checklist([])
        assert "Confirm the response fully addresses" in checklist

    def test_write_without_verification_warns(self) -> None:
        """WRITE tools without verification evidence triggers a warning."""
        records = [
            CallRecord(
                tool_name="file_write_tool",
                args_hash="abc",
                args={"path": "/tmp/test.py"},
                success_level=SuccessLevel.FULL_SUCCESS,
            ),
        ]
        checklist, _ = build_checklist(records)
        assert "file_write_tool" in checklist
        assert "NO verification" in checklist

    def test_write_non_code_file_warns(self) -> None:
        """WRITE tools for non-code files without verification produces warning, not critical error."""
        records = [
            CallRecord(
                tool_name="file_write_tool",
                args_hash="abc",
                args={"path": "/tmp/README.md"},
                success_level=SuccessLevel.FULL_SUCCESS,
            ),
        ]
        checklist, has_critical = build_checklist(records)
        assert not has_critical
        assert "If these are text/data files" in checklist

    def test_write_with_passing_verification(self) -> None:
        """WRITE tools with passing verification produces light checklist."""
        records = [
            CallRecord(
                tool_name="file_write_tool",
                args_hash="abc",
                args={"path": "/tmp/test.py"},
                success_level=SuccessLevel.FULL_SUCCESS,
            ),
            CallRecord(
                tool_name="bash_code_execute_tool",
                args_hash="def",
                args={"command": "pytest"},
                success_level=SuccessLevel.FULL_SUCCESS,
                verification_type=VerificationCategory.TEST,
            ),
        ]
        checklist, _ = build_checklist(records)
        assert "file_write_tool" in checklist
        assert "verified via" in checklist
        assert "test" in checklist

    def test_write_with_failing_verification(self) -> None:
        """WRITE tools with failing verification highlights the failure."""
        records = [
            CallRecord(
                tool_name="file_write_tool",
                args_hash="abc",
                args={"path": "/tmp/test.py"},
                success_level=SuccessLevel.FULL_SUCCESS,
            ),
            CallRecord(
                tool_name="bash_code_execute_tool",
                args_hash="def",
                args={"command": "pytest"},
                success_level=SuccessLevel.FAILURE,
                verification_type=VerificationCategory.TEST,
            ),
        ]
        checklist, _ = build_checklist(records)
        assert "Verification failed" in checklist
        assert "test" in checklist

    def test_write_with_trivial_verification_is_critical(self) -> None:
        """All verifications EMPTY_OK (trivial test output) triggers CRITICAL."""
        records = [
            CallRecord(
                tool_name="file_write_tool",
                args_hash="abc",
                args={"path": "/tmp/test.py"},
                success_level=SuccessLevel.FULL_SUCCESS,
            ),
            CallRecord(
                tool_name="bash_code_execute_tool",
                args_hash="def",
                args={"command": "pytest tests/"},
                success_level=SuccessLevel.EMPTY_OK,
                verification_type=VerificationCategory.TEST,
            ),
        ]
        checklist, has_critical = build_checklist(records)
        assert has_critical
        assert "no meaningful results" in checklist
        assert "MUST ensure tests actually run" in checklist

    def test_execute_tools_produce_verification(self) -> None:
        records = [
            CallRecord(
                tool_name="bash_code_execute_tool",
                args_hash="def",
                args={"command": "ls"},
                success_level=SuccessLevel.FULL_SUCCESS,
            ),
        ]
        checklist, _ = build_checklist(records)
        assert "bash_code_execute_tool" in checklist
        assert "Verify execution results" in checklist

    def test_execute_failures_noted_in_execute_section(self) -> None:
        """EXECUTE failures without writes are WARNING, not CRITICAL."""
        records = [
            CallRecord(
                tool_name="bash_code_execute_tool",
                args_hash="xyz",
                args={"command": "failing_cmd"},
                success_level=SuccessLevel.FAILURE,
            ),
        ]
        checklist, has_critical = build_checklist(records)
        assert not has_critical
        assert "WARNING" in checklist
        assert "failures" in checklist
        assert "bash_code_execute_tool" in checklist
        assert "unresolved failure" not in checklist

    def test_non_execute_failures_warning_when_no_writes(self) -> None:
        """Non-EXECUTE failures are WARNING (not CRITICAL) when no file writes."""
        records = [
            CallRecord(
                tool_name="web_fetch_tool",
                args_hash="abc",
                args={"url": "http://example.com"},
                success_level=SuccessLevel.FAILURE,
            ),
        ]
        checklist, has_critical = build_checklist(records)
        assert not has_critical
        assert "WARNING" in checklist
        assert "web_fetch_tool" in checklist

    def test_non_execute_failures_critical_when_writes_exist(self) -> None:
        """Non-EXECUTE failures are CRITICAL when file writes exist."""
        records = [
            CallRecord(
                tool_name="file_write_tool",
                args_hash="w1",
                args={"path": "/src/app.py", "content": "x"},
                success_level=SuccessLevel.FULL_SUCCESS,
            ),
            CallRecord(
                tool_name="web_fetch_tool",
                args_hash="abc",
                args={"url": "http://example.com"},
                success_level=SuccessLevel.FAILURE,
            ),
        ]
        checklist, has_critical = build_checklist(records)
        assert has_critical
        assert "unresolved failure" in checklist
        assert "web_fetch_tool" in checklist

    def test_browser_tools_produce_verification(self) -> None:
        records = [
            CallRecord(
                tool_name="browser_navigate_tool",
                args_hash="nav1",
                args={"url": "http://localhost:3000"},
                success_level=SuccessLevel.FULL_SUCCESS,
            ),
            CallRecord(
                tool_name="browser_interact_tool",
                args_hash="int1",
                args={"action": "click"},
                success_level=SuccessLevel.FULL_SUCCESS,
            ),
        ]
        checklist, _ = build_checklist(records)
        assert "browser_interact_tool" in checklist
        assert "browser_navigate_tool" in checklist
        assert "Verify browser interactions" in checklist

    def test_read_only_tools_no_verification(self) -> None:
        records = [
            CallRecord(
                tool_name="file_read_tool",
                args_hash="ghi",
                args={"path": "/tmp/test.py"},
                success_level=SuccessLevel.FULL_SUCCESS,
            ),
            CallRecord(
                tool_name="grep_tool",
                args_hash="jkl",
                args={"pattern": "foo"},
                success_level=SuccessLevel.FULL_SUCCESS,
            ),
        ]
        checklist, _ = build_checklist(records)
        assert "Confirm the response fully addresses" in checklist

    def test_todo_uncompleted_critical_with_writes(self, tmp_path: Path) -> None:
        """Uncompleted todos are CRITICAL when file writes exist."""
        todos_file = todos_path(str(tmp_path))
        todos_file.parent.mkdir(parents=True)
        todos_file.write_text(
            """{
  "goal": "Test goal",
  "todos": [
    {"id": "1", "content": "Test step", "status": "pending"}
  ]
}""",
            encoding="utf-8",
        )

        records = [
            CallRecord(
                tool_name="file_write_tool",
                args_hash="w1",
                args={"path": "/src/app.py", "content": "x"},
                success_level=SuccessLevel.FULL_SUCCESS,
            ),
        ]

        checklist, has_critical = build_checklist(records, workspace_root=str(tmp_path))

        assert has_critical
        assert "CRITICAL" in checklist
        assert "incomplete todos" in checklist

    def test_todo_uncompleted_warning_without_writes(self, tmp_path: Path) -> None:
        """Uncompleted todos are WARNING when no file writes."""
        todos_file = todos_path(str(tmp_path))
        todos_file.parent.mkdir(parents=True)
        todos_file.write_text(
            """{
  "goal": "Test goal",
  "todos": [
    {"id": "1", "content": "Test step", "status": "pending"}
  ]
}""",
            encoding="utf-8",
        )

        checklist, has_critical = build_checklist([], workspace_root=str(tmp_path))

        assert not has_critical
        assert "WARNING" in checklist
        assert "incomplete todos" in checklist


class TestFindLastSuccessfulVerificationCommand:
    """Test find_last_successful_verification_command extraction."""

    def test_finds_last_successful_command(self) -> None:
        records = [
            CallRecord(
                tool_name="bash_code_execute_tool",
                args_hash="v1",
                args={"command": "pytest tests/ -x"},
                success_level=SuccessLevel.FULL_SUCCESS,
                verification_type=VerificationCategory.TEST,
            ),
            CallRecord(
                tool_name="bash_code_execute_tool",
                args_hash="v2",
                args={"command": "ruff check src/"},
                success_level=SuccessLevel.FULL_SUCCESS,
                verification_type=VerificationCategory.LINT,
            ),
        ]
        cmd = find_last_successful_verification_command(records)
        assert cmd == "ruff check src/"

    def test_skips_failed_verifications(self) -> None:
        records = [
            CallRecord(
                tool_name="bash_code_execute_tool",
                args_hash="v1",
                args={"command": "pytest tests/"},
                success_level=SuccessLevel.FULL_SUCCESS,
                verification_type=VerificationCategory.TEST,
            ),
            CallRecord(
                tool_name="bash_code_execute_tool",
                args_hash="v2",
                args={"command": "ruff check src/"},
                success_level=SuccessLevel.FAILURE,
                verification_type=VerificationCategory.LINT,
            ),
        ]
        cmd = find_last_successful_verification_command(records)
        assert cmd == "pytest tests/"

    def test_returns_none_when_no_verifications(self) -> None:
        records = [
            CallRecord(
                tool_name="file_write_tool",
                args_hash="w1",
                args={"path": "/src/app.py"},
                success_level=SuccessLevel.FULL_SUCCESS,
            ),
        ]
        cmd = find_last_successful_verification_command(records)
        assert cmd is None

    def test_returns_none_for_empty_command(self) -> None:
        records = [
            CallRecord(
                tool_name="bash_code_execute_tool",
                args_hash="v1",
                args={"command": ""},
                success_level=SuccessLevel.FULL_SUCCESS,
                verification_type=VerificationCategory.TEST,
            ),
        ]
        cmd = find_last_successful_verification_command(records)
        assert cmd is None


class TestTemporalOrderChecking:
    """Test temporal ordering detection in build_checklist.

    Verifies that code writes AFTER the last successful verification
    are flagged as CRITICAL, forcing re-verification.
    """

    def test_code_write_after_verification_is_critical(self) -> None:
        """Write → verify → write again → CRITICAL (post-verification write)."""
        records = [
            CallRecord(
                tool_name="file_write_tool",
                args_hash="w1",
                args={"path": "/src/app.py"},
                success_level=SuccessLevel.FULL_SUCCESS,
            ),
            CallRecord(
                tool_name="bash_code_execute_tool",
                args_hash="v1",
                args={"command": "pytest tests/"},
                success_level=SuccessLevel.FULL_SUCCESS,
                verification_type=VerificationCategory.TEST,
            ),
            CallRecord(
                tool_name="file_edit_tool",
                args_hash="w2",
                args={"path": "/src/app.py"},
                success_level=SuccessLevel.FULL_SUCCESS,
            ),
        ]
        checklist, has_critical = build_checklist(records)
        assert has_critical
        assert "AFTER the last successful verification" in checklist

    def test_code_write_before_verification_not_critical(self) -> None:
        """Write → verify → no more writes → not critical."""
        records = [
            CallRecord(
                tool_name="file_write_tool",
                args_hash="w1",
                args={"path": "/src/app.py"},
                success_level=SuccessLevel.FULL_SUCCESS,
            ),
            CallRecord(
                tool_name="bash_code_execute_tool",
                args_hash="v1",
                args={"command": "pytest tests/"},
                success_level=SuccessLevel.FULL_SUCCESS,
                verification_type=VerificationCategory.TEST,
            ),
        ]
        checklist, has_critical = build_checklist(records)
        assert not has_critical
        assert "verified via" in checklist

    def test_non_code_write_after_verification_not_critical(self) -> None:
        """Write code → verify → write non-code → not critical."""
        records = [
            CallRecord(
                tool_name="file_write_tool",
                args_hash="w1",
                args={"path": "/src/app.py"},
                success_level=SuccessLevel.FULL_SUCCESS,
            ),
            CallRecord(
                tool_name="bash_code_execute_tool",
                args_hash="v1",
                args={"command": "pytest"},
                success_level=SuccessLevel.FULL_SUCCESS,
                verification_type=VerificationCategory.TEST,
            ),
            CallRecord(
                tool_name="file_write_tool",
                args_hash="w2",
                args={"path": "/docs/README.md"},
                success_level=SuccessLevel.FULL_SUCCESS,
            ),
        ]
        _checklist, has_critical = build_checklist(records)
        assert not has_critical

    def test_failed_verification_not_used_as_anchor(self) -> None:
        """Failed verifications are NOT treated as temporal anchors."""
        records = [
            CallRecord(
                tool_name="file_write_tool",
                args_hash="w1",
                args={"path": "/src/app.py"},
                success_level=SuccessLevel.FULL_SUCCESS,
            ),
            CallRecord(
                tool_name="bash_code_execute_tool",
                args_hash="v1",
                args={"command": "pytest"},
                success_level=SuccessLevel.FAILURE,
                verification_type=VerificationCategory.TEST,
            ),
        ]
        checklist, has_critical = build_checklist(records)
        assert has_critical
        assert "Verification failed" in checklist


class TestFailuresAreJudgedByWhatStands:
    """A failure holds the answer back only while it still stands: not once the run fixed and re-ran it, not when it
    was only exploration before the work."""

    def test_fail_fix_rerun_pass_is_not_critical(self) -> None:
        records = [write("/w/app.py"), unit_tests(FAIL), write("/w/app.py"), unit_tests()]

        assert build_checklist(records)[1] is False

    def test_a_fix_that_was_never_re_run_is_critical(self) -> None:
        checklist, critical = build_checklist([write("/w/app.py"), unit_tests(FAIL), write("/w/app.py")])

        assert critical
        assert "Verification failed for: test" in checklist

    def test_a_lint_failure_is_not_cleared_by_re_running_only_the_tests(self) -> None:
        records = [write("/w/app.py"), lint(FAIL), write("/w/app.py"), unit_tests()]

        checklist, critical = build_checklist(records)

        assert critical
        assert "Verification failed for: lint" in checklist

    def test_an_exploratory_shell_failure_before_writing_a_document_is_not_critical(self) -> None:
        assert build_checklist([shell("ls /nope", FAIL), write("/w/README.md")])[1] is False

    def test_a_missing_file_read_before_writing_it_is_not_critical(self) -> None:
        assert build_checklist([call("file_read_tool", "/w/NOTES.md", FAIL), write("/w/NOTES.md")])[1] is False

    def test_a_script_that_crashes_after_the_write_is_critical(self) -> None:
        checklist, critical = build_checklist([write("/w/app.py"), unit_tests(), shell("python app.py", FAIL)])

        assert critical
        assert "1 execution(s) failed" in checklist

    def test_a_crash_the_same_command_later_cleared_is_not_critical(self) -> None:
        records = [write("/w/app.py"), unit_tests(), shell("python app.py", FAIL), shell("python app.py")]

        assert build_checklist(records)[1] is False

    def test_a_fetch_that_failed_after_the_write_is_critical(self) -> None:
        checklist, critical = build_checklist([write("/w/R.md"), call("web_fetch_tool", "https://x", FAIL)])

        assert critical
        assert "unresolved failure(s) in: web_fetch_tool" in checklist

    def test_without_a_write_a_failure_only_warns(self) -> None:
        checklist, critical = build_checklist([shell("python app.py", FAIL), call("web_fetch_tool", "https://x", FAIL)])

        assert not critical
        assert "WARNING: 1 execution(s) had failures" in checklist
        assert "WARNING: 1 failure(s) in web_fetch_tool" in checklist

    def test_a_failure_that_was_superseded_is_not_listed_at_all(self) -> None:
        checklist, _ = build_checklist([shell("ls /nope", FAIL), write("/w/README.md")])

        assert "failed" not in checklist
        assert "failure" not in checklist


class TestChecklistCauses:
    """The causes are kept apart so the independent re-run can clear a stale verification and nothing else."""

    def test_code_never_verified(self) -> None:
        assert assess_checklist([write("/w/app.py")]).causes == {CriticalCause.UNVERIFIED_CODE}

    def test_code_changed_after_a_passing_verification(self) -> None:
        records = [write("/w/app.py"), unit_tests(), write("/w/app.py")]

        assert assess_checklist(records).causes == {CriticalCause.STALE_VERIFICATION}

    def test_a_failing_verification(self) -> None:
        assert assess_checklist([write("/w/app.py"), unit_tests(FAIL)]).causes == {CriticalCause.FAILED_VERIFICATION}

    def test_a_verification_that_ran_nothing(self) -> None:
        records = [write("/w/app.py"), shell("pytest", SuccessLevel.EMPTY_OK, VerificationCategory.TEST)]

        assert assess_checklist(records).causes == {CriticalCause.EMPTY_VERIFICATION}

    def test_a_stale_verification_beside_a_standing_crash_is_two_causes(self) -> None:
        records = [write("/w/app.py"), unit_tests(), write("/w/app.py"), shell("python app.py", FAIL)]

        assert assess_checklist(records).causes == {
            CriticalCause.STALE_VERIFICATION,
            CriticalCause.UNRESOLVED_FAILURE,
        }

    def test_work_that_stands_has_no_cause(self) -> None:
        checklist = assess_checklist([write("/w/app.py"), unit_tests()])

        assert checklist.causes == frozenset()
        assert not checklist.critical
