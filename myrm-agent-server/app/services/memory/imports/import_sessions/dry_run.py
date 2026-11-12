"""[INPUT]
- .base (POS: 共享类型、常量与状态)

[OUTPUT]
- DryRunMixin: 创建 dry-run 会话与确认导入

[POS]
`import_sessions/` 的 dry-run -> confirm 阶段。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from myrm_agent_harness.toolkits.memory import (
    MemoryImportDryRunResult,
    MemoryManager,
    MemoryOperationKind,
    MemoryOperationStatus,
)

from app.database.models.memory import MemoryImportDryRunModel
from app.schemas.memory.import_sources import import_source_label
from app.services.memory.imports.import_adapters import RequestedImportSource, build_memory_import_dry_run
from app.services.memory.imports.import_session_data import (
    attach_import_metadata,
    bounded_preview,
    build_import_plan,
    build_transaction_items,
    canonical_hash,
    capture_profile_imported_values,
    capture_profile_previous_values,
    ensure_profile_import_keys,
    normalized_from_json,
    normalized_to_json,
    summary_unmapped_count,
)
from app.services.memory.imports.import_session_models import (
    MemoryImportConfirmResult,
)

from .base import (
    DRY_RUN_STATUS_CONFIRMED,
    DRY_RUN_STATUS_PENDING,
    DRY_RUN_TTL_SECONDS,
    MemoryImportSessionBase,
    MemoryImportSessionError,
)


class DryRunMixin(MemoryImportSessionBase):
    """创建 dry-run 会话与确认导入。"""

    async def create_dry_run(
        self,
        payload: dict[str, object],
        source: RequestedImportSource,
        *,
        skip_duplicates: bool = True,
        ttl_seconds: int = DRY_RUN_TTL_SECONDS,
        session_metadata: dict[str, object] | None = None,
    ) -> tuple[str, MemoryImportDryRunResult, str, datetime]:
        """Create a persisted dry-run session and return a content-safe preview."""

        await self._expire_stale()
        await self.cleanup_sessions()
        result = build_memory_import_dry_run(payload, source)
        ensure_profile_import_keys(result.normalized_data, source=result.summary.source)
        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=ttl_seconds)
        payload_hash = canonical_hash(
            {
                "source": result.summary.source,
                "version": result.summary.version,
                "normalized_data": result.normalized_data,
            }
        )
        dry_run_id = f"memory-import:{uuid4().hex}"
        plan = build_import_plan(result.normalized_data, dry_run_id=dry_run_id, skip_duplicates=skip_duplicates)
        row = MemoryImportDryRunModel(
            id=dry_run_id,
            source=import_source_label(result.summary.source),
            status=DRY_RUN_STATUS_PENDING,
            payload_hash=payload_hash,
            normalized_data_json=normalized_to_json(result.normalized_data),
            summary_json=result.summary.model_dump(mode="json"),
            warnings_json=list(result.warnings),
            created_at=now,
            expires_at=expires_at,
            metadata_json={
                "requested_source": source,
                "plan_hash": plan.plan_hash,
                "skip_duplicates": skip_duplicates,
                **(session_metadata or {}),
            },
        )
        self._db.add(row)
        await self._db.commit()
        preview = result.model_copy(update={"normalized_data": bounded_preview(result.normalized_data), "plan": plan})
        return dry_run_id, preview, payload_hash, expires_at


    async def confirm_import(
        self,
        *,
        dry_run_id: str,
        manager: MemoryManager,
        skip_duplicates: bool = True,
    ) -> MemoryImportConfirmResult:
        """Confirm a previously reviewed import session by id."""

        await self._expire_stale()
        row = await self._get_pending_row(dry_run_id)
        normalized = normalized_from_json(row.normalized_data_json)
        if not normalized:
            raise MemoryImportSessionError("Import review does not contain mapped memories.")
        plan = build_import_plan(normalized, dry_run_id=row.id, skip_duplicates=skip_duplicates)
        expected_plan_hash = (row.metadata_json or {}).get("plan_hash")
        if isinstance(expected_plan_hash, str) and expected_plan_hash != plan.plan_hash:
            raise MemoryImportSessionError("Import plan no longer matches the reviewed dry-run session.", status_code=409)

        import_batch_id = f"memory-import-batch:{uuid4().hex}"
        profile_previous_values = await capture_profile_previous_values(manager, normalized)
        enriched = attach_import_metadata(
            normalized,
            import_batch_id=import_batch_id,
            source=row.source,
            dry_run_id=row.id,
            payload_hash=row.payload_hash,
        )
        counts = await manager.import_memories(enriched, skip_duplicates=skip_duplicates)
        stored_refs = await manager.list_memory_refs_by_metadata("import_batch_id", import_batch_id)
        profile_imported_values = await capture_profile_imported_values(manager, enriched)
        transaction_items = build_transaction_items(
            enriched,
            stored_refs=stored_refs,
            profile_previous_values=profile_previous_values,
            profile_imported_values=profile_imported_values,
        )
        total = sum(counts.values())
        now = datetime.now(UTC)
        row.status = DRY_RUN_STATUS_CONFIRMED
        row.confirmed_at = now
        row.import_batch_id = import_batch_id
        row.metadata_json = {
            **(row.metadata_json or {}),
            "transaction_ledger_summary": {
                "version": 2,
                "import_batch_id": import_batch_id,
                "created_at": now.isoformat(),
                "item_count": len(transaction_items),
            },
        }
        await self._import_ledger.record_confirmed_batch(
            import_batch_id=import_batch_id,
            dry_run_id=row.id,
            source=row.source,
            payload_hash=row.payload_hash,
            imported_count=total,
            unmapped_count=summary_unmapped_count(row.summary_json),
            transaction_items=transaction_items,
            metadata={
                "skip_duplicates": skip_duplicates,
                "dry_run_id": row.id,
                "payload_hash": row.payload_hash,
            },
        )
        await self._ledger.record_migration(
            source=row.source,
            status="complete",
            imported_count=total,
            unmapped_count=summary_unmapped_count(row.summary_json),
            metadata={
                "dry_run_id": row.id,
                "payload_hash": row.payload_hash,
                "import_batch_id": import_batch_id,
                "skip_duplicates": skip_duplicates,
                "transaction_items": len(transaction_items),
                "diagnostic_status": "pending",
                "plan_hash": plan.plan_hash,
            },
        )
        await self._ledger.record_event(
            kind=MemoryOperationKind.IMPORT_MEMORY,
            status=MemoryOperationStatus.SUCCESS,
            summary="Memory import confirmed from a server-bound dry-run session.",
            source="memory_import_session",
            target_kind="memory_import",
            target_id=row.id,
            correlation_id=import_batch_id,
            metadata={
                "dry_run_id": row.id,
                "payload_hash": row.payload_hash,
                "import_batch_id": import_batch_id,
                "imported_count": total,
                "source": row.source,
            },
        )
        await self._db.commit()
        return MemoryImportConfirmResult(
            imported=counts,
            total_imported=total,
            import_batch_id=import_batch_id,
            payload_hash=row.payload_hash,
            source=row.source,
            transaction_items=transaction_items,
        )
