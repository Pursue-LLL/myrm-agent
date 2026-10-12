"""Unit tests for LocalFirstVaultService."""

from __future__ import annotations

import base64

import pytest

from app.schemas.local_first_vault import (
    CreateE2eeShareRequest,
    DecryptE2eeShareRequest,
    DlpSanitizeRequest,
    RegisterLocalArtifactRequest,
)
from app.services.security.local_first_vault_service import (
    LocalFirstVaultService,
)


@pytest.fixture
def service() -> LocalFirstVaultService:
    """Create a fresh LocalFirstVaultService instance."""
    return LocalFirstVaultService()


def test_service_sanitize_content(service: LocalFirstVaultService) -> None:
    """Verify in-situ DLP sanitization masks all sensitive categories."""
    req = DlpSanitizeRequest(
        content="Deploy at node 10.0.0.15 on cluster.internal.corp. Contact: 13912345678. Price: $99,000.00.",
        enable_price_redaction=True,
    )
    res = service.sanitize_content(req)
    assert res.total_redactions == 4
    assert "10.0.0.15" not in res.sanitized_content
    assert "cluster.internal.corp" not in res.sanitized_content
    assert "13912345678" not in res.sanitized_content
    assert "$99,000.00" not in res.sanitized_content
    assert "[INTERNAL_IP_MASKED]" in res.sanitized_content
    assert "[CONFIDENTIAL_PRICE_REDACTED]" in res.sanitized_content


def test_service_register_and_get_local_artifact(
    service: LocalFirstVaultService,
) -> None:
    """Verify local-first disk artifact registration and non-cloud-synced invariant."""
    reg_req = RegisterLocalArtifactRequest(
        artifact_id="art_deck_01",
        title="Annual Strategic Pitch Deck",
        local_path="/mnt/volumes/user/deck.json",
        content="Confidential strategy content",
        storage_mode="local_first_disk",
    )
    item = service.register_local_artifact(reg_req)
    assert item.artifact_id == "art_deck_01"
    assert item.is_cloud_synced is False
    assert item.storage_mode == "local_first_disk"

    # Get by ID
    fetched = service.get_local_artifact("art_deck_01")
    assert fetched is not None
    assert fetched.artifact_id == "art_deck_01"

    # List
    items = service.list_local_artifacts()
    assert len(items) >= 1


def test_service_e2ee_share_and_decrypt(service: LocalFirstVaultService) -> None:
    """Verify end-to-end zero-knowledge share encryption and client key decryption."""
    # 1. Create E2EE share
    share_req = CreateE2eeShareRequest(
        artifact_id="art_deck_02",
        plaintext_content="Client node 192.168.1.20 agreed to fee $50,000.00.",
        ttl_seconds=3600,
        enable_dlp_sanitization=True,
    )
    share_res = service.create_e2ee_share(share_req)
    assert share_res.dlp_audit_passed is True
    assert share_res.ciphertext_b64 is not None
    assert share_res.client_key_b64 is not None
    assert "#share_id=" in share_res.share_url_fragment

    # 2. Decrypt with valid key
    decrypt_req = DecryptE2eeShareRequest(client_key_b64=share_res.client_key_b64)
    decrypted = service.decrypt_e2ee_share(share_res.share_id, decrypt_req)
    assert decrypted.share_id == share_res.share_id
    assert "192.168.1.20" not in decrypted.decrypted_content
    assert "[INTERNAL_IP_MASKED]" in decrypted.decrypted_content
    assert "[CONFIDENTIAL_PRICE_REDACTED]" in decrypted.decrypted_content

    # 3. Decrypt with invalid key fails
    fake_key_b64 = base64.b64encode(b"f" * 32).decode("utf-8")
    with pytest.raises(ValueError, match="does not match envelope proof"):
        service.decrypt_e2ee_share(
            share_res.share_id, DecryptE2eeShareRequest(client_key_b64=fake_key_b64)
        )
