"""A tool result is written to the call that produced it, also when calls overlap.

[INPUT]
- agent.security.guards.loop_guard::LoopGuard (POS: the guard that opens a record per call and takes its result)

[OUTPUT]
- tests: the record handle, result attribution under overlap, the no-progress streak through the finished record

[POS]
Parallel tool calls open their records before any of them returns, so "the last record" is not the one a
result belongs to. The handle ``latest_record()`` returns lets the caller say which record a result is for.
"""

from __future__ import annotations

from myrm_agent_harness.agent.security.guards.loop_guard import LoopAction, LoopGuard, SuccessLevel

BASH = "bash_code_execute_tool"


class TestCallRecordHandle:
    def test_latest_record_is_the_record_the_last_pre_check_opened(self) -> None:
        guard = LoopGuard()
        assert guard.latest_record() is None

        guard.pre_check(BASH, {"command": "ls"})
        first = guard.latest_record()
        guard.pre_check(BASH, {"command": "pwd"})

        assert first is not None
        assert first.args == {"command": "ls"}
        assert guard.latest_record() is not first

    def test_recorded_calls_is_a_snapshot_oldest_first(self) -> None:
        guard = LoopGuard()
        guard.pre_check(BASH, {"command": "ls"})
        guard.pre_check(BASH, {"command": "pwd"})

        snapshot = guard.recorded_calls()
        snapshot.clear()

        assert [rec.args["command"] for rec in guard.recorded_calls()] == ["ls", "pwd"]


class TestResultAttribution:
    def test_overlapping_calls_keep_their_own_results(self) -> None:
        guard = LoopGuard()
        failing, passing = {"command": "pytest tests/a"}, {"command": "pytest tests/b"}
        guard.pre_check(BASH, failing)
        rec_failing = guard.latest_record()
        guard.pre_check(BASH, passing)
        rec_passing = guard.latest_record()
        assert rec_failing is not None
        assert rec_passing is not None

        guard.record_result(BASH, passing, "2 passed", record=rec_passing)
        guard.record_result(BASH, failing, "AssertionError: assert 0\n1 failed", record=rec_failing)

        assert rec_passing.result_content == "2 passed"
        assert rec_passing.success_level == SuccessLevel.FULL_SUCCESS
        assert rec_failing.result_content.startswith("AssertionError")
        assert rec_failing.success_level == SuccessLevel.FAILURE

    def test_without_a_handle_the_result_goes_to_the_latest_record(self) -> None:
        guard = LoopGuard()
        guard.pre_check(BASH, {"command": "ls"})
        guard.record_result(BASH, {"command": "ls"}, "a.txt")

        latest = guard.latest_record()
        assert latest is not None
        assert latest.result_content == "a.txt"

    def test_no_progress_streak_ends_at_the_record_that_finished(self) -> None:
        guard = LoopGuard(no_progress_threshold=2)
        guard.pre_check(BASH, {"command": "check 1"})
        guard.record_result(BASH, {"command": "check 1"}, "same output")
        guard.pre_check(BASH, {"command": "check 2"})
        rec_second = guard.latest_record()
        guard.pre_check("web_search_tool", {"query": "still running"})
        assert rec_second is not None

        verdict = guard.record_result(BASH, {"command": "check 2"}, "same output", record=rec_second)

        assert verdict.action == LoopAction.WARN
