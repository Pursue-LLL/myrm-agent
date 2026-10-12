"""Server-side service managing pre-action physical gate and idempotency receipts.

[INPUT]
- PreActionSideEffectGate from myrm_agent_harness.core.security.side_effect_gate

[OUTPUT]
- SideEffectGateService: Server lifecycle manager for action challenges and receipts
- get_side_effect_gate_service: Dependency provider

[POS]
Server approvals service. Exposes high-level APIs for WebUI and workers to review
intercepted irreversible tool calls and query idempotency receipts.
"""

from __future__ import annotations

import logging
from typing import Literal

from myrm_agent_harness.core.security.side_effect_gate import (
    ActionArguments,
    ActionReceipt,
    PreActionChallenge,
    PreActionDeniedError,
    PreActionEvaluationResult,
    PreActionSideEffectGate,
    PreActionStatus,
)

from app.schemas.side_effect_gate import (
    ActionReceiptCreateRequest,
    ActionReceiptDto,
    PreActionChallengeDto,
    PreActionDecisionResponse,
)

logger = logging.getLogger(__name__)


def _challenge_to_dto(c: PreActionChallenge) -> PreActionChallengeDto:
    return PreActionChallengeDto(
        challenge_id=c.challenge_id,
        session_id=c.session_id,
        tool_name=c.tool_name,
        arguments=c.arguments,
        idempotency_key=c.idempotency_key,
        risk_level=c.risk_level.value,
        summary=c.summary,
        created_at=c.created_at,
        expires_at=c.expires_at,
    )


def _receipt_to_dto(r: ActionReceipt) -> ActionReceiptDto:
    return ActionReceiptDto(
        idempotency_key=r.idempotency_key,
        tool_name=r.tool_name,
        provider_receipt_id=r.provider_receipt_id,
        status=r.status,
        output_summary=r.output_summary,
        challenge_id=r.challenge_id,
        recorded_at=r.recorded_at,
    )


class SideEffectGateService:
    """Manages pre-action challenges and receipt ledger in server runtime."""

    def __init__(self, gate: PreActionSideEffectGate | None = None) -> None:
        self._gate = gate if gate is not None else PreActionSideEffectGate()

    @property
    def gate(self) -> PreActionSideEffectGate:
        """Internal harness gate reference."""
        return self._gate

    def evaluate_tool_action(
        self,
        session_id: str,
        tool_name: str,
        arguments: ActionArguments,
        auth_token: str | None = None,
        sequence: int = 0,
    ) -> PreActionEvaluationResult:
        """Physically evaluate and possibly intercept an action before dispatch."""
        return self._gate.evaluate_action(
            session_id=session_id,
            tool_name=tool_name,
            arguments=arguments,
            auth_token=auth_token,
            sequence=sequence,
        )

    def list_pending_challenges(self) -> list[PreActionChallengeDto]:
        """List unexpired intercepted actions awaiting human sign-off."""
        challenges = self._gate.list_pending_challenges()
        return [_challenge_to_dto(c) for c in challenges]

    def get_challenge(self, challenge_id: str) -> PreActionChallengeDto | None:
        """Get challenge details by challenge_id."""
        c = self._gate.get_challenge(challenge_id)
        return _challenge_to_dto(c) if c is not None else None

    def decide_challenge(
        self,
        challenge_id: str,
        decision: Literal["approve", "reject"],
        reviewer_id: str,
        reason: str | None = None,
    ) -> PreActionDecisionResponse:
        """Approve or reject a pending challenge."""
        challenge = self._gate.get_challenge(challenge_id)
        if challenge is None:
            return PreActionDecisionResponse(
                challenge_id=challenge_id,
                status="not_found",
                auth_token=None,
                message=f"Challenge '{challenge_id}' not found",
            )

        if decision == "approve":
            try:
                token = self._gate.authorize_challenge(challenge_id, reviewer_id=reviewer_id)
                return PreActionDecisionResponse(
                    challenge_id=challenge_id,
                    status=PreActionStatus.APPROVED.value,
                    auth_token=token,
                    message="Challenge approved, single-use execution token issued",
                )
            except PreActionDeniedError as exc:
                return PreActionDecisionResponse(
                    challenge_id=challenge_id,
                    status=PreActionStatus.EXPIRED.value,
                    auth_token=None,
                    message=f"Challenge authorization failed: {exc.reason}",
                )

        # Rejected
        rejection_reason = reason or f"Rejected by reviewer {reviewer_id}"
        self._gate.reject_challenge(challenge_id, reason=rejection_reason)
        return PreActionDecisionResponse(
            challenge_id=challenge_id,
            status=PreActionStatus.REJECTED.value,
            auth_token=None,
            message=f"Challenge rejected: {rejection_reason}",
        )

    def record_receipt(self, request: ActionReceiptCreateRequest) -> ActionReceiptDto:
        """Record external provider receipt for idempotent replay."""
        receipt = self._gate.record_execution_receipt(
            idempotency_key=request.idempotency_key,
            tool_name=request.tool_name,
            provider_receipt_id=request.provider_receipt_id,
            output_summary=request.output_summary,
            challenge_id=request.challenge_id,
        )
        return _receipt_to_dto(receipt)

    def get_receipt(self, idempotency_key: str) -> ActionReceiptDto | None:
        """Query existing execution receipt by idempotency key."""
        receipt = self._gate.receipt_cache.get_receipt(idempotency_key)
        return _receipt_to_dto(receipt) if receipt is not None else None


_global_side_effect_gate_service: SideEffectGateService | None = None


def get_side_effect_gate_service() -> SideEffectGateService:
    """Singleton getter for SideEffectGateService."""
    global _global_side_effect_gate_service
    if _global_side_effect_gate_service is None:
        _global_side_effect_gate_service = SideEffectGateService()
    return _global_side_effect_gate_service
