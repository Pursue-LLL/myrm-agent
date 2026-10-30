"""The trajectory analyzer reads the tool events the broadcaster really writes.

A hand-built event of the right name proves nothing about the name the recorder uses, so these tests record a session
through the production writer (``ToolCallBroadcaster`` into an ``EventLogger`` on a file backend) and read it back
through ``TraceAnalyzer``.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from myrm_agent_harness.agent.event_log.backends.file_backend import FileEventLogBackend
from myrm_agent_harness.agent.event_log.logger import EventLogger
from myrm_agent_harness.agent.skills.evolution.pipeline.trace_analyzer import TraceAnalyzer
from myrm_agent_harness.agent.streaming.broadcast.tool_call_broadcaster import ToolCallBroadcaster

_SESSION_ID = "sess-trajectory"
_PASSWORD = "Pr0dDbPassw0rd!"
# Call ids as the providers issue them (DeepSeek style): long mixed alphanumeric runs a leak scan would take for keys.
_READ_ID = "call_00_3nrnFlx48weKv0yTotV43729_vtx8763"
_BASH_ID = "call_00_Yp7wQ2LkR9sTv4XcB1nMzE86_ab12345"


async def _record_failed_bash_session(tmp_path: Path, *, error: str) -> TraceAnalyzer:
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
    await broadcaster.on_pre_tool_use(
        "pre_tool_use", {**payload(_BASH_ID, "bash"), "tool_input": {"command": "cat .env"}}
    )
    await broadcaster.on_post_tool_use_failure("post_tool_use_failure", {**payload(_BASH_ID, "bash"), "error": error})
    await event_logger.close()
    return TraceAnalyzer(backend)


@pytest.mark.asyncio
async def test_a_recorded_failure_reaches_the_trajectory_with_its_tool_and_error(tmp_path: Path) -> None:
    analyzer = await _record_failed_bash_session(tmp_path, error="exit 1")

    trajectory = await analyzer.extract_trajectory(_SESSION_ID, "bash")

    assert "- **bash** (Target): 1 次调用, 成功率 0.0%, 失败 1 次" in trajectory
    assert "- **read_file**: 1 次调用, 成功率 100.0%, 失败 0 次" in trajectory
    assert "[tool_failure]" in trajectory
    assert "exit 1" in trajectory


@pytest.mark.asyncio
async def test_the_trajectory_holds_no_credential_the_log_masked(tmp_path: Path) -> None:
    analyzer = await _record_failed_bash_session(tmp_path, error=f"auth failed for password={_PASSWORD}")

    trajectory = await analyzer.extract_trajectory(_SESSION_ID, "bash")

    assert "auth failed" in trajectory
    assert _PASSWORD not in trajectory


@pytest.mark.asyncio
async def test_a_session_the_log_holds_nothing_for_has_no_trajectory(tmp_path: Path) -> None:
    analyzer = await _record_failed_bash_session(tmp_path, error="exit 1")
    skill = MagicMock(skill_id="bash", content="def run():\n    pass")

    assert await analyzer.extract_trajectory("another-session", "bash") == ""
    assert await analyzer.extract_trajectory_with_code("another-session", skill) == ""
