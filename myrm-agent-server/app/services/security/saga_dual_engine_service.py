"""Spatiotemporal Duality, Connector Trust Gate & Declarative Saga Service.

[INPUT]
- GrantTrustLeaseRequest, RevokeTrustLeaseRequest, ExecuteDualToolRequest.

[OUTPUT]
- ConnectorTrustLeaseDto, RevokeTrustLeaseResponse, ExecuteDualToolResponse,
  SagaRollbackResponse, EmissionAuditRecordDto.

[POS]
- Server security service. Wraps harness SpatiotemporalDualEngineGuard to enforce
  tool duality, connector trust leases, and declarative Saga compensation.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.saga_dual_engine import (
    ConnectorTrustGate,
    ConnectorTrustLease,
    EmissionAuditRecord,
    SagaExecutionEngine,
    SpatiotemporalDualEngineGuard,
    ToolIntent,
)

from app.schemas.saga_dual_engine import (
    ConnectorTrustLeaseDto,
    EmissionAuditRecordDto,
    ExecuteDualToolRequest,
    ExecuteDualToolResponse,
    GrantTrustLeaseRequest,
    RevokeTrustLeaseRequest,
    RevokeTrustLeaseResponse,
    SagaRollbackResponse,
)

logger = logging.getLogger(__name__)


def _lease_to_dto(lease: ConnectorTrustLease) -> ConnectorTrustLeaseDto:
    """Convert domain lease to DTO."""
    return ConnectorTrustLeaseDto(
        lease_id=lease.lease_id,
        connector_id=lease.connector_id,
        host=lease.host,
        authorized_scopes=list(lease.authorized_scopes),
        expires_at=lease.expires_at,
        is_active=lease.is_active,
    )


def _audit_to_dto(record: EmissionAuditRecord) -> EmissionAuditRecordDto:
    """Convert domain emission audit record to DTO."""
    return EmissionAuditRecordDto(
        audit_id=record.audit_id,
        agent_id=record.agent_id,
        approver_id=record.approver_id,
        connector_id=record.connector_id,
        tool_name=record.tool_name,
        params_hash=record.params_hash,
        receipt=record.receipt,
        compensation_status=record.compensation_status.value,
        timestamp=record.timestamp,
    )


class SagaDualEngineService:
    """Service governing spatiotemporal tool duality, connector trust, and saga rollbacks."""

    def __init__(self) -> None:
        self._saga_engine = SagaExecutionEngine()
        self._trust_gate = ConnectorTrustGate()
        self._guard = SpatiotemporalDualEngineGuard(
            saga_engine=self._saga_engine,
            trust_gate=self._trust_gate,
        )

    @property
    def guard(self) -> SpatiotemporalDualEngineGuard:
        """Underlying harness guard."""
        return self._guard

    def grant_lease(self, req: GrantTrustLeaseRequest) -> ConnectorTrustLeaseDto:
        """Grant an explicit trust authorization lease to an external connector."""
        lease = self._trust_gate.grant_lease(
            connector_id=req.connector_id,
            host=req.host,
            authorized_scopes=req.authorized_scopes,
            ttl_seconds=req.ttl_seconds,
        )
        return _lease_to_dto(lease)

    def revoke_lease(self, req: RevokeTrustLeaseRequest) -> RevokeTrustLeaseResponse:
        """Revoke an active connector trust lease."""
        revoked = self._trust_gate.revoke_lease(req.lease_id)
        return RevokeTrustLeaseResponse(revoked=revoked, lease_id=req.lease_id)

    def execute_tool(self, req: ExecuteDualToolRequest) -> ExecuteDualToolResponse:
        """Execute tool enforcing spatiotemporal duality, connector trust, and HITL confirmation."""
        intent = ToolIntent(req.intent)

        # Register compensator stub if provided and not yet registered
        if req.compensator_name:
            def dummy_compensator(params: object) -> bool:
                logger.info("Executing compensating action '%s' with %s", req.compensator_name, params)
                return True

            self._saga_engine.register_compensator(req.compensator_name, dummy_compensator)

        def tool_action() -> str:
            return f"Executed {req.tool_name} successfully with params {req.params}"

        output, audit_rec = self._guard.execute_tool(
            tool_name=req.tool_name,
            intent=intent,
            action_fn=tool_action,
            params=req.params,
            agent_id=req.agent_id,
            approver_id=req.approver_id,
            connector_id=req.connector_id,
            connector_host=req.connector_host,
            required_scope=req.required_scope,
            hitl_confirmed=req.hitl_confirmed,
            compensator_name=req.compensator_name,
            compensation_params=req.compensation_params,
        )

        return ExecuteDualToolResponse(
            tool_name=req.tool_name,
            intent=intent.value,
            output=output,
            audit_record=_audit_to_dto(audit_rec) if audit_rec is not None else None,
        )

    def rollback_saga(self) -> SagaRollbackResponse:
        """Trigger declarative reverse LIFO rollback of all recorded emission steps."""
        step_count = self._saga_engine.step_count
        rollback_results = self._guard.rollback_saga()
        all_ok = all(success for _, success in rollback_results) if rollback_results else True
        return SagaRollbackResponse(
            total_steps_rolled_back=step_count,
            success=all_ok,
            details=rollback_results,
        )

    def get_audit_log(self) -> list[EmissionAuditRecordDto]:
        """Fetch full immutable emission audit trail."""
        records = self._guard.get_audit_log()
        return [_audit_to_dto(r) for r in records]


_service_instance: SagaDualEngineService | None = None


def get_saga_dual_engine_service() -> SagaDualEngineService:
    """Obtain or initialize the singleton SagaDualEngineService instance."""
    global _service_instance
    if _service_instance is None:
        _service_instance = SagaDualEngineService()
    return _service_instance
