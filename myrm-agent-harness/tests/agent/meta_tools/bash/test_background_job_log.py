"""The log of a background job as the registry, ``bash_process_tool`` and the file read tool meet it.

The writer's own rules are in ``test_background_output_spill``; here a job runs in the registry and the log is read the
way the model and the activity panel read the evicted output of a foreground command.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock

import pytest
from langchain_core.runnables import RunnableConfig

import myrm_agent_harness.agent.meta_tools.bash._background.output_spill as spill_module
from myrm_agent_harness.agent.context_management.infra.evicted import read_evicted_line_range
from myrm_agent_harness.agent.meta_tools.bash._background.registry import get_background_registry
from myrm_agent_harness.agent.meta_tools.bash._background.types import OUTPUT_RING_LINES
from myrm_agent_harness.agent.meta_tools.bash.bash_process_tools import create_bash_process_tool
from myrm_agent_harness.agent.meta_tools.file_ops.file_read_tool import create_file_read_tool
from myrm_agent_harness.core.context_vars import workspace_root_var
from myrm_agent_harness.toolkits.code_execution.executors.models import AsyncProcessProtocol
from tests.agent.meta_tools.bash.fake_background_proc import FakeProc
from tests.agent.meta_tools.bash.real_stack import SESSION_ID, RealBashStack

pytestmark = pytest.mark.usefixtures("jobs")

_SESSION = "log-session"
_CONFIG: RunnableConfig = {"configurable": {"context": {"session_id": _SESSION}}}


async def _finished_job(
    jobs: list[FakeProc], pid: int, lines: int, *, finish_listener: AsyncMock | None = None
) -> None:
    """A job that printed ``line-1`` to ``line-<lines>`` and ended, once its reader has settled it."""
    stdout = [("\n".join(f"line-{i}" for i in range(1, lines + 1)) + "\n").encode()] if lines else []
    proc = FakeProc(pid=pid, stdout=stdout, stderr=[])
    jobs.append(proc)
    registry = get_background_registry()
    await registry.register(
        cast(AsyncProcessProtocol, proc), command="generate", session_id=_SESSION, finish_listener=finish_listener
    )
    proc.finish(0)
    reader = registry._entries[pid].reader_task
    assert reader is not None
    await asyncio.wait_for(reader, timeout=5)


async def _output(pid: int, **arguments: object) -> dict[str, object]:
    result = await create_bash_process_tool().ainvoke({"action": "output", "pid": pid, **arguments}, config=_CONFIG)
    return cast(dict[str, object], result["content"])


def _log_lines(workspace: Path, content: dict[str, object]) -> list[str]:
    return (workspace / str(content["log_file"])).read_text(encoding="utf-8").splitlines()


@pytest.mark.asyncio
async def test_the_log_of_a_job_longer_than_the_ring_holds_every_line_from_the_first(
    jobs: list[FakeProc], workspace: Path
) -> None:
    printed = OUTPUT_RING_LINES + 250
    await _finished_job(jobs, 73001, printed)

    content = await _output(73001)

    assert content["dropped"] is True
    # The place the evicted output of a foreground command lives: .context/<chat>/evicted/<file>.
    assert str(content["log_file"]).startswith(f".context/{_SESSION}/evicted/output_")
    assert _log_lines(workspace, content) == [f"line-{i}" for i in range(1, printed + 1)]
    assert cast(list[str], content["stdout"])[-1] == f"line-{printed}"


@pytest.mark.asyncio
async def test_the_file_read_tool_reads_the_log_of_a_real_job_by_the_path_the_output_names(
    real_stack: RealBashStack,
) -> None:
    """The real bash tool starts the job, the real registry and writer log it, the real file read tool opens the log."""
    token = workspace_root_var.set(str(real_stack.workspace))
    try:
        pid = await real_stack.start_background("seq 1 300 | sed 's/^/line-/'")
    finally:
        workspace_root_var.reset(token)
    await real_stack.process_tool.ainvoke(
        {"action": "wait", "pid": pid, "timeout_seconds": 10}, config=real_stack.config
    )
    content = await real_stack.read_job(pid)
    assert content["exit_code"] == 0
    log_file = str(content["log_file"])
    assert log_file.startswith(f".context/{SESSION_ID}/evicted/output_")

    read_whole = await create_file_read_tool().ainvoke({"paths": [log_file]}, config=real_stack.config)
    read_by_fast_track = await create_file_read_tool(path_policy="evicted_uploaded").ainvoke(
        {"paths": [log_file]}, config=_with_chat(real_stack.config, SESSION_ID)
    )

    for read in (read_whole, read_by_fast_track):
        assert "1|line-1\n" in read
        assert "300|line-300" in read


def _with_chat(config: RunnableConfig, chat_id: str) -> RunnableConfig:
    """*config* with the chat id the evicted-file read policy checks a path against."""
    context = {**config["configurable"]["context"], "chat_id": chat_id}
    return {"configurable": {"context": context}}


@pytest.mark.asyncio
async def test_a_listed_job_names_its_log_once_it_has_one(jobs: list[FakeProc], workspace: Path) -> None:
    await _finished_job(jobs, 73003, 120)
    await _finished_job(jobs, 73004, 3)

    result = await create_bash_process_tool().ainvoke({"action": "list"}, config=_CONFIG)
    rows = {row["pid"]: row for row in result["content"]["processes"]}

    assert (workspace / rows[73003]["log_file"]).is_file()
    assert "log_file" not in rows[73004]
    assert "vault_log_ref" not in rows[73003]


@pytest.mark.asyncio
async def test_a_job_below_the_threshold_leaves_no_file_and_names_none(jobs: list[FakeProc], workspace: Path) -> None:
    await _finished_job(jobs, 73005, 79)

    content = await _output(73005)

    assert content["dropped"] is False
    assert "log_file" not in content
    assert not (workspace / ".context").exists()


@pytest.mark.asyncio
async def test_without_a_workspace_the_job_runs_and_nothing_is_written(jobs: list[FakeProc], tmp_path: Path) -> None:
    token = workspace_root_var.set("")
    try:
        await _finished_job(jobs, 73006, OUTPUT_RING_LINES + 20)
    finally:
        workspace_root_var.reset(token)

    content = await _output(73006)

    assert content["dropped"] is True
    assert "log_file" not in content
    assert cast(list[str], content["stdout"])[-1] == f"line-{OUTPUT_RING_LINES + 20}"
    assert not any(tmp_path.rglob("output_*.txt"))


@pytest.mark.asyncio
async def test_a_directory_that_cannot_be_created_does_not_stop_the_job(jobs: list[FakeProc], tmp_path: Path) -> None:
    """A file where the workspace should be: the log cannot start, and the job is read and settled as if it had no log."""
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("a file where the workspace would be")
    finished = AsyncMock()
    token = workspace_root_var.set(str(blocker))
    try:
        await _finished_job(jobs, 73007, 300, finish_listener=finished)
    finally:
        workspace_root_var.reset(token)

    registry = get_background_registry()
    entry = registry._entries[73007]
    content = await _output(73007, max_lines=OUTPUT_RING_LINES)

    finished.assert_awaited_once()
    assert entry.reader_task is not None
    assert entry.reader_task.done()
    assert entry.reader_task.exception() is None
    assert entry.stdout_total == 300
    assert cast(list[str], content["stdout"])[-1] == "line-300"
    assert content["dropped"] is True
    assert "log_file" not in content
    assert entry.info.vault_log_ref is None


@pytest.mark.asyncio
async def test_a_capped_log_ends_with_the_marker_the_evicted_reader_reports(
    jobs: list[FakeProc], workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(spill_module, "MAX_STORED_CHARS", 1_500)
    printed = 300
    await _finished_job(jobs, 73008, printed)
    content = await _output(73008)

    page = read_evicted_line_range(workspace / str(content["log_file"]), offset=0, limit=5)

    assert page.storage_truncated is True
    assert page.original_chars == sum(len(f"line-{i}") + 1 for i in range(1, printed + 1))
    assert page.content.splitlines()[0] == "line-1"
