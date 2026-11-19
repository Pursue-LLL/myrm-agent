"""Tests for StorageBackendStrategy over a real StorageProvider."""

from __future__ import annotations

from pathlib import Path

import pytest

from myrm_agent_harness.agent.meta_tools.file_ops.strategies.storage_strategy import (
    StorageBackendStrategy,
)
from myrm_agent_harness.toolkits.storage import LocalStorageBackend


@pytest.mark.asyncio
async def test_strategy_round_trips_through_local_storage_backend(tmp_path: Path) -> None:
    strategy = StorageBackendStrategy(LocalStorageBackend(tmp_path))

    await strategy.write_file("notes/a.txt", "hello world")

    assert await strategy.read_file("notes/a.txt") == ["hello world"]
    assert await strategy.get_file_size("notes/a.txt") == len("hello world")


@pytest.mark.asyncio
async def test_missing_path_message_is_the_plain_text(tmp_path: Path) -> None:
    strategy = StorageBackendStrategy(LocalStorageBackend(tmp_path))

    assert await strategy.missing_path_message("notes/a.txt") == "Path not found: notes/a.txt"
