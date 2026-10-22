"""Service mediating One-Model Multi-Agent Shared Context Token Budget Governance (Item 52).

[INPUT]
- RegisterRoleBudgetRequest, GovernancePrecheckRequest, RecordConsumptionRequest.

[OUTPUT]
- TokenBudgetGovernanceService coordinating budget ceilings, fan-out prechecks,
  and routing overhead Doctor alerts.

[POS]
- Server-side service layer for token budget governance & routing overhead visualization.
"""

from __future__ import annotations

import logging
import threading

from myrm_agent_harness.agent.sub_agents.token_budget_governance import (
    ConsumptionCategory,
    ConsumptionRecord,
    DoctorNudgeAlert,
    GovernancePrecheckResult,
    RoleBudgetSpec,
    SharedTokenBudgetGovernor,
    SharedTokenBudgetSnapshot,
)

from app.schemas.token_budget_governance import (
    ConsumptionCategoryEnum,
    ConsumptionRecordDTO,
    DoctorNudgeAlertDTO,
    GovernancePrecheckRequest,
    GovernancePrecheckResponseDTO,
    NudgeSeverityEnum,
    RecordConsumptionRequest,
    RegisterRoleBudgetRequest,
    RoleBudgetSpecDTO,
    SharedTokenBudgetSnapshotDTO,
)

logger = logging.getLogger(__name__)


def _spec_to_dto(spec: RoleBudgetSpec) -> RoleBudgetSpecDTO:
    return RoleBudgetSpecDTO(
        role_name=spec.role_name,
        token_ceiling=spec.token_ceiling,
        stop_condition=spec.stop_condition,
        allow_overflow=spec.allow_overflow,
    )


def _record_to_dto(rec: ConsumptionRecord) -> ConsumptionRecordDTO:
    return ConsumptionRecordDTO(
        record_id=rec.record_id,
        agent_role=rec.agent_role,
        category=ConsumptionCategoryEnum(rec.category),
        prompt_tokens=rec.prompt_tokens,
        completion_tokens=rec.completion_tokens,
        total_tokens=rec.total_tokens,
        timestamp=rec.timestamp,
        metadata=dict(rec.metadata),
    )


def _precheck_to_dto(res: GovernancePrecheckResult) -> GovernancePrecheckResponseDTO:
    return GovernancePrecheckResponseDTO(
        passed=res.passed,
        requested_tokens=res.requested_tokens,
        remaining_budget=res.remaining_budget,
        reason=res.reason,
    )


def _alert_to_dto(alert: DoctorNudgeAlert) -> DoctorNudgeAlertDTO:
    return DoctorNudgeAlertDTO(
        alert_id=alert.alert_id,
        severity=NudgeSeverityEnum(alert.severity),
        message=alert.message,
        handoff_count=alert.handoff_count,
        routing_ratio=alert.routing_ratio,
        suggested_action=alert.suggested_action,
        created_at=alert.created_at,
    )


def _snapshot_to_dto(snap: SharedTokenBudgetSnapshot) -> SharedTokenBudgetSnapshotDTO:
    return SharedTokenBudgetSnapshotDTO(
        session_id=snap.session_id,
        primary_model=snap.primary_model,
        shared_token_ceiling=snap.shared_token_ceiling,
        total_tokens_spent=snap.total_tokens_spent,
        routing_tokens_spent=snap.routing_tokens_spent,
        execution_tokens_spent=snap.execution_tokens_spent,
        routing_ratio=snap.routing_ratio,
        role_budgets={k: _spec_to_dto(v) for k, v in snap.role_budgets.items()},
        role_usage=dict(snap.role_usage),
        active_alerts=[_alert_to_dto(a) for a in snap.active_alerts],
    )


class TokenBudgetGovernanceService:
    """Service providing session-scoped token governance and Doctor diagnostics."""

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._governors: dict[str, SharedTokenBudgetGovernor] = {}

    def get_or_create_governor(
        self,
        session_id: str,
        primary_model: str = "claude-3-5-sonnet",
        shared_token_ceiling: int = 100_000,
    ) -> SharedTokenBudgetGovernor:
        with self._lock:
            if session_id not in self._governors:
                self._governors[session_id] = SharedTokenBudgetGovernor(
                    session_id=session_id,
                    primary_model=primary_model,
                    shared_token_ceiling=shared_token_ceiling,
                )
            return self._governors[session_id]

    def register_role_budget(
        self, session_id: str, request: RegisterRoleBudgetRequest
    ) -> RoleBudgetSpecDTO:
        gov = self.get_or_create_governor(session_id)
        spec = RoleBudgetSpec(
            role_name=request.role_name,
            token_ceiling=request.token_ceiling,
            stop_condition=request.stop_condition,
            allow_overflow=request.allow_overflow,
        )
        gov.register_role_budget(spec)
        return _spec_to_dto(spec)

    def precheck_fanout(
        self, session_id: str, request: GovernancePrecheckRequest
    ) -> GovernancePrecheckResponseDTO:
        gov = self.get_or_create_governor(session_id)
        result = gov.precheck_fanout(
            role_name=request.role_name,
            estimated_tokens=request.estimated_tokens,
        )
        return _precheck_to_dto(result)

    def record_consumption(
        self, session_id: str, request: RecordConsumptionRequest
    ) -> ConsumptionRecordDTO:
        gov = self.get_or_create_governor(session_id)
        category = (
            ConsumptionCategory.ROUTING_OVERHEAD
            if request.category == ConsumptionCategoryEnum.ROUTING_OVERHEAD
            else ConsumptionCategory.EXECUTION_PAYLOAD
        )
        record = gov.record_consumption(
            agent_role=request.agent_role,
            category=category,
            prompt_tokens=request.prompt_tokens,
            completion_tokens=request.completion_tokens,
            metadata=request.metadata,
        )
        return _record_to_dto(record)

    def evaluate_doctor_nudge(
        self,
        session_id: str,
        threshold_routing_ratio: float = 0.35,
        max_handoffs: int = 5,
    ) -> list[DoctorNudgeAlertDTO]:
        gov = self.get_or_create_governor(session_id)
        alerts = gov.evaluate_doctor_nudge(
            threshold_routing_ratio=threshold_routing_ratio,
            max_handoffs=max_handoffs,
        )
        return [_alert_to_dto(a) for a in alerts]

    def get_snapshot(self, session_id: str) -> SharedTokenBudgetSnapshotDTO:
        gov = self.get_or_create_governor(session_id)
        snap = gov.get_snapshot()
        return _snapshot_to_dto(snap)

    def reset_session(self, session_id: str) -> None:
        with self._lock:
            if session_id in self._governors:
                self._governors[session_id].reset()
                self._governors.pop(session_id, None)


_token_budget_governance_service_instance: TokenBudgetGovernanceService | None = None


def get_token_budget_governance_service() -> TokenBudgetGovernanceService:
    """Return singleton instance of TokenBudgetGovernanceService."""
    global _token_budget_governance_service_instance
    if _token_budget_governance_service_instance is None:
        _token_budget_governance_service_instance = TokenBudgetGovernanceService()
    return _token_budget_governance_service_instance
