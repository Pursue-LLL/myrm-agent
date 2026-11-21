"""Fixtures shared by the bash meta-tool tests."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from unittest.mock import patch

import pytest

from myrm_agent_harness.agent.meta_tools.bash._background.registry import get_background_registry
from myrm_agent_harness.core.context_vars import workspace_root_var
from tests.agent.meta_tools.bash.fake_background_proc import FakeProc
from tests.agent.meta_tools.bash.real_stack import RealBashStack, StubBin, real_bash_stack

_BACKGROUND = "myrm_agent_harness.agent.meta_tools.bash._background"


@pytest.fixture(autouse=True)
def _fake_pids_have_no_process_group() -> Iterator[None]:
    """Registry tests register invented pids; looking one up in the real process table could match a stranger's group.

    Tests that run real processes override this fixture by name.
    """
    with (
        patch(f"{_BACKGROUND}.consume.snapshot_group_members", return_value=()),
        patch(f"{_BACKGROUND}.termination.snapshot_group_members", return_value=()),
    ):
        yield


@pytest.fixture
async def jobs() -> AsyncIterator[list[FakeProc]]:
    """The fake jobs a test started in the process-wide registry; each one is finished at teardown so no reader task outlives its test."""
    registry = get_background_registry()
    registry._entries.clear()
    started: list[FakeProc] = []
    yield started
    for proc in started:
        proc.finish(0)
    await asyncio.sleep(0.05)
    registry._entries.clear()


@pytest.fixture
def workspace(tmp_path: Path) -> Iterator[Path]:
    """The workspace a job's log is written into: a job of 80 lines or more has nowhere to write without one."""
    token = workspace_root_var.set(str(tmp_path))
    yield tmp_path
    workspace_root_var.reset(token)


@pytest.fixture
async def real_stack(tmp_path: Path) -> AsyncIterator[RealBashStack]:
    """The real bash tool on a real local executor rooted at a temporary workspace."""
    async with real_bash_stack(tmp_path) as stack:
        yield stack


@pytest.fixture
def stub_bin(monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory) -> StubBin:
    """Stand-ins for host tools, ahead of everything else on the PATH a real stack's shell starts with.

    Use it before the stack's first command: the shell reads its environment when it starts.
    """
    directory = tmp_path_factory.mktemp("stub-bin")
    monkeypatch.setenv("PATH", f"{directory}{os.pathsep}{os.environ.get('PATH', '')}")
    return StubBin(directory)


@pytest.fixture(scope="module")
async def shared_real_stack(tmp_path_factory: pytest.TempPathFactory) -> AsyncIterator[RealBashStack]:
    """One real stack for a whole module, for tests that do not depend on the shell's state or on each other.

    Starting and closing the shell costs about two seconds each time, so a module of independent cases pays once.
    """
    async with real_bash_stack(tmp_path_factory.mktemp("real-stack")) as stack:
        yield stack
