"""The embedded vector store stays a single-writer database.

[INPUT]
- app.core.retriever.vector.defaults::create_default_vector_store (POS: business default store factory)

[POS]
Real file locks, no mocks of the lock itself: a second process on the same data directory must
be refused (and degrade to memory mode), while the lock of a process that died must not block
the next start, so the factory never needs to delete lock files.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from myrm_agent_harness.toolkits.vector.config import DeploymentMode, VectorStoreConfig
from myrm_agent_harness.toolkits.vector.qdrant.factory import clear_embedded_stores
from qdrant_client import QdrantClient

from app.core.retriever.vector import defaults

_HOLDER_SCRIPT = (
    "import sys\n"
    "from qdrant_client import QdrantClient\n"
    "client = QdrantClient(path=sys.argv[1])\n"
    "print('ready', flush=True)\n"
    "sys.stdin.read()\n"
)


@pytest.fixture
async def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Path]:
    path = tmp_path / "qdrant"
    monkeypatch.setattr(
        defaults,
        "get_default_vector_store_config",
        lambda: VectorStoreConfig(mode=DeploymentMode.EMBEDDED, local_path=str(path)),
    )
    yield path
    await clear_embedded_stores()


async def test_held_lock_is_kept_and_second_opener_degrades_to_memory(data_dir: Path) -> None:
    holder = QdrantClient(path=str(data_dir))
    try:
        store = await defaults.create_default_vector_store()

        assert store is not None
        assert store.is_persistent is False
        assert list(data_dir.rglob(".lock")), "creating a store must not delete a lock file another opener holds"
        with pytest.raises(RuntimeError, match="already accessed"):
            QdrantClient(path=str(data_dir))
    finally:
        holder.close()


async def test_lock_of_a_killed_process_does_not_block_the_next_start(data_dir: Path) -> None:
    holder = subprocess.Popen(
        [sys.executable, "-c", _HOLDER_SCRIPT, str(data_dir)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout is not None
        assert holder.stdout.readline().strip() == "ready"
        holder.kill()
        holder.wait(timeout=10)
    finally:
        if holder.poll() is None:
            holder.kill()
            holder.wait()
        for pipe in (holder.stdin, holder.stdout):
            if pipe is not None:
                pipe.close()

    store = await defaults.create_default_vector_store()

    assert store is not None
    assert store.is_persistent is True
