from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from myrm_agent_harness.toolkits.memory import MemoryMutationRef, MemoryMutationResult, ProfileAttributeSnapshot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.models import Base
from app.database.models.memory import MemoryImportBatchModel, MemoryImportItemModel
from app.services.memory.import_ledger import (
    IMPORT_BATCH_STATUS_PARTIAL,
    IMPORT_BATCH_STATUS_ROLLED_BACK,
    IMPORT_ITEM_STATUS_CONFLICT,
    IMPORT_ITEM_STATUS_MISSING,
    IMPORT_ITEM_STATUS_ROLLED_BACK,
    MemoryImportLedgerService,
)
from app.services.memory.import_sessions import MemoryImportSessionError, MemoryImportSessionService


class _FakeMemoryManager:
    def __init__(self) -> None:
        self.profile_values: dict[str, str] = {"tone": "concise"}
        self.profile_versions: dict[str, int] = {"tone": 1}
        self.memory_ids_by_type: dict[str, list[str]] = {}

    def edit_profile(self, key: str, value: str) -> None:
        self.profile_values[key] = value
        self.profile_versions[key] = self.profile_versions.get(key, 0) + 1

    async def import_memories(
        self,
        data: dict[str, list[dict[str, object]]],
        *,
        skip_duplicates: bool = True,
    ) -> dict[str, int]:
        _ = skip_duplicates
        counts: dict[str, int] = {}
        for memory_type, entries in data.items():
            if memory_type == "profile":
                imported = 0
                for entry in entries:
                    key = str(entry.get("key", ""))
                    value = str(entry.get("value", ""))
                    if key:
                        self.edit_profile(key, value)
                        imported += 1
                counts[memory_type] = imported
                continue
            ids = [f"{memory_type}-{index}" for index, _entry in enumerate(entries)]
            self.memory_ids_by_type[memory_type] = ids
            counts[memory_type] = len(ids)
        return counts

    async def list_memory_refs_by_metadata(
        self,
        metadata_key: str,
        metadata_value: str,
    ) -> dict[str, list[dict[str, str]]]:
        _ = (metadata_key, metadata_value)
        return {
            memory_type: [
                {"id": memory_id, "import_item_id": f"{metadata_value}:{memory_type}:{index}"}
                for index, memory_id in enumerate(memory_ids)
            ]
            for memory_type, memory_ids in self.memory_ids_by_type.items()
            if memory_ids
        }

    async def delete_memories_by_ids(self, memory_ids_by_type: dict[str, list[str]]) -> MemoryMutationResult:
        result = MemoryMutationResult()
        for memory_type, memory_ids in memory_ids_by_type.items():
            current_ids = self.memory_ids_by_type.get(memory_type, [])
            removed = [memory_id for memory_id in memory_ids if memory_id in current_ids]
            self.memory_ids_by_type[memory_type] = [memory_id for memory_id in current_ids if memory_id not in removed]
            for memory_id in removed:
                result.deleted_refs.append(
                    MemoryMutationRef(memory_type=memory_type, memory_id=memory_id, backend="fake")
                )
            for memory_id in memory_ids:
                if memory_id not in removed:
                    result.missing_refs.append(
                        MemoryMutationRef(
                            memory_type=memory_type,
                            memory_id=memory_id,
                            backend="fake",
                            reason="not_found",
                        )
                    )
        return result

    async def get_profile_attribute(self, key: str) -> str | None:
        return self.profile_values.get(key)

    async def get_profile_attribute_snapshot(self, key: str) -> ProfileAttributeSnapshot:
        value = self.profile_values.get(key)
        if value is None:
            return ProfileAttributeSnapshot(key=key, exists=False)
        revision = f"{key}:{self.profile_versions.get(key, 0)}:{value}"
        return ProfileAttributeSnapshot(key=key, value=value, exists=True, revision=revision)

    async def restore_profile_attributes(self, values: dict[str, str | None]) -> int:
        restored = 0
        for key, value in values.items():
            if value is None:
                self.profile_values.pop(key, None)
                self.profile_versions[key] = self.profile_versions.get(key, 0) + 1
            else:
                self.edit_profile(key, value)
            restored += 1
        return restored


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
async def test_import_rollback_uses_ledger_and_blocks_changed_profile(
    db_session: AsyncSession,
) -> None:
    manager = _FakeMemoryManager()
    service = MemoryImportSessionService(db_session)
    payload = {
        "data": {
            "profile": [{"key": "tone", "value": "detailed"}],
            "semantic": [{"content": "Use the durable ledger for import rollback.", "metadata": {}}],
        }
    }
    dry_run_id, _preview, _payload_hash, _expires_at = await service.create_dry_run(payload, "native_json")
    confirm = await service.confirm_import(dry_run_id=dry_run_id, manager=manager)

    manager.profile_values["tone"] = "changed-after-import"
    preview = await service.preview_rollback(manager=manager, import_batch_id=confirm.import_batch_id)

    assert preview.conflict_items == 1
    assert preview.reversible_items == 1
    assert [warning.code for warning in preview.warnings] == ["profile_guarded", "profile_conflicts"]

    result = await service.rollback_import(manager=manager, import_batch_id=confirm.import_batch_id)

    assert result.rolled_back == {"semantic": 1}
    assert result.conflict_items == 1
    assert result.missing_items == 0
    assert result.failed_items == 0
    assert manager.profile_values["tone"] == "changed-after-import"

    batch = await db_session.get(MemoryImportBatchModel, confirm.import_batch_id)
    assert batch is not None
    assert batch.status == IMPORT_BATCH_STATUS_PARTIAL

    rows = (
        await db_session.execute(
            select(MemoryImportItemModel).where(MemoryImportItemModel.batch_id == confirm.import_batch_id)
        )
    ).scalars()
    statuses = {row.memory_type: row.status for row in rows}
    assert statuses == {"profile": IMPORT_ITEM_STATUS_CONFLICT, "semantic": IMPORT_ITEM_STATUS_ROLLED_BACK}


@pytest.mark.asyncio
async def test_import_rollback_marks_missing_memory_item_without_false_success(
    db_session: AsyncSession,
) -> None:
    manager = _FakeMemoryManager()
    service = MemoryImportSessionService(db_session)
    payload = {
        "data": {
            "semantic": [{"content": "Track exact rollback refs.", "metadata": {}}],
        }
    }
    dry_run_id, _preview, _payload_hash, _expires_at = await service.create_dry_run(payload, "native_json")
    confirm = await service.confirm_import(dry_run_id=dry_run_id, manager=manager)

    manager.memory_ids_by_type["semantic"] = []
    result = await service.rollback_import(manager=manager, import_batch_id=confirm.import_batch_id)

    assert result.rolled_back == {}
    assert result.missing_items == 1
    assert result.failed_items == 0

    batch = await db_session.get(MemoryImportBatchModel, confirm.import_batch_id)
    assert batch is not None
    assert batch.status == IMPORT_BATCH_STATUS_PARTIAL

    row = (
        await db_session.execute(
            select(MemoryImportItemModel).where(MemoryImportItemModel.batch_id == confirm.import_batch_id)
        )
    ).scalar_one()
    assert row.status == IMPORT_ITEM_STATUS_MISSING


@pytest.mark.asyncio
async def test_confirm_import_rejects_changed_review_plan(
    db_session: AsyncSession,
) -> None:
    manager = _FakeMemoryManager()
    service = MemoryImportSessionService(db_session)
    payload = {"data": {"semantic": [{"content": "Pin import plans to reviewed options.", "metadata": {}}]}}
    dry_run_id, preview, _payload_hash, _expires_at = await service.create_dry_run(
        payload,
        "native_json",
        skip_duplicates=True,
    )

    assert preview.plan is not None
    with pytest.raises(MemoryImportSessionError) as exc_info:
        await service.confirm_import(dry_run_id=dry_run_id, manager=manager, skip_duplicates=False)

    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_profile_rollback_blocks_same_value_aba_revision(
    db_session: AsyncSession,
) -> None:
    manager = _FakeMemoryManager()
    service = MemoryImportSessionService(db_session)
    payload = {"data": {"profile": [{"key": "tone", "value": "detailed"}]}}
    dry_run_id, _preview, _payload_hash, _expires_at = await service.create_dry_run(payload, "native_json")
    confirm = await service.confirm_import(dry_run_id=dry_run_id, manager=manager)

    manager.edit_profile("tone", "detailed")
    preview = await service.preview_rollback(manager=manager, import_batch_id=confirm.import_batch_id)
    result = await service.rollback_import(manager=manager, import_batch_id=confirm.import_batch_id)

    assert preview.conflict_items == 1
    assert result.conflict_items == 1
    assert result.rolled_back == {}
    assert manager.profile_values["tone"] == "detailed"

    row = (
        await db_session.execute(
            select(MemoryImportItemModel).where(MemoryImportItemModel.batch_id == confirm.import_batch_id)
        )
    ).scalar_one()
    assert row.status == IMPORT_ITEM_STATUS_CONFLICT


@pytest.mark.asyncio
async def test_recover_incomplete_rollback_journal_resumes_batch(
    db_session: AsyncSession,
) -> None:
    manager = _FakeMemoryManager()
    service = MemoryImportSessionService(db_session)
    payload = {"data": {"semantic": [{"content": "Recover rollback journals on startup.", "metadata": {}}]}}
    dry_run_id, _preview, _payload_hash, _expires_at = await service.create_dry_run(payload, "native_json")
    confirm = await service.confirm_import(dry_run_id=dry_run_id, manager=manager)
    batch = await db_session.get(MemoryImportBatchModel, confirm.import_batch_id)
    assert batch is not None
    MemoryImportLedgerService(db_session).begin_batch_rollback(batch, started_at=datetime.now(UTC))
    await db_session.commit()

    recovered = await service.recover_incomplete_rollbacks(manager)

    assert recovered == 1
    assert manager.memory_ids_by_type["semantic"] == []
    batch = await db_session.get(MemoryImportBatchModel, confirm.import_batch_id)
    assert batch is not None
    assert batch.status == IMPORT_BATCH_STATUS_ROLLED_BACK

    row = (
        await db_session.execute(
            select(MemoryImportItemModel).where(MemoryImportItemModel.batch_id == confirm.import_batch_id)
        )
    ).scalar_one()
    assert row.status == IMPORT_ITEM_STATUS_ROLLED_BACK


@pytest.mark.asyncio
async def test_rollback_import_resumes_target_in_progress_batch(
    db_session: AsyncSession,
) -> None:
    manager = _FakeMemoryManager()
    service = MemoryImportSessionService(db_session)
    payload = {"data": {"semantic": [{"content": "Retry an in-progress rollback by target id.", "metadata": {}}]}}
    dry_run_id, _preview, _payload_hash, _expires_at = await service.create_dry_run(payload, "native_json")
    confirm = await service.confirm_import(dry_run_id=dry_run_id, manager=manager)
    batch = await db_session.get(MemoryImportBatchModel, confirm.import_batch_id)
    assert batch is not None
    MemoryImportLedgerService(db_session).begin_batch_rollback(batch, started_at=datetime.now(UTC))
    await db_session.commit()

    result = await service.rollback_import(manager=manager, import_batch_id=confirm.import_batch_id)

    assert result.total_rolled_back == 1
    assert result.integrity_status == "ready"
    batch = await db_session.get(MemoryImportBatchModel, confirm.import_batch_id)
    assert batch is not None
    assert batch.status == IMPORT_BATCH_STATUS_ROLLED_BACK
