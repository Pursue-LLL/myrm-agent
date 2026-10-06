"""Service layer for Connector Catalog Trust Grading and Server Review Provenance.

[INPUT]
- CatalogTrustRegistry and connector inspection requests.

[OUTPUT]
- ConnectorTrustService, get_connector_trust_service.

[POS]
- app.services.security.connector_trust_service
"""

from __future__ import annotations

import logging
import time

from app.core.integrations.catalog.trust_models import (
    CatalogTrustProfile,
    TrustTier,
)
from app.core.integrations.catalog.trust_registry import CatalogTrustRegistry
from app.schemas.connector_trust import (
    CatalogTrustProfileResponse,
    ContinuousReviewReportResponse,
    InstallationPreflightRequest,
    InstallationPreflightResponse,
    UnreviewedDisclosureResponse,
)

logger = logging.getLogger(__name__)


class ConnectorTrustService:
    """Manages connector catalog trust grading, installation preflight, and continuous review."""

    def __init__(self, registry: CatalogTrustRegistry | None = None) -> None:
        self._registry = registry or CatalogTrustRegistry.get_instance()

    @property
    def registry(self) -> CatalogTrustRegistry:
        return self._registry

    def get_trust_profile(self, connector_id: str) -> CatalogTrustProfileResponse:
        """Fetch trust classification profile for connector."""
        profile: CatalogTrustProfile = self._registry.get_profile(connector_id)
        return CatalogTrustProfileResponse(
            connector_id=profile.connector_id,
            trust_tier=profile.trust_tier,
            review=profile.review,
            capabilities=profile.capabilities,
            least_privilege=profile.least_privilege,
            provenance=profile.provenance,
        )

    def list_trust_profiles(self) -> list[CatalogTrustProfileResponse]:
        """List all verified and reviewed connector profiles."""
        profiles = self._registry.list_profiles()
        return [
            CatalogTrustProfileResponse(
                connector_id=p.connector_id,
                trust_tier=p.trust_tier,
                review=p.review,
                capabilities=p.capabilities,
                least_privilege=p.least_privilege,
                provenance=p.provenance,
            )
            for p in profiles
        ]

    def evaluate_installation_preflight(
        self, req: InstallationPreflightRequest
    ) -> InstallationPreflightResponse:
        """Evaluate connector safety, least-privilege boundary, and provenance drift before installation."""
        profile: CatalogTrustProfile = self._registry.get_profile(req.connector_id)
        target_ver = req.target_version or profile.provenance.pinned_version

        is_unreviewed = profile.trust_tier == TrustTier.UNREVIEWED
        has_drift = False
        drift_msg: str | None = None

        if not is_unreviewed:
            has_drift, drift_msg = self._registry.check_provenance_drift(
                req.connector_id, target_ver
            )

        disclosure: str | None = None
        if is_unreviewed:
            disclosure = (
                f"Notice: The connector '{req.connector_id}' is NOT audited by Myrm Security. "
                f"MCP servers execute with the host process permissions. Proceeding gives this server "
                f"access to your system. Review source code carefully before enabling."
            )

        is_approved = profile.trust_tier in (
            TrustTier.OFFICIAL_VERIFIED,
            TrustTier.COMMUNITY_REVIEWED,
        ) and not has_drift

        logger.info(
            "Preflight evaluated for connector %s: tier=%s, approved=%s, drift=%s",
            req.connector_id,
            profile.trust_tier.value,
            is_approved,
            has_drift,
        )

        return InstallationPreflightResponse(
            connector_id=req.connector_id,
            trust_tier=profile.trust_tier.value,
            is_approved_for_install=is_approved,
            requires_explicit_unreviewed_confirmation=is_unreviewed,
            unreviewed_risk_disclosure=disclosure,
            recommended_tools=profile.least_privilege.recommended_tools,
            sensitive_tools_isolated=profile.least_privilege.sensitive_tools_isolated,
            rationale=profile.least_privilege.rationale,
            pinned_version=profile.provenance.pinned_version,
            has_provenance_drift=has_drift,
            drift_warning=drift_msg if has_drift else None,
        )

    def record_installed_connector(self, connector_id: str, version: str) -> None:
        """Register active installed version for drift tracking."""
        self._registry.record_installation(connector_id, version)

    def perform_continuous_review(self) -> ContinuousReviewReportResponse:
        """Scan active profiles for expiration and version provenance drift."""
        now = time.time()
        expired, drifts = self._registry.perform_continuous_review()
        total = len(self._registry.list_profiles())
        logger.info(
            "Continuous review completed: total=%d, expired=%d, drifts=%d",
            total,
            len(expired),
            len(drifts),
        )
        return ContinuousReviewReportResponse(
            total_audited=total,
            expired_revocations=expired,
            drift_alerts=drifts,
            audit_timestamp=now,
        )

    def get_unreviewed_disclosure(self, connector_id: str) -> UnreviewedDisclosureResponse:
        """Generate honest risk disclosure for unreviewed integration entries."""
        profile = self._registry.get_profile(connector_id)
        if profile.trust_tier != TrustTier.UNREVIEWED:
            return UnreviewedDisclosureResponse(
                connector_id=connector_id,
                disclosure_text=f"Connector '{connector_id}' is verified under {profile.trust_tier.value}.",
                risk_acknowledgement_required=False,
            )

        text = (
            f"SECURITY DISCLOSURE: '{connector_id}' is an unreviewed third-party connector. "
            f"Unlike sandboxed environments, MCP tools run with full local process permissions. "
            f"Untrusted tools can read system files, environment variables, or initiate unauthorized egress. "
            f"You must explicitly acknowledge and assume full responsibility before connecting."
        )
        return UnreviewedDisclosureResponse(
            connector_id=connector_id,
            disclosure_text=text,
            risk_acknowledgement_required=True,
        )


_service_instance: ConnectorTrustService | None = None


def get_connector_trust_service() -> ConnectorTrustService:
    """Singleton provider for ConnectorTrustService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = ConnectorTrustService()
    return _service_instance
