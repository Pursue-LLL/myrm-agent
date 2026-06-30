"""Unit tests for VaultCredentialService (real DB, no mocks)."""

from __future__ import annotations

import pytest
from myrm_agent_harness.core.security.credential_vault import get_global_credential_vault

from app.services.security.vault_credential_service import VaultCredentialService


@pytest.fixture(autouse=True)
def _master_key(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.security.master_key import MasterKeyProvider

    MasterKeyProvider._reset_for_testing()
    monkeypatch.setenv("MYRM_MASTER_KEY", "test-master-key-vault-service")
    yield
    MasterKeyProvider._reset_for_testing()
    get_global_credential_vault().clear()


@pytest.mark.asyncio
async def test_save_and_sync_roundtrip() -> None:
    service = VaultCredentialService()
    await service.save_credential(
        label="svc-roundtrip",
        password="pw-123",
        totp_seed="JBSWY3DPEHPK3PXP",
        description="roundtrip test",
    )

    vault = get_global_credential_vault()
    assert vault.get_password("svc-roundtrip") == "pw-123"
    token = vault.get_totp_token("svc-roundtrip")
    assert len(token) == 6
    assert token.isdigit()

    vault.clear()
    await service.sync_all_to_vault()
    assert vault.get_password("svc-roundtrip") == "pw-123"


@pytest.mark.asyncio
async def test_update_description_only_preserves_vault_password() -> None:
    service = VaultCredentialService()
    await service.save_credential(label="svc-desc-only", password="keep-me")
    assert get_global_credential_vault().get_password("svc-desc-only") == "keep-me"

    await service.save_credential(label="svc-desc-only", description="metadata only")
    assert get_global_credential_vault().get_password("svc-desc-only") == "keep-me"


@pytest.mark.asyncio
async def test_delete_removes_from_vault() -> None:
    service = VaultCredentialService()
    await service.save_credential(label="svc-delete", password="pw-del")
    assert get_global_credential_vault().get_password("svc-delete") == "pw-del"

    deleted = await service.delete_credential("svc-delete")
    assert deleted is True
    with pytest.raises(KeyError):
        get_global_credential_vault().get_password("svc-delete")
