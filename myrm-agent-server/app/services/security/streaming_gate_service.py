"""Streaming Endpoint Identity Gate Parity Service.

[INPUT]
- EvaluateStreamingAccessRequest, StreamingEndpointContractDto.

[OUTPUT]
- EvaluateStreamingAccessResponse, StreamingParityAuditResponse, StreamingEndpointContractDto list.

[POS]
- Server security service. Wraps harness StreamingIdentityGateEvaluator to enforce
  strict REST-parity authentication and scope bindings on long-lived event streams.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.streaming_gate import (
    GateDecision,
    StreamingClientIdentity,
    StreamingEndpointContract,
    StreamingEndpointRegistry,
    StreamingIdentityGateEvaluator,
    StreamingParityAuditIssue,
    StreamingTransport,
)

from app.schemas.streaming_gate import (
    EvaluateStreamingAccessRequest,
    EvaluateStreamingAccessResponse,
    StreamingClientIdentityDto,
    StreamingEndpointContractDto,
    StreamingGateVerdictDto,
    StreamingParityAuditIssueDto,
    StreamingParityAuditResponse,
)

logger = logging.getLogger(__name__)

DEFAULT_STREAMING_CONTRACTS: tuple[StreamingEndpointContract, ...] = (
    StreamingEndpointContract(
        endpoint_path="/api/v1/agents/general_agent/streaming",
        transport=StreamingTransport.SERVER_SENT_EVENTS,
        requires_auth=True,
        required_scope="chat:stream",
        target_resource_type="chat",
        supports_remote_access=True,
    ),
    StreamingEndpointContract(
        endpoint_path="/api/v1/tasks/stream",
        transport=StreamingTransport.SERVER_SENT_EVENTS,
        requires_auth=True,
        required_scope="tasks:stream",
        target_resource_type="task",
        supports_remote_access=True,
    ),
    StreamingEndpointContract(
        endpoint_path="/api/v1/events/notifications/stream",
        transport=StreamingTransport.SERVER_SENT_EVENTS,
        requires_auth=True,
        required_scope="notifications:stream",
        target_resource_type="notification",
        supports_remote_access=True,
    ),
    StreamingEndpointContract(
        endpoint_path="/api/v1/eval/stream",
        transport=StreamingTransport.SERVER_SENT_EVENTS,
        requires_auth=True,
        required_scope="eval:stream",
        target_resource_type="eval",
        supports_remote_access=True,
    ),
    StreamingEndpointContract(
        endpoint_path="/api/v1/eval/matrix/stream",
        transport=StreamingTransport.SERVER_SENT_EVENTS,
        requires_auth=True,
        required_scope="eval:stream",
        target_resource_type="eval",
        supports_remote_access=True,
    ),
    StreamingEndpointContract(
        endpoint_path="/api/v1/wiki/ingest_stream",
        transport=StreamingTransport.SERVER_SENT_EVENTS,
        requires_auth=True,
        required_scope="wiki:stream",
        target_resource_type="wiki",
        supports_remote_access=True,
    ),
    StreamingEndpointContract(
        endpoint_path="/api/v1/workspace/stream",
        transport=StreamingTransport.SERVER_SENT_EVENTS,
        requires_auth=True,
        required_scope="workspace:stream",
        target_resource_type="workspace",
        supports_remote_access=True,
    ),
)


def _to_domain_contract(dto: StreamingEndpointContractDto) -> StreamingEndpointContract:
    return StreamingEndpointContract(
        endpoint_path=dto.endpoint_path,
        transport=StreamingTransport(dto.transport),
        requires_auth=dto.requires_auth,
        required_scope=dto.required_scope,
        target_resource_type=dto.target_resource_type,
        supports_remote_access=dto.supports_remote_access,
    )


def _to_dto_contract(domain: StreamingEndpointContract) -> StreamingEndpointContractDto:
    return StreamingEndpointContractDto(
        endpoint_path=domain.endpoint_path,
        transport=domain.transport.value,
        requires_auth=domain.requires_auth,
        required_scope=domain.required_scope,
        target_resource_type=domain.target_resource_type,
        supports_remote_access=domain.supports_remote_access,
    )


def _to_domain_identity(dto: StreamingClientIdentityDto) -> StreamingClientIdentity:
    return StreamingClientIdentity(
        subject_id=dto.subject_id,
        auth_source=dto.auth_source,
        granted_scopes=tuple(dto.granted_scopes),
        bound_resource_ids=tuple(dto.bound_resource_ids),
        is_loopback=dto.is_loopback,
        is_remote=dto.is_remote,
    )


def _to_dto_issue(domain: StreamingParityAuditIssue) -> StreamingParityAuditIssueDto:
    return StreamingParityAuditIssueDto(
        endpoint_path=domain.endpoint_path,
        transport=domain.transport.value,
        issue_type=domain.issue_type,
        description=domain.description,
        severity=domain.severity,
    )


class StreamingGateService:
    """Service governing streaming endpoint identity gate parity and audits."""

    def __init__(self) -> None:
        self._registry = StreamingEndpointRegistry()
        self._registry.register_contracts(DEFAULT_STREAMING_CONTRACTS)
        self._evaluator = StreamingIdentityGateEvaluator(registry=self._registry)

    def list_contracts(self) -> list[StreamingEndpointContractDto]:
        """List all declared streaming endpoint contracts."""
        return [_to_dto_contract(c) for c in self._registry.list_contracts()]

    def register_contract(self, contract_dto: StreamingEndpointContractDto) -> None:
        """Register or update a streaming endpoint security contract."""
        domain_contract = _to_domain_contract(contract_dto)
        self._registry.register_contract(domain_contract)

    def evaluate_access(
        self, req: EvaluateStreamingAccessRequest
    ) -> EvaluateStreamingAccessResponse:
        """Evaluate access for a client identity connecting to a streaming endpoint."""
        contract = self._registry.get_contract(req.endpoint_path)
        if contract is None:
            # Default conservative contract for uncatalogued streaming routes
            contract = StreamingEndpointContract(
                endpoint_path=req.endpoint_path,
                transport=StreamingTransport.SERVER_SENT_EVENTS,
                requires_auth=True,
                required_scope=None,
            )

        identity = _to_domain_identity(req.client_identity)
        verdict = self._evaluator.evaluate_access(
            contract=contract,
            identity=identity,
            requested_resource_id=req.requested_resource_id,
        )

        allowed = verdict.decision == GateDecision.ALLOWED
        return EvaluateStreamingAccessResponse(
            verdict=StreamingGateVerdictDto(
                decision=verdict.decision.value,
                endpoint_path=verdict.endpoint_path,
                reason=verdict.reason,
                status_code=verdict.status_code,
            ),
            allowed=allowed,
        )

    def run_parity_audit(self) -> StreamingParityAuditResponse:
        """Perform systematic parity audit across all registered streaming contracts."""
        contracts = self._registry.list_contracts()
        issues = self._evaluator.audit_parity(contracts)

        return StreamingParityAuditResponse(
            total_endpoints_evaluated=len(contracts),
            total_issues_found=len(issues),
            is_compliant=len(issues) == 0,
            issues=[_to_dto_issue(i) for i in issues],
        )


_service_instance: StreamingGateService | None = None


def get_streaming_gate_service() -> StreamingGateService:
    """Obtain or initialize singleton StreamingGateService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = StreamingGateService()
    return _service_instance
