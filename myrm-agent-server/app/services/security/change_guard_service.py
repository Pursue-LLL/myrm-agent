"""Service layer for Agent Authority ChangeGuard review decision lanes and evidence hardening.

[INPUT]
- EvaluateChangesRequest DTOs.

[OUTPUT]
- EvaluateChangesResponse DTOs containing separated Lane A gates and Lane B review questions.

[POS]
- Server service layer providing SafeAI ChangeGuard WS1-WS5 compliance.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.change_guard import (
    CanonicalOutcome,
    ChangeClass,
    ChangeGuard,
    ChangeGuardEvaluationResult,
    ChangeGuardException,
    ChangeGuardExceptionsManager,
    ChangeGuardPolicyConfig,
    EvidenceRecord,
    EvidenceType,
    Gateability,
    HardenedFinding,
    LaneDecisionSummary,
    ProvenanceClass,
)

from app.schemas.change_guard import (
    ChangeGuardConfigSummary,
    ChangeGuardExceptionDto,
    EvaluateChangesRequest,
    EvaluateChangesResponse,
    EvidenceRecordDto,
    HardenedFindingDto,
    LaneDecisionSummaryDto,
)

logger = logging.getLogger(__name__)


def _to_harness_finding(dto: HardenedFindingDto) -> HardenedFinding:
    """Convert API DTO finding to harness HardenedFinding domain object."""
    ev_raw = dto.evidence.evidence_type.replace("_", "-").lower()
    ev_type = EvidenceType(ev_raw)
    ch_class = ChangeClass(dto.change_class.upper())
    prov_class = ProvenanceClass(dto.provenance_class.lower())
    gate_raw = dto.gateability.replace("_", "-").lower()
    gate_class = Gateability(gate_raw)

    evidence = EvidenceRecord(
        evidence_type=ev_type,
        source_file=dto.evidence.source_file,
        line_number=dto.evidence.line_number,
        pattern_matched=dto.evidence.pattern_matched,
        sha256_digest=dto.evidence.sha256_digest,
        description=dto.evidence.description,
    )

    return HardenedFinding(
        finding_id=dto.finding_id,
        rule_id=dto.rule_id,
        category=dto.category,
        target_object=dto.target_object,
        change_class=ch_class,
        provenance_class=prov_class,
        gateability=gate_class,
        evidence=evidence,
        message=dto.message,
    )


def _to_harness_exception(dto: ChangeGuardExceptionDto) -> ChangeGuardException:
    """Convert API DTO exception to harness ChangeGuardException domain object."""
    return ChangeGuardException(
        exception_id=dto.exception_id,
        finding_or_rule_id=dto.finding_or_rule_id,
        scope=dto.scope,
        risk_owner=dto.risk_owner,
        rationale=dto.rationale,
        compensating_controls=dto.compensating_controls,
        expires_at=dto.expires_at,
        review_trigger=dto.review_trigger,
    )


def _to_dto_finding(f: HardenedFinding) -> HardenedFindingDto:
    """Convert harness HardenedFinding to API DTO."""
    ev_dto = EvidenceRecordDto(
        evidence_type=f.evidence.evidence_type.value,
        source_file=f.evidence.source_file,
        line_number=f.evidence.line_number,
        pattern_matched=f.evidence.pattern_matched,
        sha256_digest=f.evidence.sha256_digest,
        description=f.evidence.description,
    )
    return HardenedFindingDto(
        finding_id=f.finding_id,
        rule_id=f.rule_id,
        category=f.category,
        target_object=f.target_object,
        change_class=f.change_class.value,
        provenance_class=f.provenance_class.value,
        gateability=f.gateability.value,
        evidence=ev_dto,
        message=f.message,
    )


def _to_dto_lane_summary(summary: LaneDecisionSummary) -> LaneDecisionSummaryDto:
    """Convert harness LaneDecisionSummary to API DTO."""
    return LaneDecisionSummaryDto(
        lane=summary.lane.value,
        outcome=summary.outcome.value,
        findings=[_to_dto_finding(f) for f in summary.findings],
        unresolved_questions=list(summary.unresolved_questions),
    )


def _to_dto_response(res: ChangeGuardEvaluationResult) -> EvaluateChangesResponse:
    """Convert consolidated harness evaluation result to API response DTO."""
    return EvaluateChangesResponse(
        overall_outcome=res.overall_outcome.value,
        lane_a=_to_dto_lane_summary(res.lane_a),
        lane_b=_to_dto_lane_summary(res.lane_b),
        highest_change_class=res.highest_change_class.value,
        applied_exceptions=list(res.applied_exceptions),
        stale_or_expired_exceptions=list(res.stale_or_expired_exceptions),
    )


class ChangeGuardService:
    """Service wrapping ChangeGuard evaluation and governance workflows."""

    def evaluate_changes(self, request: EvaluateChangesRequest) -> EvaluateChangesResponse:
        """Evaluate change findings against review decision lanes and authority gates."""
        harness_findings = tuple(_to_harness_finding(f) for f in request.findings)
        harness_exceptions = tuple(_to_harness_exception(e) for e in request.exceptions)

        auth_threshold = (
            ChangeClass(request.fail_on_authority_change.upper())
            if request.fail_on_authority_change is not None
            else None
        )

        config = ChangeGuardPolicyConfig(
            fail_on_authority_change=auth_threshold,
            enforce_definition_review_floor=request.enforce_definition_review_floor,
            strict_exceptions=request.strict_exceptions,
        )

        exceptions_mgr = ChangeGuardExceptionsManager(harness_exceptions)
        guard = ChangeGuard(config=config, exceptions_manager=exceptions_mgr)

        result = guard.evaluate_changes(
            findings=harness_findings,
            current_time_iso=request.current_time_iso,
        )

        if result.overall_outcome in (CanonicalOutcome.BLOCK, CanonicalOutcome.REVIEW_REQUIRED):
            logger.info(
                "ChangeGuard evaluation yielded %s: lane_a=%s, lane_b=%s, highest=%s",
                result.overall_outcome.value,
                result.lane_a.outcome.value,
                result.lane_b.outcome.value,
                result.highest_change_class.value,
            )

        return _to_dto_response(result)

    def get_config_summary(self) -> ChangeGuardConfigSummary:
        """Return supported ChangeGuard configuration options and classification enums."""
        return ChangeGuardConfigSummary(
            supported_change_classes=[c.value for c in ChangeClass],
            supported_provenance_classes=[p.value for p in ProvenanceClass],
            supported_evidence_types=[e.value for e in EvidenceType],
            definition_prefixes=[
                "PROMPT_",
                "PROMPT_FILE_",
                "SKILL_",
                "TOOL_DEF_",
                "MODEL_CONFIG_",
                "WORKFLOW_",
                "CC_",
            ],
        )


_service_instance: ChangeGuardService | None = None


def get_change_guard_service() -> ChangeGuardService:
    """FastAPI dependency provider for ChangeGuardService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = ChangeGuardService()
    return _service_instance
