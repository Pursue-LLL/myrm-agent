"""[INPUT]
- .base (POS: 共享类型、常量与状态)

[OUTPUT]
- ReadinessMixin: 诊断、就绪复核与首轮结果保存

[POS]
`import_sessions/` 的导入后就绪诊断阶段。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import desc, select

from app.database.models.memory import MemoryImportDryRunModel
from app.schemas.memory.archive import MemoryImportReadiness

from .base import (
    ImportReadinessRecheckFacts,
    MemoryImportSessionBase,
    MemoryImportSessionError,
)


class ReadinessMixin(MemoryImportSessionBase):
    """诊断、就绪复核与首轮结果保存。"""

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

        from app.services.memory.imports.readiness import build_import_readiness
        from app.services.migration.source.source_secrets_importer import external_source_providers_configured

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
