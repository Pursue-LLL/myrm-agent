"""LocalExecutor.warm_up: the shared venv is built in the background, once, and never outlives the executor."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest

from myrm_agent_harness.toolkits.code_execution.config import ExecutionConfig
from myrm_agent_harness.toolkits.code_execution.executors.local.executor import LocalExecutor
from tests.toolkits.code_execution._venv_spawn import VENV_SPAWN, FakeVenvSpawn


def _executor(tmp_path: Path) -> LocalExecutor:
    config = ExecutionConfig()
    config.local.shared_venv_path = str(tmp_path / "venvs")
    return LocalExecutor(config)


@pytest.mark.asyncio
async def test_warm_up_returns_before_the_venv_exists(tmp_path: Path) -> None:
    executor = _executor(tmp_path)
    started, release = asyncio.Event(), asyncio.Event()

    async def slow_resolve() -> str:
        started.set()
        await release.wait()
        return "python"

    with patch.object(executor._venv_manager, "get_python_executable", side_effect=slow_resolve) as resolve:
        executor.warm_up()
        await asyncio.wait_for(started.wait(), timeout=1)
        task = executor._venv_warm_task
        assert task is not None
        assert not task.done()
        release.set()
        await task

    resolve.assert_awaited_once()


@pytest.mark.asyncio
async def test_warm_up_twice_builds_once(tmp_path: Path) -> None:
    executor = _executor(tmp_path)

    with patch.object(executor._venv_manager, "get_python_executable", return_value="python") as resolve:
        executor.warm_up()
        first_task = executor._venv_warm_task
        executor.warm_up()
        assert first_task is not None
        assert executor._venv_warm_task is first_task
        await first_task

    resolve.assert_awaited_once()


@pytest.mark.asyncio
async def test_the_first_run_waits_for_the_warm_up_instead_of_building_again(tmp_path: Path) -> None:
    executor = _executor(tmp_path)
    spawn = FakeVenvSpawn()

    with patch(VENV_SPAWN, side_effect=spawn):
        executor.warm_up()
        interpreter = await executor._venv_manager.get_python_executable()
        await executor._venv_manager.ensure_pip_ready_for("pip --version")

    assert len(spawn.creations) == 1
    assert interpreter == str(tmp_path / "venvs" / "bin" / "python")


@pytest.fixture
def stuck_warm_up_executor(tmp_path: Path) -> Iterator[LocalExecutor]:
    """An executor whose venv creation never finishes, so its warm-up is still running when it is released."""
    executor = _executor(tmp_path)

    async def never_finishes() -> str:
        await asyncio.Event().wait()
        return "python"

    with patch.object(executor._venv_manager, "get_python_executable", side_effect=never_finishes):
        yield executor


@pytest.mark.asyncio
async def test_close_cancels_a_warm_up_that_is_still_running(stuck_warm_up_executor: LocalExecutor) -> None:
    stuck_warm_up_executor.warm_up()
    task = stuck_warm_up_executor._venv_warm_task
    assert task is not None
    await asyncio.sleep(0)
    assert not task.done()

    await asyncio.wait_for(stuck_warm_up_executor.close(), timeout=1)

    assert task.cancelled()


@pytest.mark.asyncio
async def test_leaving_the_context_manager_cancels_a_warm_up_that_is_still_running(
    stuck_warm_up_executor: LocalExecutor,
) -> None:
    async with stuck_warm_up_executor:
        stuck_warm_up_executor.warm_up()
        task = stuck_warm_up_executor._venv_warm_task
        assert task is not None
        await asyncio.sleep(0)
        assert not task.done()

    assert task.cancelled()


@pytest.mark.asyncio
async def test_a_failed_warm_up_is_logged_and_the_next_run_retries(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    executor = _executor(tmp_path)

    with patch.object(executor._venv_manager, "get_python_executable", side_effect=[OSError("disk full"), "python"]):
        with caplog.at_level(logging.WARNING):
            executor.warm_up()
            task = executor._venv_warm_task
            assert task is not None
            await task

        assert "venv warm-up failed" in caplog.text
        assert "disk full" in caplog.text
        assert await executor._venv_manager.get_python_executable() == "python"
