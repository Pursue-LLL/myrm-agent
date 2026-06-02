import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def e2e_client():
    """Client for E2E testing without mocks."""
    # Ensure database and settings are initialized naturally.
    with TestClient(app) as client:
        yield client

def test_system_ingress_url_e2e(e2e_client, monkeypatch):
    """End-to-end test for Public Ingress URL resolver.
    
    Sets the CP_PUBLIC_INGRESS_URL environment variable (simulating Plane injection)
    and verifies the full API stack returns the correct value.
    """
    # Simulate Control Plane injecting the URL via Env Var
    # The settings object uses validation_alias="CP_PUBLIC_INGRESS_URL"
    from app.config.settings import settings
    original_url = settings.cp_public_ingress_url
    
    settings.cp_public_ingress_url = "https://e2e-public.ngrok.app/"
    
    try:
        response = e2e_client.get("/api/v1/system/ingress-url")
        assert response.status_code == 200
        # Should be stripped of trailing slash
        assert response.json() == {"ingress_url": "https://e2e-public.ngrok.app"}
    finally:
        # Restore settings
        settings.cp_public_ingress_url = original_url
