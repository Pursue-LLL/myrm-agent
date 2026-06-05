from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from myrm_agent_harness.toolkits.memory import MemoryMutationRef, MemoryMutationResult, ProfileAttributeSnapshot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.models import Base
from app.database.models.agent_event import AgentEvent, AgentTurn
from app.database.models.chat import Chat, Message
from app.database.models.memory import (
    MemoryArchiveRestoreBatchModel,
    MemoryArchiveRestoreItemModel,
    MemoryOperationEventModel,
    SharedContextBindingModel,
    SharedContextModel,
)
from app.services.memory.archive import MemoryArchiveService
from app.services.memory.archive_restore import MemoryArchiveRestoreService
from app.services.memory.archive_restore_common import (
    RESTORE_BATCH_STATUS_CONFIRMED,
    RESTORE_BATCH_STATUS_IN_PROGRESS,
    RESTORE_BATCH_STATUS_ROLLED_BACK,
    RESTORE_ITEM_STATUS_ROLLED_BACK,
    MemoryArchiveRestoreError,
)
from app.services.memory.import_adapters import build_memory_import_dry_run


class _ArchiveMemoryManager:
    async def export_all(self) -> dict[str, list[dict[str, object]]]:
        return {
            "semantic": [
                {
                    "id": "mem-1",
                    "content": "Use SQLite. api_key=super-secret-token",
                    "metadata": {"source": "test"},
                }
            ]
        }


class _RestoreMemoryManager:
    def __init__(self) -> None:
        self.profile_values: dict[str, str] = {}
        self.profile_versions: dict[str, int] = {}
        self.memory_ids_by_type: dict[str, list[str]] = {}

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
                        self.profile_values[key] = value
                        self.profile_versions[key] = self.profile_versions.get(key, 0) + 1
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
        _ = metadata_key
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
                result.deleted_refs.append(MemoryMutationRef(memory_type=memory_type, memory_id=memory_id, backend="fake"))
            for memory_id in memory_ids:
                if memory_id not in removed:
                    result.missing_refs.append(
                        MemoryMutationRef(memory_type=memory_type, memory_id=memory_id, backend="fake", reason="not_found")
                    )
        return result

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
            else:
                self.profile_values[key] = value
            self.profile_versions[key] = self.profile_versions.get(key, 0) + 1
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
async def test_memory_archive_exports_single_sandbox_sections(db_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    context = SharedContextModel(
        id="ctx-1",
        namespace="shared:ctx-1",
        name="Project Rules",
        description="Current project rules",
        status="active",
        policy={"write_mode": "proposal_required"},
    )
    binding = SharedContextBindingModel(
        id="bind-1",
        context_id="ctx-1",
        target_type="agent",
        target_id="agent-1",
    )
    chat = Chat(id="chat-1", title="Planning", source="web")
    message = Message(
        id="msg-1",
        chat_id="chat-1",
        role="user",
        content="Remember this project uses SQLite.",
        sent_at=now,
        sent_timezone="UTC",
    )
    turn = AgentTurn(id="turn-1", chat_id="chat-1", turn_index=1, status="completed")
    event = AgentEvent(
        id="event-1",
        turn_id="turn-1",
        event_type="memory_write",
        level="info",
        event_index=1,
        payload={"memory_id": "mem-1"},
    )
    audit = MemoryOperationEventModel(
        id="audit-1",
        kind="write",
        status="success",
        occurred_at=now,
        summary="Memory write recorded.",
        metadata_json={"source": "test"},
    )
    db_session.add_all([context, binding, chat, message, turn, event, audit])
    await db_session.commit()

    archive = await MemoryArchiveService(db_session).export_archive(_ArchiveMemoryManager())

    section_counts = {section.name: section.item_count for section in archive.manifest.sections}
    assert archive.manifest.format == "myrm_memory_archive"
    assert section_counts["memory"] == 1
    assert section_counts["shared_context"] == 2
    assert section_counts["conversation"] == 1
    assert section_counts["replay"] == 1
    assert section_counts["audit"] == 1
    assert archive.manifest.content_redacted is True
    memory_section = archive.data["memory"]
    assert isinstance(memory_section, dict)
    semantic = memory_section["semantic"]
    assert isinstance(semantic, list)
    assert semantic[0]["content"] == "Use SQLite. api_key=[REDACTED]"


def test_memory_archive_dry_run_counts_supported_sections() -> None:
    payload = {
        "manifest": {
            "format": "myrm_memory_archive",
            "version": 1,
            "created_at": datetime.now(UTC).isoformat(),
            "producer": "test",
            "content_redacted": False,
            "sections": [
                {"name": "memory", "status": "ready", "item_count": 3, "warning_codes": []},
                {"name": "audit", "status": "ready", "item_count": 2, "warning_codes": ["redacted"]},
            ],
        },
        "data": {},
    }

    result = MemoryArchiveService.dry_run_archive(payload)

    assert result.total_items == 5
    assert result.supported_items == 5
    assert result.unsupported_items == 0
    assert result.warning_codes == ["redacted"]


def test_myrm_archive_memory_section_uses_import_review_path() -> None:
    payload = {
        "manifest": {
            "format": "myrm_memory_archive",
            "version": 1,
            "created_at": datetime.now(UTC).isoformat(),
            "producer": "test",
            "content_redacted": True,
            "sections": [
                {"name": "memory", "status": "ready", "item_count": 1, "warning_codes": []},
                {"name": "shared_context", "status": "ready", "item_count": 1, "warning_codes": []},
            ],
        },
        "data": {
            "memory": {"semantic": [{"content": "Archive memory import stays review-bound.", "metadata": {}}]},
            "shared_context": {"contexts": [{"id": "ctx-1", "name": "Project"}]},
        },
    }

    result = build_memory_import_dry_run(payload, "myrm_archive")

    assert result.summary.source == "myrm_archive"
    assert result.summary.mapped_items == 1
    assert result.summary.unmapped_items == 1
    assert result.normalized_data == {"semantic": [{"content": "Archive memory import stays review-bound.", "metadata": {}}]}
    assert result.warnings == ["myrm_archive_non_memory_sections_review_only"]
    archive_mapping = next(mapping for mapping in result.mappings if mapping.source_bucket == "archive.shared_context")
    assert archive_mapping.status == "unsupported"
    assert archive_mapping.unmapped_count == 1


@pytest.mark.asyncio
async def test_archive_restore_dry_run_returns_hash_and_blocks_secret(db_session: AsyncSession) -> None:
    payload = _restore_payload(
        {
            "memory": {
                "semantic": [
                    {
                        "content": "Never persist OPENAI_API_KEY=sk-" + "a" * 48,
                        "metadata": {},
                    }
                ]
            }
        }
    )

    preview = await MemoryArchiveRestoreService(db_session).dry_run_restore(payload)

    assert len(preview.payload_hash) == 64
    assert preview.plan.status == "critical"
    assert preview.plan.blocked_items == 1
    assert preview.plan.security_findings[0].section == "memory"
    assert preview.plan.security_findings[0].verdict == "redacted"
    assert "security_preflight_blocked" in preview.plan.warning_codes


@pytest.mark.asyncio
async def test_archive_restore_confirm_rejects_changed_review_hash(db_session: AsyncSession) -> None:
    service = MemoryArchiveRestoreService(db_session)
    manager = _RestoreMemoryManager()
    payload = _restore_payload({"memory": {"semantic": [{"content": "Use SQLite.", "metadata": {}}]}})
    preview = await service.dry_run_restore(payload)

    with pytest.raises(MemoryArchiveRestoreError) as exc_info:
        await service.restore_archive(
            payload,
            manager=manager,
            expected_payload_hash=preview.payload_hash,
            expected_plan_hash="0" * 64,
        )

    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_archive_restore_empty_section_selection_restores_nothing(db_session: AsyncSession) -> None:
    payload = _restore_payload({"memory": {"semantic": [{"content": "Use SQLite.", "metadata": {}}]}})

    preview = await MemoryArchiveRestoreService(db_session).dry_run_restore(payload, sections=[])

    assert preview.plan.restorable_items == 0
    assert preview.plan.skipped_items == 1
    assert preview.plan.status == "critical"
    assert preview.plan.sections[0].mode == "skip"
    assert preview.plan.sections[0].warning_codes == ["section_not_selected"]


@pytest.mark.asyncio
async def test_archive_restore_confirm_writes_journaled_batch(db_session: AsyncSession) -> None:
    service = MemoryArchiveRestoreService(db_session)
    manager = _RestoreMemoryManager()
    payload = _restore_payload({"memory": {"semantic": [{"content": "Restore through a journal.", "metadata": {}}]}})
    preview = await service.dry_run_restore(payload)

    result = await service.restore_archive(
        payload,
        manager=manager,
        expected_payload_hash=preview.payload_hash,
        expected_plan_hash=preview.plan.plan_hash,
    )

    assert result.total_restored == 1
    batch = await db_session.get(MemoryArchiveRestoreBatchModel, result.restore_batch_id)
    assert batch is not None
    assert batch.status == RESTORE_BATCH_STATUS_CONFIRMED
    assert batch.payload_hash == preview.payload_hash
    assert batch.plan_hash == preview.plan.plan_hash
    assert batch.metadata_json is not None
    journal = batch.metadata_json.get("restore_journal")
    assert isinstance(journal, dict)
    assert journal["status"] == RESTORE_BATCH_STATUS_CONFIRMED


@pytest.mark.asyncio
async def test_archive_restore_recovery_rebuilds_metadata_ledger_and_rolls_back(
    db_session: AsyncSession,
) -> None:
    manager = _RestoreMemoryManager()
    manager.memory_ids_by_type["semantic"] = ["semantic-0"]
    batch = MemoryArchiveRestoreBatchModel(
        id="memory-archive-restore:recover",
        source="myrm_archive",
        status=RESTORE_BATCH_STATUS_IN_PROGRESS,
        payload_hash="a" * 64,
        plan_hash="b" * 64,
        created_at=datetime.now(UTC),
        confirmed_at=datetime.now(UTC),
        metadata_json={"restore_journal": {"status": RESTORE_BATCH_STATUS_IN_PROGRESS}},
    )
    db_session.add(batch)
    await db_session.commit()

    recovered = await MemoryArchiveRestoreService(db_session).recover_incomplete_restores(manager)

    assert recovered == 1
    assert manager.memory_ids_by_type["semantic"] == []
    recovered_batch = await db_session.get(MemoryArchiveRestoreBatchModel, batch.id)
    assert recovered_batch is not None
    assert recovered_batch.status == RESTORE_BATCH_STATUS_ROLLED_BACK
    item = (
        await db_session.execute(select(MemoryArchiveRestoreItemModel).where(MemoryArchiveRestoreItemModel.batch_id == batch.id))
    ).scalar_one()
    assert item.status == RESTORE_ITEM_STATUS_ROLLED_BACK


@pytest.mark.asyncio
async def test_archive_restore_health_reports_content_blind_counters(db_session: AsyncSession) -> None:
    batch = MemoryArchiveRestoreBatchModel(
        id="memory-archive-restore:health",
        source="myrm_archive",
        status=RESTORE_BATCH_STATUS_IN_PROGRESS,
        payload_hash="a" * 64,
        plan_hash="b" * 64,
        created_at=datetime.now(UTC),
        confirmed_at=datetime.now(UTC),
    )
    item = MemoryArchiveRestoreItemModel(
        id="restore-item-health",
        batch_id=batch.id,
        section="memory",
        item_kind="semantic",
        source_id="source",
        target_id="target",
        status="failed",
        created_at=datetime.now(UTC),
    )
    db_session.add_all([batch, item])
    await db_session.commit()

    health = await MemoryArchiveRestoreService(db_session).restore_health()

    assert health.status == "critical"
    assert health.in_progress_batches == 1
    assert health.failed_items == 1


def _restore_payload(data: dict[str, object]) -> dict[str, object]:
    return {
        "manifest": {
            "format": "myrm_memory_archive",
            "version": 1,
            "created_at": datetime.now(UTC).isoformat(),
            "producer": "test",
            "content_redacted": True,
            "sections": [
                {"name": "memory", "status": "ready", "item_count": 1, "warning_codes": []},
            ],
        },
        "data": data,
    }
