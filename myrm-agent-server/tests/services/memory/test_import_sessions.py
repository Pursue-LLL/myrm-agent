from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from myrm_agent_harness.toolkits.memory import MemoryMutationRef, MemoryMutationResult, ProfileAttributeSnapshot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.models import Base
from app.database.models.memory import (
    MemoryImportBatchModel,
    MemoryImportDryRunModel,
    MemoryImportItemModel,
    MemoryMigrationProvenanceModel,
)
from app.services.memory.imports.import_ledger import (
    IMPORT_BATCH_STATUS_PARTIAL,
    IMPORT_BATCH_STATUS_ROLLED_BACK,
    IMPORT_ITEM_STATUS_CONFLICT,
    IMPORT_ITEM_STATUS_MISSING,
    IMPORT_ITEM_STATUS_ROLLED_BACK,
    MemoryImportLedgerService,
)
from app.services.memory.imports.import_sessions import (
    ImportReadinessRecheckFacts,
    MemoryImportSessionError,
    MemoryImportSessionService,
)
from app.services.memory.operations.crud.import_readiness import build_import_readiness


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
                result.deleted_refs.append(MemoryMutationRef(memory_type=memory_type, memory_id=memory_id, backend="fake"))
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
        await db_session.execute(select(MemoryImportItemModel).where(MemoryImportItemModel.batch_id == confirm.import_batch_id))
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
        await db_session.execute(select(MemoryImportItemModel).where(MemoryImportItemModel.batch_id == confirm.import_batch_id))
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
        await db_session.execute(select(MemoryImportItemModel).where(MemoryImportItemModel.batch_id == confirm.import_batch_id))
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
        await db_session.execute(select(MemoryImportItemModel).where(MemoryImportItemModel.batch_id == confirm.import_batch_id))
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


@pytest.mark.asyncio
async def test_save_post_import_readiness_persists_session_and_provenance_metadata(
    db_session: AsyncSession,
) -> None:
    manager = _FakeMemoryManager()
    service = MemoryImportSessionService(db_session)
    payload = {"data": {"semantic": [{"content": "Persist readiness contract state.", "metadata": {}}]}}
    dry_run_id, _preview, _payload_hash, _expires_at = await service.create_dry_run(payload, "native_json")
    confirm = await service.confirm_import(dry_run_id=dry_run_id, manager=manager)

    readiness_issues = [
        {
            "code": "mcp_servers_imported_disabled",
            "severity": "warning",
            "params": {"count": 2},
        }
    ]
    await service.save_post_import_readiness(
        import_batch_id=confirm.import_batch_id,
        readiness_status="warning",
        readiness_issues=readiness_issues,
    )

    dry_run = await db_session.get(MemoryImportDryRunModel, dry_run_id)
    assert dry_run is not None
    assert isinstance(dry_run.metadata_json, dict)
    post_import_readiness = dry_run.metadata_json.get("post_import_readiness")
    assert isinstance(post_import_readiness, dict)
    assert post_import_readiness.get("status") == "warning"
    assert post_import_readiness.get("issues") == readiness_issues

    provenance = (
        await db_session.execute(
            select(MemoryMigrationProvenanceModel).order_by(MemoryMigrationProvenanceModel.started_at.desc())
        )
    ).scalars().first()
    assert provenance is not None
    assert isinstance(provenance.metadata_json, dict)
    assert provenance.metadata_json.get("readiness_status") == "warning"
    assert provenance.metadata_json.get("readiness_issue_count") == 1
    assert provenance.metadata_json.get("readiness_issue_codes") == ["mcp_servers_imported_disabled"]


@pytest.mark.asyncio
async def test_save_post_import_readiness_persists_recheck_facts_ssot(
    db_session: AsyncSession,
) -> None:
    manager = _FakeMemoryManager()
    service = MemoryImportSessionService(db_session)
    payload = {"data": {"semantic": [{"content": "Persist recheck facts.", "metadata": {}}]}}
    dry_run_id, _preview, _payload_hash, _expires_at = await service.create_dry_run(payload, "native_json")
    confirm = await service.confirm_import(dry_run_id=dry_run_id, manager=manager)

    facts = ImportReadinessRecheckFacts(
        source_has_api_keys=True,
        diagnostic_status="ready",
        diagnostic_failed_count=0,
        mcp_config_count=3,
        workspace_rules_skipped=1,
    )
    await service.save_post_import_readiness(
        import_batch_id=confirm.import_batch_id,
        readiness_status="warning",
        readiness_issues=[],
        recheck_facts=facts,
    )
    await service.save_post_import_readiness(
        import_batch_id=confirm.import_batch_id,
        readiness_status="ready",
        readiness_issues=[],
    )

    dry_run = await db_session.get(MemoryImportDryRunModel, dry_run_id)
    assert dry_run is not None
    metadata = dry_run.metadata_json
    assert isinstance(metadata, dict)
    recheck_block = metadata.get("recheck_facts")
    assert isinstance(recheck_block, dict)
    assert recheck_block.get("mcp_config_count") == 3
    assert recheck_block.get("workspace_rules_skipped") == 1

    loaded = await service.load_import_readiness_recheck_facts(confirm.import_batch_id)
    assert loaded.mcp_config_count == 3
    assert loaded.workspace_rules_skipped == 1


@pytest.mark.asyncio
async def test_save_post_import_first_turn_outcome_persists_once(
    db_session: AsyncSession,
) -> None:
    manager = _FakeMemoryManager()
    service = MemoryImportSessionService(db_session)
    payload = {"data": {"semantic": [{"content": "Track first turn outcome after migration.", "metadata": {}}]}}
    dry_run_id, _preview, _payload_hash, _expires_at = await service.create_dry_run(payload, "native_json")
    confirm = await service.confirm_import(dry_run_id=dry_run_id, manager=manager)

    await service.save_post_import_first_turn_outcome(
        import_batch_id=confirm.import_batch_id,
        readiness_status="warning",
        outcome="success",
        had_fatal_error=False,
        chat_id="chat-1",
        message_id="msg-1",
    )
    await service.save_post_import_first_turn_outcome(
        import_batch_id=confirm.import_batch_id,
        readiness_status="warning",
        outcome="failed",
        had_fatal_error=True,
        chat_id="chat-2",
        message_id="msg-2",
    )

    dry_run = await db_session.get(MemoryImportDryRunModel, dry_run_id)
    assert dry_run is not None
    assert isinstance(dry_run.metadata_json, dict)
    first_turn = dry_run.metadata_json.get("post_import_first_turn")
    assert isinstance(first_turn, dict)
    assert first_turn.get("outcome") == "success"
    assert first_turn.get("chat_id") == "chat-1"
    assert first_turn.get("message_id") == "msg-1"

    provenance = (
        await db_session.execute(
            select(MemoryMigrationProvenanceModel).order_by(MemoryMigrationProvenanceModel.started_at.desc())
        )
    ).scalars().first()
    assert provenance is not None
    assert isinstance(provenance.metadata_json, dict)
    assert provenance.metadata_json.get("first_turn_outcome") == "success"
    assert provenance.metadata_json.get("first_turn_readiness_status") == "warning"
    assert provenance.metadata_json.get("first_turn_had_fatal_error") is False
    assert provenance.metadata_json.get("first_turn_chat_id") == "chat-1"
    assert provenance.metadata_json.get("first_turn_message_id") == "msg-1"


@pytest.mark.asyncio
async def test_load_import_readiness_recheck_facts_prefers_recheck_facts_ssot(
    db_session: AsyncSession,
) -> None:
    manager = _FakeMemoryManager()
    service = MemoryImportSessionService(db_session)
    payload = {"data": {"semantic": [{"content": "SSOT recheck facts.", "metadata": {}}]}}
    dry_run_id, _preview, _payload_hash, _expires_at = await service.create_dry_run(
        payload,
        "native_json",
        session_metadata={"source_has_api_keys": False},
    )
    confirm = await service.confirm_import(dry_run_id=dry_run_id, manager=manager)
    await service.save_post_import_readiness(
        import_batch_id=confirm.import_batch_id,
        readiness_status="warning",
        readiness_issues=[
            {
                "code": "mcp_servers_imported_disabled",
                "severity": "warning",
                "params": {"count": 99},
            }
        ],
        recheck_facts=ImportReadinessRecheckFacts(
            source_has_api_keys=True,
            diagnostic_status="ready",
            diagnostic_failed_count=0,
            mcp_config_count=2,
            workspace_rules_skipped=1,
        ),
    )

    facts = await service.load_import_readiness_recheck_facts(confirm.import_batch_id)

    assert facts.source_has_api_keys is True
    assert facts.diagnostic_status == "ready"
    assert facts.mcp_config_count == 2
    assert facts.workspace_rules_skipped == 1


@pytest.mark.asyncio
async def test_load_import_readiness_recheck_facts_from_session_metadata(
    db_session: AsyncSession,
) -> None:
    manager = _FakeMemoryManager()
    service = MemoryImportSessionService(db_session)
    payload = {"data": {"semantic": [{"content": "Recheck facts.", "metadata": {}}]}}
    dry_run_id, _preview, _payload_hash, _expires_at = await service.create_dry_run(
        payload,
        "native_json",
        session_metadata={"source_has_api_keys": True},
    )
    confirm = await service.confirm_import(dry_run_id=dry_run_id, manager=manager)
    await service.save_post_import_diagnostic(
        import_batch_id=confirm.import_batch_id,
        diagnostic_run_id="diag-ready",
        diagnostic_status="ready",
        failed_count=0,
    )
    await service.save_post_import_readiness(
        import_batch_id=confirm.import_batch_id,
        readiness_status="critical",
        readiness_issues=[
            {
                "code": "providers_not_configured",
                "severity": "critical",
                "params": {},
            },
            {
                "code": "mcp_servers_imported_disabled",
                "severity": "warning",
                "params": {"count": 2},
            },
        ],
    )

    facts = await service.load_import_readiness_recheck_facts(confirm.import_batch_id)

    assert facts.source_has_api_keys is True
    assert facts.diagnostic_status == "ready"
    assert facts.mcp_config_count == 2
    assert facts.workspace_rules_skipped == 0


@pytest.mark.asyncio
async def test_recheck_import_readiness_uses_current_provider_state(
    db_session: AsyncSession,
) -> None:
    manager = _FakeMemoryManager()
    service = MemoryImportSessionService(db_session)
    payload = {"data": {"semantic": [{"content": "Recheck endpoint.", "metadata": {}}]}}
    dry_run_id, _preview, _payload_hash, _expires_at = await service.create_dry_run(
        payload,
        "native_json",
        session_metadata={"source_has_api_keys": True},
    )
    confirm = await service.confirm_import(dry_run_id=dry_run_id, manager=manager)
    await service.save_post_import_diagnostic(
        import_batch_id=confirm.import_batch_id,
        diagnostic_run_id="diag-ready",
        diagnostic_status="ready",
        failed_count=0,
    )
    await service.save_post_import_readiness(
        import_batch_id=confirm.import_batch_id,
        readiness_status="critical",
        readiness_issues=[{"code": "providers_not_configured", "severity": "critical", "params": {}}],
    )

    facts = await service.load_import_readiness_recheck_facts(confirm.import_batch_id)

    readiness = build_import_readiness(
        providers_configured=True,
        source_has_api_keys=facts.source_has_api_keys,
        diagnostic_status=facts.diagnostic_status,
        diagnostic_failed_count=facts.diagnostic_failed_count,
        mcp_config_count=facts.mcp_config_count,
        workspace_rules_skipped=facts.workspace_rules_skipped,
    )

    assert readiness.status == "ready"
    assert readiness.issues == []
