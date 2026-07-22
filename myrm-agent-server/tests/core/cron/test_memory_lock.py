"""Tests for CrossProcessCronLock default lock directory."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.core.cron.adapters.memory_lock import CrossProcessCronLock


def test_constructor_default_uses_myrm_data_dir() -> None:
    expected = Path(os.environ["MYRM_DATA_DIR"]).expanduser().resolve() / "locks" / "cron"
    lock = CrossProcessCronLock()
    assert lock.lock_dir == expected


@pytest.mark.asyncio
async def test_isolated_lock_dirs_allow_concurrent_acquire(tmp_path: Path) -> None:
    first = CrossProcessCronLock(lock_dir=tmp_path / "runtime-a")
    second = CrossProcessCronLock(lock_dir=tmp_path / "runtime-b")

    assert await first.try_acquire("cron:scheduler:lock") is True
    assert await second.try_acquire("cron:scheduler:lock") is True

    await first.release("cron:scheduler:lock")
    await second.release("cron:scheduler:lock")


@pytest.mark.asyncio
async def test_shared_lock_dir_blocks_second_acquire(tmp_path: Path) -> None:
    lock_dir = tmp_path / "shared"
    first = CrossProcessCronLock(lock_dir=lock_dir)
    second = CrossProcessCronLock(lock_dir=lock_dir)

    assert await first.try_acquire("cron:scheduler:lock") is True
    assert await second.try_acquire("cron:scheduler:lock") is False

    await first.release("cron:scheduler:lock")
