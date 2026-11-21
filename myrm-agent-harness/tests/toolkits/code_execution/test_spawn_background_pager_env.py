"""A background job never waits at a pager.

A job on a pseudo-terminal, which is how a job starts on POSIX without an OS sandbox, gives git, man and gh a real
terminal, and a pager there waits at the first page for a key nobody sends. The spawn therefore pins ``PAGER`` and
``GIT_PAGER`` to ``cat`` whatever the host exports, while the ``env`` of the caller's context, the one place a job's
environment is set on purpose, still wins.
"""

from __future__ import annotations

import asyncio
import contextlib
import sys
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest

from myrm_agent_harness.toolkits.code_execution.config import ExecutionConfig
from myrm_agent_harness.toolkits.code_execution.executors.local.executor import LocalExecutor
from myrm_agent_harness.toolkits.code_execution.executors.models import ExecutionContext
from myrm_agent_harness.toolkits.code_execution.sandbox.providers.null import NullProvider
from myrm_agent_harness.toolkits.code_execution.sandbox.sandbox_types import SandboxStatus


@pytest.fixture
def executor(tmp_path: Path) -> Iterator[LocalExecutor]:
    """A local executor with the OS sandbox off, so a job starts the way it does in a container."""
    no_sandbox = (NullProvider(), SandboxStatus(enabled=False, provider_name="null", reason="test"))
    with (
        patch(
            "myrm_agent_harness.toolkits.code_execution.sandbox.detector.detect_sandbox_provider",
            return_value=no_sandbox,
        ),
        patch("myrm_agent_harness.toolkits.code_execution.sandbox.detect_sandbox_provider", return_value=no_sandbox),
    ):
        local = LocalExecutor(ExecutionConfig())
        local.bind_workspace(str(tmp_path))
        yield local


async def _pagers_of_a_job(executor: LocalExecutor, workspace: Path, env: dict[str, str] | None = None) -> list[str]:
    """``PAGER`` and ``GIT_PAGER`` as a job started with *env* reads them."""
    script = "import os; print(os.environ.get('PAGER', 'unset'), os.environ.get('GIT_PAGER', 'unset'))"
    context = ExecutionContext(code=sys.executable, args=["-c", script], workspace_root=str(workspace), env=env)
    process = await executor.spawn_background_process(context)
    try:
        stdout = process.stdout
        assert isinstance(stdout, asyncio.StreamReader)
        return (await stdout.readline()).decode("utf-8").split()
    finally:
        with contextlib.suppress(ProcessLookupError):
            process.terminate()
        await process.wait()


async def test_a_job_pages_through_cat(executor: LocalExecutor, tmp_path: Path) -> None:
    assert await _pagers_of_a_job(executor, tmp_path) == ["cat", "cat"]


async def test_a_job_does_not_take_the_pager_of_the_host(
    executor: LocalExecutor, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PAGER", "less")
    monkeypatch.setenv("GIT_PAGER", "less")

    assert await _pagers_of_a_job(executor, tmp_path) == ["cat", "cat"]


async def test_a_job_keeps_the_pager_its_caller_sets(executor: LocalExecutor, tmp_path: Path) -> None:
    assert await _pagers_of_a_job(executor, tmp_path, {"PAGER": "more", "GIT_PAGER": "less"}) == ["more", "less"]
