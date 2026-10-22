"""Fixtures of the scheduled-backup service tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.services.instance_archive.auto_backup.harness import Harness


@pytest.fixture
def harness(source_state: Path) -> Harness:
    return Harness(source_state)


@pytest.fixture
def unknown_home_dir() -> str:
    """A folder under the home of a user that does not exist, so ``~`` expansion cannot resolve it."""
    return "~no-such-user-4f1d9c/Backups"
