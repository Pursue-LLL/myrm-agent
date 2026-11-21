"""What a bash call announces about the streams it stored in full, on the success path and on the failure path."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.runnables import RunnableConfig

from myrm_agent_harness.agent.meta_tools.bash._executor.error import BashExecutionError
from myrm_agent_harness.agent.meta_tools.bash._tool.evicted_emit import (
    emit_failure_evicted_refs,
    emit_result_evicted_refs,
)

_EMIT = "myrm_agent_harness.agent.context_management.infra.evicted.emit_evicted_ref"
_CONFIG: RunnableConfig = {"configurable": {"context": {"session_id": "s"}}}

_STDOUT_STORED = {
    "evicted_ref": "out_1.txt",
    "evicted_stored_chars": 4096,
    "evicted_total_lines": 120,
    "evicted_storage_truncated": True,
}
_STDERR_STORED = {
    "stderr_evicted_ref": "err_1.txt",
    "stderr_evicted_stored_chars": 2048,
    "stderr_evicted_total_lines": 100,
    "stderr_evicted_storage_truncated": False,
}


@pytest.mark.asyncio
async def test_a_stored_stdout_goes_out_with_the_preview_the_model_got() -> None:
    with patch(_EMIT, new=AsyncMock()) as emit:
        await emit_result_evicted_refs(_STDOUT_STORED, formatted_content="head of the output", config=_CONFIG)

    emit.assert_awaited_once()
    call = emit.await_args_list[0]
    assert call.args == ("out_1.txt",)
    assert call.kwargs == {
        "tool_name": "bash_code_execute_tool",
        "preview_stdout": "head of the output",
        "stored_chars": 4096,
        "total_lines": 120,
        "storage_truncated": True,
        "stream": "stdout",
        "config": _CONFIG,
    }


@pytest.mark.asyncio
async def test_a_stored_stderr_goes_out_without_a_preview() -> None:
    with patch(_EMIT, new=AsyncMock()) as emit:
        await emit_result_evicted_refs(_STDERR_STORED, formatted_content="the output", config=_CONFIG)

    emit.assert_awaited_once()
    call = emit.await_args_list[0]
    assert call.args == ("err_1.txt",)
    assert call.kwargs == {
        "tool_name": "bash_code_execute_tool",
        "stored_chars": 2048,
        "total_lines": 100,
        "storage_truncated": False,
        "stream": "stderr",
        "config": _CONFIG,
    }


@pytest.mark.asyncio
async def test_both_streams_go_out_stdout_first() -> None:
    with patch(_EMIT, new=AsyncMock()) as emit:
        await emit_result_evicted_refs({**_STDERR_STORED, **_STDOUT_STORED}, formatted_content="x", config=_CONFIG)

    assert [(call.args[0], call.kwargs["stream"]) for call in emit.await_args_list] == [
        ("out_1.txt", "stdout"),
        ("err_1.txt", "stderr"),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("count", ["12", None, 1.5])
async def test_a_count_that_is_not_an_integer_goes_out_as_none(count: object) -> None:
    stored = {"evicted_ref": "out_1.txt", "evicted_stored_chars": count, "evicted_total_lines": count}

    with patch(_EMIT, new=AsyncMock()) as emit:
        await emit_result_evicted_refs(stored, formatted_content="x", config=_CONFIG)

    kwargs = emit.await_args_list[0].kwargs
    assert kwargs["stored_chars"] is None
    assert kwargs["total_lines"] is None
    assert kwargs["storage_truncated"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("ref", [None, "", 7])
async def test_a_reference_that_is_not_a_string_is_not_announced(ref: object) -> None:
    with patch(_EMIT, new=AsyncMock()) as emit:
        await emit_result_evicted_refs(
            {"evicted_ref": ref, "stderr_evicted_ref": ref}, formatted_content="x", config=_CONFIG
        )

    emit.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_failed_call_announces_both_stored_streams_without_a_preview() -> None:
    error = BashExecutionError(
        "boom",
        stdout_evicted_ref="out_1.txt",
        stdout_evicted_stored_chars=32,
        stdout_evicted_total_lines=1,
        stdout_evicted_storage_truncated=True,
        stderr_evicted_ref="err_1.txt",
        stderr_evicted_stored_chars=1500,
        stderr_evicted_total_lines=12,
    )

    with patch(_EMIT, new=AsyncMock()) as emit:
        await emit_failure_evicted_refs(error, config=_CONFIG)

    assert [(call.args, call.kwargs) for call in emit.await_args_list] == [
        (
            ("out_1.txt",),
            {
                "tool_name": "bash_code_execute_tool",
                "stored_chars": 32,
                "total_lines": 1,
                "storage_truncated": True,
                "stream": "stdout",
                "config": _CONFIG,
            },
        ),
        (
            ("err_1.txt",),
            {
                "tool_name": "bash_code_execute_tool",
                "stored_chars": 1500,
                "total_lines": 12,
                "storage_truncated": False,
                "stream": "stderr",
                "config": _CONFIG,
            },
        ),
    ]


@pytest.mark.asyncio
async def test_a_failed_announcement_is_logged_and_the_other_stream_still_goes_out(
    caplog: pytest.LogCaptureFixture,
) -> None:
    error = BashExecutionError("boom", stdout_evicted_ref="out_1.txt", stderr_evicted_ref="err_1.txt")
    caplog.set_level(logging.WARNING)

    with patch(_EMIT, new=AsyncMock(side_effect=[RuntimeError("emit down"), None])) as emit:
        await emit_failure_evicted_refs(error, config=_CONFIG)

    assert [call.kwargs["stream"] for call in emit.await_args_list] == ["stdout", "stderr"]
    assert "Failed to emit stdout evicted ref out_1.txt: emit down" in caplog.text


@pytest.mark.asyncio
async def test_a_failed_call_without_stored_streams_announces_nothing() -> None:
    with patch(_EMIT, new=AsyncMock()) as emit:
        await emit_failure_evicted_refs(BashExecutionError("boom"), config=_CONFIG)

    emit.assert_not_awaited()
