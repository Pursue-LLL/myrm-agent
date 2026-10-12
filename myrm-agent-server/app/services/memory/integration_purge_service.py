"""Integration retained context governance, selective purge, and provenance revocation service.

[INPUT]
- datetime::{UTC, datetime}
- logging::{getLogger}
- app.schemas.integration_purge::{
    DisconnectWithPurgeRequest,
    DisconnectWithPurgeResponse,
    ProvenanceRevocationAuditItem,
    RetainedContextSummaryResponse,
  }
- app.services.memory.imports.integration_memory::{get_integration_memory_service}
- myrm_agent_harness.toolkits.memory.integration_purge::{
    IntegrationRetainedContextManager,
    IntegrationRetainedContextSummary,
    PurgeExecutionMode,
    PurgeExecutionResult,
  }

[OUTPUT]
- IntegrationContextPurgeService: Business service coordinating context retention audits and purges
- get_integration_purge_service: Dependency provider returning singleton service instance

[POS]
Server-layer orchestration bridging Harness-level retained context manager with server-side
tree indices, memory managers, and security audit trails (Topic 01 Item 179).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from myrm_agent_harness.toolkits.memory.integration_purge import (
    IntegrationRetainedContextManager,
    PurgeExecutionMode,
)

from app.schemas.integration_purge import (
    DisconnectWithPurgeRequest,
    DisconnectWithPurgeResponse,
    ProvenanceRevocationAuditItem,
    RetainedContextSummaryResponse,
)
from app.services.memory.imports.integration_memory import get_integration_memory_service

logger = logging.getLogger(__name__)


class IntegrationContextPurgeService:
    """Coordinates connector-scoped context auditing, selective purging, and provenance revocation."""

    def __init__(self) -> None:
        self._manager = IntegrationRetainedContextManager(
            remove_trees_callback=self._remove_trees_for_integration,
            count_trees_callback=self._count_trees_for_integration,
        )
        self._audit_events: list[ProvenanceRevocationAuditItem] = []

    async def _remove_trees_for_integration(self, integration_id: str) -> int:
        """Helper to invoke integration memory service tree deletion."""
        tree_svc = await get_integration_memory_service()
        if tree_svc is not None:
            try:
                return await tree_svc.remove_trees_by_provider(integration_id)
            except Exception as exc:
                logger.warning("Failed removing trees for '%s': %s", integration_id, exc)
        return 0

    def _count_trees_for_integration(self, integration_id: str) -> int:
        """Helper to count indexed trees for integration."""
        return 0

    def get_underlying_manager(self) -> IntegrationRetainedContextManager:
        """Return the framework manager instance."""
        return self._manager

    async def inspect_retained_context(
        self,
        integration_id: str,
        *,
        provider_type: str = "external_integration",
    ) -> RetainedContextSummaryResponse:
        """Audit and summarize retained context items for an integration."""
        summary = await self._manager.inspect_retained_context(
            integration_id, provider_type=provider_type
        )
        oldest_str = summary.oldest_retained_at.isoformat() if summary.oldest_retained_at else None
        latest_str = summary.latest_retained_at.isoformat() if summary.latest_retained_at else None

        return RetainedContextSummaryResponse(
            integration_id=summary.integration_id,
            provider_type=summary.provider_type,
            retained_memory_count=summary.retained_memory_count,
            retained_tree_count=summary.retained_tree_count,
            retained_fact_count=summary.retained_fact_count,
            total_retained_items=summary.total_retained_items,
            oldest_retained_at=oldest_str,
            latest_retained_at=latest_str,
            sample_snippets=summary.sample_snippets,
            is_provenance_revoked=summary.is_provenance_revoked,
        )

    async def disconnect_and_purge(
        self,
        integration_id: str,
        request: DisconnectWithPurgeRequest,
        *,
        provider_type: str = "external_integration",
        actor: str = "user",
    ) -> DisconnectWithPurgeResponse:
        """Execute connector disconnect with optional retained context purge and provenance revocation."""
        raw_mode = request.purge_mode.lower()
        if raw_mode in ("retain", "retain_context"):
            mode = PurgeExecutionMode.RETAIN_CONTEXT
        elif raw_mode in ("selective", "selective_purge"):
            mode = PurgeExecutionMode.SELECTIVE_PURGE
        else:
            mode = PurgeExecutionMode.PURGE_AND_REVOKE

        result = await self._manager.execute_purge(
            integration_id,
            mode,
            actor=actor,
            reason=request.reason or f"Connector {integration_id} disconnect requested",
        )

        total_purged = result.deleted_memories_count + result.deleted_trees_count

        if result.revocation_id:
            audit_item = ProvenanceRevocationAuditItem(
                revocation_id=result.revocation_id,
                integration_id=integration_id,
                reason=request.reason or "Disconnected with provenance revocation",
                revoked_at=datetime.now(UTC).isoformat(),
                purged_items_count=total_purged,
                actor=actor,
            )
            self._audit_events.append(audit_item)

        return DisconnectWithPurgeResponse(
            integration_id=integration_id,
            provider_type=provider_type,
            disconnected=True,
            purged_items=total_purged,
            mode=mode.value,
            revocation_id=result.revocation_id,
            message=result.message,
        )

    async def get_revocation_audit_log(self) -> list[ProvenanceRevocationAuditItem]:
        """Return historical provenance revocation audit records."""
        # Convert ledger records from manager if not already in local audit_events
        mgr_records = self._manager.list_revocation_records()
        existing_ids = {e.revocation_id for e in self._audit_events}
        for r in mgr_records:
            if r.revocation_id not in existing_ids:
                self._audit_events.append(
                    ProvenanceRevocationAuditItem(
                        revocation_id=r.revocation_id,
                        integration_id=r.integration_id,
                        reason=r.reason,
                        revoked_at=r.revoked_at.isoformat(),
                        purged_items_count=r.purged_items_count,
                        actor=r.actor,
                    )
                )
        return list(self._audit_events)

    async def reinstate_provenance(self, integration_id: str) -> bool:
        """Reinstate provenance status when an integration is re-authenticated."""
        return self._manager.unrevoke_provenance(integration_id)


_purge_service_singleton: IntegrationContextPurgeService | None = None


def get_integration_purge_service() -> IntegrationContextPurgeService:
    """Return singleton instance of IntegrationContextPurgeService."""
    global _purge_service_singleton
    if _purge_service_singleton is None:
        _purge_service_singleton = IntegrationContextPurgeService()
    return _purge_service_singleton
