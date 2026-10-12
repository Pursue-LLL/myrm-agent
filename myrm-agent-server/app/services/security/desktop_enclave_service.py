"""Service orchestrating Desktop Action Safe Enclave, panic controls, and telemetry audit deck.

[INPUT]
- EvaluateActionRequest, ChallengeDecisionRequest, PanicTriggerRequest
- DesktopActionEnclaveGate, DesktopActionAuditDeck from myrm_agent_harness

[OUTPUT]
- DesktopEnclaveService: business service interfacing between HTTP routers and harness enclave.

[POS]
Server security service layer. Provides centralized desktop action governance for computer-use agents.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.desktop_enclave import (
    ActionEnclaveChallenge,
    CriticalActionBlockedError,
    CriticalDesktopAction,
    DesktopActionAuditDeck,
    DesktopActionEnclaveGate,
    DesktopActionPanickedError,
    DesktopActionRiskLevel,
    DesktopActionType,
)

from app.schemas.desktop_enclave import (
    ActionEnclaveChallengeDto,
    ChallengeDecisionRequest,
    ChallengeDecisionResponse,
    DesktopActionDto,
    EvaluateActionRequest,
    EvaluateActionResponse,
    LiveIntentFeedItem,
    LiveIntentFeedResponse,
    PanicStatusResponse,
)

logger = logging.getLogger(__name__)


def _action_dto_to_domain(dto: DesktopActionDto) -> CriticalDesktopAction:
    """Map Pydantic DTO to Harness domain dataclass."""
    try:
        action_type = DesktopActionType(dto.action_type)
    except ValueError:
        action_type = DesktopActionType.SYSTEM_COMMAND

    try:
        risk_level = DesktopActionRiskLevel(dto.risk_level)
    except ValueError:
        risk_level = DesktopActionRiskLevel.SAFE

    return CriticalDesktopAction(
        action_id=dto.action_id,
        action_type=action_type,
        semantic_intent=dto.semantic_intent,
        coordinates=dto.coordinates,
        target_element_text=dto.target_element_text,
        payload_text=dto.payload_text,
        risk_level=risk_level,
        timestamp=dto.timestamp,
    )


def _domain_to_action_dto(domain: CriticalDesktopAction) -> DesktopActionDto:
    """Map Harness domain dataclass to Pydantic DTO."""
    return DesktopActionDto(
        action_id=domain.action_id,
        action_type=str(domain.action_type),
        semantic_intent=domain.semantic_intent,
        coordinates=domain.coordinates,
        target_element_text=domain.target_element_text,
        payload_text=domain.payload_text,
        risk_level=str(domain.risk_level),
        timestamp=domain.timestamp,
    )


def _challenge_to_dto(domain: ActionEnclaveChallenge) -> ActionEnclaveChallengeDto:
    """Map Harness challenge domain model to Pydantic DTO."""
    return ActionEnclaveChallengeDto(
        challenge_id=domain.challenge_id,
        action=_domain_to_action_dto(domain.action),
        reason=domain.reason,
        status=domain.status,
        created_at=domain.created_at,
    )


class DesktopEnclaveService:
    """Singleton service for Computer-Use action gate and audit deck."""

    def __init__(
        self,
        gate: DesktopActionEnclaveGate | None = None,
        audit_deck: DesktopActionAuditDeck | None = None,
    ) -> None:
        self._audit_deck = audit_deck or DesktopActionAuditDeck(capacity=2000)
        self._gate = gate or DesktopActionEnclaveGate(audit_deck=self._audit_deck)

    @property
    def gate(self) -> DesktopActionEnclaveGate:
        """Underlying harness enclave gate."""
        return self._gate

    @property
    def audit_deck(self) -> DesktopActionAuditDeck:
        """Underlying harness telemetry deck."""
        return self._audit_deck

    def evaluate_action(self, request: EvaluateActionRequest) -> EvaluateActionResponse:
        """Evaluate action safety, creating challenge if high risk or rejecting if panicked."""
        domain_action = _action_dto_to_domain(request.action)
        try:
            allowed, challenge = self._gate.evaluate_action(domain_action)
            if allowed:
                return EvaluateActionResponse(
                    allowed=True,
                    challenge=None,
                    reason="Action verified safe by enclave policy",
                )
            challenge_dto = _challenge_to_dto(challenge) if challenge else None
            return EvaluateActionResponse(
                allowed=False,
                challenge=challenge_dto,
                reason=challenge.reason if challenge else "Action intercepted for verification",
            )
        except DesktopActionPanickedError as exc:
            return EvaluateActionResponse(
                allowed=False,
                challenge=None,
                reason=f"Emergency panic active: {exc.reason}",
            )

    def decide_challenge(self, request: ChallengeDecisionRequest) -> ChallengeDecisionResponse:
        """Record human sign-off or denial on intercepted challenge."""
        if request.approved:
            try:
                approved_action = self._gate.approve_challenge(request.challenge_id)
                return ChallengeDecisionResponse(
                    challenge_id=request.challenge_id,
                    status="approved",
                    action=_domain_to_action_dto(approved_action),
                    message="Challenge approved successfully",
                )
            except (KeyError, ValueError, DesktopActionPanickedError) as exc:
                return ChallengeDecisionResponse(
                    challenge_id=request.challenge_id,
                    status="error",
                    action=None,
                    message=str(exc),
                )

        try:
            self._gate.reject_challenge(request.challenge_id, reason=request.reason)
            return ChallengeDecisionResponse(
                challenge_id=request.challenge_id,
                status="rejected",
                action=None,
                message="Challenge rejected by user",
            )
        except CriticalActionBlockedError:
            return ChallengeDecisionResponse(
                challenge_id=request.challenge_id,
                status="rejected",
                action=None,
                message="Challenge successfully blocked and rejected",
            )
        except (KeyError, ValueError) as exc:
            return ChallengeDecisionResponse(
                challenge_id=request.challenge_id,
                status="error",
                action=None,
                message=str(exc),
            )

    def trigger_panic(self, reason: str = "Emergency stop activated") -> PanicStatusResponse:
        """Engage emergency panic stop across all desktop agent activities."""
        self._gate.trigger_panic(reason=reason)
        return PanicStatusResponse(
            is_panicked=self._gate.is_panicked,
            panic_reason=self._gate.panic_reason,
        )

    def reset_panic(self) -> PanicStatusResponse:
        """Reset emergency panic stop."""
        self._gate.reset_panic()
        return PanicStatusResponse(
            is_panicked=self._gate.is_panicked,
            panic_reason=self._gate.panic_reason,
        )

    def get_panic_status(self) -> PanicStatusResponse:
        """Return current panic circuit breaker state."""
        return PanicStatusResponse(
            is_panicked=self._gate.is_panicked,
            panic_reason=self._gate.panic_reason,
        )

    def get_pending_challenges(self) -> list[ActionEnclaveChallengeDto]:
        """Fetch all challenges awaiting human approval."""
        challenges = self._gate.list_pending_challenges()
        return [_challenge_to_dto(ch) for ch in challenges]

    def get_live_intent_feed(self, limit: int = 20) -> LiveIntentFeedResponse:
        """Fetch Live Intent HUD telemetry projection."""
        raw_feed = self._audit_deck.get_live_intent_feed(limit=limit)
        items: list[LiveIntentFeedItem] = []
        for r in raw_feed:
            items.append(
                LiveIntentFeedItem(
                    record_id=str(r["record_id"]),
                    action_id=str(r["action_id"]),
                    action_type=str(r["action_type"]),
                    semantic_intent=str(r["semantic_intent"]),
                    risk_level=str(r["risk_level"]),
                    enclave_verified=bool(r["enclave_verified"]),
                    executed=bool(r["executed"]),
                    status=str(r["status"]),
                    execution_latency_ms=float(r["execution_latency_ms"]),
                    recorded_at=float(r["recorded_at"]),
                )
            )
        return LiveIntentFeedResponse(feed=items, count=len(items))


# Global default instance
default_desktop_enclave_service = DesktopEnclaveService()
