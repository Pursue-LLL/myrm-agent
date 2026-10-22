"""[INPUT] StartReviewLoopRequest, AdvanceReviewLoopRequest, session_id, loop_id.
[OUTPUT] ReviewLoopResponse, ReviewLoopListResponse managing Tri-Perspective reviews and bounded self-healing iterations.
[POS] Service layer for Multi-Perspective Parallel Subagent Review & Bounded Review Loop (Item 32).
"""

from __future__ import annotations

import logging
import threading
import uuid
from typing import Dict, Optional

from myrm_agent_harness.agent.sub_agents.review_loop import (
    MultiPerspectiveReviewPipeline,
    PerspectiveReviewReport,
    ReviewFinding,
    ReviewPerspective,
)

from app.schemas.review_loop import (
    AdvanceReviewLoopRequest,
    FindingSeverityEnum,
    LoopRoundDTO,
    PerspectiveReportDTO,
    ReviewFindingDTO,
    ReviewLoopListResponse,
    ReviewLoopResponse,
    ReviewLoopStatusEnum,
    ReviewPerspectiveEnum,
    StartReviewLoopRequest,
)

logger = logging.getLogger(__name__)


def _to_finding_dto(f: ReviewFinding) -> ReviewFindingDTO:
    return ReviewFindingDTO(
        perspective=ReviewPerspectiveEnum(f.perspective.value),
        severity=FindingSeverityEnum(f.severity.value),
        file_path=f.file_path,
        issue=f.issue,
        suggestion=f.suggestion,
        line_number=f.line_number,
    )


def _to_report_dto(r: PerspectiveReviewReport) -> PerspectiveReportDTO:
    return PerspectiveReportDTO(
        perspective=ReviewPerspectiveEnum(r.perspective.value),
        reviewer_name=r.reviewer_name,
        approved=r.approved,
        findings=[_to_finding_dto(f) for f in r.findings],
        summary=r.summary,
    )


class _ReviewLoopState:
    """Internal mutable tracking state for an active review loop."""

    def __init__(
        self,
        loop_id: str,
        session_id: str,
        context_description: str | None,
        max_rounds: int,
    ) -> None:
        self.loop_id = loop_id
        self.session_id = session_id
        self.context_description = context_description
        self.max_rounds = max_rounds
        self.status = ReviewLoopStatusEnum.IN_REVIEW
        self.current_diff: str = ""
        self.rounds: list[LoopRoundDTO] = []
        self.is_clean = False
        self.final_summary = ""

    def to_response(self) -> ReviewLoopResponse:
        return ReviewLoopResponse(
            loop_id=self.loop_id,
            session_id=self.session_id,
            status=self.status,
            current_round=len(self.rounds),
            max_rounds=self.max_rounds,
            is_clean=self.is_clean,
            rounds=list(self.rounds),
            final_summary=self.final_summary,
        )


class ReviewLoopService:
    """Session-isolated coordinator managing multi-perspective review loops and bounded self-healing."""

    def __init__(self, pipeline: MultiPerspectiveReviewPipeline | None = None) -> None:
        self._lock = threading.Lock()
        self._pipeline = pipeline or MultiPerspectiveReviewPipeline()
        self._loops: Dict[str, Dict[str, _ReviewLoopState]] = {}

    def start_review_loop(self, req: StartReviewLoopRequest) -> ReviewLoopResponse:
        """Initialize a new review loop and execute Round 1 across all three perspectives."""
        loop_id = f"loop_{uuid.uuid4().hex[:12]}"
        state = _ReviewLoopState(
            loop_id=loop_id,
            session_id=req.session_id,
            context_description=req.context_description,
            max_rounds=req.max_rounds,
        )
        state.current_diff = req.diff_content

        # Run Round 1
        reports = self._pipeline.run_parallel_review(
            diff=req.diff_content,
            context=req.context_description,
        )
        all_findings = self._pipeline.aggregate_findings(reports)
        has_blocking = self._pipeline.has_blocking_issues(all_findings)

        round_dto = LoopRoundDTO(
            round_number=1,
            perspective_reports={
                p.value: _to_report_dto(reports[p])
                for p in ReviewPerspective
                if p in reports
            },
            all_findings=[_to_finding_dto(f) for f in all_findings],
            has_blocking_issues=has_blocking,
            fix_description=None,
            converged=not has_blocking,
        )
        state.rounds.append(round_dto)

        if not has_blocking:
            state.status = ReviewLoopStatusEnum.CONVERGED
            state.is_clean = True
            state.final_summary = "Review loop successfully converged in Round 1 with 0 blocking issues."
        elif req.max_rounds == 1:
            state.status = ReviewLoopStatusEnum.MAX_ROUNDS_REACHED
            state.is_clean = False
            state.final_summary = "Reached maximum allowed rounds (1) with unresolved blocking issues."
        else:
            state.status = ReviewLoopStatusEnum.IN_REVIEW
            state.is_clean = False
            state.final_summary = f"Round 1 discovered {len(all_findings)} issues needing remediation."

        with self._lock:
            if req.session_id not in self._loops:
                self._loops[req.session_id] = {}
            self._loops[req.session_id][loop_id] = state

        logger.info(
            "Review loop '%s' started for session %s (status=%s, clean=%s)",
            loop_id,
            req.session_id,
            state.status,
            state.is_clean,
        )
        return state.to_response()

    def advance_round(
        self,
        session_id: str,
        loop_id: str,
        req: AdvanceReviewLoopRequest,
    ) -> Optional[ReviewLoopResponse]:
        """Apply worker remediation diff and execute next review round."""
        with self._lock:
            state = self._loops.get(session_id, {}).get(loop_id)

        if state is None:
            return None

        if state.status in (ReviewLoopStatusEnum.CONVERGED, ReviewLoopStatusEnum.MAX_ROUNDS_REACHED):
            return state.to_response()

        next_round_number = len(state.rounds) + 1
        state.current_diff = req.fixed_diff

        # Run parallel review on fixed diff
        reports = self._pipeline.run_parallel_review(
            diff=req.fixed_diff,
            context=state.context_description,
        )
        all_findings = self._pipeline.aggregate_findings(reports)
        has_blocking = self._pipeline.has_blocking_issues(all_findings)

        round_dto = LoopRoundDTO(
            round_number=next_round_number,
            perspective_reports={
                p.value: _to_report_dto(reports[p])
                for p in ReviewPerspective
                if p in reports
            },
            all_findings=[_to_finding_dto(f) for f in all_findings],
            has_blocking_issues=has_blocking,
            fix_description=req.fix_note or f"Remediation patch applied for Round {next_round_number}",
            converged=not has_blocking,
        )
        state.rounds.append(round_dto)

        if not has_blocking:
            state.status = ReviewLoopStatusEnum.CONVERGED
            state.is_clean = True
            state.final_summary = (
                f"Review loop successfully converged in Round {next_round_number} with clean diff."
            )
        elif next_round_number >= state.max_rounds:
            state.status = ReviewLoopStatusEnum.MAX_ROUNDS_REACHED
            state.is_clean = False
            state.final_summary = (
                f"Reached maximum allowed rounds ({state.max_rounds}) with remaining issues."
            )
        else:
            state.status = ReviewLoopStatusEnum.IN_REVIEW
            state.is_clean = False
            state.final_summary = (
                f"Round {next_round_number} completed; {len(all_findings)} issues remaining."
            )

        logger.info(
            "Review loop '%s' advanced to Round %d (status=%s, clean=%s)",
            loop_id,
            next_round_number,
            state.status,
            state.is_clean,
        )
        return state.to_response()

    def get_review_loop(self, session_id: str, loop_id: str) -> Optional[ReviewLoopResponse]:
        """Fetch current status and rounds for an active or completed review loop."""
        with self._lock:
            state = self._loops.get(session_id, {}).get(loop_id)
        return state.to_response() if state else None

    def list_review_loops(self, session_id: str) -> ReviewLoopListResponse:
        """List all review loops associated with a session."""
        with self._lock:
            states = list(self._loops.get(session_id, {}).values())
        responses = [s.to_response() for s in states]
        return ReviewLoopListResponse(
            session_id=session_id,
            loops=responses,
            total_count=len(responses),
        )

    def cleanup_session(self, session_id: str) -> bool:
        """Release review loop memory state when a session terminates."""
        with self._lock:
            if session_id in self._loops:
                del self._loops[session_id]
                logger.info("Cleaned up review loop state for session %s", session_id)
                return True
        return False


_instance: Optional[ReviewLoopService] = None


def get_review_loop_service() -> ReviewLoopService:
    """Singleton getter for ReviewLoopService."""
    global _instance
    if _instance is None:
        _instance = ReviewLoopService()
    return _instance
