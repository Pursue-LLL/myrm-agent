"""The guard re-runs the last verification in the sandbox when code was written after it passed."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from myrm_agent_harness.agent.middlewares.completion.completion_guard import (
    CompletionGuard,
    reset_completion_guard,
)
from myrm_agent_harness.agent.middlewares.completion.completion_guard import guard as guard_module
from myrm_agent_harness.agent.security.guards.loop_guard import (
    CallRecord,
    SuccessLevel,
    VerificationCategory,
)
from tests.support.call_records import (
    FAIL,
    shell,
    unit_tests,
    write,
)
from tests.support.completion_guard_harness import (
    LOOP_GUARD_PATCH,
    make_state,
    pending,
    reasons_of,
)


class TestIndependentRerun:
    """Test CompletionGuard independent re-run in sandbox."""

    def setup_method(self) -> None:
        self.guard = CompletionGuard()
        reset_completion_guard()

    @pytest.mark.asyncio
    async def test_rerun_passes_allows_completion(self) -> None:
        """When independent re-run passes, agent is allowed to complete."""
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

        mock_executor = MagicMock()
        mock_result = MagicMock(exit_code=0, stdout="OK", stderr="")
        mock_executor.execute_bash = AsyncMock(return_value=mock_result)

        state = make_state([AIMessage(content="Done.")])
        with (
            patch(LOOP_GUARD_PATCH) as mock_guard,
            patch(
                "myrm_agent_harness.toolkits.code_execution.executors.base.get_executor",
                return_value=mock_executor,
            ),
        ):
            mock_guard.return_value.recorded_calls.return_value = records
            result = await self.guard.aafter_model(state, None)

        assert result is None

    @pytest.mark.asyncio
    async def test_rerun_logs_the_command_masked(self, caplog: pytest.LogCaptureFixture) -> None:
        """The re-run line quotes a command the model wrote, so it shows the command masked."""
        caplog.set_level(logging.INFO)
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
                args={"command": "pytest tests/ --key Zx81qpLm"},
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
        mock_executor = MagicMock()
        mock_executor.execute_bash = AsyncMock(return_value=MagicMock(exit_code=0, stdout="OK", stderr=""))

        state = make_state([AIMessage(content="Done.")])
        with (
            patch(LOOP_GUARD_PATCH) as mock_guard,
            patch(
                "myrm_agent_harness.toolkits.code_execution.executors.base.get_executor",
                return_value=mock_executor,
            ),
        ):
            mock_guard.return_value.recorded_calls.return_value = records
            assert await self.guard.aafter_model(state, None) is None

        assert "Independent re-run" in caplog.text
        assert "Zx81qpLm" not in caplog.text

    @pytest.mark.asyncio
    async def test_rerun_fails_blocks_completion(self) -> None:
        """When independent re-run fails, agent is blocked from completing."""
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

        mock_executor = MagicMock()
        mock_result = MagicMock(exit_code=1, stdout="", stderr="FAILED")
        mock_executor.execute_bash = AsyncMock(return_value=mock_result)

        state = make_state([AIMessage(content="Done.")])
        with (
            patch(LOOP_GUARD_PATCH) as mock_guard,
            patch(
                "myrm_agent_harness.toolkits.code_execution.executors.base.get_executor",
                return_value=mock_executor,
            ),
        ):
            mock_guard.return_value.recorded_calls.return_value = records
            result = await self.guard.aafter_model(state, None)

        assert pending(result).text

    @pytest.mark.asyncio
    async def test_failed_verification_not_bypassed_by_rerun(self) -> None:
        """When critical error is 'verification failed' (not temporal), rerun must NOT bypass."""
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
                success_level=SuccessLevel.FAILURE,
                verification_type=VerificationCategory.TEST,
            ),
        ]

        mock_executor = MagicMock()
        mock_result = MagicMock(exit_code=0, stdout="OK", stderr="")
        mock_executor.execute_bash = AsyncMock(return_value=mock_result)

        state = make_state([AIMessage(content="Done.")])
        with (
            patch(LOOP_GUARD_PATCH) as mock_guard,
            patch(
                "myrm_agent_harness.toolkits.code_execution.executors.base.get_executor",
                return_value=mock_executor,
            ),
        ):
            mock_guard.return_value.recorded_calls.return_value = records
            result = await self.guard.aafter_model(state, None)

        assert pending(result).text

    @pytest.mark.asyncio
    async def test_no_executor_falls_back_to_blocking(self) -> None:
        """When sandbox executor is unavailable, falls back to blocking."""
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

        state = make_state([AIMessage(content="Done.")])
        with (
            patch(LOOP_GUARD_PATCH) as mock_guard,
            patch(
                "myrm_agent_harness.toolkits.code_execution.executors.base.get_executor",
                return_value=None,
            ),
        ):
            mock_guard.return_value.recorded_calls.return_value = records
            result = await self.guard.aafter_model(state, None)

        assert pending(result).text


class TestRerunClearsOnlyAStaleVerification:
    """A green re-run answers one question: does the code written after the last pass still pass."""

    def setup_method(self) -> None:
        self.guard = CompletionGuard()
        reset_completion_guard()

    async def attempt_to_finish(self, records: list[CallRecord], *, rerun_passes: bool) -> tuple[object, AsyncMock]:
        rerun = AsyncMock(return_value=rerun_passes)
        with (
            patch(LOOP_GUARD_PATCH) as mock_guard,
            patch.object(guard_module, "rerun_verification_in_sandbox", rerun),
        ):
            mock_guard.return_value.recorded_calls.return_value = records
            return await self.guard.aafter_model(make_state([AIMessage(content="Done.")]), None), rerun

    @pytest.mark.asyncio
    async def test_a_green_rerun_clears_code_written_after_the_last_pass(self) -> None:
        result, rerun = await self.attempt_to_finish([unit_tests(), write("/w/app.py")], rerun_passes=True)

        assert result is None
        rerun.assert_awaited_once_with("pytest")

    @pytest.mark.asyncio
    async def test_a_script_that_crashed_after_the_write_is_not_cleared_by_a_green_rerun(self) -> None:
        records = [unit_tests(), write("/w/app.py"), shell("python app.py", FAIL)]

        result, rerun = await self.attempt_to_finish(records, rerun_passes=True)

        assert reasons_of(result).verification
        rerun.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_failed_rerun_still_holds_the_answer_back(self) -> None:
        result, rerun = await self.attempt_to_finish([unit_tests(), write("/w/app.py")], rerun_passes=False)

        assert reasons_of(result).verification
        rerun.assert_awaited_once()
