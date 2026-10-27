"""The independent sandbox re-run fails closed: only a command that exits 0 lets the completion through."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.agent.middlewares.completion.completion_guard_rerun import rerun_verification_in_sandbox

_GET_EXECUTOR = "myrm_agent_harness.toolkits.code_execution.executors.base.get_executor"


def _executor(*, exit_code: int | None = None, error: Exception | None = None) -> MagicMock:
    executor = MagicMock()
    if error is not None:
        executor.execute_bash = AsyncMock(side_effect=error)
    else:
        executor.execute_bash = AsyncMock(return_value=MagicMock(exit_code=exit_code, stdout="out", stderr="err"))
    return executor


@pytest.mark.asyncio
async def test_a_command_that_exits_zero_passes() -> None:
    executor = _executor(exit_code=0)
    with patch(_GET_EXECUTOR, return_value=executor):
        assert await rerun_verification_in_sandbox("pytest -q") is True

    context = executor.execute_bash.await_args.args[0]
    assert (context.code, context.timeout) == ("pytest -q", 120)


@pytest.mark.asyncio
async def test_a_command_that_exits_non_zero_fails() -> None:
    with patch(_GET_EXECUTOR, return_value=_executor(exit_code=1)):
        assert await rerun_verification_in_sandbox("pytest -q") is False


@pytest.mark.asyncio
async def test_no_executor_fails_closed() -> None:
    with patch(_GET_EXECUTOR, return_value=None):
        assert await rerun_verification_in_sandbox("pytest -q") is False


@pytest.mark.asyncio
async def test_an_executor_that_raises_fails_closed() -> None:
    with patch(_GET_EXECUTOR, return_value=_executor(error=RuntimeError("sandbox down"))):
        assert await rerun_verification_in_sandbox("pytest -q") is False
