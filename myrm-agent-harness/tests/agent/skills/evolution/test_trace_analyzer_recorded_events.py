"""The slice analyzer reads the tool events the broadcaster really writes.

A hand-built event of the right name proves nothing about the name the recorder uses, so these tests record the
slice through the production writer (``ToolCallBroadcaster`` into an ``EventLogger`` on a file backend) and read it
back through ``TraceAnalyzer``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from myrm_agent_harness.agent.event_log.backends.file_backend import FileEventLogBackend
from myrm_agent_harness.agent.event_log.logger import EventLogger
from myrm_agent_harness.agent.skills.evolution.pipeline.trace_analyzer import TraceAnalyzer
from myrm_agent_harness.agent.streaming.broadcast.tool_call_broadcaster import ToolCallBroadcaster

_SESSION_ID = "sess-slice"
_PASSWORD = "Pr0dDbPassw0rd!"
# Call ids as the providers issue them (DeepSeek style): long mixed alphanumeric runs a leak scan would take for keys.
_READ_ID = "call_00_3nrnFlx48weKv0yTotV43729_vtx8763"
_BASH_ID = "call_00_Yp7wQ2LkR9sTv4XcB1nMzE86_ab12345"
_OTHER_ID = "call_00_Hd5ZaK8wL3mQx9TvB2nYr71_cd67890"


async def _record(tmp_path: Path, *, fail_second: bool) -> TraceAnalyzer:
    backend = FileEventLogBackend(tmp_path, _SESSION_ID)
    event_logger = EventLogger(backend, _SESSION_ID)
    await event_logger.start()
    broadcaster = ToolCallBroadcaster(event_logger)

    def payload(call_id: str, tool: str) -> dict[str, object]:
        return {"tool_name": tool, "tool_call_id": call_id, "session_id": _SESSION_ID}

    await broadcaster.on_pre_tool_use(
        "pre_tool_use", {**payload(_READ_ID, "read_file"), "tool_input": {"path": "a.py"}}
    )
    await broadcaster.on_post_tool_use("post_tool_use", {**payload(_READ_ID, "read_file"), "tool_output": "file body"})
    start = {**payload(_BASH_ID, "bash"), "tool_input": {"command": "cat .env", "env": {"DB_PASSWORD": _PASSWORD}}}
    await broadcaster.on_pre_tool_use("pre_tool_use", start)
    if fail_second:
        await broadcaster.on_post_tool_use_failure(
            "post_tool_use_failure", {**payload(_BASH_ID, "bash"), "error": "exit 1"}
        )
    else:
        await broadcaster.on_post_tool_use("post_tool_use", {**payload(_BASH_ID, "bash"), "tool_output": "done"})
    await broadcaster.on_pre_tool_use("pre_tool_use", {**payload(_OTHER_ID, "web_search"), "tool_input": {"q": "x"}})
    await event_logger.close()
    return TraceAnalyzer(backend)


@pytest.mark.asyncio
async def test_a_recorded_slice_is_formatted_with_its_actions_results_and_errors(tmp_path: Path) -> None:
    analyzer = await _record(tmp_path, fail_second=True)

    result = await analyzer.analyze_slice(_SESSION_ID, [_READ_ID, _BASH_ID])

    assert result is not None
    assert "[Action] read_file({'path': 'a.py'})" in result.formatted_trace
    assert "[Success] -> file body" in result.formatted_trace
    assert "[Error] -> exit 1" in result.formatted_trace
    assert "web_search" not in result.formatted_trace
    assert result.is_coherent is True


@pytest.mark.asyncio
async def test_a_slice_of_failures_only_is_not_coherent(tmp_path: Path) -> None:
    analyzer = await _record(tmp_path, fail_second=True)

    result = await analyzer.analyze_slice(_SESSION_ID, [_BASH_ID])

    assert result is not None
    assert result.is_coherent is False


@pytest.mark.asyncio
async def test_the_slice_the_analyzer_hands_to_the_model_holds_no_credential_the_log_masked(tmp_path: Path) -> None:
    analyzer = await _record(tmp_path, fail_second=False)

    result = await analyzer.analyze_slice(_SESSION_ID, [_BASH_ID])

    assert result is not None
    assert "cat .env" in result.formatted_trace
    assert _PASSWORD not in result.formatted_trace


@pytest.mark.asyncio
async def test_a_huge_argument_is_clipped_in_the_slice_handed_to_the_model(tmp_path: Path) -> None:
    backend = FileEventLogBackend(tmp_path, _SESSION_ID)
    event_logger = EventLogger(backend, _SESSION_ID)
    await event_logger.start()
    broadcaster = ToolCallBroadcaster(event_logger)
    call = {"tool_name": "write_file", "tool_call_id": _READ_ID, "session_id": _SESSION_ID}
    content = "x = 1\n" * 5_000
    await broadcaster.on_pre_tool_use("pre_tool_use", {**call, "tool_input": {"path": "a.py", "content": content}})
    await broadcaster.on_post_tool_use("post_tool_use", {**call, "tool_output": "ok"})
    await event_logger.close()

    result = await TraceAnalyzer(backend).analyze_slice(_SESSION_ID, [_READ_ID])

    assert result is not None
    assert result.formatted_trace.startswith("\n[Action] write_file({'path': 'a.py'")
    assert len(result.formatted_trace) < 1000
