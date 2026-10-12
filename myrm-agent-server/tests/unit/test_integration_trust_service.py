"""Unit tests for IntegrationTrustService."""

from __future__ import annotations

import pytest

from app.schemas.integration_trust import (
    DisconnectIntegrationRequest,
)
from app.services.security.integration_trust_service import (
    IntegrationTrustService,
)


@pytest.fixture
def sample_service() -> IntegrationTrustService:
    return IntegrationTrustService()


def test_get_and_list_disclosures(sample_service: IntegrationTrustService) -> None:
    # 1. Retrieve Google Workspace disclosure
    gw = sample_service.get_disclosure("google_workspace")
    assert gw is not None
    assert gw.provider_id == "google_workspace"
    assert "Gmail" in gw.display_name
    assert len(gw.data_types_read) > 0
    assert "purge all synced email memory trees" in gw.purge_policy_summary

    # 2. Retrieve GitHub disclosure
    gh = sample_service.get_disclosure("github")
    assert gh is not None
    assert gh.provider_id == "github"

    # 3. Retrieve non-existent disclosure
    none_disc = sample_service.get_disclosure("non_existent_provider")
    assert none_disc is None

    # 4. List all disclosures
    all_disc = sample_service.list_disclosures()
    assert len(all_disc) >= 3


def test_get_revoke_config(sample_service: IntegrationTrustService) -> None:
    cfg = sample_service.get_revoke_config("google_workspace")
    assert cfg is not None
    assert cfg.supports_remote_revoke is True
    assert cfg.revocation_endpoint == "https://oauth2.googleapis.com/revoke"
    assert cfg.manual_revoke_url == "https://myaccount.google.com/permissions"


def test_disconnect_provider_with_purge(sample_service: IntegrationTrustService) -> None:
    req = DisconnectIntegrationRequest(
        provider_id="google_workspace",
        purge_synced_data=True,
    )
    res = sample_service.disconnect_provider(req)
    assert res.success is True
    assert res.receipt.provider_id == "google_workspace"
    assert res.receipt.cleared_memory_trees >= 0
    assert res.receipt.revocation_status == "REVOKED_REMOTE"
    assert res.receipt.timestamp != ""


def test_disconnect_provider_without_purge(sample_service: IntegrationTrustService) -> None:
    req = DisconnectIntegrationRequest(
        provider_id="google_workspace",
        purge_synced_data=False,
    )
    res = sample_service.disconnect_provider(req)
    assert res.success is True
    assert res.receipt.cleared_memory_trees == 0
    assert res.receipt.cleared_documents == 0
    assert res.receipt.revocation_status == "REVOKED_REMOTE"
