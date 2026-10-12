"""Unit tests for ConnectorTrustService."""

from __future__ import annotations

import pytest

from app.core.integrations.catalog.trust_models import TrustTier
from app.core.integrations.catalog.trust_registry import CatalogTrustRegistry
from app.schemas.connector_trust import InstallationPreflightRequest
from app.services.security.connector_trust_service import ConnectorTrustService


@pytest.fixture
def service() -> ConnectorTrustService:
    # Use clean registry instance for unit tests
    reg = CatalogTrustRegistry()
    return ConnectorTrustService(registry=reg)


def test_get_official_verified_profile(service: ConnectorTrustService) -> None:
    profile = service.get_trust_profile("github")

    assert profile.connector_id == "github"
    assert profile.trust_tier == TrustTier.OFFICIAL_VERIFIED
    assert profile.review.status.value == "APPROVED"
    assert "list_issues" in profile.least_privilege.recommended_tools
    assert "delete_branch" in profile.least_privilege.sensitive_tools_isolated
    assert profile.provenance.pinned_version == "v0.6.2"


def test_get_unreviewed_fallback_profile(service: ConnectorTrustService) -> None:
    profile = service.get_trust_profile("unknown-thirdparty-server")

    assert profile.connector_id == "unknown-thirdparty-server"
    assert profile.trust_tier == TrustTier.UNREVIEWED
    assert profile.review.status.value == "PENDING_REVIEW"
    assert len(profile.least_privilege.recommended_tools) == 0
    assert "* (All unreviewed tools)" in profile.least_privilege.sensitive_tools_isolated


def test_installation_preflight_verified_vs_unreviewed(service: ConnectorTrustService) -> None:
    # 1. Official verified connector
    req_github = InstallationPreflightRequest(connector_id="github", target_version="v0.6.2")
    resp_github = service.evaluate_installation_preflight(req_github)

    assert resp_github.is_approved_for_install is True
    assert resp_github.requires_explicit_unreviewed_confirmation is False
    assert resp_github.has_provenance_drift is False
    assert resp_github.unreviewed_risk_disclosure is None
    assert "list_issues" in resp_github.recommended_tools

    # 2. Unreviewed connector
    req_unreviewed = InstallationPreflightRequest(connector_id="unverified-ai-agent-server")
    resp_unreviewed = service.evaluate_installation_preflight(req_unreviewed)

    assert resp_unreviewed.is_approved_for_install is False
    assert resp_unreviewed.requires_explicit_unreviewed_confirmation is True
    assert resp_unreviewed.unreviewed_risk_disclosure is not None
    assert "NOT audited by Myrm Security" in resp_unreviewed.unreviewed_risk_disclosure


def test_installation_preflight_provenance_drift_detected(
    service: ConnectorTrustService,
) -> None:
    # Target version diverges from pinned v0.6.2
    req_drift = InstallationPreflightRequest(
        connector_id="github", target_version="v99.0.0-unauthorized"
    )
    resp_drift = service.evaluate_installation_preflight(req_drift)

    assert resp_drift.has_provenance_drift is True
    assert resp_drift.is_approved_for_install is False
    assert "Version drift detected" in (resp_drift.drift_warning or "")


def test_continuous_review_and_installed_drift(service: ConnectorTrustService) -> None:
    # Record an installation with a drifted version
    service.record_installed_connector("slack", "v999.0.0-tampered")

    report = service.perform_continuous_review()
    assert report.total_audited >= 3
    assert any("slack: Version drift detected" in d for d in report.drift_alerts)


def test_unreviewed_disclosure_response(service: ConnectorTrustService) -> None:
    # 1. Unreviewed
    unrev = service.get_unreviewed_disclosure("some-random-mcp")
    assert unrev.risk_acknowledgement_required is True
    assert "SECURITY DISCLOSURE" in unrev.disclosure_text

    # 2. Reviewed
    rev = service.get_unreviewed_disclosure("github")
    assert rev.risk_acknowledgement_required is False
    assert "OFFICIAL_VERIFIED" in rev.disclosure_text
