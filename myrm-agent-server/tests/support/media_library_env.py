"""A media library on a throwaway database and a local storage under a temp directory.

[INPUT]
- app.core.media.service::media_library_service (POS: the media library's write path)
- app.platform_utils (POS: the process-wide DB session factory and storage provider the production code resolves)
- myrm_agent_harness.toolkits.storage.local::LocalStorageBackend (POS: the real local storage backend)

[OUTPUT]
- MediaLibraryEnv: the sessions and storage behind the library, and ``store()`` to put a media item in it
- media_library_env(): async context manager that points every ``get_session_factory()`` and
  ``get_storage_provider()`` caller at them for the duration of a test

[POS]
Shared by the media library tests (reference loader, persistence callback, file endpoint). The singletons are replaced
at their source, so callers that imported the getters by name resolve to the same database and storage.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

import pytest
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app import platform_utils
from app.core.media.service import media_library_service
from app.database.models import Base, MediaLibrary


@dataclass(frozen=True, slots=True)
class MediaLibraryEnv:
    sessions: async_sessionmaker[AsyncSession]
    storage: LocalStorageBackend

    async def store(
        self,
        content: bytes,
        *,
        content_type: str = "image/png",
        prompt: str | None = None,
        model: str | None = None,
        session_id: str | None = None,
    ) -> MediaLibrary:
        """Write ``content`` through the library's own save path and commit the record."""
        async with self.sessions() as session:
            record = await media_library_service.save_media(
                session,
                image_bytes=content,
                content_type=content_type,
                prompt=prompt,
                model=model,
                session_id=session_id,
            )
            await session.commit()
            return record

    async def records(self) -> list[MediaLibrary]:
        """Every committed record, oldest first."""
        async with self.sessions() as session:
            return list((await session.execute(select(MediaLibrary).order_by(MediaLibrary.created_at))).scalars())


@asynccontextmanager
async def media_library_env(storage_root: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[MediaLibraryEnv]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        # The backend creates its root directory in the constructor, which must not run on the event loop.
        storage = await asyncio.to_thread(LocalStorageBackend, storage_root)
        monkeypatch.setattr(platform_utils, "_session_factory", sessions)
        monkeypatch.setattr(platform_utils, "_storage_provider", storage)
        yield MediaLibraryEnv(sessions=sessions, storage=storage)
    finally:
        await engine.dispose()
