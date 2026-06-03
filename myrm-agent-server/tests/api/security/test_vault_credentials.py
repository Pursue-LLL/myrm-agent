import pytest
from fastapi.testclient import TestClient
from app.main import app

@pytest.fixture
def client() -> TestClient:
    return TestClient(app)

def test_create_vault_credential(client: TestClient):
    response = client.post(
        "/api/v1/security/vault-credentials",
        json={
            "label": "test-cred-1",
            "password": "test-password-123",
            "description": "Test credential"
        }
    )
    assert response.status_code == 201
    data = response.json()
    assert data["label"] == "test-cred-1"
    assert data["has_password"] is True
    assert data["has_totp_seed"] is False
    assert data["description"] == "Test credential"

def test_list_vault_credentials(client: TestClient):
    # First create one
    client.post(
        "/api/v1/security/vault-credentials",
        json={
            "label": "test-cred-2",
            "password": "test-password-456"
        }
    )
    
    response = client.get("/api/v1/security/vault-credentials")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert any(c["label"] == "test-cred-2" for c in data)
    
    # Ensure no passwords are leaked
    for cred in data:
        assert "password" not in cred
        assert "encrypted_password" not in cred

def test_delete_vault_credential(client: TestClient):
    # First create one
    client.post(
        "/api/v1/security/vault-credentials",
        json={
            "label": "test-cred-3",
            "password": "test-password-789"
        }
    )
    
    # Delete it
    response = client.delete("/api/v1/security/vault-credentials/test-cred-3")
    assert response.status_code == 204
    
    # Verify it's gone
    list_response = client.get("/api/v1/security/vault-credentials")
    data = list_response.json()
    assert not any(c["label"] == "test-cred-3" for c in data)
