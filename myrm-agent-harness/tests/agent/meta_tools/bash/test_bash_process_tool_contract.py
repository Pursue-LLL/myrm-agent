"""The result and schema contract of ``bash_process_tool``: the fields it has, the limits it states."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import ToolMessage
from pydantic import ValidationError

import myrm_agent_harness.agent.meta_tools.bash._background.registry as registry_module
from myrm_agent_harness.agent.meta_tools.bash._background.output_spill import BackgroundOutputSpillWriter
from myrm_agent_harness.agent.meta_tools.bash._background.registry import (
    BackgroundProcessRegistry,
    get_background_registry,
)
from myrm_agent_harness.agent.meta_tools.bash._background.types import OUTPUT_RING_LINES, WAIT_MAX_SECONDS
from myrm_agent_harness.agent.meta_tools.bash.bash_process_tools import (
    BASH_PROCESS_TOOL_NAME,
    create_bash_process_tool,
    resolve_bash_process_tool_description,
)
from myrm_agent_harness.agent.middlewares.tooling._tool_helpers.timeouts import get_tool_timeout
from myrm_agent_harness.agent.middlewares.tooling.tool_executor import execute_with_retry
from myrm_agent_harness.toolkits.code_execution.executors.models import AsyncProcessProtocol
from tests.agent.meta_tools.bash.test_background_registry import _FakeProc

_SESSION = "contract-session"
_CONFIG = {"configurable": {"context": {"session_id": _SESSION}}}
_EXECUTOR = "myrm_agent_harness.agent.middlewares.tooling.tool_executor"
_SPILL_FILE = "output_contract.txt"


@pytest.fixture(autouse=True)
async def jobs() -> AsyncIterator[list[_FakeProc]]:
    """The fake jobs a test started; each one is finished at teardown so no reader task outlives its test."""
    registry = get_background_registry()
    registry._entries.clear()  # type: ignore[attr-defined]
    started: list[_FakeProc] = []
    yield started
    for proc in started:
        proc.finish(0)
    await asyncio.sleep(0.05)
    registry._entries.clear()  # type: ignore[attr-defined]


@pytest.fixture
def spill_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """Send a job's spill log to a temporary file; a job past 79 lines has no workspace to write into otherwise."""

    def _paths(self: BackgroundOutputSpillWriter) -> None:
        self._filename = _SPILL_FILE  # type: ignore[attr-defined]
        self._abs_path = tmp_path / _SPILL_FILE  # type: ignore[attr-defined]

    monkeypatch.setattr(BackgroundOutputSpillWriter, "_ensure_paths", _paths)
    return _SPILL_FILE


async def _start_job(jobs: list[_FakeProc], pid: int, *, lines: int = 0) -> _FakeProc:
    stdout = [f"line-{i}\n".encode() for i in range(1, lines + 1)]
    proc = _FakeProc(pid=pid, stdout=stdout, stderr=[])
    jobs.append(proc)
    await get_background_registry().register(cast(AsyncProcessProtocol, proc), command="generate", session_id=_SESSION)
    return proc


def _schema() -> dict[str, dict[str, dict[str, object]]]:
    return create_bash_process_tool().args_schema.model_json_schema()  # type: ignore[union-attr, return-value]


def test_schema_has_no_incremental_polling_or_filter_fields() -> None:
    assert set(_schema()["properties"]) == {"action", "pid", "max_lines", "timeout_seconds", "force", "data"}


@pytest.mark.asyncio
async def test_results_carry_no_cursor_poll_hint_or_filter(jobs: list[_FakeProc]) -> None:
    await _start_job(jobs, 71001, lines=1)
    tool = create_bash_process_tool()

    results = [
        await tool.ainvoke({"action": "list"}, config=_CONFIG),
        await tool.ainvoke({"action": "output", "pid": 71001}, config=_CONFIG),
        await tool.ainvoke({"action": "wait", "pid": 71001, "timeout_seconds": 1}, config=_CONFIG),
    ]

    text = json.dumps(results)
    for removed in ("next_cursor", "since_cursor", "poll_hint", "suggested_wait_ms", "filter"):
        assert removed not in text


def test_the_schema_limits_are_the_shared_limits() -> None:
    properties = _schema()["properties"]

    assert properties["max_lines"]["maximum"] == OUTPUT_RING_LINES
    assert properties["timeout_seconds"]["maximum"] == WAIT_MAX_SECONDS
    assert str(OUTPUT_RING_LINES) in str(properties["max_lines"]["description"])
    assert str(WAIT_MAX_SECONDS) in str(properties["timeout_seconds"]["description"])


@pytest.mark.parametrize("locale", ["en", "zh"])
def test_the_descriptions_state_the_wait_limit(locale: str) -> None:
    text = resolve_bash_process_tool_description(locale)

    assert str(WAIT_MAX_SECONDS) in text
    assert "120" not in text


def test_the_action_description_states_the_wait_limit() -> None:
    description = str(_schema()["properties"]["action"]["description"])

    assert str(WAIT_MAX_SECONDS) in description
    assert "120" not in description


def test_the_wait_limit_is_below_the_deadline_the_executor_gives_the_tool() -> None:
    arguments: dict[str, object] = {"action": "wait", "timeout_seconds": WAIT_MAX_SECONDS}

    assert get_tool_timeout(BASH_PROCESS_TOOL_NAME, arguments) > WAIT_MAX_SECONDS


@pytest.mark.asyncio
async def test_the_registry_caps_a_wait_at_the_shared_limit() -> None:
    capped_at: list[float] = []

    async def _fake_wait_for_exit(
        _get_info: object, pid: int, *, timeout_seconds: float, max_seconds: float
    ) -> dict[str, object]:
        capped_at.append(max_seconds)
        return {"found": True, "still_running": True, "pid": pid}

    with patch.object(registry_module, "wait_for_exit", _fake_wait_for_exit):
        await BackgroundProcessRegistry().wait_for_process(1, timeout_seconds=WAIT_MAX_SECONDS * 5)

    assert capped_at == [WAIT_MAX_SECONDS]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("action", "past_the_limit"),
    [("wait", {"timeout_seconds": WAIT_MAX_SECONDS + 1}), ("output", {"max_lines": OUTPUT_RING_LINES + 1})],
)
async def test_a_value_past_a_stated_limit_is_rejected(action: str, past_the_limit: dict[str, int]) -> None:
    with pytest.raises(ValidationError):
        await create_bash_process_tool().ainvoke({"action": action, "pid": 1, **past_the_limit}, config=_CONFIG)


@pytest.mark.asyncio
async def test_a_wait_that_runs_out_names_the_seconds_it_waited(jobs: list[_FakeProc]) -> None:
    await _start_job(jobs, 71002)
    started = time.monotonic()

    result = await create_bash_process_tool().ainvoke(
        {"action": "wait", "pid": 71002, "timeout_seconds": 1}, config=_CONFIG
    )

    waited = time.monotonic() - started
    assert result["content"]["still_running"] is True
    assert "after 1s" in result["content"]["message"]
    assert 1.0 <= waited < 2.5


@pytest.mark.asyncio
async def test_cancelling_a_wait_returns_at_once_and_leaves_the_job_running(jobs: list[_FakeProc]) -> None:
    await _start_job(jobs, 71003)
    waiting = asyncio.create_task(
        create_bash_process_tool().ainvoke(
            {"action": "wait", "pid": 71003, "timeout_seconds": WAIT_MAX_SECONDS}, config=_CONFIG
        )
    )
    await asyncio.sleep(0.2)

    cancelled_at = time.monotonic()
    waiting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiting

    info = get_background_registry().get(71003)
    assert time.monotonic() - cancelled_at < 1.0
    assert info is not None
    assert info.status == "running"


@pytest.mark.asyncio
async def test_a_finished_wait_carries_what_output_carries(jobs: list[_FakeProc], spill_log: str) -> None:
    lines = OUTPUT_RING_LINES + 20
    proc = await _start_job(jobs, 71004, lines=lines)
    proc.finish(0)
    tool = create_bash_process_tool()

    waited = await tool.ainvoke({"action": "wait", "pid": 71004, "timeout_seconds": 5}, config=_CONFIG)
    output = await tool.ainvoke({"action": "output", "pid": 71004}, config=_CONFIG)

    for result in (waited, output):
        content = result["content"]
        assert content["dropped"] is True
        assert content["spill_log_ref"] == spill_log
        assert content["stdout"][-1] == f"line-{lines}"
    assert waited["content"]["stdout"] == output["content"]["stdout"]


@pytest.mark.asyncio
async def test_a_finished_wait_of_a_short_job_is_not_dropped(jobs: list[_FakeProc]) -> None:
    proc = await _start_job(jobs, 71005, lines=3)
    proc.finish(0)

    result = await create_bash_process_tool().ainvoke(
        {"action": "wait", "pid": 71005, "timeout_seconds": 5}, config=_CONFIG
    )

    assert result["content"]["stdout"] == ["line-1", "line-2", "line-3"]
    assert result["content"]["dropped"] is False
    assert "spill_log_ref" not in result["content"]


@pytest.mark.performance
@pytest.mark.asyncio
async def test_a_wait_of_the_limit_comes_back_in_one_call_before_the_executor_deadline(
    jobs: list[_FakeProc],
) -> None:
    """Runs the real ``wait(WAIT_MAX_SECONDS)`` through the executor: a limit at or past its deadline is retried."""
    await _start_job(jobs, 71010)
    tool = create_bash_process_tool()
    arguments: dict[str, object] = {"action": "wait", "pid": 71010, "timeout_seconds": WAIT_MAX_SECONDS}
    calls = 0

    async def _handler(_request: object) -> ToolMessage:
        nonlocal calls
        calls += 1
        result = await tool.ainvoke(arguments, config=_CONFIG)
        return ToolMessage(content=json.dumps(result["content"]), name=BASH_PROCESS_TOOL_NAME, tool_call_id="tc-1")

    request = MagicMock()
    request.tool_call = {"name": BASH_PROCESS_TOOL_NAME, "id": "tc-1", "args": arguments}
    started = time.monotonic()
    with (
        patch(f"{_EXECUTOR}.get_event_logger", return_value=None),
        patch(f"{_EXECUTOR}.get_terminal_errors", return_value=set()),
    ):
        message = await execute_with_retry(request, _handler, BASH_PROCESS_TOOL_NAME, "tc-1", allowed_domains=None)

    elapsed = time.monotonic() - started
    assert calls == 1
    assert isinstance(message, ToolMessage)
    assert json.loads(str(message.content))["still_running"] is True
    assert WAIT_MAX_SECONDS <= elapsed < get_tool_timeout(BASH_PROCESS_TOOL_NAME, arguments)
