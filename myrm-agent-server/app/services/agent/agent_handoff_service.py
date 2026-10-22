"""
[POS] app/services/agent/agent_handoff_service.py
[INPUT] pathlib.Path, app/schemas/agent_handoff.py, myrm_agent_harness.toolkits.memory.handoff
[OUTPUT] AgentHandoffService, get_agent_handoff_service

Service layer governing typed cross-agent handoff memorandum persistence, CAS claim, and lifecycle state.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import os
import threading
import time
import uuid
from pathlib import Path

from myrm_agent_harness.toolkits.memory.handoff import (
    AgentHandoffEngine,
    AgentHandoffSpec,
    FailedApproachRecord,
    FinalizeSessionRequest,
    FinalizeSessionResult,
    HandoffClaimReceipt,
    ImplicitConstraintRecord,
)

from app.schemas.agent_handoff import (
    AgentHandoffSpecDTO,
    CancelHandoffRequestDTO,
    ClaimHandoffRequestDTO,
    CompleteHandoffRequestDTO,
    CreateInChatHandoffRequestDTO,
    FailedApproachDTO,
    FinalizeSessionRequestDTO,
    FinalizeSessionResponseDTO,
    HandoffActionRequestDTO,
    HandoffAdvanceStageRequestDTO,
    HandoffClaimReceiptDTO,
    HandoffListResponseDTO,
    HandoffStageInfoDTO,
    ImplicitConstraintDTO,
    InChatHandoffCardDTO,
)


def _spec_to_dto(spec: AgentHandoffSpec) -> AgentHandoffSpecDTO:
    """Transform internal Harness AgentHandoffSpec to public API DTO."""
    return AgentHandoffSpecDTO(
        handoff_id=spec.handoff_id,
        session_id=spec.session_id,
        source_profile_id=spec.source_profile_id,
        target_profile_id=spec.target_profile_id,
        active_goal=spec.active_goal,
        failed_approaches=[
            FailedApproachDTO(
                approach_name=fa.approach_name,
                rejected_reason=fa.rejected_reason,
                evidence_snippet=fa.evidence_snippet,
                attempted_by_profile_id=fa.attempted_by_profile_id,
            )
            for fa in spec.failed_approaches
        ],
        implicit_constraints=[
            ImplicitConstraintDTO(
                scope=ic.scope,
                constraint_rule=ic.constraint_rule,
                rationale=ic.rationale,
            )
            for ic in spec.implicit_constraints
        ],
        errors_and_fixes=list(spec.errors_and_fixes),
        pending_asks=list(spec.pending_asks),
        next_actions=list(spec.next_actions),
        status=spec.status.value,
        created_at=spec.created_at,
        claimed_at=spec.claimed_at,
        claimed_by_profile_id=spec.claimed_by_profile_id,
        claimed_by_session_id=spec.claimed_by_session_id,
        completed_at=spec.completed_at,
    )


class AgentHandoffService:
    """Business service wrapping the underlying AgentHandoffEngine facade."""

    def __init__(self, engine: AgentHandoffEngine | None = None) -> None:
        if engine is not None:
            self._engine = engine
        else:
            base_dir_env = os.getenv("MYRM_AGENT_HANDOFF_DIR", ".myrm/handoffs")
            storage_dir = Path(base_dir_env).resolve()
            self._engine = AgentHandoffEngine(storage_dir=storage_dir)
        self._in_chat_handoffs: dict[str, InChatHandoffCardDTO] = {}
        self._in_chat_lock = threading.Lock()

    def finalize_session(self, req: FinalizeSessionRequestDTO) -> FinalizeSessionResponseDTO:
        """Finalize working session and write durable handoff memorandum."""
        harness_req = FinalizeSessionRequest(
            session_id=req.session_id,
            source_profile_id=req.source_profile_id,
            target_profile_id=req.target_profile_id,
            active_goal=req.active_goal,
            failed_approaches=[
                FailedApproachRecord(
                    approach_name=fa.approach_name,
                    rejected_reason=fa.rejected_reason,
                    evidence_snippet=fa.evidence_snippet,
                    attempted_by_profile_id=fa.attempted_by_profile_id,
                )
                for fa in req.failed_approaches
            ],
            implicit_constraints=[
                ImplicitConstraintRecord(
                    scope=ic.scope,
                    constraint_rule=ic.constraint_rule,
                    rationale=ic.rationale,
                )
                for ic in req.implicit_constraints
            ],
            errors_and_fixes=list(req.errors_and_fixes),
            pending_asks=list(req.pending_asks),
            next_actions=list(req.next_actions),
        )
        result: FinalizeSessionResult = self._engine.finalize_session(harness_req)
        return FinalizeSessionResponseDTO(
            session_id=result.session_id,
            handoff_id=result.handoff_id,
            persisted_path=result.persisted_path,
            status=result.status.value,
            timestamp=result.timestamp,
        )

    def claim_handoff(self, handoff_id: str, req: ClaimHandoffRequestDTO) -> HandoffClaimReceiptDTO:
        """Atomically claim a pending handoff, enforcing mutual exclusion."""
        receipt: HandoffClaimReceipt = self._engine.claim_handoff(
            handoff_id=handoff_id,
            claimer_profile_id=req.claimer_profile_id,
            claimer_session_id=req.claimer_session_id,
        )
        return HandoffClaimReceiptDTO(
            handoff_id=receipt.handoff_id,
            claimed_by_profile_id=receipt.claimed_by_profile_id,
            claimed_by_session_id=receipt.claimed_by_session_id,
            claim_timestamp=receipt.claim_timestamp,
            handoff_spec=_spec_to_dto(receipt.handoff_spec),
        )

    def complete_handoff(self, handoff_id: str, req: CompleteHandoffRequestDTO) -> AgentHandoffSpecDTO:
        """Mark a claimed handoff memorandum as completed."""
        updated = self._engine.complete_handoff(
            handoff_id=handoff_id,
            completing_session_id=req.completing_session_id,
        )
        return _spec_to_dto(updated)

    def cancel_handoff(self, handoff_id: str, req: CancelHandoffRequestDTO) -> AgentHandoffSpecDTO:
        """Cancel an existing pending or claimed handoff packet."""
        cancelled = self._engine.cancel_handoff(
            handoff_id=handoff_id,
            cancelling_session_id=req.cancelling_session_id,
            reason=req.reason,
        )
        return _spec_to_dto(cancelled)

    def get_handoff(self, handoff_id: str) -> AgentHandoffSpecDTO | None:
        """Retrieve a specific handoff memorandum by ID."""
        spec = self._engine.get_handoff(handoff_id)
        if spec is None:
            return None
        return _spec_to_dto(spec)

    def list_pending(self, target_profile_id: str | None = None) -> HandoffListResponseDTO:
        """List all unassigned or matching pending handoff memorandums."""
        specs = self._engine.list_pending(target_profile_id=target_profile_id)
        dtos = [_spec_to_dto(s) for s in specs]
        return HandoffListResponseDTO(handoffs=dtos, total_count=len(dtos))

    def list_by_session(self, session_id: str) -> HandoffListResponseDTO:
        """List all handoff records associated with a specific session ID."""
        specs = self._engine.list_by_session(session_id=session_id)
        dtos = [_spec_to_dto(s) for s in specs]
        return HandoffListResponseDTO(handoffs=dtos, total_count=len(dtos))

    # --- In-Chat Task Handoff & Five-Stage Orchestration Stack ---

    @staticmethod
    def _create_default_stages() -> list[HandoffStageInfoDTO]:
        """Construct canonical BkashJosi 5-Stage Orchestration Stack."""
        return [
            HandoffStageInfoDTO(
                stage_id="intent_routing",
                label="意图确认与分流 (Intent Routing)",
                status="pending",
                summary="",
            ),
            HandoffStageInfoDTO(
                stage_id="context_injection",
                label="环境与上下文准备 (Scene & Context)",
                status="pending",
                summary="",
            ),
            HandoffStageInfoDTO(
                stage_id="action_execution",
                label="动作执行与计算 (Action Execution)",
                status="pending",
                summary="",
            ),
            HandoffStageInfoDTO(
                stage_id="artifact_delivery",
                label="工件生成与交付 (Artifact Delivery)",
                status="pending",
                summary="",
            ),
            HandoffStageInfoDTO(
                stage_id="acceptance_verification",
                label="验收评测与确认 (Acceptance Verification)",
                status="pending",
                summary="",
            ),
        ]

    def create_in_chat_handoff(self, req: CreateInChatHandoffRequestDTO) -> InChatHandoffCardDTO:
        """Create a new in-chat bot delegation with initialized five-stage stack."""
        handoff_id = f"handoff_{uuid.uuid4().hex[:12]}"
        now = time.time()
        stages = self._create_default_stages()

        if req.requires_approval:
            status = "awaiting_approval"
            stages[0].status = "in_progress"
            stages[0].summary = "等待用户审批派发..."
            stages[0].timestamp = now
        else:
            status = "in_progress"
            stages[0].status = "completed"
            stages[0].summary = "意图已确认并直接下发"
            stages[0].timestamp = now
            stages[1].status = "in_progress"
            stages[1].summary = "加载环境与上下文..."
            stages[1].timestamp = now

        card = InChatHandoffCardDTO(
            handoff_id=handoff_id,
            session_id=req.session_id,
            source_agent=req.source_agent,
            target_agent=req.target_agent,
            task_intent=req.task_intent,
            status=status,
            requires_approval=req.requires_approval,
            stages=stages,
            deliverables=[],
            orchestrator_summary=None,
            resume_context_note=req.resume_context_note,
            created_at=now,
            updated_at=now,
        )

        with self._in_chat_lock:
            self._in_chat_handoffs[handoff_id] = card

        return card

    def get_in_chat_handoff(self, handoff_id: str) -> InChatHandoffCardDTO | None:
        """Retrieve an in-chat handoff delegation card by ID."""
        with self._in_chat_lock:
            return self._in_chat_handoffs.get(handoff_id)

    def handle_handoff_action(self, handoff_id: str, req: HandoffActionRequestDTO) -> InChatHandoffCardDTO:
        """Handle human gate or inline completion action."""
        with self._in_chat_lock:
            card = self._in_chat_handoffs.get(handoff_id)
            if card is None:
                raise KeyError(f"In-chat handoff '{handoff_id}' was not found.")

            now = time.time()
            if req.action == "approve":
                card.status = "in_progress"
                if len(card.stages) > 0:
                    card.stages[0].status = "completed"
                    card.stages[0].summary = f"用户已批准派发: {req.comment or '允许执行'}"
                    card.stages[0].timestamp = now
                if len(card.stages) > 1 and card.stages[1].status == "pending":
                    card.stages[1].status = "in_progress"
                    card.stages[1].timestamp = now
            elif req.action == "reject":
                card.status = "rejected"
                if len(card.stages) > 0:
                    card.stages[0].status = "failed"
                    card.stages[0].summary = f"移交已被驳回: {req.comment or '用户拒绝'}"
                    card.stages[0].timestamp = now
            elif req.action == "send_to_pr":
                pr_tag = f"PR: #{uuid.uuid4().hex[:6]}"
                if pr_tag not in card.deliverables:
                    card.deliverables.append(pr_tag)
                card.orchestrator_summary = f"成果已成功直通提交 PR ({pr_tag})。{card.orchestrator_summary or ''}".strip()
            elif req.action == "accept":
                card.status = "completed"
                for stage in card.stages:
                    if stage.status != "completed":
                        stage.status = "completed"
                        stage.timestamp = now
                if not card.orchestrator_summary:
                    card.orchestrator_summary = "用户已确认采纳交付产物。"

            card.updated_at = now
            return card

    def advance_stage(self, handoff_id: str, req: HandoffAdvanceStageRequestDTO) -> InChatHandoffCardDTO:
        """Advance status and logs of a stage in the five-stage stack."""
        with self._in_chat_lock:
            card = self._in_chat_handoffs.get(handoff_id)
            if card is None:
                raise KeyError(f"In-chat handoff '{handoff_id}' was not found.")

            now = time.time()
            for stage in card.stages:
                if stage.stage_id == req.stage_id:
                    stage.status = req.status
                    if req.summary:
                        stage.summary = req.summary
                    stage.timestamp = now
                    break

            if req.deliverables:
                for item in req.deliverables:
                    if item not in card.deliverables:
                        card.deliverables.append(item)

            if req.orchestrator_summary:
                card.orchestrator_summary = req.orchestrator_summary

            # Check if all stages are completed
            if all(s.status == "completed" for s in card.stages):
                card.status = "completed"

            card.updated_at = now
            return card

    def list_in_chat_handoffs(self, session_id: str | None = None) -> list[InChatHandoffCardDTO]:
        """List in-chat handoffs, optionally filtered by session_id."""
        with self._in_chat_lock:
            items = list(self._in_chat_handoffs.values())
        if session_id:
            items = [item for item in items if item.session_id == session_id]
        return sorted(items, key=lambda x: x.created_at, reverse=True)


_AGENT_HANDOFF_SERVICE_INSTANCE: AgentHandoffService | None = None
_AGENT_HANDOFF_SERVICE_LOCK = threading.Lock()


def get_agent_handoff_service() -> AgentHandoffService:
    """Singleton provider for AgentHandoffService."""
    global _AGENT_HANDOFF_SERVICE_INSTANCE
    if _AGENT_HANDOFF_SERVICE_INSTANCE is None:
        with _AGENT_HANDOFF_SERVICE_LOCK:
            if _AGENT_HANDOFF_SERVICE_INSTANCE is None:
                _AGENT_HANDOFF_SERVICE_INSTANCE = AgentHandoffService()
    return _AGENT_HANDOFF_SERVICE_INSTANCE
