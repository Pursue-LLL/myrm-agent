"""Fixtures shared by the bash meta-tool tests."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import patch

import pytest

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
