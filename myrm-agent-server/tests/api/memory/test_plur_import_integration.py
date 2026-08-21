"""Integration tests for PLUR memory import end-to-end dry-run and session persistence.

[INPUT]
PLUR YAML/JSON payload.

[OUTPUT]
End-to-end dry-run creation, batch confirmation, and database ledger verification.

[POS]
Integration test ensuring PLUR payload transitions through MemoryImportSessionService into DB.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.models import Base
from app.services.memory.imports.import_sessions import MemoryImportSessionService
from tests.services.memory.test_import_sessions import _FakeMemoryManager


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.mark.asyncio
async def test_plur_import_session_full_lifecycle(db_session: AsyncSession) -> None:
    """Verify PLUR YAML payload traverses dry-run and confirmation lifecycle into DB."""
    manager = _FakeMemoryManager()
    service = MemoryImportSessionService(db_session)

    raw_yaml = """
- domain: backend
  scope: global
  type: preference
  content: Always use Pydantic v2 BaseModels with strict types
- domain: repo
  scope: project:open-perplexity
  type: rule
  content: Monorepo backend lives in myrm-agent/myrm-agent-server
"""

    payload: dict[str, object] = {
        "_source": "plur",
        "raw_yaml": raw_yaml,
    }

    dry_run_id, preview, _payload_hash, _expires_at = await service.create_dry_run(
        payload,
        "plur",
    )

    assert dry_run_id.startswith("memory-import:")
    assert preview.summary.source == "plur"
    assert preview.summary.mapped_items == 2

    confirm = await service.confirm_import(dry_run_id=dry_run_id, manager=manager)
    assert confirm.total_imported == 2
    assert confirm.source == "plur"
    assert confirm.import_batch_id.startswith("memory-import-batch:")
