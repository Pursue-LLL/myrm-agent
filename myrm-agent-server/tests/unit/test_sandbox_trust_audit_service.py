"""Unit tests for SandboxTrustAuditService."""

from __future__ import annotations

import pytest

from app.schemas.sandbox_trust_audit import (
    GetBoundaryCardRequest,
    GetTrustBadgeRequest,
    SandboxHealthAuditRequest,
)
from app.services.security.sandbox_trust_audit_service import (
    SandboxTrustAuditService,
)


@pytest.fixture
def service() -> SandboxTrustAuditService:
    """Create a fresh SandboxTrustAuditService instance."""
    return SandboxTrustAuditService()


def test_service_run_audit_clean(service: SandboxTrustAuditService) -> None:
    """Verify that a clean sandbox environment passes health audit with 100 score."""
    req = SandboxHealthAuditRequest(
        environment_id="env_unit_clean",
        isolation_level="cloud_dedicated_sandbox",
        mounted_paths=["/workspace", "/tmp/sandbox"],
        env_vars={"NODE_ENV": "development"},
        is_root=False,
        egress_monitored=True,
    )
    report = service.run_audit(req)
    assert report.passed is True
    assert report.score == 100
    assert len(report.checks) == 4
    assert all(c.status == "pass" for c in report.checks)


def test_service_run_audit_violations(service: SandboxTrustAuditService) -> None:
    """Verify that host filesystem mount leaks and raw credentials trigger failures."""
    req = SandboxHealthAuditRequest(
        environment_id="env_unit_leaky",
        isolation_level="local_restricted_container",
        mounted_paths=["/workspace", "~/.ssh", "/var/run/docker.sock"],
        env_vars={"STRIPE_SECRET_KEY": "sk_test_1234567890"},
        is_root=True,
        egress_monitored=False,
    )
    report = service.run_audit(req)
    assert report.passed is False
    assert report.score <= 40
    failed_checks = [c for c in report.checks if c.status == "fail"]
    assert len(failed_checks) >= 2


def test_service_get_trust_badge(service: SandboxTrustAuditService) -> None:
    """Verify dynamic trust level badge computation across isolation levels."""
    # 1. Cloud dedicated
    badge_cloud = service.get_trust_badge(
        GetTrustBadgeRequest(
            isolation_level="cloud_dedicated_sandbox",
            audit_score=95,
        )
    )
    assert badge_cloud.trust_grade == "maximum_isolation"
    assert badge_cloud.color_hex == "#10B981"
    assert "云托管专属沙箱" in badge_cloud.badge_label

    # 2. Host direct
    badge_host = service.get_trust_badge(
        GetTrustBadgeRequest(
            isolation_level="host_direct_full_trust",
            audit_score=40,
        )
    )
    assert badge_host.trust_grade == "unconfined_host"
    assert badge_host.color_hex == "#F59E0B"


def test_service_get_boundary_card(service: SandboxTrustAuditService) -> None:
    """Verify permission boundary card generation."""
    card = service.get_boundary_card(
        GetBoundaryCardRequest(
            environment_id="env_unit_card",
            isolation_level="cloud_dedicated_sandbox",
            allowed_paths=["/workspace", "/data"],
        )
    )
    assert card.environment_id == "env_unit_card"
    assert "/workspace" in card.allowed_paths
    assert "~/.ssh" in card.denied_paths
    assert len(card.active_guards) >= 3
    assert "Sentinel" in card.egress_policy
