"""Service layer for Pre-Flight Irreversible Write Interception and Emergency Kill Switch.

[INPUT]
- Harness PreFlightIrreversibleWriteGuard and schema request DTOs.

[OUTPUT]
- IrreversibleWriteGuardService managing tool write interception, contracts, and emergency kill switches.

[POS]
Service layer bridging HTTP presentation with harness irreversible write guard.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.irreversible_write_guard import (
    IrreversibleWriteContract,
    IrreversibleWriteIntent,
    PreFlightIrreversibleWriteGuard,
    RiskLevel,
    WriteDomain,
)

from app.schemas.irreversible_write_guard import (
    ApproveIntentRequest,
    BlastRadiusCardResponse,
    ContractResponse,
    EmergencyKillRequest,
    EmergencyKillResponse,
    InterceptToolCallRequest,
    InterceptToolCallResponse,
    IrreversibleWriteIntentResponse,
    RegisterContractRequest,
)

logger = logging.getLogger(__name__)


class IrreversibleWriteGuardService:
    """Manages pre-flight interception, explosion radius review, and emergency kill switches."""

    def __init__(
        self, guard: PreFlightIrreversibleWriteGuard | None = None
    ) -> None:
        self.guard = guard or PreFlightIrreversibleWriteGuard()

    def intercept_tool_call(
        self, req: InterceptToolCallRequest
    ) -> InterceptToolCallResponse:
        """Evaluate whether a tool performs irreversible external writes and suspend it if so."""
        intent = self.guard.intercept(
            session_id=req.session_id,
            tool_name=req.tool_name,
            arguments=req.arguments,
            ttl_seconds=req.ttl_seconds,
        )

        if intent is None:
            return InterceptToolCallResponse(
                intercepted=False,
                intent=None,
                reason=f"Tool '{req.tool_name}' is not registered as an irreversible write action.",
            )

        logger.warning(
            "Pre-flight interception triggered for irreversible write tool '%s' (domain: %s, intent: %s)",
            intent.tool_name,
            intent.domain,
            intent.intent_id,
        )

        return InterceptToolCallResponse(
            intercepted=True,
            intent=self._convert_intent(intent),
            reason=(
                f"Irreversible write tool '{req.tool_name}' suspended. "
                "Requires blast radius review and user approval before dispatch."
            ),
        )

    def approve_intent(
        self, intent_id: str, req: ApproveIntentRequest
    ) -> IrreversibleWriteIntentResponse:
        """Approve a suspended irreversible write intent."""
        approved = self.guard.approve(intent_id=intent_id, approver=req.approver)
        logger.info(
            "Intent '%s' approved by '%s' for dispatch.",
            intent_id,
            req.approver,
        )
        return self._convert_intent(approved)

    def emergency_kill(
        self, intent_id: str, req: EmergencyKillRequest
    ) -> EmergencyKillResponse:
        """Trigger emergency kill switch on an intercepted action."""
        kill_result = self.guard.emergency_kill(intent_id=intent_id, reason=req.reason)
        logger.warning(
            "Emergency kill switch triggered for intent '%s'. Action aborted: %s",
            intent_id,
            req.reason,
        )
        return EmergencyKillResponse(
            intent_id=kill_result.intent_id,
            killed=kill_result.killed,
            reason=kill_result.reason,
            timestamp=kill_result.timestamp,
        )

    def get_intent(self, intent_id: str) -> IrreversibleWriteIntentResponse | None:
        """Retrieve intent by ID."""
        intent = self.guard.get_intent(intent_id)
        if intent is None:
            return None
        return self._convert_intent(intent)

    def list_pending(
        self, session_id: str | None = None
    ) -> list[IrreversibleWriteIntentResponse]:
        """List active pending confirmation intents."""
        intents = self.guard.list_pending(session_id=session_id)
        return [self._convert_intent(i) for i in intents]

    def register_contract(self, req: RegisterContractRequest) -> ContractResponse:
        """Register a new tool contract for pre-flight interception."""
        domain = WriteDomain(req.domain.lower())
        risk = RiskLevel(req.default_risk_level.lower())
        contract = IrreversibleWriteContract(
            tool_name=req.tool_name,
            domain=domain,
            description=req.description,
            default_risk_level=risk,
        )
        self.guard.registry.register(contract)
        return ContractResponse(
            tool_name=contract.tool_name,
            domain=contract.domain.value,
            description=contract.description,
            default_risk_level=contract.default_risk_level.value,
        )

    def list_contracts(self) -> list[ContractResponse]:
        """List all registered irreversible write contracts."""
        contracts = self.guard.registry.list_contracts()
        return [
            ContractResponse(
                tool_name=c.tool_name,
                domain=c.domain.value,
                description=c.description,
                default_risk_level=c.default_risk_level.value,
            )
            for c in contracts
        ]

    @staticmethod
    def _convert_intent(intent: IrreversibleWriteIntent) -> IrreversibleWriteIntentResponse:
        card = BlastRadiusCardResponse(
            intent_id=intent.blast_radius.intent_id,
            domain=intent.blast_radius.domain.value,
            title=intent.blast_radius.title,
            summary=intent.blast_radius.summary,
            details=intent.blast_radius.details,
            risk_level=intent.blast_radius.risk_level.value,
            created_at=intent.blast_radius.created_at,
            expires_at=intent.blast_radius.expires_at,
        )
        return IrreversibleWriteIntentResponse(
            intent_id=intent.intent_id,
            session_id=intent.session_id,
            tool_name=intent.tool_name,
            domain=intent.domain.value,
            arguments=intent.arguments,
            blast_radius=card,
            status=intent.status.value,
            resolution_reason=intent.resolution_reason,
            created_at=intent.created_at,
        )


_service_instance: IrreversibleWriteGuardService | None = None


def get_irreversible_write_guard_service() -> IrreversibleWriteGuardService:
    """FastAPI dependency provider for IrreversibleWriteGuardService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = IrreversibleWriteGuardService()
    return _service_instance


def reset_irreversible_write_guard_service() -> None:
    """Reset singleton instance (useful for testing)."""
    global _service_instance
    _service_instance = None

