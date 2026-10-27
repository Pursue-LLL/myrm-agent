"""Shared fixtures for deep-research tests."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from tests.agent.sub_agents.guard_state_probe import parent_run_in_progress


@pytest.fixture
def parent_run() -> Iterator[None]:
    """A parent run in progress: its guards are reset and it has done some work."""
    with parent_run_in_progress():
        yield
