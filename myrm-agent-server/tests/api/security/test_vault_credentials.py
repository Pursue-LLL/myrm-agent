"""Integration tests for vault credentials REST API (no mocks, real DB)."""

import pytest
from fastapi.testclient import TestClient

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="security")
@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_create_vault_credential_syncs_to_global_vault(client: TestClient) -> None:
    from myrm_agent_harness.core.security.credential_vault import get_global_credential_vault

    get_global_credential_vault().clear()
    response = client.post(
        "/api/v1/security/vault-credentials",
        json={
            "label": "api-vault-sync",
            "password": "api-sync-pw",
            "totp_seed": "JBSWY3DPEHPK3PXP",
        },
    )
    assert response.status_code == 201
    assert get_global_credential_vault().get_password("api-vault-sync") == "api-sync-pw"
    token = get_global_credential_vault().get_totp_token("api-vault-sync")
    assert len(token) == 6 and token.isdigit()


def test_update_vault_credential_description_preserves_global_vault(client: TestClient) -> None:
    from myrm_agent_harness.core.security.credential_vault import get_global_credential_vault

    get_global_credential_vault().clear()
    client.post(
        "/api/v1/security/vault-credentials",
        json={"label": "api-desc-only", "password": "persist-pw"},
    )
    response = client.put(
        "/api/v1/security/vault-credentials/api-desc-only",
        json={"description": "desc changed only"},
    )
    assert response.status_code == 200
    assert get_global_credential_vault().get_password("api-desc-only") == "persist-pw"


def test_create_vault_credential(client: TestClient) -> None:
    response = client.post(
        "/api/v1/security/vault-credentials",
        json={
            "label": "test-cred-1",
            "password": "test-password-123",
            "description": "Test credential",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["label"] == "test-cred-1"
    assert data["has_password"] is True
    assert data["has_totp_seed"] is False
    assert data["description"] == "Test credential"


def test_list_vault_credentials(client: TestClient) -> None:
    client.post(
        "/api/v1/security/vault-credentials",
        json={
            "label": "test-cred-2",
            "password": "test-password-456",
        },
    )

    response = client.get("/api/v1/security/vault-credentials")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert any(c["label"] == "test-cred-2" for c in data)

    for cred in data:
        assert "password" not in cred
        assert "encrypted_password" not in cred


def test_delete_vault_credential(client: TestClient) -> None:
    client.post(
        "/api/v1/security/vault-credentials",
        json={
            "label": "test-cred-3",
            "password": "test-password-789",
        },
    )

    response = client.delete("/api/v1/security/vault-credentials/test-cred-3")
    assert response.status_code == 204

    list_response = client.get("/api/v1/security/vault-credentials")
    data = list_response.json()
    assert not any(c["label"] == "test-cred-3" for c in data)


def test_create_vault_credential_requires_secret(client: TestClient) -> None:
    response = client.post(
        "/api/v1/security/vault-credentials",
        json={"label": "empty-cred"},
    )
    assert response.status_code == 400
    assert "password or totp_seed" in response.json()["detail"]


def test_create_vault_credential_conflict(client: TestClient) -> None:
    payload = {"label": "dup-cred", "password": "pw1"}
    assert client.post("/api/v1/security/vault-credentials", json=payload).status_code == 201
    response = client.post("/api/v1/security/vault-credentials", json=payload)
    assert response.status_code == 409


def test_create_totp_only_credential(client: TestClient) -> None:
    response = client.post(
        "/api/v1/security/vault-credentials",
        json={
            "label": "totp-only-cred",
            "totp_seed": "JBSWY3DPEHPK3PXP",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["has_totp_seed"] is True
    assert data["has_password"] is False


def test_update_vault_credential(client: TestClient) -> None:
    client.post(
        "/api/v1/security/vault-credentials",
        json={"label": "upd-cred", "password": "old-pw"},
    )
    response = client.put(
        "/api/v1/security/vault-credentials/upd-cred",
        json={"password": "new-pw", "description": "updated"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["description"] == "updated"
    assert data["has_password"] is True


def test_delete_nonexistent_returns_404(client: TestClient) -> None:
    response = client.delete("/api/v1/security/vault-credentials/no-such-label")
    assert response.status_code == 404


def test_update_nonexistent_returns_404(client: TestClient) -> None:
    response = client.put(
        "/api/v1/security/vault-credentials/no-such-label",
        json={"password": "x"},
    )
    assert response.status_code == 404
