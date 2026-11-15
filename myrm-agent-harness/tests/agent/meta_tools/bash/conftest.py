"""Fixtures shared by the bash meta-tool tests."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.agent.meta_tools.bash.real_stack import RealBashStack, real_bash_stack

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
async def real_stack(tmp_path: Path) -> AsyncIterator[RealBashStack]:
    """The real bash tool on a real local executor rooted at a temporary workspace."""
    async with real_bash_stack(tmp_path) as stack:
        yield stack


@pytest.fixture(scope="module")
async def shared_real_stack(tmp_path_factory: pytest.TempPathFactory) -> AsyncIterator[RealBashStack]:
    """One real stack for a whole module, for tests that do not depend on the shell's state or on each other.

    Starting and closing the shell costs about two seconds each time, so a module of independent cases pays once.
    """
    async with real_bash_stack(tmp_path_factory.mktemp("real-stack")) as stack:
        yield stack
