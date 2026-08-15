"""Memory import dry-run session service.

[INPUT]
app.services.memory.imports.import_adapters::build_memory_import_dry_run (POS: 记忆导入 dry-run adapter)
app.services.memory.imports.import_session_data::* (POS: 记忆导入会话数据转换层)
app.services.memory.imports.import_session_models::* (POS: 记忆导入会话 DTO 层)
app.services.memory.imports.import_ledger::MemoryImportLedgerService (POS: 导入批次/条目账本状态机)
app.services.memory.imports.import_rollback::* (POS: 记忆导入回滚辅助层)
app.services.memory.ledger.operation_ledger::MemoryOperationLedgerService (POS: 单用户记忆观测账本服务)
app.database.models.memory::MemoryImportDryRunModel (POS: 记忆域模型)
myrm_agent_harness.toolkits.memory::MemoryManager (POS: Unified memory manager and core facade of the Memory Toolkit)

[OUTPUT]
MemoryImportSessionService: creates bound dry-run sessions, confirms imports by dry-run id, records transaction ledgers, previews rollback, rolls back batches, stores post-import diagnostics/readiness contracts and first-turn execution outcomes, loads readiness recheck facts for confirmed batches, and exposes cleanup metrics.

[POS]
单用户记忆导入审查会话服务。把外部记忆导入从客户端数据提交收口为服务端绑定、可审计、可诊断、可预演回滚的 dry-run -> confirm 流程。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import uuid4

from myrm_agent_harness.toolkits.memory import (
    MemoryImportDryRunResult,
    MemoryManager,
    MemoryOperationKind,
    MemoryOperationStatus,
    MemoryType,
)
from sqlalchemy import delete, desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.memory import MemoryImportBatchModel, MemoryImportDryRunModel
from app.schemas.memory.archive import MemoryImportReadiness
from app.services.memory.imports.import_adapter_registry import import_source_label
from app.services.memory.imports.import_adapters import RequestedImportSource, build_memory_import_dry_run
from app.services.memory.imports.import_ledger import (
    IMPORT_BATCH_STATUS_CONFIRMED,
    IMPORT_BATCH_STATUS_ROLLBACK_IN_PROGRESS,
    IMPORT_ITEM_STATUS_CONFLICT,
    IMPORT_ITEM_STATUS_MISSING,
    IMPORT_ITEM_STATUS_ROLLBACK_FAILED,
    IMPORT_ITEM_STATUS_SKIPPED,
    MemoryImportLedgerService,
)
from app.services.memory.imports.import_rollback import (
    count_profile_conflicts,
    is_imported_memory_item,
    is_imported_profile_item,
    preview_items_by_type,
    rollback_memory_items,
    rollback_preview_warnings,
    rollback_profile_items,
)
from app.services.memory.imports.import_session_data import (
    attach_import_metadata,
    build_import_plan,
    build_transaction_items,
    canonical_hash,
    capture_profile_imported_values,
    capture_profile_previous_values,
    normalized_from_json,
    normalized_to_json,
    summary_unmapped_count,
)
from app.services.memory.imports.import_session_models import (
    MemoryImportConfirmResult,
    MemoryImportRollbackPreviewResult,
    MemoryImportRollbackResult,
)
from app.services.memory.ledger.operation_ledger import MemoryOperationLedgerService

DRY_RUN_TTL_SECONDS = 30 * 60
DRY_RUN_RETENTION_DAYS = 7
DRY_RUN_STATUS_PENDING = "pending"
DRY_RUN_STATUS_CONFIRMED = "confirmed"
DRY_RUN_STATUS_EXPIRED = "expired"
DRY_RUN_STATUS_ROLLED_BACK = "rolled_back"


class MemoryImportSessionError(Exception):
    """Raised when an import review session cannot be confirmed."""

    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class ImportReadinessRecheckFacts:
    """Stored import-batch facts combined with live provider checks during recheck."""

    source_has_api_keys: bool
    diagnostic_status: str | None
    diagnostic_failed_count: int
    mcp_config_count: int
    workspace_rules_skipped: int
    migration_competitor: str | None = None

    def to_metadata_block(self) -> dict[str, object]:
        block: dict[str, object] = {
            "source_has_api_keys": self.source_has_api_keys,
            "diagnostic_status": self.diagnostic_status,
            "diagnostic_failed_count": self.diagnostic_failed_count,
            "mcp_config_count": self.mcp_config_count,
            "workspace_rules_skipped": self.workspace_rules_skipped,
        }
        if self.migration_competitor:
            block["migration_competitor"] = self.migration_competitor
        return block

    @classmethod
    def from_metadata_block(cls, block: dict[str, object]) -> ImportReadinessRecheckFacts:
        diagnostic_status_raw = block.get("diagnostic_status")
        diagnostic_status = (
            diagnostic_status_raw.strip()
            if isinstance(diagnostic_status_raw, str) and diagnostic_status_raw.strip()
            else None
        )
        competitor_raw = block.get("migration_competitor")
        migration_competitor = (
            competitor_raw.strip()
            if isinstance(competitor_raw, str) and competitor_raw.strip()
            else None
        )
        return cls(
            source_has_api_keys=block.get("source_has_api_keys") is True,
            diagnostic_status=diagnostic_status,
            diagnostic_failed_count=_coerce_non_negative_int(block.get("diagnostic_failed_count")),
            mcp_config_count=_coerce_non_negative_int(block.get("mcp_config_count")),
            workspace_rules_skipped=_coerce_non_negative_int(block.get("workspace_rules_skipped")),
            migration_competitor=migration_competitor,
        )


def _coerce_non_negative_int(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(0, value)
    if isinstance(value, float):
        return max(0, int(value))
    return 0


class MemoryImportSessionService:
    """Creates and confirms server-bound memory import review sessions."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._ledger = MemoryOperationLedgerService(db)
        self._import_ledger = MemoryImportLedgerService(db)

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
        preview = result.model_copy(update={"normalized_data": {}, "plan": plan})
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

    async def preview_rollback(
        self,
        *,
        manager: MemoryManager,
        dry_run_id: str | None = None,
        import_batch_id: str | None = None,
    ) -> MemoryImportRollbackPreviewResult:
        """Return a content-safe preview for a confirmed import rollback."""

        await self._expire_stale()
        batch = await self._get_confirmed_batch(dry_run_id=dry_run_id, import_batch_id=import_batch_id)
        items = await self._import_ledger.list_items(batch.id)
        profile_items = [item for item in items if is_imported_profile_item(item)]
        profile_conflicts = await count_profile_conflicts(manager, profile_items)
        items_by_type = preview_items_by_type(items, profile_conflicts=profile_conflicts)
        skipped_items = sum(1 for item in items if item.status == IMPORT_ITEM_STATUS_SKIPPED)
        missing_items = sum(1 for item in items if item.status == IMPORT_ITEM_STATUS_MISSING)
        reversible_items = sum(items_by_type.values())
        profile_keys = sorted(item.profile_key for item in profile_items if item.profile_key)
        warnings = rollback_preview_warnings(
            reversible_items=reversible_items,
            profile_keys=profile_keys,
            profile_conflicts=profile_conflicts,
            memory_rows_missing=sum(1 for item in items if is_imported_memory_item(item) and not item.memory_ids_json),
        )

        return MemoryImportRollbackPreviewResult(
            import_batch_id=batch.id,
            source=batch.source,
            total_items=len(items),
            reversible_items=reversible_items,
            items_by_type=items_by_type,
            profile_keys=profile_keys,
            warnings=warnings,
            skipped_items=skipped_items,
            conflict_items=profile_conflicts,
            missing_items=missing_items,
        )

    async def rollback_import(
        self,
        *,
        manager: MemoryManager,
        dry_run_id: str | None = None,
        import_batch_id: str | None = None,
    ) -> MemoryImportRollbackResult:
        """Rollback a confirmed import batch by deleting records tagged with its batch id."""

        await self._expire_stale()
        batch = await self._get_rollback_batch(dry_run_id=dry_run_id, import_batch_id=import_batch_id)
        if _rollback_in_progress(batch):
            return await self._execute_batch_rollback(manager=manager, batch=batch, recovering=True)
        await self.recover_incomplete_rollbacks(manager, exclude_batch_id=batch.id)
        return await self._execute_batch_rollback(manager=manager, batch=batch)

    async def recover_incomplete_rollbacks(self, manager: MemoryManager, *, exclude_batch_id: str | None = None) -> int:
        """Resume batches that were journaled before a process interruption."""

        recovered = 0
        for batch in await self._import_ledger.list_incomplete_rollbacks():
            if batch.id == exclude_batch_id:
                continue
            await self._execute_batch_rollback(manager=manager, batch=batch, recovering=True)
            recovered += 1
        return recovered

    async def _execute_batch_rollback(
        self,
        *,
        manager: MemoryManager,
        batch: MemoryImportBatchModel,
        recovering: bool = False,
    ) -> MemoryImportRollbackResult:
        items = await self._import_ledger.list_items(batch.id)
        now = datetime.now(UTC)
        if not recovering:
            self._import_ledger.begin_batch_rollback(batch, started_at=now)
            await self._db.commit()
        memory_result = await rollback_memory_items(manager, self._import_ledger, items, rolled_back_at=now)
        rolled_back = dict(memory_result.rolled_back)
        profile_result = await rollback_profile_items(manager, self._import_ledger, items, rolled_back_at=now)
        if profile_result.rolled_back > 0:
            rolled_back[MemoryType.PROFILE.value] = profile_result.rolled_back
        total = sum(rolled_back.values())
        failed_items = sum(1 for item in items if item.status == IMPORT_ITEM_STATUS_ROLLBACK_FAILED)
        missing_items = sum(1 for item in items if item.status == IMPORT_ITEM_STATUS_MISSING)
        conflict_items = profile_result.conflicts
        self._import_ledger.mark_batch_rollback(
            batch,
            rolled_back_count=total,
            conflict_count=conflict_items,
            missing_count=missing_items,
            failed_count=failed_items,
            rolled_back_at=now,
        )
        await self._mark_dry_run_rolled_back(batch, total, now)
        integrity_status = await self._rollback_integrity_status(manager=manager, batch=batch)
        event_status = (
            MemoryOperationStatus.ERROR
            if failed_items > 0
            else MemoryOperationStatus.WARNING
            if conflict_items > 0 or missing_items > 0
            else MemoryOperationStatus.SUCCESS
        )
        await self._ledger.record_event(
            kind=MemoryOperationKind.FORGET,
            status=event_status,
            summary="Memory import batch rolled back.",
            source="memory_import_session",
            target_kind="memory_import",
            target_id=batch.dry_run_id,
            correlation_id=batch.id,
            metadata={
                "dry_run_id": batch.dry_run_id,
                "payload_hash": batch.payload_hash,
                "import_batch_id": batch.id,
                "rolled_back_count": total,
                "conflict_items": conflict_items,
                "missing_items": missing_items,
                "failed_items": failed_items,
                "integrity_status": integrity_status,
                "recovered": recovering,
                "source": batch.source,
            },
        )
        await self._db.commit()
        return MemoryImportRollbackResult(
            import_batch_id=batch.id,
            rolled_back=rolled_back,
            total_rolled_back=total,
            source=batch.source,
            conflict_items=conflict_items,
            missing_items=missing_items,
            failed_items=failed_items,
            deleted_refs=memory_result.deleted_refs,
            missing_refs=memory_result.missing_refs,
            forbidden_refs=memory_result.forbidden_refs,
            failed_refs=memory_result.failed_refs,
            integrity_status=integrity_status,
        )

    async def save_post_import_diagnostic(
        self,
        *,
        import_batch_id: str,
        diagnostic_run_id: str,
        diagnostic_status: str,
        failed_count: int,
    ) -> None:
        """Attach the automatic post-import diagnostic result to the import session."""

        result = await self._db.execute(
            select(MemoryImportDryRunModel)
            .where(MemoryImportDryRunModel.import_batch_id == import_batch_id)
            .order_by(desc(MemoryImportDryRunModel.confirmed_at))
            .limit(1)
        )
        row = result.scalar_one_or_none()
        await self._import_ledger.save_post_import_diagnostic(
            import_batch_id=import_batch_id,
            diagnostic_run_id=diagnostic_run_id,
            diagnostic_status=diagnostic_status,
            failed_count=failed_count,
        )
        if row is None:
            await self._db.commit()
            return
        row.metadata_json = {
            **(row.metadata_json or {}),
            "post_import_diagnostic": {
                "run_id": diagnostic_run_id,
                "status": diagnostic_status,
                "failed_count": failed_count,
                "completed_at": datetime.now(UTC).isoformat(),
            },
        }
        await self._ledger.update_migration_metadata_by_batch(
            import_batch_id=import_batch_id,
            metadata={
                "diagnostic_run_id": diagnostic_run_id,
                "diagnostic_status": diagnostic_status,
                "diagnostic_failed_count": failed_count,
            },
        )
        await self._db.commit()

    async def load_import_readiness_recheck_facts(
        self,
        import_batch_id: str,
    ) -> ImportReadinessRecheckFacts:
        """Load persisted batch facts required to rebuild the import readiness contract."""

        normalized_batch_id = import_batch_id.strip()
        if not normalized_batch_id:
            raise MemoryImportSessionError("Import batch id is required.", status_code=400)

        result = await self._db.execute(
            select(MemoryImportDryRunModel)
            .where(MemoryImportDryRunModel.import_batch_id == normalized_batch_id)
            .order_by(desc(MemoryImportDryRunModel.confirmed_at))
            .limit(1)
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise MemoryImportSessionError("Import batch not found.", status_code=404)

        meta = row.metadata_json if isinstance(row.metadata_json, dict) else {}
        recheck_facts_block = meta.get("recheck_facts")
        if isinstance(recheck_facts_block, dict):
            return ImportReadinessRecheckFacts.from_metadata_block(recheck_facts_block)

        source_has_api_keys = meta.get("source_has_api_keys") is True

        diagnostic_status: str | None = None
        diagnostic_failed_count = 0
        post_import_diagnostic = meta.get("post_import_diagnostic")
        if isinstance(post_import_diagnostic, dict):
            raw_status = post_import_diagnostic.get("status")
            if isinstance(raw_status, str) and raw_status.strip():
                diagnostic_status = raw_status.strip()
            failed_raw = post_import_diagnostic.get("failed_count")
            if isinstance(failed_raw, int):
                diagnostic_failed_count = failed_raw

        mcp_config_count = 0
        workspace_rules_skipped = 0
        post_import_readiness = meta.get("post_import_readiness")
        if isinstance(post_import_readiness, dict):
            issues_raw = post_import_readiness.get("issues")
            if isinstance(issues_raw, list):
                for item in issues_raw:
                    if not isinstance(item, dict):
                        continue
                    code = str(item.get("code", "")).strip()
                    params_raw = item.get("params")
                    params = params_raw if isinstance(params_raw, dict) else {}
                    count_raw = params.get("count", params.get("failed_count", 0))
                    count = int(count_raw) if isinstance(count_raw, (int, float)) else 0
                    if code == "mcp_servers_imported_disabled":
                        mcp_config_count = count
                    elif code == "workspace_rules_skipped":
                        workspace_rules_skipped = count

        return ImportReadinessRecheckFacts(
            source_has_api_keys=source_has_api_keys,
            diagnostic_status=diagnostic_status,
            diagnostic_failed_count=diagnostic_failed_count,
            mcp_config_count=mcp_config_count,
            workspace_rules_skipped=workspace_rules_skipped,
        )

    async def resolve_live_import_readiness(
        self,
        import_batch_id: str,
    ) -> MemoryImportReadiness:
        """Rebuild post-import readiness using persisted batch facts and live provider state."""

        from app.services.memory.operations.crud.import_readiness import build_import_readiness
        from app.services.migration.source_secrets_importer import external_source_providers_configured

        facts = await self.load_import_readiness_recheck_facts(import_batch_id)
        providers_configured = await external_source_providers_configured()
        return build_import_readiness(
            providers_configured=providers_configured,
            source_has_api_keys=facts.source_has_api_keys,
            diagnostic_status=facts.diagnostic_status,
            diagnostic_failed_count=facts.diagnostic_failed_count,
            mcp_config_count=facts.mcp_config_count,
            workspace_rules_skipped=facts.workspace_rules_skipped,
            migration_competitor=facts.migration_competitor,
        )

    async def save_post_import_readiness(
        self,
        *,
        import_batch_id: str,
        readiness_status: str,
        readiness_issues: list[dict[str, object]],
        recheck_facts: ImportReadinessRecheckFacts | None = None,
    ) -> None:
        """Attach post-import execution readiness contract to review session metadata."""

        result = await self._db.execute(
            select(MemoryImportDryRunModel)
            .where(MemoryImportDryRunModel.import_batch_id == import_batch_id)
            .order_by(desc(MemoryImportDryRunModel.confirmed_at))
            .limit(1)
        )
        row = result.scalar_one_or_none()
        if row is not None:
            metadata_patch: dict[str, object] = {
                **(row.metadata_json or {}),
                "post_import_readiness": {
                    "status": readiness_status,
                    "issues": readiness_issues,
                    "completed_at": datetime.now(UTC).isoformat(),
                },
            }
            if recheck_facts is not None:
                metadata_patch["recheck_facts"] = recheck_facts.to_metadata_block()
            row.metadata_json = metadata_patch
        await self._ledger.update_migration_metadata_by_batch(
            import_batch_id=import_batch_id,
            metadata={
                "readiness_status": readiness_status,
                "readiness_issue_count": len(readiness_issues),
                "readiness_issue_codes": [
                    str(item.get("code", ""))
                    for item in readiness_issues
                    if isinstance(item, dict) and str(item.get("code", "")).strip()
                ],
            },
        )
        await self._db.commit()

    async def save_post_import_first_turn_outcome(
        self,
        *,
        import_batch_id: str,
        readiness_status: Literal["ready", "warning", "critical"],
        outcome: Literal["success", "failed", "no_output"],
        had_fatal_error: bool,
        chat_id: str | None,
        message_id: str,
    ) -> None:
        """Attach first-turn execution outcome for migration readiness dual-anchor tracking."""

        result = await self._db.execute(
            select(MemoryImportDryRunModel)
            .where(MemoryImportDryRunModel.import_batch_id == import_batch_id)
            .order_by(desc(MemoryImportDryRunModel.confirmed_at))
            .limit(1)
        )
        row = result.scalar_one_or_none()
        if row is not None:
            current_meta = row.metadata_json if isinstance(row.metadata_json, dict) else {}
            existing = current_meta.get("post_import_first_turn")
            if isinstance(existing, dict) and isinstance(existing.get("outcome"), str):
                return
            recorded_at = datetime.now(UTC).isoformat()
            row.metadata_json = {
                **current_meta,
                "post_import_first_turn": {
                    "readiness_status": readiness_status,
                    "outcome": outcome,
                    "had_fatal_error": had_fatal_error,
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "recorded_at": recorded_at,
                },
            }
        else:
            recorded_at = datetime.now(UTC).isoformat()

        await self._ledger.update_migration_metadata_by_batch(
            import_batch_id=import_batch_id,
            metadata={
                "first_turn_readiness_status": readiness_status,
                "first_turn_outcome": outcome,
                "first_turn_had_fatal_error": had_fatal_error,
                "first_turn_chat_id": chat_id,
                "first_turn_message_id": message_id,
                "first_turn_recorded_at": recorded_at,
            },
        )
        await self._db.commit()

    async def cleanup_sessions(self, *, retention_days: int = DRY_RUN_RETENTION_DAYS) -> int:
        """Remove completed import review sessions after the rollback retention window."""

        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        result = await self._db.execute(
            delete(MemoryImportDryRunModel)
            .where(MemoryImportDryRunModel.status != DRY_RUN_STATUS_PENDING)
            .where(MemoryImportDryRunModel.created_at < cutoff)
        )
        await self._db.commit()
        return int(result.rowcount or 0)

    async def session_metrics(self) -> dict[str, int]:
        """Return content-free import review session counts for maintenance visibility."""

        metrics: dict[str, int] = {
            DRY_RUN_STATUS_PENDING: 0,
            DRY_RUN_STATUS_CONFIRMED: 0,
            DRY_RUN_STATUS_EXPIRED: 0,
            DRY_RUN_STATUS_ROLLED_BACK: 0,
        }
        now = datetime.now(UTC)
        result = await self._db.execute(select(MemoryImportDryRunModel.status, MemoryImportDryRunModel.expires_at))
        for status, expires_at in result.all():
            effective_status = (
                DRY_RUN_STATUS_EXPIRED if status == DRY_RUN_STATUS_PENDING and _as_aware(expires_at) <= now else str(status)
            )
            metrics[effective_status] = metrics.get(effective_status, 0) + 1
        return metrics

    async def get_pending_session_metadata(self, dry_run_id: str) -> dict[str, object]:
        """Return metadata stored on a pending dry-run session (e.g. migration instruction plan)."""

        row = await self._get_pending_row(dry_run_id)
        raw = row.metadata_json
        return raw if isinstance(raw, dict) else {}

    async def _get_pending_row(self, dry_run_id: str) -> MemoryImportDryRunModel:
        row = await self._db.get(MemoryImportDryRunModel, dry_run_id)
        if row is None:
            raise MemoryImportSessionError("Import review session was not found.", status_code=404)
        if row.status != DRY_RUN_STATUS_PENDING:
            raise MemoryImportSessionError("Import review session is no longer pending.")
        if _as_aware(row.expires_at) <= datetime.now(UTC):
            row.status = DRY_RUN_STATUS_EXPIRED
            await self._db.commit()
            raise MemoryImportSessionError("Import review session has expired.")
        return row

    async def _get_confirmed_batch(
        self,
        *,
        dry_run_id: str | None,
        import_batch_id: str | None,
    ) -> MemoryImportBatchModel:
        batch = await self._get_batch(dry_run_id=dry_run_id, import_batch_id=import_batch_id)
        if batch.status != IMPORT_BATCH_STATUS_CONFIRMED:
            raise MemoryImportSessionError("Import batch is not eligible for rollback.")
        return batch

    async def _get_rollback_batch(
        self,
        *,
        dry_run_id: str | None,
        import_batch_id: str | None,
    ) -> MemoryImportBatchModel:
        batch = await self._get_batch(dry_run_id=dry_run_id, import_batch_id=import_batch_id)
        if batch.status != IMPORT_BATCH_STATUS_CONFIRMED and not _rollback_in_progress(batch):
            raise MemoryImportSessionError("Import batch is not eligible for rollback.")
        return batch

    async def _get_batch(
        self,
        *,
        dry_run_id: str | None,
        import_batch_id: str | None,
    ) -> MemoryImportBatchModel:
        if not dry_run_id and not import_batch_id:
            raise MemoryImportSessionError("Rollback requires a dry-run id or import batch id.")
        if dry_run_id and import_batch_id:
            raise MemoryImportSessionError("Rollback accepts either dry-run id or import batch id, not both.")
        batch = await self._import_ledger.get_batch(dry_run_id=dry_run_id, import_batch_id=import_batch_id)
        if batch is None:
            raise MemoryImportSessionError("Import batch was not found.", status_code=404)
        return batch

    async def _mark_dry_run_rolled_back(
        self,
        batch: MemoryImportBatchModel,
        total_rolled_back: int,
        rolled_back_at: datetime,
    ) -> None:
        row = await self._db.get(MemoryImportDryRunModel, batch.dry_run_id)
        if row is None:
            return
        row.status = DRY_RUN_STATUS_ROLLED_BACK
        row.metadata_json = {
            **(row.metadata_json or {}),
            "rolled_back_at": rolled_back_at.isoformat(),
            "rolled_back_count": total_rolled_back,
            "transaction_ledger_summary": {
                "version": 2,
                "import_batch_id": batch.id,
                "item_count": batch.transaction_item_count,
                "rolled_back_count": total_rolled_back,
            },
        }

    async def _rollback_integrity_status(self, *, manager: MemoryManager, batch: MemoryImportBatchModel) -> str:
        refs = await manager.list_memory_refs_by_metadata("import_batch_id", batch.id)
        remaining_refs = sum(len(values) for values in refs.values())
        if remaining_refs > 0:
            return "critical"
        items = await self._import_ledger.list_items(batch.id)
        if any(
            item.status in {IMPORT_ITEM_STATUS_CONFLICT, IMPORT_ITEM_STATUS_ROLLBACK_FAILED, IMPORT_ITEM_STATUS_MISSING}
            for item in items
        ):
            return "warning"
        return "ready"

    async def _expire_stale(self) -> None:
        await self._db.execute(
            update(MemoryImportDryRunModel)
            .where(MemoryImportDryRunModel.status == DRY_RUN_STATUS_PENDING)
            .where(MemoryImportDryRunModel.expires_at <= datetime.now(UTC))
            .values(status=DRY_RUN_STATUS_EXPIRED)
        )
        await self._db.commit()


def _as_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _rollback_in_progress(batch: MemoryImportBatchModel) -> bool:
    return (
        batch.status == IMPORT_BATCH_STATUS_ROLLBACK_IN_PROGRESS
        or batch.rollback_status == IMPORT_BATCH_STATUS_ROLLBACK_IN_PROGRESS
    )
