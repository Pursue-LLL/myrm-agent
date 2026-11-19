"""The ToolError a failed bash call hands to the model: its message, its hint and its category."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.runnables import RunnableConfig

from myrm_agent_harness.agent.meta_tools.bash._executor.error import BashExecutionError
from myrm_agent_harness.agent.meta_tools.bash._tool.failure import build_failure_error

_CONFIG: RunnableConfig = {"configurable": {"context": {"session_id": "s"}}}
_DEFAULT_HINT = "Please fix the code and try again."
_GIT_CLONE_COMMAND = "git clone https://github.com/example/repo"
_MISSING_MODULE = "ModuleNotFoundError: No module named 'pydantic_settings'"


@pytest.mark.asyncio
async def test_an_exception_that_is_not_a_bash_error_gets_the_default_hint() -> None:
    error = await build_failure_error(ValueError("boom"), command="ls", config=_CONFIG)

    assert str(error) == "boom"
    assert error.user_hint == _DEFAULT_HINT
    assert error.diagnostic_info == {}


@pytest.mark.asyncio
async def test_a_bash_error_carries_its_hint_and_its_category() -> None:
    source = BashExecutionError("boom", error_hint="Retry with -v", error_category="EXEC")

    error = await build_failure_error(source, command="ls", config=_CONFIG)

    assert str(error) == "boom"
    assert error.user_hint == "Retry with -v"
    assert error.diagnostic_info == {"error_category": "EXEC"}


@pytest.mark.asyncio
async def test_a_bash_error_without_a_category_has_no_diagnostic_info() -> None:
    error = await build_failure_error(BashExecutionError("boom"), command="ls", config=_CONFIG)

    assert error.diagnostic_info == {}
    assert error.user_hint == _DEFAULT_HINT


@pytest.mark.asyncio
async def test_the_output_pattern_diagnosis_follows_the_error_hint() -> None:
    source = BashExecutionError(_MISSING_MODULE, error_hint="Check the environment")

    error = await build_failure_error(source, command="python3 run.py", config=_CONFIG)

    assert error.user_hint.startswith(
        "Check the environment\n\n[Diagnostic Hint] Python cannot import 'pydantic_settings'"
    )


@pytest.mark.asyncio
async def test_the_output_pattern_diagnosis_stands_alone_when_the_error_has_no_hint() -> None:
    error = await build_failure_error(BashExecutionError(_MISSING_MODULE), command="python3 run.py", config=_CONFIG)

    assert error.user_hint.startswith("[Diagnostic Hint] Python cannot import 'pydantic_settings'")


@pytest.mark.asyncio
async def test_the_diagnosis_reads_the_command_of_the_call() -> None:
    cloning = await build_failure_error(BashExecutionError("boom"), command=_GIT_CLONE_COMMAND, config=_CONFIG)
    listing = await build_failure_error(BashExecutionError("boom"), command="ls", config=_CONFIG)

    assert cloning.user_hint.startswith("[Diagnostic Hint] 'git clone' failed or timed out")
    assert listing.user_hint == _DEFAULT_HINT


@pytest.mark.asyncio
async def test_an_exception_that_is_not_a_bash_error_gets_no_diagnosis() -> None:
    error = await build_failure_error(ValueError(_MISSING_MODULE), command="python3 run.py", config=_CONFIG)

    assert error.user_hint == _DEFAULT_HINT


@pytest.mark.asyncio
async def test_the_stored_streams_of_a_bash_error_are_announced() -> None:
    source = BashExecutionError("boom", stderr_evicted_ref="err_1.txt", stderr_evicted_stored_chars=1500)

    with patch("myrm_agent_harness.agent.context_management.infra.evicted.emit_evicted_ref", new=AsyncMock()) as emit:
        await build_failure_error(source, command="ls", config=_CONFIG)

    emit.assert_awaited_once()
    call = emit.await_args_list[0]
    assert call.args == ("err_1.txt",)
    assert call.kwargs["config"] == _CONFIG
