"""Fixtures for the ima connector suite: an isolated on-disk database and the cron-entry harness.

A file database (not ``:memory:``) is deliberate: the importer runs concurrent workers with one short session each,
and an in-memory database would funnel them through a single shared connection whose rollbacks discard each other's
uncommitted work.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup import CorpusDedupScanner
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.models import Base
from app.services.wiki.source_sync.ima import importer, job_runner
from app.services.wiki.source_sync.ima.context import SyncContext
from app.services.wiki.source_sync.ima.engine import SliceOutcome
from app.services.wiki.source_sync.ima.models import ImaCredentials
from app.services.wiki.source_sync.publish_helpers import RawConflictPolicy, publish_source_markdown

from .job_runner_support import POLL_S, FakeArchiver, Harness, job_id
from .support import Downloads


@pytest_asyncio.fixture
async def ima_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'ima.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr("app.database.connection.get_session_factory", lambda: factory)
    yield factory
    await engine.dispose()


@pytest.fixture
def fast_importer(monkeypatch: pytest.MonkeyPatch) -> None:
    """The importer paces its downloads for ima's rate limits; tests do not need to wait."""
    monkeypatch.setattr(importer, "_PACE_S", 0.0)


@pytest.fixture
def downloads(monkeypatch: pytest.MonkeyPatch) -> Downloads:
    fake = Downloads()
    monkeypatch.setattr("app.services.wiki.source_sync.ima.content.download_media", fake)
    return fake


@pytest.fixture
def harness(tmp_path: Path, ima_db: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch) -> Iterator[Harness]:
    h = Harness()
    archiver = FakeArchiver(tmp_path, h.events)

    async def credentials() -> ImaCredentials | None:
        return h.credentials

    async def run_slice(ctx: SyncContext) -> SliceOutcome:
        h.contexts.append(ctx)
        if h.gate is not None:
            await h.gate.wait()
        for relative_path, body in h.publish.items():
            await publish_source_markdown(
                ctx.structure,
                relative_path=relative_path,
                content=body,
                auto_compile=ctx.compiler_enqueue is not None,
                compiler_enqueue=ctx.compiler_enqueue,
                conflict_policy=RawConflictPolicy.SUPERSEDE,
            )
        if h.slice_error is not None:
            raise h.slice_error
        return h.outcome

    async def source_config(db: AsyncSession, *, agent_id: str | None) -> SimpleNamespace:
        return SimpleNamespace(auto_compile=h.auto_compile)

    async def snapshot(archiver: object, *, agent_id: str | None) -> None:
        h.snapshots += 1
        h.events.append("snapshot")

    async def dedup(*, agent_id: str | None) -> bool:
        h.dedups += 1
        h.events.append("scan")
        if h.scan_completes and archiver._structure.raw_dir.exists():
            CorpusDedupScanner(archiver._structure).scan(incremental=True)
        return h.scan_completes

    async def find_active_job(agent_id: str | None) -> SimpleNamespace | None:
        if job_id(agent_id) in h.paused:
            return None
        if h.pause_after_admission:
            h.pause(agent_id)
        return SimpleNamespace(id=job_id(agent_id))

    async def is_job_active(job_id: str) -> bool:
        if h.mandate_read_error is not None:
            raise h.mandate_read_error
        return job_id not in h.paused

    monkeypatch.setattr(job_runner, "find_active_job", find_active_job)
    monkeypatch.setattr(job_runner, "is_job_active", is_job_active)
    monkeypatch.setattr(job_runner, "_MANDATE_POLL_S", POLL_S)
    monkeypatch.setattr(job_runner, "load_credentials", credentials)
    monkeypatch.setattr(job_runner, "run_slice", run_slice)
    monkeypatch.setattr(job_runner, "load_wiki_source_sync_config", source_config)
    monkeypatch.setattr(job_runner, "get_wiki_archiver", lambda llm, agent_id=None: archiver)
    monkeypatch.setattr("app.services.wiki.ingest_events.publish_wiki_ingest_snapshot", snapshot)
    monkeypatch.setattr(job_runner, "run_post_sync_dedup_scan", dedup)
    job_runner._slice_locks.clear()
    yield h
    h.release()
