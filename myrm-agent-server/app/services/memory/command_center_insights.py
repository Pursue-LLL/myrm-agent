"""Memory command center insight builders.

[INPUT]
myrm_agent_harness.toolkits.memory::MemoryManager (POS: Unified memory manager and core facade)
myrm_agent_harness.toolkits.memory::get_scan_metrics (POS: Global security scan metrics singleton)
myrm_agent_harness.toolkits.memory::get_search_metrics (POS: Global search quality metrics singleton)
app.database.models.chat::Message (POS: 会话消息 ORM)
app.services.memory.operation_ledger::MemoryOperationLedgerService (POS: 记忆操作账本服务)

[OUTPUT]
MemoryCommandCenterInsights: influence, cost, conflict, replay, eval, privacy, and migration projections.

[POS]
个人大脑指挥中心洞察服务。把可解释性、成本、冲突、回放覆盖层、eval、隐私与迁移投影从主聚合服务中拆出，保持单一职责。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Literal

from myrm_agent_harness.toolkits.memory import MemoryManager, MemoryType, get_scan_metrics, get_search_metrics
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.chat import Message
from app.schemas.memory.command_center import (
    MemoryCommandConflictItem,
    MemoryCommandConnectorStatus,
    MemoryCommandCostProfile,
    MemoryCommandEvalMetric,
    MemoryCommandInfluenceItem,
    MemoryCommandInfluenceRef,
    MemoryCommandMigrationProvenance,
    MemoryCommandPlaneSummary,
    MemoryCommandPrivacySignal,
    MemoryCommandReplayEvent,
    MemoryCommandReplayOverlay,
    MemoryCommandTimelineEvent,
    MemoryCommandWaterfallStep,
)
from app.services.memory.archive_restore import ArchiveRestoreHealth
from app.services.memory.command_center_projection_utils import (
    WATERFALL_PHASES,
    WaterfallPhase,
    dict_int,
    eval_metric,
    event_phase,
    optional_float,
    optional_str,
    preview_content,
    waterfall_description,
    waterfall_phase,
    waterfall_status,
)
from app.services.memory.import_adapter_registry import memory_import_adapter_status, memory_import_supported_sources
from app.services.memory.import_ledger import ImportRollbackHealth
from app.services.memory.import_sessions import (
    DRY_RUN_RETENTION_DAYS,
    DRY_RUN_STATUS_CONFIRMED,
    DRY_RUN_STATUS_EXPIRED,
    DRY_RUN_STATUS_PENDING,
    DRY_RUN_STATUS_ROLLED_BACK,
    MemoryImportSessionService,
)
from app.services.memory.operation_ledger import MemoryOperationLedgerService

logger = logging.getLogger(__name__)


class MemoryCommandCenterInsights:
    """Builds derived command-center insight sections."""

    def __init__(
        self,
        db: AsyncSession,
        memory_manager: MemoryManager,
        ledger: MemoryOperationLedgerService,
    ) -> None:
        self._db = db
        self._memory_manager = memory_manager
        self._ledger = ledger

    async def build_influence(self) -> list[MemoryCommandInfluenceItem]:
        result = await self._db.execute(
            select(Message).where(Message.extra_data.is_not(None)).order_by(desc(Message.created_at)).limit(40)
        )
        items: list[MemoryCommandInfluenceItem] = []
        for message in result.scalars().all():
            extra_data = message.extra_data or {}
            refs = self._extract_influence_refs(extra_data)
            if not refs:
                continue
            prompt_tokens, cached_tokens, _completion_tokens = self._extract_token_counts(extra_data)
            items.append(
                MemoryCommandInfluenceItem(
                    id=f"message:{message.id}",
                    chat_id=message.chat_id,
                    message_id=message.id,
                    occurred_at=message.created_at,
                    answer_preview=preview_content(message.content, limit=220),
                    influence_refs=refs,
                    prompt_tokens=prompt_tokens,
                    cached_tokens=cached_tokens,
                )
            )
            if len(items) >= 8:
                break
        return items

    async def build_cost_profile(self, influence: list[MemoryCommandInfluenceItem]) -> MemoryCommandCostProfile:
        result = await self._db.execute(
            select(Message).where(Message.extra_data.is_not(None)).order_by(desc(Message.created_at)).limit(50)
        )
        prompt_tokens = 0
        cached_tokens = 0
        completion_tokens = 0
        cited_memory_refs = 0
        for message in result.scalars().all():
            extra_data = message.extra_data or {}
            prompt, cached, completion = self._extract_token_counts(extra_data)
            prompt_tokens += prompt
            cached_tokens += cached
            completion_tokens += completion
            cited_memory_refs += len(self._extract_influence_refs(extra_data))
        estimated_memory_tokens = sum(len(ref.content_preview.split()) for item in influence for ref in item.influence_refs)
        return MemoryCommandCostProfile(
            prompt_tokens=prompt_tokens,
            cached_tokens=cached_tokens,
            completion_tokens=completion_tokens,
            cited_memory_refs=cited_memory_refs,
            estimated_memory_tokens=estimated_memory_tokens,
            cache_friendly=cached_tokens > 0 or estimated_memory_tokens <= 300,
        )

    async def build_conflicts(self) -> list[MemoryCommandConflictItem]:
        items: list[MemoryCommandConflictItem] = []
        for memory_type in (MemoryType.SEMANTIC, MemoryType.CLAIM):
            try:
                memories = await self._memory_manager.list_memories(memory_type, limit=80)
            except Exception as exc:
                logger.warning("Memory conflict scan failed for %s: %s", memory_type.value, exc)
                continue
            for memory in memories:
                corrected = bool(memory.metadata.get("corrected")) if hasattr(memory, "metadata") else False
                correction_of = getattr(memory, "correction_of", None)
                if correction_of:
                    items.append(
                        MemoryCommandConflictItem(
                            id=f"correction:{memory.id}",
                            kind="correction",
                            status="resolved",
                            memory_id=memory.id,
                            related_memory_id=str(correction_of),
                            title=memory_type.value,
                            description=preview_content(memory.content),
                            created_at=getattr(memory, "created_at", None),
                        )
                    )
                elif corrected:
                    items.append(
                        MemoryCommandConflictItem(
                            id=f"superseded:{memory.id}",
                            kind="supersession",
                            status="resolved",
                            memory_id=memory.id,
                            title=memory_type.value,
                            description=preview_content(memory.content),
                            created_at=getattr(memory, "created_at", None),
                        )
                    )
                elif memory_type == MemoryType.CLAIM:
                    items.append(
                        MemoryCommandConflictItem(
                            id=f"claim:{memory.id}",
                            kind="claim",
                            status="active",
                            memory_id=memory.id,
                            title=memory_type.value,
                            description=preview_content(memory.content),
                            created_at=getattr(memory, "created_at", None),
                        )
                    )
                if len(items) >= 8:
                    return items
        return items

    async def build_replay(
        self,
        timeline: list[MemoryCommandTimelineEvent],
        influence: list[MemoryCommandInfluenceItem],
    ) -> list[MemoryCommandReplayOverlay]:
        overlays: dict[str, MemoryCommandReplayOverlay] = {}
        for item in influence:
            if not item.chat_id:
                continue
            overlays[item.chat_id] = MemoryCommandReplayOverlay(
                chat_id=item.chat_id,
                message_id=item.message_id,
                event_count=1,
                influence_count=len(item.influence_refs),
                last_event_at=item.occurred_at,
                last_summary=item.answer_preview,
            )
        for event in timeline:
            if event.target_kind != "chat" or not event.target_id:
                continue
            current = overlays.get(event.target_id)
            if current is None:
                overlays[event.target_id] = MemoryCommandReplayOverlay(
                    chat_id=event.target_id,
                    message_id=None,
                    event_count=1,
                    influence_count=event.influence_count,
                    last_event_at=event.occurred_at,
                    last_summary=event.description,
                )
                continue
            overlays[event.target_id] = current.model_copy(
                update={
                    "event_count": current.event_count + 1,
                    "influence_count": current.influence_count + event.influence_count,
                    "last_event_at": max(current.last_event_at, event.occurred_at),
                }
            )
        return sorted(overlays.values(), key=lambda item: item.last_event_at, reverse=True)[:8]

    def build_replay_events(self, timeline: list[MemoryCommandTimelineEvent]) -> list[MemoryCommandReplayEvent]:
        return [
            MemoryCommandReplayEvent(
                id=event.id,
                phase=event_phase(event.kind),
                status=event.status,
                occurred_at=event.occurred_at,
                title=event.title,
                summary=event.description,
                target_kind=event.target_kind,
                target_id=event.target_id,
                influence_count=event.influence_count,
            )
            for event in timeline[:24]
        ]

    def build_waterfall(
        self,
        timeline: list[MemoryCommandTimelineEvent],
        influence: list[MemoryCommandInfluenceItem],
        cost: MemoryCommandCostProfile,
    ) -> list[MemoryCommandWaterfallStep]:
        counts: dict[WaterfallPhase, int] = {}
        latest: dict[WaterfallPhase, datetime] = {}
        for event in timeline:
            phase = waterfall_phase(event.kind)
            counts[phase] = counts.get(phase, 0) + 1
            latest[phase] = event.occurred_at
        recall_count = sum(len(item.influence_refs) for item in influence)
        if recall_count:
            counts["recall"] = max(counts.get("recall", 0), recall_count)
            counts["cite"] = max(counts.get("cite", 0), recall_count)
        if cost.estimated_memory_tokens:
            counts["inject"] = max(counts.get("inject", 0), 1)

        return [
            MemoryCommandWaterfallStep(
                phase=phase,
                status=waterfall_status(phase, counts.get(phase, 0)),
                event_count=counts.get(phase, 0),
                evidence_count=recall_count if phase in {"recall", "cite"} else 0,
                latest_at=latest.get(phase),
                description=waterfall_description(phase, counts.get(phase, 0)),
            )
            for phase in WATERFALL_PHASES
        ]

    def build_eval_metrics(
        self,
        *,
        timeline: list[MemoryCommandTimelineEvent],
        influence: list[MemoryCommandInfluenceItem],
        conflicts: list[MemoryCommandConflictItem],
        migration: MemoryCommandMigrationProvenance,
    ) -> list[MemoryCommandEvalMetric]:
        event_count = len(timeline)
        influence_count = sum(len(item.influence_refs) for item in influence)
        resolved_conflicts = sum(1 for item in conflicts if item.status == "resolved")

        search_snap = get_search_metrics().snapshot()
        cs_hits = search_snap.cross_session_hits
        sourced_total = search_snap.total_sourced_hits
        cs_pct = round(search_snap.cross_session_hit_rate * 100)

        return [
            eval_metric("event_coverage", event_count > 0, event_count >= 10, f"{event_count} memory events are visible."),
            eval_metric(
                "influence_coverage",
                influence_count > 0,
                influence_count >= 5,
                f"{influence_count} cited memory references are attached to answers.",
            ),
            eval_metric(
                "conflict_governance",
                bool(conflicts),
                resolved_conflicts == len(conflicts) and bool(conflicts),
                f"{resolved_conflicts}/{len(conflicts)} visible conflicts are resolved.",
            ),
            eval_metric(
                "migration_readiness",
                migration.coverage_status != "not_tracked",
                migration.coverage_status == "complete",
                f"{migration.tracked_imports} imported memories, {migration.unmapped_items} unmapped items.",
            ),
            eval_metric(
                "cross_session_transfer",
                cs_hits > 0,
                cs_hits >= 5,
                f"{cs_pct}% of recalled memories come from previous conversations ({cs_hits} cross-session hits out of {sourced_total} sourced results).",
            ),
        ]

    @staticmethod
    def build_connectors() -> list[MemoryCommandConnectorStatus]:
        from app.services.connect import PROFILES, ConnectorStatus, get_connect_service

        service = get_connect_service()
        states = {s.profile_id: s for s in service.list_all_states()}
        result: list[MemoryCommandConnectorStatus] = []

        status_map = {
            ConnectorStatus.READY: "ready",
            ConnectorStatus.CONFIGURED: "manual_config_required",
            ConnectorStatus.MISSING: "missing",
        }

        for profile in PROFILES.values():
            state = states.get(profile.id)
            status = status_map.get(state.status if state else ConnectorStatus.MISSING, "missing")
            result.append(
                MemoryCommandConnectorStatus(
                    id=profile.id,
                    label=profile.label,
                    status=status,
                    supported_actions=["generate_config", "doctor", "revoke"],
                    notes=profile.description,
                )
            )
        return result

    @staticmethod
    def build_privacy_signals(timeline: list[MemoryCommandTimelineEvent]) -> list[MemoryCommandPrivacySignal]:
        warning_count = sum(1 for event in timeline if event.status in {"warning", "error"})

        scan = get_scan_metrics().snapshot()
        security_events = scan.blocked + scan.redacted
        if scan.total_scans == 0:
            redaction_status: Literal["ready", "warning", "missing"] = "missing"
        else:
            redaction_status = "warning" if security_events > 0 else "ready"

        return [
            MemoryCommandPrivacySignal(
                id="approval_gate",
                label="Approval-gated writes",
                status="ready",
                evidence="Pending memories and shared-context proposals are actioned through the governance inbox.",
                event_count=sum(1 for event in timeline if event.kind in {"approve", "reject"}),
            ),
            MemoryCommandPrivacySignal(
                id="sensitive_event_visibility",
                label="Sensitive event visibility",
                status="warning" if warning_count else "ready",
                evidence=f"{warning_count} warning or error events are visible in the memory ledger.",
                event_count=warning_count,
            ),
            MemoryCommandPrivacySignal(
                id="secret_redaction",
                label="Secret redaction evidence",
                status=redaction_status,
                evidence=f"{security_events} blocked or redacted events out of {scan.total_scans} scans.",
                event_count=security_events,
            ),
        ]

    @staticmethod
    def build_plane_summary(
        *,
        health_status: str,
        storage_mode: str,
        timeline: list[MemoryCommandTimelineEvent],
        governance_backlog: int,
        import_rollback_health: ImportRollbackHealth,
        archive_restore_health: ArchiveRestoreHealth,
    ) -> MemoryCommandPlaneSummary:
        failed_count = sum(1 for event in timeline if event.status in {"warning", "error"})
        last_event = max((event.occurred_at for event in timeline), default=None)
        return MemoryCommandPlaneSummary(
            enabled=True,
            content_visibility="not_shared",
            health_status=health_status,
            import_rollback_health_status=import_rollback_health.status,
            archive_restore_health_status=archive_restore_health.status,
            event_count=len(timeline),
            failed_event_count=failed_count,
            queue_backlog=governance_backlog,
            import_rollback_in_progress=import_rollback_health.in_progress_batches,
            import_rollback_failed=import_rollback_health.failed_batches,
            import_rollback_partial=import_rollback_health.partial_batches,
            import_rollback_missing_items=import_rollback_health.missing_items,
            import_rollback_failed_items=import_rollback_health.failed_items,
            archive_restore_in_progress=archive_restore_health.in_progress_batches,
            archive_restore_failed=archive_restore_health.failed_batches,
            archive_restore_partial=archive_restore_health.partial_batches,
            archive_restore_rollback_in_progress=archive_restore_health.rollback_in_progress_batches,
            archive_restore_rollback_failed=archive_restore_health.rollback_failed_batches,
            archive_restore_missing_items=archive_restore_health.missing_items,
            archive_restore_failed_items=archive_restore_health.failed_items,
            storage_mode=storage_mode,
            last_event_at=last_event,
            redaction_scope="metadata_only",
            sandbox_isolation="local_or_per_user_sandbox",
        )

    async def build_migration(self) -> MemoryCommandMigrationProvenance:
        tracked, unmapped, raw_coverage = await self._ledger.migration_summary()
        latest = await self._ledger.latest_migration()
        latest_metadata = latest.metadata_json if latest and isinstance(latest.metadata_json, dict) else {}
        raw_batch_id = latest_metadata.get("import_batch_id")
        raw_diagnostic_status = latest_metadata.get("diagnostic_status")
        raw_diagnostic_run_id = latest_metadata.get("diagnostic_run_id")
        session_metrics = await MemoryImportSessionService(self._db).session_metrics()
        coverage = raw_coverage if raw_coverage in {"not_tracked", "partial", "complete"} else "not_tracked"
        return MemoryCommandMigrationProvenance(
            supported_sources=memory_import_supported_sources(),
            tracked_imports=tracked,
            unmapped_items=unmapped,
            coverage_status=coverage,
            adapter_status=memory_import_adapter_status(),
            last_import_batch_id=raw_batch_id if isinstance(raw_batch_id, str) else None,
            verification_recommended=tracked > 0 and raw_diagnostic_status != "ready",
            last_import_diagnostic_status=raw_diagnostic_status if isinstance(raw_diagnostic_status, str) else None,
            last_import_diagnostic_run_id=raw_diagnostic_run_id if isinstance(raw_diagnostic_run_id, str) else None,
            cleanup_pending_sessions=session_metrics.get(DRY_RUN_STATUS_PENDING, 0),
            cleanup_confirmed_sessions=session_metrics.get(DRY_RUN_STATUS_CONFIRMED, 0),
            cleanup_expired_sessions=session_metrics.get(DRY_RUN_STATUS_EXPIRED, 0),
            cleanup_rolled_back_sessions=session_metrics.get(DRY_RUN_STATUS_ROLLED_BACK, 0),
            cleanup_retention_days=DRY_RUN_RETENTION_DAYS,
        )

    @staticmethod
    def _extract_influence_refs(extra_data: dict[str, object]) -> list[MemoryCommandInfluenceRef]:
        raw_refs = extra_data.get("citedMemoryRefs")
        if not isinstance(raw_refs, list):
            return []
        refs: list[MemoryCommandInfluenceRef] = []
        for raw_ref in raw_refs:
            if not isinstance(raw_ref, dict):
                continue
            memory_id = raw_ref.get("id")
            memory_type = raw_ref.get("memory_type")
            if not isinstance(memory_id, str) or not isinstance(memory_type, str):
                continue
            primary_namespace = optional_str(raw_ref.get("primary_namespace"))
            raw_namespaces = raw_ref.get("namespaces")
            if primary_namespace is None and isinstance(raw_namespaces, list) and raw_namespaces:
                primary_namespace = optional_str(raw_namespaces[0])
            refs.append(
                MemoryCommandInfluenceRef(
                    memory_id=memory_id,
                    memory_type=memory_type,
                    score=optional_float(raw_ref.get("score")),
                    content_preview=preview_content(str(raw_ref.get("content") or ""), limit=180),
                    primary_namespace=primary_namespace,
                    source_chat_id=optional_str(raw_ref.get("source_chat_id")),
                    source_message_id=optional_str(raw_ref.get("source_message_id")),
                    reason="memory_recall_tool",
                )
            )
        return refs

    @staticmethod
    def _extract_token_counts(extra_data: dict[str, object]) -> tuple[int, int, int]:
        usage = extra_data.get("usage")
        token_economics = extra_data.get("tokenEconomics")
        context_budget = extra_data.get("contextBudget")
        prompt_tokens = dict_int(usage, "prompt_tokens") + dict_int(token_economics, "prompt_tokens")
        cached_tokens = dict_int(usage, "cached_tokens") + dict_int(token_economics, "cached_tokens")
        completion_tokens = dict_int(usage, "completion_tokens") + dict_int(token_economics, "completion_tokens")
        if prompt_tokens == 0:
            prompt_tokens = dict_int(context_budget, "used_tokens")
        return (prompt_tokens, cached_tokens, completion_tokens)
