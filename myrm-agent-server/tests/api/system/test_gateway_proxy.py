import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.system.router import router


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/system")
    return TestClient(app)

def test_gateway_health_no_token(client: TestClient) -> None:
    """Test that the gateway health proxy endpoint handles missing token."""
    response = client.post("/api/v1/system/gateway/health", json={"gateway_token": None})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "error"
    assert "Gateway PAT token is required" in data["message"]

def test_gateway_health_invalid_token(client: TestClient) -> None:
    """Test that the gateway health proxy endpoint validates token format (SSRF protection)."""
    response = client.post("/api/v1/system/gateway/health", json={"gateway_token": "invalid token @!!"})
    assert response.status_code == 422
    assert "gateway_token" in response.text

def test_gateway_health_with_token_connection_error(client: TestClient) -> None:
    """Test that the gateway health proxy handles connection failures to control plane."""
    # Since we are not mocking httpx, this will attempt to hit the control plane URL.
    # Depending on settings, it might hit a real dev URL or fail.
    response = client.post("/api/v1/system/gateway/health", json={"gateway_token": "test_token"})
    assert response.status_code == 200
    data = response.json()
    
    # We don't have a real CP running in the test environment, so it should fail gracefully
    # with either a connection error or a 404/502 depending on what's at the URL.
    if data.get("status") == "error":
        assert "Gateway returned error" in data["message"] or "Failed to connect" in data["message"]
    else:
        # If it miraculously connects (e.g. hitting a real deployed service)
        assert "overall_healthy" in data
