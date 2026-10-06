"""
[POS] app/services/security/browser_human_handoff_service.py
[INPUT] myrm_agent_harness.core.security.browser_human_handoff, app.schemas.browser_human_handoff
[OUTPUT] BrowserHumanHandoffService, get_browser_human_handoff_service

Service layer for Browser Human Handoff Gate Suite.
Orchestrates page safety inspections, mutual-exclusion browser profile leases,
and human intervention lifecycle.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.browser_human_handoff import (
    BrowserHumanHandoffGateSuite,
    BrowserProfileLease,
    DOMContentHealthInspection,
    HandoffInterceptionResult,
)

from app.schemas.browser_human_handoff import (
    AcquireBrowserLeaseRequest,
    BrowserHumanHandoffMetricsResponse,
    BrowserProfileLeaseResponse,
    DOMContentHealthResponse,
    HandoffInterceptionResponse,
    InspectPageSafetyRequest,
    InspectPageSafetyResponse,
    ReleaseBrowserLeaseRequest,
    ResolveHandoffRequest,
)

logger = logging.getLogger(__name__)


class BrowserHumanHandoffService:
    """Business service governing browser human handoffs and profile leases."""

    def __init__(self, suite: BrowserHumanHandoffGateSuite | None = None) -> None:
        self._suite = suite or BrowserHumanHandoffGateSuite()

    def inspect_page_safety(self, request: InspectPageSafetyRequest) -> InspectPageSafetyResponse:
        """Inspect extracted page DOM for anti-bot challenges and empty-content corruptions."""
        interception, health = self._suite.inspect_page_safety(
            html_or_dom=request.html_or_dom,
            url=request.url,
        )
        return InspectPageSafetyResponse(
            interception=self._map_interception(interception),
            health=self._map_health(health),
        )

    def resolve_handoff(self, request: ResolveHandoffRequest) -> HandoffInterceptionResponse:
        """Resolve a pending handoff gate after human operator completes the challenge."""
        resolved = self._suite.resolve_handoff(request.interception_id)
        return self._map_interception(resolved)

    def list_pending_handoffs(self) -> list[HandoffInterceptionResponse]:
        """List all browser screens currently awaiting human assistance."""
        pending = self._suite.list_pending_handoffs()
        return [self._map_interception(item) for item in pending]

    def acquire_lease(self, request: AcquireBrowserLeaseRequest) -> BrowserProfileLeaseResponse:
        """Acquire an exclusive profile lease for an agent task."""
        lease = self._suite.acquire_profile_lease(
            profile_name=request.profile_name,
            consumer_id=request.consumer_id,
            ttl_seconds=request.ttl_seconds,
        )
        return self._map_lease(lease)

    def release_lease(self, request: ReleaseBrowserLeaseRequest) -> BrowserProfileLeaseResponse:
        """Release an active browser profile lease."""
        released = self._suite.release_profile_lease(request.lease_id)
        return self._map_lease(released)

    def get_active_lease(self, profile_name: str) -> BrowserProfileLeaseResponse | None:
        """Retrieve current valid lease for a browser profile if present."""
        lease = self._suite.get_active_lease(profile_name)
        if lease is None:
            return None
        return self._map_lease(lease)

    def list_active_leases(self) -> list[BrowserProfileLeaseResponse]:
        """List all active non-expired browser profile leases."""
        leases = self._suite.list_active_leases()
        return [self._map_lease(item) for item in leases]

    def get_metrics(self) -> BrowserHumanHandoffMetricsResponse:
        """Retrieve metrics snapshot."""
        metrics = self._suite.metrics
        return BrowserHumanHandoffMetricsResponse(
            captcha_interceptions_total=metrics.captcha_interceptions_total,
            confirm_screens_intercepted_total=metrics.confirm_screens_intercepted_total,
            zero_content_corruptions_detected_total=metrics.zero_content_corruptions_detected_total,
            browser_leases_granted_total=metrics.browser_leases_granted_total,
            browser_leases_released_total=metrics.browser_leases_released_total,
            handoffs_resolved_total=metrics.handoffs_resolved_total,
        )

    @staticmethod
    def _map_interception(item: HandoffInterceptionResult) -> HandoffInterceptionResponse:
        return HandoffInterceptionResponse(
            interception_id=item.interception_id,
            trigger_type=item.trigger_type.value if item.trigger_type else None,
            matched_selector=item.matched_selector,
            is_handoff_required=item.is_handoff_required,
            explanation=item.explanation,
            is_resolved=item.is_resolved,
            timestamp=item.timestamp,
        )

    @staticmethod
    def _map_health(item: DOMContentHealthInspection) -> DOMContentHealthResponse:
        return DOMContentHealthResponse(
            url=item.url,
            content_length=item.content_length,
            node_count=item.node_count,
            is_corrupted_zero_content=item.is_corrupted_zero_content,
            diagnosis=item.diagnosis,
            timestamp=item.timestamp,
        )

    @staticmethod
    def _map_lease(item: BrowserProfileLease) -> BrowserProfileLeaseResponse:
        return BrowserProfileLeaseResponse(
            lease_id=item.lease_id,
            profile_name=item.profile_name,
            consumer_id=item.consumer_id,
            acquired_at=item.acquired_at,
            ttl_seconds=item.ttl_seconds,
            status=item.status.value,
        )


_default_service: BrowserHumanHandoffService | None = None


def get_browser_human_handoff_service() -> BrowserHumanHandoffService:
    """Dependency provider returning singleton instance of BrowserHumanHandoffService."""
    global _default_service
    if _default_service is None:
        _default_service = BrowserHumanHandoffService()
    return _default_service

