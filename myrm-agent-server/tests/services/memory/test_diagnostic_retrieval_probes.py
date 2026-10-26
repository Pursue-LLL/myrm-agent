"""The retrieval probes look memories up to test the pipeline; no memory they hit counts as used."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock

import pytest
from myrm_agent_harness.toolkits.memory.types import MemoryType
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.memory.diagnostics.diagnostics import MemoryDiagnosticsService


class _RecordingManager:
    has_vector = True
    last_retrieval_trace = None
    config = SimpleNamespace(bm25_top_k=20, bm25_max_corpus_size=5000)

    def __init__(self) -> None:
        self.search_kwargs: list[dict[str, object]] = []

    def get_enabled_types(self) -> list[MemoryType]:
        return [MemoryType.SEMANTIC]

    async def search(self, query: str, **kwargs: object) -> list[object]:
        _ = query
        self.search_kwargs.append(kwargs)
        return []


def _service(manager: _RecordingManager) -> MemoryDiagnosticsService:
    return MemoryDiagnosticsService(cast(AsyncSession, MagicMock()), cast(MagicMock, manager), ledger=MagicMock())


@pytest.mark.asyncio
async def test_retrieval_pipeline_probe_does_not_track_access() -> None:
    manager = _RecordingManager()

    await _service(manager)._run_retrieval_pipeline_probe()

    assert [kwargs["track_access"] for kwargs in manager.search_kwargs] == [False]


@pytest.mark.asyncio
async def test_sparse_cjk_recall_probe_does_not_track_access() -> None:
    manager = _RecordingManager()

    probe = await _service(manager)._run_sparse_cjk_recall_probe()

    assert probe.status == "ready"
    assert [kwargs["track_access"] for kwargs in manager.search_kwargs] == [False]
