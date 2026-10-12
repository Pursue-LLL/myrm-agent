"""Service orchestrating Session Provenance Tracker, Two-Stage Staging Gate, and Business Caps Guardrail.

[INPUT]
- RegisterSeenEntitiesRequest, CheckProvenanceRequest, StageChangeRequest
- IssueHostTokenRequest, ApplyStagedChangeRequest, CheckCapsRequest
- Harness SessionProvenanceTracker, TwoStageApprovalGate, BusinessCapsGuardrail, SerializedWriteLockManager

[OUTPUT]
- ProvenanceStagingService: enterprise security service managing session entity provenance and out-of-chat host staging.

[POS]
Server service layer. Enforces ID provenance checks and host token staging for business-critical mutations.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.provenance_gate import (
    BusinessCapsGuardrail,
    HostApprovalToken,
    SerializedWriteLockManager,
    SessionProvenanceTracker,
    StagedChangeDraft,
    TwoStageApprovalGate,
)

from app.schemas.provenance_staging import (
    ApplyStagedChangeRequest,
    CapsViolationDto,
    CheckCapsRequest,
    CheckCapsResponse,
    CheckProvenanceRequest,
    CheckProvenanceResponse,
    HostApprovalTokenDto,
    IssueHostTokenRequest,
    RegisterSeenEntitiesRequest,
    RegisterSeenEntitiesResponse,
    RejectStagedChangeRequest,
    StageChangeRequest,
    StagedChangeDraftDto,
)

logger = logging.getLogger(__name__)


def _draft_to_dto(domain: StagedChangeDraft) -> StagedChangeDraftDto:
    """Map Harness staged change draft domain model to Pydantic DTO."""
    return StagedChangeDraftDto(
        staged_id=domain.staged_id,
        session_id=domain.session_id,
        target_entity_id=domain.target_entity_id,
        mutation_type=domain.mutation_type,
        diff_payload=domain.diff_payload,
        status=str(domain.status),
        host_token_id=domain.host_token_id,
        created_at=domain.created_at,
        expires_at=domain.expires_at,
    )


def _token_dto_to_domain(dto: HostApprovalTokenDto) -> HostApprovalToken:
    """Map token DTO to Harness domain model."""
    return HostApprovalToken(
        token_id=dto.token_id,
        staged_id=dto.staged_id,
        operator_id=dto.operator_id,
        signature=dto.signature,
        issued_at=dto.issued_at,
        valid_until=dto.valid_until,
    )


def _token_to_dto(domain: HostApprovalToken) -> HostApprovalTokenDto:
    """Map token domain model to DTO."""
    return HostApprovalTokenDto(
        token_id=domain.token_id,
        staged_id=domain.staged_id,
        operator_id=domain.operator_id,
        signature=domain.signature,
        issued_at=domain.issued_at,
        valid_until=domain.valid_until,
    )


class ProvenanceStagingService:
    """Singleton service coordinating entity provenance, staged changes, and caps."""

    def __init__(
        self,
        tracker: SessionProvenanceTracker | None = None,
        staging_gate: TwoStageApprovalGate | None = None,
        caps_guardrail: BusinessCapsGuardrail | None = None,
        write_locks: SerializedWriteLockManager | None = None,
    ) -> None:
        self._tracker = tracker or SessionProvenanceTracker()
        self._staging_gate = staging_gate or TwoStageApprovalGate()
        self._caps_guardrail = caps_guardrail or BusinessCapsGuardrail()
        self._write_locks = write_locks or SerializedWriteLockManager()

    @property
    def tracker(self) -> SessionProvenanceTracker:
        """Underlying provenance tracker."""
        return self._tracker

    @property
    def staging_gate(self) -> TwoStageApprovalGate:
        """Underlying staging gate."""
        return self._staging_gate

    @property
    def caps_guardrail(self) -> BusinessCapsGuardrail:
        """Underlying business caps guardrail."""
        return self._caps_guardrail

    @property
    def write_locks(self) -> SerializedWriteLockManager:
        """Underlying write lock manager."""
        return self._write_locks

    def register_seen_entities(self, request: RegisterSeenEntitiesRequest) -> RegisterSeenEntitiesResponse:
        """Register entities observed by read tools in a session."""
        self._tracker.record_observed_entities(
            session_id=request.session_id,
            entity_ids=request.entity_ids,
            entity_type=request.entity_type,
            source_tool=request.source_tool,
        )
        total_observed = len(self._tracker.list_observed_entities(request.session_id))
        return RegisterSeenEntitiesResponse(
            session_id=request.session_id,
            registered_count=len(request.entity_ids),
            total_observed_count=total_observed,
        )

    def check_provenance(self, request: CheckProvenanceRequest) -> CheckProvenanceResponse:
        """Check whether candidate entity ID was observed before permitting mutation."""
        is_observed = self._tracker.is_entity_observed(request.session_id, request.entity_id)
        if is_observed:
            return CheckProvenanceResponse(
                session_id=request.session_id,
                entity_id=request.entity_id,
                allowed=True,
                reason="Entity verified in session provenance cache",
            )
        return CheckProvenanceResponse(
            session_id=request.session_id,
            entity_id=request.entity_id,
            allowed=False,
            reason=f"Entity '{request.entity_id}' has not been observed in session '{request.session_id}'",
        )

    def stage_change(self, request: StageChangeRequest) -> StagedChangeDraftDto:
        """Stage a mutation draft prior to host authorization."""
        draft = self._staging_gate.stage_change(
            session_id=request.session_id,
            target_entity_id=request.target_entity_id,
            mutation_type=request.mutation_type,
            diff_payload=request.diff_payload,
            ttl_seconds=request.ttl_seconds,
        )
        return _draft_to_dto(draft)

    def issue_host_token(self, request: IssueHostTokenRequest) -> HostApprovalTokenDto:
        """Issue an authentic host signed authorization token."""
        token = self._staging_gate.issue_host_approval_token(
            staged_id=request.staged_id,
            operator_id=request.operator_id,
            ttl_seconds=request.ttl_seconds,
        )
        return _token_to_dto(token)

    def apply_staged_change(self, request: ApplyStagedChangeRequest) -> StagedChangeDraftDto:
        """Apply a staged change presenting host signed authorization token."""
        domain_token = _token_dto_to_domain(request.token)
        applied = self._staging_gate.apply_staged_change(request.staged_id, domain_token)
        return _draft_to_dto(applied)

    def reject_staged_change(self, request: RejectStagedChangeRequest) -> StagedChangeDraftDto:
        """Reject and cancel a staged mutation draft."""
        rejected = self._staging_gate.reject_staged_change(request.staged_id)
        return _draft_to_dto(rejected)

    def get_staged_change(self, staged_id: str) -> StagedChangeDraftDto | None:
        """Retrieve staged draft details by ID."""
        draft = self._staging_gate.get_staged_change(staged_id)
        return _draft_to_dto(draft) if draft else None

    def list_staged_changes(self, session_id: str | None = None) -> list[StagedChangeDraftDto]:
        """List active staged changes."""
        changes = self._staging_gate.list_staged_changes(session_id=session_id)
        return [_draft_to_dto(c) for c in changes]

    def check_caps(self, request: CheckCapsRequest) -> CheckCapsResponse:
        """Validate input parameters against hardcoded Python caps."""
        violations = self._caps_guardrail.check_caps(
            discount_percent=request.discount_percent,
            affected_rows=request.affected_rows,
            budget_delta=request.budget_delta,
        )
        passed = len(violations) == 0
        dtos = [
            CapsViolationDto(
                parameter_name=v.parameter_name,
                attempted_value=v.attempted_value,
                max_allowed_value=v.max_allowed_value,
                compliant_alternative=v.compliant_alternative,
                message=v.message,
            )
            for v in violations
        ]
        return CheckCapsResponse(passed=passed, violations=dtos)


# Global singleton instance
default_provenance_staging_service = ProvenanceStagingService()
