"""Integration tests for PLUR memory import end-to-end dry-run and session persistence.

[INPUT]
Official PLUR engram store payload (Open Engram Standard v1 shape).

[OUTPUT]
End-to-end dry-run creation, preview sample, batch confirmation, and error-free
handling of inactive lifecycle states.

[POS]
Integration test ensuring a PLUR store payload transitions through
MemoryImportSessionService into DB with the real statement/status schema.
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


_OFFICIAL_ENGRAM_YAML = """
engrams:
  - id: ENG-2026-05-06-001
    statement: "Always use Pydantic v2 BaseModels with strict types"
    type: behavioral
    status: active
    scope: global
    visibility: private
    domain: backend
  - id: ENG-2026-05-06-002
    statement: "Monorepo backend lives in myrm-agent/myrm-agent-server"
    type: architectural
    status: active
    scope: project:open-perplexity
    visibility: private
    domain: repo
  - id: ENG-2026-05-06-003
    statement: "Old deploy checklist superseded by the pipeline"
    type: procedural
    status: retired
    scope: global
    visibility: private
    domain: ops
"""


@pytest.mark.asyncio
async def test_plur_import_session_full_lifecycle(db_session: AsyncSession) -> None:
    """Verify an official PLUR store payload traverses dry-run and confirmation."""
    manager = _FakeMemoryManager()
    service = MemoryImportSessionService(db_session)

    payload: dict[str, object] = {
        "_source": "plur",
        "raw_yaml": _OFFICIAL_ENGRAM_YAML,
    }

    dry_run_id, preview, _payload_hash, _expires_at = await service.create_dry_run(
        payload,
        "plur",
    )

    assert dry_run_id.startswith("memory-import:")
    assert preview.summary.source == "plur"
    assert preview.summary.mapped_items == 2
    assert preview.summary.unmapped_items == 1
    assert "plur_inactive_skipped" in preview.warnings
    assert preview.normalized_data, "dry-run preview must expose a bounded sample"
    sample_contents = [str(item.get("content", "")) for entries in preview.normalized_data.values() for item in entries]
    assert any("Pydantic v2" in content for content in sample_contents)
    assert all("Old deploy checklist" not in content for content in sample_contents)

    confirm = await service.confirm_import(dry_run_id=dry_run_id, manager=manager)
    assert confirm.total_imported == 2
    assert confirm.source == "plur"
    assert confirm.import_batch_id.startswith("memory-import-batch:")


@pytest.mark.asyncio
async def test_plur_payload_without_engrams_reports_explicit_reason(db_session: AsyncSession) -> None:
    """An empty PLUR payload must fail with a readable reason, not a silent zero."""

    service = MemoryImportSessionService(db_session)
    _dry_run_id, preview, _payload_hash, _expires_at = await service.create_dry_run(
        {"_source": "plur"},
        "plur",
    )

    assert preview.summary.mapped_items == 0
    assert "plur_no_engrams_found" in preview.warnings
    assert preview.mappings and preview.mappings[0].reason
