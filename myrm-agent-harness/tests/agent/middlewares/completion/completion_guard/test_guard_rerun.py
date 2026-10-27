"""The guard re-runs the last verification in the sandbox when code was written after it passed."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from myrm_agent_harness.agent.middlewares.completion.completion_guard import (
    CompletionGuard,
    reset_completion_guard,
)
from myrm_agent_harness.agent.security.guards.loop_guard import (
    CallRecord,
    SuccessLevel,
    VerificationCategory,
)
from tests.support.completion_guard_harness import (
    LOOP_GUARD_PATCH,
    make_state,
    pending,
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
            mock_guard.return_value._window = records
            result = await self.guard.aafter_model(state, None)

        assert result is None

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
            mock_guard.return_value._window = records
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
            mock_guard.return_value._window = records
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
            mock_guard.return_value._window = records
            result = await self.guard.aafter_model(state, None)

        assert pending(result).text
