"""
[INPUT]
- myrm_agent_harness.agent.sub_agents.conflict_gate.*
- app.schemas.conflict_gate.*

[OUTPUT]
- ConflictGateService

[POS]
Server 业务层多 Bot 并行产出冲突对账与合并前拦截门服务（Topic 12 · 第 19 项）。
聚合 Harness 层的 ParallelWorkConflictDetector，提供多 Worker 写集碰撞检测、门禁阻断判定与四策略对账解决调度。
"""

from __future__ import annotations

import logging

from myrm_agent_harness.agent.sub_agents.conflict_gate import (
    ParallelWorkConflictDetector,
    ResolutionStrategy,
    WorkConflictItem,
    WriteFingerprint,
    WriteMutationType,
)

from app.schemas.conflict_gate import (
    ConflictGateVerdictResponseDTO,
    ConflictResolveResponseDTO,
    ResolutionStrategyLiteral,
    WorkConflictItemDTO,
    WriteFingerprintDTO,
    WriteMutationTypeLiteral,
)

logger = logging.getLogger(__name__)


class ConflictGateService:
    """Service governing parallel work collision detection and manual/automatic reconciliation."""

    def __init__(self, detector: ParallelWorkConflictDetector | None = None) -> None:
        self._detector = detector or ParallelWorkConflictDetector()

    def evaluate_fingerprints(self, session_id: str, fingerprints: list[WriteFingerprintDTO]) -> ConflictGateVerdictResponseDTO:
        """Evaluate worker write-set fingerprints and return collision gate verdict."""
        domain_fps: list[WriteFingerprint] = []
        for fp in fingerprints:
            mut_type: WriteMutationType = (
                fp.mutation_type if fp.mutation_type in ("file", "artifact", "config", "card") else "file"
            )
            domain_fps.append(
                WriteFingerprint(
                    worker_id=fp.worker_id,
                    resource_id=fp.resource_id,
                    mutation_type=mut_type,
                    content_hash=fp.content_hash,
                    summary=fp.summary,
                    timestamp=fp.timestamp or "",
                )
            )

        verdict = self._detector.evaluate_write_fingerprints(session_id, domain_fps)

        conflicts_dto = [self._to_conflict_dto(c) for c in verdict.conflicts]
        clean_dto = [self._to_fingerprint_dto(cw) for cw in verdict.clean_writes]

        return ConflictGateVerdictResponseDTO(
            session_id=session_id,
            is_blocked=verdict.is_blocked,
            total_conflicts=verdict.total_conflicts,
            conflicts=conflicts_dto,
            clean_writes=clean_dto,
        )

    def get_pending_conflicts(self, session_id: str) -> list[WorkConflictItemDTO]:
        """Fetch all unresolved conflicts for a specific chat session."""
        items = self._detector.get_pending_conflicts(session_id)
        return [self._to_conflict_dto(item) for item in items]

    def resolve_conflict(
        self,
        conflict_id: str,
        strategy: ResolutionStrategyLiteral,
        resolved_content: str | None = None,
    ) -> ConflictResolveResponseDTO:
        """Apply a resolution strategy to reconcile a detected conflict."""
        dom_strat: ResolutionStrategy = strategy
        item = self._detector.resolve_conflict(
            conflict_id=conflict_id,
            strategy=dom_strat,
            resolved_content=resolved_content,
        )

        if not item:
            return ConflictResolveResponseDTO(
                conflict_id=conflict_id,
                success=False,
                message=f"Conflict {conflict_id} not found in pending register",
                conflict=None,
            )

        return ConflictResolveResponseDTO(
            conflict_id=conflict_id,
            success=True,
            message=f"Conflict reconciled successfully via strategy {strategy}",
            conflict=self._to_conflict_dto(item),
        )

    def _to_fingerprint_dto(self, fp: WriteFingerprint) -> WriteFingerprintDTO:
        mut_type: WriteMutationTypeLiteral = (
            fp.mutation_type if fp.mutation_type in ("file", "artifact", "config", "card") else "file"
        )
        return WriteFingerprintDTO(
            worker_id=fp.worker_id,
            resource_id=fp.resource_id,
            mutation_type=mut_type,
            content_hash=fp.content_hash,
            summary=fp.summary,
            timestamp=fp.timestamp,
        )

    def _to_conflict_dto(self, c: WorkConflictItem) -> WorkConflictItemDTO:
        mut_type: WriteMutationTypeLiteral = (
            c.mutation_type if c.mutation_type in ("file", "artifact", "config", "card") else "file"
        )
        strat_val: ResolutionStrategyLiteral | None = (
            c.resolution_strategy
            if c.resolution_strategy in ("keep_worker_a", "keep_worker_b", "three_way_merge", "abort_both")
            else None
        )
        return WorkConflictItemDTO(
            conflict_id=c.conflict_id,
            session_id=c.session_id,
            resource_id=c.resource_id,
            mutation_type=mut_type,
            worker_a=self._to_fingerprint_dto(c.worker_a),
            worker_b=self._to_fingerprint_dto(c.worker_b),
            status=c.status,
            resolution_strategy=strat_val,
            resolved_content=c.resolved_content,
            resolved_at=c.resolved_at,
        )
