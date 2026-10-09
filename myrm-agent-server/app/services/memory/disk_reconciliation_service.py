"""[POS]: app/services/memory/disk_reconciliation_service.py
[INPUT]: Harness reconciliation modules, write gates, and server DTO schemas.
[OUTPUT]: DiskReconciliationService orchestrating bi-directional disk-memory FTS reconciliation and write-gate governance.
"""

from __future__ import annotations

from pathlib import Path

from myrm_agent_harness.toolkits.memory import (
    DiskMemoryFtsReconciler,
    FtsReconciledHit,
    MemoryWriteGate,
    ReconciliationReport,
    WriteGateCheckResult,
    WriteGatePolicy,
)

from app.schemas.disk_reconciliation import (
    FtsReconciledHitDTO,
    ReconciliationReportDTO,
    ReconciliationStatsDTO,
    SetWriteGatePolicyRequestDTO,
    TriggerReconciliationRequestDTO,
    WriteGateCheckResultDTO,
)


class DiskReconciliationService:
    """Business service orchestrating disk-to-FTS synchronization and memory write gate controls."""

    def __init__(
        self,
        db_path: Path | str | None = None,
        default_policy: WriteGatePolicy = WriteGatePolicy.ENABLED,
    ) -> None:
        if db_path is None:
            base_dir = Path("/tmp/myrm_reconciliation_service")
            base_dir.mkdir(parents=True, exist_ok=True)
            self._db_path = base_dir / "reconciliation.db"
        else:
            self._db_path = Path(db_path)

        self._write_gate = MemoryWriteGate(default_policy=default_policy)
        self._reconciler = DiskMemoryFtsReconciler(db_path=self._db_path, write_gate=self._write_gate)

    def trigger_reconciliation(self, request: TriggerReconciliationRequestDTO) -> ReconciliationReportDTO:
        """Runs a bi-directional reconciliation pass over disk directories."""
        roots = [Path(r) for r in request.roots] if request.roots else [Path("/tmp/myrm_memory_notes")]
        report: ReconciliationReport = self._reconciler.reconcile(
            roots=roots,
            session_id=request.session_id,
        )
        return self._report_to_dto(report)

    def check_write_gate(self, session_id: str | None = None) -> WriteGateCheckResultDTO:
        """Evaluates whether writes are permitted globally or for a specific session."""
        check: WriteGateCheckResult = self._write_gate.check_write_allowed(session_id=session_id)
        return WriteGateCheckResultDTO(
            is_allowed=check.is_allowed,
            policy=check.policy.value,
            reason=check.reason,
        )

    def set_write_gate_policy(self, request: SetWriteGatePolicyRequestDTO) -> WriteGateCheckResultDTO:
        """Updates the write gate policy globally or for a specific session."""
        try:
            policy_enum = WriteGatePolicy(request.policy)
        except ValueError as err:
            valid_policies = [p.value for p in WriteGatePolicy]
            raise ValueError(f"Invalid policy '{request.policy}'. Must be one of: {valid_policies}") from err

        if request.session_id:
            self._write_gate.set_session_policy(session_id=request.session_id, policy=policy_enum)
        else:
            self._write_gate.set_global_policy(policy=policy_enum)

        return self.check_write_gate(session_id=request.session_id)

    def clear_session_policy(self, session_id: str) -> None:
        """Clears session override, reverting to the global policy."""
        self._write_gate.clear_session_policy(session_id=session_id)

    def search(self, query: str, limit: int = 20) -> list[FtsReconciledHitDTO]:
        """Executes full-text ranked query across reconciled memory notes."""
        hits: list[FtsReconciledHit] = self._reconciler.search(query=query, limit=limit)
        return [
            FtsReconciledHitDTO(
                file_path=h.file_path,
                title=h.title,
                snippet=h.snippet,
                rank_score=h.rank_score,
            )
            for h in hits
        ]

    def get_stats(self) -> ReconciliationStatsDTO:
        """Computes summary metrics for the reconciliation index and active write policy."""
        count = self._reconciler.get_indexed_count()
        policy = self._write_gate.global_policy.value
        return ReconciliationStatsDTO(
            total_indexed_files=count,
            global_write_policy=policy,
        )

    @staticmethod
    def _report_to_dto(report: ReconciliationReport) -> ReconciliationReportDTO:
        return ReconciliationReportDTO(
            reconcile_id=report.reconcile_id,
            scanned_disk_files_count=report.scanned_disk_files_count,
            indexed_or_updated_count=report.indexed_or_updated_count,
            pruned_dead_rows_count=report.pruned_dead_rows_count,
            duration_ms=report.duration_ms,
            status=report.status,
            created_at=report.created_at,
        )


_reconciliation_service_instance: DiskReconciliationService | None = None


def get_disk_reconciliation_service() -> DiskReconciliationService:
    """Dependency provider for DiskReconciliationService."""
    global _reconciliation_service_instance
    if _reconciliation_service_instance is None:
        _reconciliation_service_instance = DiskReconciliationService()
    return _reconciliation_service_instance
