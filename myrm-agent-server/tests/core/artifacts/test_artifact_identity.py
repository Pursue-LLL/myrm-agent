"""One file of a chat is one artifact: a stable id with a new version per registration, and the path it tracks."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from myrm_agent_harness.agent.artifacts.vault import ArtifactVault
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.artifacts.listener import upsert_processor_artifact
from app.core.artifacts.processor import LocalArtifactProcessor
from app.database.models import Base
from app.database.models.artifact import Artifact, ArtifactVersion

SessionFactory = Callable[[], AsyncSession]


@pytest_asyncio.fixture
async def session_factory(tmp_path: Path) -> AsyncIterator[SessionFactory]:
    # A file database: concurrent sessions get their own connections and the real write locking.
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'identity.db'}", connect_args={"timeout": 30})
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    root.mkdir()
    return root


@pytest.fixture
def processor(tmp_path: Path, workspace: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[LocalArtifactProcessor]:
    executor = MagicMock()
    executor.workspace_path = str(workspace)
    monkeypatch.setattr("app.platform_utils.get_storage_provider", lambda: LocalStorageBackend(tmp_path / "storage"))
    with patch("myrm_agent_harness.toolkits.code_execution.executors.base.get_executor", return_value=executor):
        yield LocalArtifactProcessor(chat_id="chat-1")


async def _persist(processor: LocalArtifactProcessor, path: str) -> str:
    result = await processor._persist_file("index.html", path, "text/html", None)
    assert result is not None
    return result.file_id


async def _upsert(
    session_factory: SessionFactory,
    workspace: Path,
    page: Path,
    file_id: str = "file_stable",
    source_path: str | None = None,
) -> str:
    async with session_factory() as db:
        return await upsert_processor_artifact(
            db,
            file_id=file_id,
            filename=page.name,
            sandbox_path=str(page),
            workspace_root=str(workspace),
            chat_id="chat-1",
            source_path=source_path,
        )


async def _rows(session_factory: SessionFactory) -> tuple[int, int]:
    async with session_factory() as db:
        artifacts = (await db.execute(select(func.count()).select_from(Artifact))).scalar_one()
        versions = (await db.execute(select(func.count()).select_from(ArtifactVersion))).scalar_one()
    return artifacts, versions


async def _stored_source_path(session_factory: SessionFactory, file_id: str = "file_stable") -> str | None:
    async with session_factory() as db:
        artifact = await db.get(Artifact, file_id)
    assert artifact is not None
    return artifact.source_path


@pytest.mark.asyncio
async def test_processing_a_file_twice_keeps_its_artifact_id(workspace: Path, processor: LocalArtifactProcessor) -> None:
    page = workspace / "site" / "index.html"
    page.parent.mkdir()
    page.write_text("<h1>v1</h1>", encoding="utf-8")

    first = await _persist(processor, "site/index.html")
    page.write_text("<h1>v2, edited</h1>", encoding="utf-8")
    second = await _persist(processor, str(page))

    assert first == second


@pytest.mark.asyncio
async def test_processing_a_file_records_its_path_relative_to_the_workspace(
    workspace: Path, processor: LocalArtifactProcessor, _mock_upsert_processor_artifact: AsyncMock
) -> None:
    page = workspace / "site" / "index.html"
    page.parent.mkdir()
    page.write_text("<h1>page</h1>", encoding="utf-8")
    event: dict[str, object] = {
        "type": "artifacts_ready",
        "data": [{"filename": "index.html", "path": "site/index.html", "type": "html"}],
        "read_content": AsyncMock(),
        "message_id": "msg-1",
    }

    assert await processor.process_artifacts_ready(event) is not None

    _mock_upsert_processor_artifact.assert_awaited_once()
    assert _mock_upsert_processor_artifact.await_args.kwargs["source_path"] == "site/index.html"


@pytest.mark.asyncio
async def test_registering_a_file_again_adds_a_version_to_the_same_artifact(
    session_factory: SessionFactory, workspace: Path
) -> None:
    page = workspace / "index.html"
    page.write_text("<h1>v1</h1>", encoding="utf-8")
    await _upsert(session_factory, workspace, page)
    page.write_text("<h1>v2</h1>", encoding="utf-8")
    latest = await _upsert(session_factory, workspace, page)

    assert await _rows(session_factory) == (1, 2)
    async with session_factory() as db:
        version = await db.get(ArtifactVersion, latest)
    assert version is not None
    assert ArtifactVault(str(workspace)).get(str(version.vault_uri)) == b"<h1>v2</h1>"


@pytest.mark.asyncio
async def test_a_registration_that_lost_the_insert_race_joins_the_existing_artifact(
    session_factory: SessionFactory, workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    page = workspace / "index.html"
    page.write_text("<h1>page</h1>", encoding="utf-8")

    async with session_factory() as db:
        real_flush = db.flush
        rival_registered = False

        async def flush_after_a_rival_registration() -> None:
            # The lookup already found no row; the other registration of the same file lands before this insert.
            nonlocal rival_registered
            if not rival_registered:
                rival_registered = True
                await _upsert(session_factory, workspace, page)
            await real_flush()

        monkeypatch.setattr(db, "flush", flush_after_a_rival_registration)
        await upsert_processor_artifact(
            db,
            file_id="file_stable",
            filename=page.name,
            sandbox_path=str(page),
            workspace_root=str(workspace),
            chat_id="chat-1",
        )

    assert rival_registered
    assert await _rows(session_factory) == (1, 2)


@pytest.mark.asyncio
async def test_concurrent_registrations_of_one_file_keep_a_single_artifact(
    session_factory: SessionFactory, workspace: Path
) -> None:
    page = workspace / "index.html"
    page.write_text("<h1>page</h1>", encoding="utf-8")

    await asyncio.gather(*(_upsert(session_factory, workspace, page) for _ in range(4)))

    assert await _rows(session_factory) == (1, 4)


@pytest.mark.asyncio
async def test_the_source_path_is_stored_and_kept_by_a_registration_that_names_none(
    session_factory: SessionFactory, workspace: Path
) -> None:
    page = workspace / "site" / "index.html"
    page.parent.mkdir()
    page.write_text("<h1>page</h1>", encoding="utf-8")

    await _upsert(session_factory, workspace, page, source_path="site/index.html")
    assert await _stored_source_path(session_factory) == "site/index.html"

    # Bytes that no workspace file backs (a stored-content registration) must not erase where the file lives.
    await _upsert(session_factory, workspace, page)
    assert await _stored_source_path(session_factory) == "site/index.html"


@pytest.mark.asyncio
async def test_a_newly_named_source_path_replaces_the_stored_one(session_factory: SessionFactory, workspace: Path) -> None:
    page = workspace / "index.html"
    page.write_text("<h1>page</h1>", encoding="utf-8")

    await _upsert(session_factory, workspace, page, source_path="old/index.html")
    await _upsert(session_factory, workspace, page, source_path="index.html")

    assert await _stored_source_path(session_factory) == "index.html"
