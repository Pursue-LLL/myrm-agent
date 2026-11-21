"""The result and schema contract of ``bash_process_tool``: the fields it has, the limits it states."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig
from pydantic import ValidationError

import myrm_agent_harness.agent.meta_tools.bash._background.registry as registry_module
from myrm_agent_harness.agent.meta_tools.bash._background.poll import snapshot_entry
from myrm_agent_harness.agent.meta_tools.bash._background.registry import (
    BackgroundProcessRegistry,
    get_background_registry,
)
from myrm_agent_harness.agent.meta_tools.bash._background.types import (
    INPUT_WAIT_IDLE_SECONDS,
    OUTPUT_RING_LINES,
    WAIT_MAX_SECONDS,
)
from myrm_agent_harness.agent.meta_tools.bash.bash_process_tools import (
    BASH_PROCESS_TOOL_NAME,
    create_bash_process_tool,
    resolve_bash_process_tool_description,
)
from myrm_agent_harness.agent.middlewares.tooling._tool_helpers.timeouts import get_tool_timeout
from myrm_agent_harness.agent.middlewares.tooling.tool_executor import execute_with_retry
from myrm_agent_harness.toolkits.code_execution.executors.models import AsyncProcessProtocol
from tests.agent.meta_tools.bash.fake_background_proc import FakeOutputPipe, FakeProc, wait_until

_SESSION = "contract-session"
_CONFIG: RunnableConfig = {"configurable": {"context": {"session_id": _SESSION}}}
_EXECUTOR = "myrm_agent_harness.agent.middlewares.tooling.tool_executor"

# Every test starts from an empty registry and leaves no reader task behind.
pytestmark = pytest.mark.usefixtures("jobs")


async def _start_job(jobs: list[FakeProc], pid: int, *, lines: int = 0) -> FakeProc:
    stdout = [f"line-{i}\n".encode() for i in range(1, lines + 1)]
    proc = FakeProc(pid=pid, stdout=stdout, stderr=[])
    jobs.append(proc)
    await get_background_registry().register(cast(AsyncProcessProtocol, proc), command="generate", session_id=_SESSION)
    return proc


async def _start_prompting_job(jobs: list[FakeProc], pid: int, *, prompt: bytes = b"Continue? [y/N] ") -> FakeProc:
    """A running job that has printed *prompt* without a newline and holds its pipe open, as a program that waits does."""
    proc = FakeProc(pid=pid, stdout=[], stdout_pipe=FakeOutputPipe([prompt], hold_open=True), stdin=MagicMock())
    jobs.append(proc)
    registry = get_background_registry()
    await registry.register(cast(AsyncProcessProtocol, proc), command="installer", session_id=_SESSION)
    await wait_until(lambda: registry.get_partial_line(pid) != "", what="the prompt to reach the unfinished line")
    return proc


def _schema() -> dict[str, dict[str, dict[str, object]]]:
    return create_bash_process_tool().args_schema.model_json_schema()  # type: ignore[union-attr]


def test_schema_has_no_incremental_polling_or_filter_fields() -> None:
    assert set(_schema()["properties"]) == {"action", "pid", "max_lines", "timeout_seconds", "force", "data"}


@pytest.mark.asyncio
async def test_results_carry_no_cursor_poll_hint_or_filter(jobs: list[FakeProc]) -> None:
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
async def test_a_wait_that_runs_out_names_the_seconds_it_waited(jobs: list[FakeProc]) -> None:
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
async def test_cancelling_a_wait_returns_at_once_and_leaves_the_job_running(jobs: list[FakeProc]) -> None:
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
async def test_a_finished_wait_carries_what_output_carries(jobs: list[FakeProc], workspace: Path) -> None:
    lines = OUTPUT_RING_LINES + 20
    proc = await _start_job(jobs, 71004, lines=lines)
    proc.finish(0)
    tool = create_bash_process_tool()

    waited = await tool.ainvoke({"action": "wait", "pid": 71004, "timeout_seconds": 5}, config=_CONFIG)
    output = await tool.ainvoke({"action": "output", "pid": 71004}, config=_CONFIG)

    for result in (waited, output):
        content = result["content"]
        assert content["dropped"] is True
        assert content["log_file"].startswith(f".context/{_SESSION}/evicted/output_")
        assert (workspace / content["log_file"]).is_file()
        assert content["stdout"][-1] == f"line-{lines}"
    assert waited["content"]["stdout"] == output["content"]["stdout"]


@pytest.mark.asyncio
async def test_a_finished_wait_of_a_short_job_is_not_dropped(jobs: list[FakeProc]) -> None:
    proc = await _start_job(jobs, 71005, lines=3)
    proc.finish(0)

    result = await create_bash_process_tool().ainvoke(
        {"action": "wait", "pid": 71005, "timeout_seconds": 5}, config=_CONFIG
    )

    assert result["content"]["stdout"] == ["line-1", "line-2", "line-3"]
    assert result["content"]["dropped"] is False
    assert "log_file" not in result["content"]


@pytest.mark.performance
@pytest.mark.asyncio
async def test_a_wait_of_the_limit_comes_back_in_one_call_before_the_executor_deadline(
    jobs: list[FakeProc],
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


@pytest.mark.asyncio
async def test_output_and_wait_return_the_unfinished_last_line_of_a_running_job(jobs: list[FakeProc]) -> None:
    await _start_prompting_job(jobs, 71020)
    tool = create_bash_process_tool()

    output = await tool.ainvoke({"action": "output", "pid": 71020}, config=_CONFIG)
    waited = await tool.ainvoke({"action": "wait", "pid": 71020, "timeout_seconds": 1}, config=_CONFIG)

    assert output["content"]["partial_line"] == "Continue? [y/N]"
    assert output["content"]["stdout"] == []
    assert waited["content"]["still_running"] is True
    assert waited["content"]["partial_line"] == "Continue? [y/N]"


@pytest.mark.asyncio
async def test_a_running_job_without_an_unfinished_line_has_no_partial_line_field(jobs: list[FakeProc]) -> None:
    await _start_job(jobs, 71021, lines=2)
    tool = create_bash_process_tool()

    output = await tool.ainvoke({"action": "output", "pid": 71021}, config=_CONFIG)
    waited = await tool.ainvoke({"action": "wait", "pid": 71021, "timeout_seconds": 1}, config=_CONFIG)

    assert "partial_line" not in output["content"]
    assert waited["content"]["still_running"] is True
    assert "partial_line" not in waited["content"]


@pytest.mark.asyncio
async def test_a_finished_job_has_no_partial_line_and_its_unfinished_line_is_its_last_line(
    jobs: list[FakeProc],
) -> None:
    proc = await _start_prompting_job(jobs, 71022, prompt=b"building\nlast words")
    proc.finish(0)
    tool = create_bash_process_tool()

    waited = await tool.ainvoke({"action": "wait", "pid": 71022, "timeout_seconds": 5}, config=_CONFIG)
    output = await tool.ainvoke({"action": "output", "pid": 71022}, config=_CONFIG)

    for result in (waited, output):
        assert "partial_line" not in result["content"]
        assert result["content"]["stdout"] == ["building", "last words"]


@pytest.mark.asyncio
async def test_the_idle_note_is_fixed_text_and_the_job_s_words_appear_once_in_the_result(
    jobs: list[FakeProc],
) -> None:
    await _start_prompting_job(jobs, 71023)
    registry = get_background_registry()
    with registry._lock:
        registry._entries[71023].info.last_output_at = time.time() - INPUT_WAIT_IDLE_SECONDS - 2.0

    result = await create_bash_process_tool().ainvoke({"action": "output", "pid": 71023}, config=_CONFIG)

    content = result["content"]
    assert content["waiting_for_input"] is True
    assert "Continue" not in content["input_wait_hint"]
    assert content["partial_line"] == "Continue? [y/N]"
    assert json.dumps(content).count("Continue?") == 1


@pytest.mark.asyncio
async def test_polling_a_job_redacts_nothing_and_a_read_redacts_its_unfinished_line_once(
    jobs: list[FakeProc],
) -> None:
    """``wait`` takes a snapshot every 0.1 s: redacting the unfinished line there would cost more than the poll."""
    await _start_prompting_job(jobs, 71024)
    registry = get_background_registry()
    calls: list[str] = []

    def _counting(text: str) -> str:
        calls.append(text)
        return text

    poll = "myrm_agent_harness.agent.meta_tools.bash._background.poll"
    with patch(f"{poll}.redact_sensitive_text", _counting):
        for _ in range(20):
            registry.get(71024)
        with registry._lock:
            snapshot_entry(registry._entries[71024])
        assert calls == []

        assert registry.get_partial_line(71024) == "Continue? [y/N]"
        assert calls == ["Continue? [y/N]"]
