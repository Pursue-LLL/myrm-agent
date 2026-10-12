"""Business service for Auto Memory Staleness Decay and Consolidation Audit Suite (Item 158).

[INPUT]
- RegisterMemoryRequest, TouchRecallRequest, RunAuditRequest, ApplyConsolidationRequest, and ArchiveMemoriesRequest.

[OUTPUT]
- MemoryItemProfileDTO, MemoryAuditReportDTO, and status update payloads.

[POS]
- Service layer in myrm-agent-server/app/services/memory/staleness_consolidation_service.py.
"""

from __future__ import annotations

from app.schemas.staleness_consolidation import (
    ApplyConsolidationRequest,
    ArchiveMemoriesRequest,
    ConsolidationProposalDTO,
    MemoryAuditReportDTO,
    MemoryItemProfileDTO,
    MemoryStatusDTO,
    RegisterMemoryRequest,
    RepoAssertionCheckResultDTO,
    RunAuditRequest,
    TouchRecallRequest,
)
from myrm_agent_harness.toolkits.memory.staleness_consolidation import (
    AutoMemoryStalenessAndConsolidationAuditSuite,
    ConsolidationProposal,
    MemoryAuditReport,
    MemoryItemProfile,
    RepoAssertionCheckResult,
)


class StalenessConsolidationService:
    """Coordinates memory staleness calculation, codebase validity checks, and consolidation."""

    def __init__(
        self,
        audit_suite: AutoMemoryStalenessAndConsolidationAuditSuite | None = None,
    ) -> None:
        self.suite = audit_suite or AutoMemoryStalenessAndConsolidationAuditSuite()

    @staticmethod
    def _profile_to_dto(item: MemoryItemProfile) -> MemoryItemProfileDTO:
        return MemoryItemProfileDTO(
            memory_id=item.memory_id,
            content=item.content,
            category=item.category,
            created_at=item.created_at,
            last_recalled_at=item.last_recalled_at,
            recalled_count=item.recalled_count,
            staleness_score=item.staleness_score,
            status=item.status,
            referenced_paths=list(item.referenced_paths),
            referenced_assertions=list(item.referenced_assertions),
            invalidation_reason=item.invalidation_reason,
            subsumed_by_id=item.subsumed_by_id,
        )

    @staticmethod
    def _report_to_dto(report: MemoryAuditReport) -> MemoryAuditReportDTO:
        return MemoryAuditReportDTO(
            total_items=report.total_items,
            active_items=report.active_items,
            stale_items=report.stale_items,
            invalidated_items=report.invalidated_items,
            consolidated_items=report.consolidated_items,
            archived_items=report.archived_items,
            average_staleness=report.average_staleness,
            invalidated_results=[
                RepoAssertionCheckResultDTO(
                    memory_id=r.memory_id,
                    is_valid=r.is_valid,
                    missing_paths=list(r.missing_paths),
                    failed_assertions=list(r.failed_assertions),
                    diagnostic=r.diagnostic,
                )
                for r in report.invalidated_results
            ],
            consolidation_proposals=[
                ConsolidationProposalDTO(
                    proposal_id=p.proposal_id,
                    source_memory_ids=list(p.source_memory_ids),
                    category=p.category,
                    proposed_content=p.proposed_content,
                    rationale=p.rationale,
                )
                for p in report.consolidation_proposals
            ],
            generated_at=report.generated_at,
        )

    def register_memory(self, req: RegisterMemoryRequest) -> MemoryItemProfileDTO:
        """Register a new memory record into the staleness tracking suite."""
        item = MemoryItemProfile(
            memory_id=req.memory_id,
            content=req.content,
            category=req.category,
            created_at=req.created_at,
            referenced_paths=list(req.referenced_paths),
            referenced_assertions=list(req.referenced_assertions),
        )
        saved = self.suite.register_memory(item)
        return self._profile_to_dto(saved)

    def get_memory(self, memory_id: str) -> MemoryItemProfileDTO | None:
        """Fetch an individual memory profile by ID."""
        item = self.suite.get_memory(memory_id)
        if item is None:
            return None
        return self._profile_to_dto(item)

    def list_memories(
        self,
        status: MemoryStatusDTO | None = None,
    ) -> list[MemoryItemProfileDTO]:
        """List memory profiles optionally filtered by status."""
        items = self.suite.list_memories(status=status)
        return [self._profile_to_dto(it) for it in items]

    def touch_recall(self, req: TouchRecallRequest) -> MemoryItemProfileDTO | None:
        """Record recall touch to reset elapsed time and increment frequency."""
        updated = self.suite.touch_recall(req.memory_id, now_iso=req.now_iso)
        if updated is None:
            return None
        return self._profile_to_dto(updated)

    def run_audit(self, req: RunAuditRequest) -> MemoryAuditReportDTO:
        """Run an end-to-end memory health audit and return full report."""
        report = self.suite.generate_audit_report(
            workspace_dir=req.workspace_dir, now_iso=req.now_iso
        )
        return self._report_to_dto(report)

    def apply_consolidation(
        self, req: ApplyConsolidationRequest
    ) -> MemoryItemProfileDTO | None:
        """Approve and execute a consolidation proposal."""
        new_item = self.suite.apply_consolidation(
            req.proposal_id, now_iso=req.now_iso
        )
        if new_item is None:
            return None
        return self._profile_to_dto(new_item)

    def archive_memories(self, req: ArchiveMemoriesRequest) -> list[str]:
        """Safely move stale or invalidated memories to archived state."""
        return self.suite.archive_memories(req.memory_ids)
