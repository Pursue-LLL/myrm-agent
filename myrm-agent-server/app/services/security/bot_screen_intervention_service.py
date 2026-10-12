"""
[POS] app/services/security/bot_screen_intervention_service.py
[INPUT] app.schemas.bot_screen_intervention, myrm_agent_harness.core.security.bot_screen_intervention
[OUTPUT] BotScreenInterventionService, get_bot_screen_intervention_service

Service layer for Bot Screen Auditable Operational Control & Intervention Evidence.
Coordinates enterprise screen action boundary checks, tamper-proof human takeover audit trails,
and autonomous post-action visual/DOM verification probes.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import logging

from fastapi import HTTPException, status
from myrm_agent_harness.core.security.bot_screen_intervention import (
    BotScreenAuditableControlSuite,
    InterventionEvidenceBundle,
    ScreenElementAction,
    ScreenRiskTier,
)

from app.schemas.bot_screen_intervention import (
    BotScreenOperationalMetricsResponse,
    ClassifyElementRiskRequest,
    ClassifyElementRiskResponse,
    EvaluateScreenActionRequest,
    EvaluateScreenActionResponse,
    InterventionEventResponse,
    InterventionEvidenceBundleResponse,
    RecordInterventionEventRequest,
    ScreenAssertionProbeResponse,
    SealEvidenceBundleRequest,
    StartInterventionRequest,
    StartInterventionResponse,
    VerifyScreenAssertionRequest,
)

logger = logging.getLogger(__name__)


class BotScreenInterventionService:
    """Service managing screen action operational boundaries and takeover audit evidence."""

    def __init__(self, suite: BotScreenAuditableControlSuite | None = None) -> None:
        self._suite = suite or BotScreenAuditableControlSuite()

    def classify_element_risk(self, request: ClassifyElementRiskRequest) -> ClassifyElementRiskResponse:
        """Classify screen UI element into an operational risk tier."""
        tier = self._suite.classify_element_risk(
            selector=request.selector,
            label=request.label,
            action_type=request.action_type,
        )
        return ClassifyElementRiskResponse(
            selector=request.selector,
            label=request.label,
            risk_tier=tier.value,
        )

    def evaluate_action(self, request: EvaluateScreenActionRequest) -> EvaluateScreenActionResponse:
        """Evaluate screen action against operational boundary policies."""
        try:
            tier_enum = ScreenRiskTier(request.risk_tier)
        except ValueError:
            tier_enum = ScreenRiskTier.STANDARD_WRITE

        action = ScreenElementAction(
            action_id=request.action_id,
            target_selector=request.target_selector,
            action_type=request.action_type,
            label=request.label,
            value_masked=request.value_masked,
            risk_tier=tier_enum,
        )
        decision, reason = self._suite.evaluate_action(action)

        return EvaluateScreenActionResponse(
            action_id=request.action_id,
            decision=decision.value,
            reason=reason,
        )

    def start_intervention(self, request: StartInterventionRequest) -> StartInterventionResponse:
        """Begin human takeover intervention session."""
        intervention_id = self._suite.start_intervention(
            session_id=request.session_id,
            operator_id=request.operator_id,
            before_snapshot_hash=request.before_snapshot_hash,
        )
        return StartInterventionResponse(
            intervention_id=intervention_id,
            session_id=request.session_id,
            operator_id=request.operator_id,
        )

    def record_event(self, request: RecordInterventionEventRequest) -> InterventionEventResponse:
        """Record sanitized event during active human takeover."""
        event = self._suite.record_intervention_event(
            intervention_id=request.intervention_id,
            event_type=request.event_type,
            target_selector=request.target_selector,
            raw_data=request.raw_data,
        )
        if event is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Active intervention session '{request.intervention_id}' not found or already sealed.",
            )
        return InterventionEventResponse(
            event_id=event.event_id,
            event_type=event.event_type,
            target_selector=event.target_selector,
            timestamp=event.timestamp,
            data_sanitized=event.data_sanitized,
        )

    def seal_evidence_bundle(self, request: SealEvidenceBundleRequest) -> InterventionEvidenceBundleResponse:
        """Seal cryptographic audit bundle upon human takeover completion."""
        bundle = self._suite.seal_intervention_bundle(
            intervention_id=request.intervention_id,
            after_snapshot_hash=request.after_snapshot_hash,
        )
        if bundle is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Active intervention session '{request.intervention_id}' not found to seal.",
            )
        return self._map_bundle(bundle)

    def get_evidence_bundle(self, intervention_id: str) -> InterventionEvidenceBundleResponse:
        """Retrieve sealed evidence bundle by intervention ID."""
        bundle = self._suite.get_evidence_bundle(intervention_id)
        if bundle is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Sealed evidence bundle '{intervention_id}' not found.",
            )
        return self._map_bundle(bundle)

    def verify_screen_assertion(self, request: VerifyScreenAssertionRequest) -> ScreenAssertionProbeResponse:
        """Run post-execution UI state assertion probe."""
        probe = self._suite.verify_screen_assertion(
            probe_id=request.probe_id,
            expected_selector=request.expected_selector,
            expected_text_contains=request.expected_text_contains,
            actual_text=request.actual_text,
            visual_hash_match=request.visual_hash_match,
        )
        return ScreenAssertionProbeResponse(
            probe_id=probe.probe_id,
            expected_selector=probe.expected_selector,
            passed=probe.passed,
            detail=probe.detail,
        )

    def get_metrics(self) -> BotScreenOperationalMetricsResponse:
        """Retrieve cumulative metrics for screen operations and takeover audits."""
        m = self._suite.metrics
        return BotScreenOperationalMetricsResponse(
            total_screen_actions=m.total_screen_actions,
            approval_checkpoints_triggered=m.approval_checkpoints_triggered,
            manual_takeovers_conducted=m.manual_takeovers_conducted,
            assertion_failures=m.assertion_failures,
            evidence_bundles_sealed=m.evidence_bundles_sealed,
        )

    @staticmethod
    def _map_bundle(bundle: InterventionEvidenceBundle) -> InterventionEvidenceBundleResponse:
        return InterventionEvidenceBundleResponse(
            session_id=bundle.session_id,
            intervention_id=bundle.intervention_id,
            operator_id=bundle.operator_id,
            start_time=bundle.start_time,
            end_time=bundle.end_time,
            before_snapshot_hash=bundle.before_snapshot_hash,
            after_snapshot_hash=bundle.after_snapshot_hash,
            event_count=bundle.event_count,
            bundle_sha256=bundle.bundle_sha256,
            is_tamper_evident=bundle.is_tamper_evident,
        )


_service_instance: BotScreenInterventionService | None = None


def get_bot_screen_intervention_service() -> BotScreenInterventionService:
    """Dependency provider for BotScreenInterventionService singleton."""
    global _service_instance
    if _service_instance is None:
        _service_instance = BotScreenInterventionService()
    return _service_instance
