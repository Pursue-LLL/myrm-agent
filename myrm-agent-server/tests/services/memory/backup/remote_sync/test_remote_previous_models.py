"""Remote backups after the embedding model changed.

[INPUT]
app.services.memory.backup.remote_sync.runner::run_remote_backup

[OUTPUT]
Whether a backup run keeps the complete remote backups while memories sit under a previous embedding model, and
resumes once they are migrated.

[POS]
Real memory stores and the real runner; only the remote storage is an in-memory double. Enabling embedding for the
first time or switching the model leaves existing memories under the old model until they are migrated. A snapshot
taken meanwhile holds none of them, and rotation would push the complete backups out in favor of the empty ones.
"""

from __future__ import annotations

from datetime import datetime, timedelta, tzinfo
from itertools import count
from pathlib import Path
from types import SimpleNamespace
from typing import Self

import pytest
from myrm_agent_harness.toolkits.memory import MemoryManager
from myrm_agent_harness.toolkits.vector.qdrant.factory import clear_embedded_stores

from app.services.memory.backup.remote_sync import runner
from app.services.memory.backup.remote_sync.runner import run_remote_backup
from app.services.memory.backup.snapshot import decode_snapshot
from tests.support.in_memory_remote_backup import InMemoryBackupStrategy
from tests.support.offline_memory import offline_memory_manager

pytestmark = pytest.mark.integration

TAG = "1a2b3c4d"
MEMORIES = 5
KEPT_BACKUPS = 3

# (model the complete backups were made under, model the user switches to); None is keyword-only search.
SCENARIOS = {
    "first enable (keyword search to embedding)": (None, "local/model-a"),
    "model switch (A to B)": ("local/model-a", "local/model-b"),
}


@pytest.fixture(autouse=True)
def _linux_and_a_clock_that_advances_per_read(monkeypatch: pytest.MonkeyPatch) -> None:
    """A backup name carries a one-second timestamp: a clock that moves on every read keeps runs apart without sleeping."""
    ticks = count()

    class AdvancingClock(datetime):
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> Self:
            return cls(2026, 1, 1, tzinfo=tz) + timedelta(seconds=next(ticks))

    monkeypatch.setattr(runner, "datetime", AdvancingClock)
    monkeypatch.setattr(runner, "platform", SimpleNamespace(system=lambda: "Linux"))


async def _run_backups(manager: MemoryManager, remote: InMemoryBackupStrategy, rounds: int) -> list[tuple[str, str | None]]:
    outcomes: list[tuple[str, str | None]] = []
    for _ in range(rounds):
        result = await run_remote_backup(manager, remote, instance_tag=TAG, device_name="laptop", max_backups=KEPT_BACKUPS)
        outcomes.append((result.status, result.error_code))
    return outcomes


def _memories_per_backup(remote: InMemoryBackupStrategy) -> list[int]:
    return [decode_snapshot(data).memory_count for _, data in sorted(remote._storage.items())]


async def _make_complete_backups(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, remote: InMemoryBackupStrategy, model: str | None
) -> None:
    async with offline_memory_manager(tmp_path / "memory", monkeypatch, embedding_model=model) as manager:
        for index in range(MEMORIES):
            await manager.add_knowledge(f"fact number {index}")
        assert await _run_backups(manager, remote, KEPT_BACKUPS) == [("ok", None)] * KEPT_BACKUPS
    await clear_embedded_stores()
    assert _memories_per_backup(remote) == [MEMORIES] * KEPT_BACKUPS


@pytest.mark.parametrize("origin", [origin for origin, _ in SCENARIOS.values()], ids=list(SCENARIOS))
async def test_an_unchanged_configuration_keeps_producing_complete_backups(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, origin: str | None
) -> None:
    remote = InMemoryBackupStrategy()
    await _make_complete_backups(tmp_path, monkeypatch, remote, origin)

    async with offline_memory_manager(tmp_path / "memory", monkeypatch, embedding_model=origin) as manager:
        assert await _run_backups(manager, remote, KEPT_BACKUPS) == [("ok", None)] * KEPT_BACKUPS

    assert _memories_per_backup(remote) == [MEMORIES] * KEPT_BACKUPS


@pytest.mark.parametrize(("origin", "target"), SCENARIOS.values(), ids=SCENARIOS)
async def test_a_changed_embedding_model_never_replaces_complete_backups_with_empty_ones(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, origin: str | None, target: str | None
) -> None:
    remote = InMemoryBackupStrategy()
    await _make_complete_backups(tmp_path, monkeypatch, remote, origin)

    async with offline_memory_manager(tmp_path / "memory", monkeypatch, embedding_model=target) as manager:
        assert await _run_backups(manager, remote, KEPT_BACKUPS) == [("failed", "previous_model")] * KEPT_BACKUPS
        assert _memories_per_backup(remote) == [MEMORIES] * KEPT_BACKUPS

        migration = await manager.reindex_from_orphans()
        assert (migration.migrated, migration.failed) == (MEMORIES, 0)
        await manager.add_knowledge("written after the migration")
        assert await _run_backups(manager, remote, 1) == [("ok", None)]

    assert _memories_per_backup(remote) == [MEMORIES, MEMORIES, MEMORIES + 1]
