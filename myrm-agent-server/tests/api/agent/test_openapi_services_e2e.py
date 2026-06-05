"""OpenAPI Services API endpoint integration test.

Tests the /api/v1/agents/openapi-services/parse-spec and /test-request endpoints
using a real remote spec (Swagger Petstore) without mocks.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

PETSTORE_SPEC_URL = "https://petstore3.swagger.io/api/v3/openapi.json"


@pytest.fixture
def client():
    """Create a test client with the OpenAPI services router mounted."""
    from fastapi import FastAPI

    from app.api.agents.openapi_services import router

    app = FastAPI()
    app.include_router(router, prefix="/api/v1/agents")
    return TestClient(app)


class TestGetPresetsEndpoint:
    """Test GET /api/v1/agents/openapi-services/presets"""

    def test_get_saas_presets(self, client: TestClient):
        """Should return built-in SaaS presets with selected_endpoints."""
        response = client.get("/api/v1/agents/openapi-services/presets")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 3

        # Verify GitHub preset
        github_preset = next((p for p in data if "GitHub" in p["name"]), None)
        assert github_preset is not None
        assert "spec_url" in github_preset
        assert "auth_type" in github_preset
        assert "selected_endpoints" in github_preset
        assert isinstance(github_preset["selected_endpoints"], list)
        assert "issues/get" in github_preset["selected_endpoints"]


class TestParseSpecEndpoint:
    """Test POST /api/v1/agents/openapi-services/parse-spec"""

    def test_parse_spec_from_url(self, client: TestClient):
        """Parse real Petstore spec from URL."""
        response = client.post(
            "/api/v1/agents/openapi-services/parse-spec",
            json={"spec_url": PETSTORE_SPEC_URL},
        )
        assert response.status_code == 200
        data = response.json()

        assert data["title"] == "Swagger Petstore - OpenAPI 3.0"
        assert data["spec_version"] == "openapi_3x"
        assert data["endpoint_count"] > 10
        assert len(data["endpoints"]) > 10
        assert data["base_url"] != ""
        assert "tags" in data

        # Verify endpoint structure
        ep = data["endpoints"][0]
        assert "operation_id" in ep
        assert "method" in ep
        assert "path" in ep

    def test_parse_spec_from_content(self, client: TestClient):
        """Parse inline JSON spec content."""
        spec_json = """{
            "openapi": "3.0.0",
            "info": {"title": "Inline Test API", "version": "1.0.0"},
            "paths": {
                "/health": {
                    "get": {
                        "operationId": "healthCheck",
                        "summary": "Health check endpoint",
                        "responses": {"200": {"description": "OK"}}
                    }
                }
            }
        }"""
        response = client.post(
            "/api/v1/agents/openapi-services/parse-spec",
            json={"spec_content": spec_json},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Inline Test API"
        assert data["endpoint_count"] == 1
        assert data["endpoints"][0]["operation_id"] == "healthCheck"

    def test_parse_spec_missing_source(self, client: TestClient):
        """Should return 400 when neither URL nor content provided."""
        response = client.post(
            "/api/v1/agents/openapi-services/parse-spec",
            json={},
        )
        assert response.status_code == 400

    def test_parse_spec_invalid_url(self, client: TestClient):
        """Should return 422 for unreachable spec URL."""
        response = client.post(
            "/api/v1/agents/openapi-services/parse-spec",
            json={"spec_url": "https://nonexistent-domain-xyz123.com/spec.json"},
        )
        assert response.status_code == 422 or response.status_code == 500

    def test_parse_spec_ssrf_blocked(self, client: TestClient):
        """Should block internal IP access via SSRF protection."""
        response = client.post(
            "/api/v1/agents/openapi-services/parse-spec",
            json={"spec_url": "http://169.254.169.254/latest/meta-data/"},
        )
        assert response.status_code == 422
        assert "SSRF" in response.json()["detail"] or "Blocked" in response.json()["detail"]

    def test_parse_spec_invalid_content(self, client: TestClient):
        """Should return error for invalid spec content."""
        response = client.post(
            "/api/v1/agents/openapi-services/parse-spec",
            json={"spec_content": "not valid yaml or json"},
        )
        assert response.status_code == 422


class TestTestRequestEndpoint:
    """Test POST /api/v1/agents/openapi-services/test-request"""

    def test_successful_request(self, client: TestClient):
        """Execute a real test request against Petstore API.

        Verifies endpoint connectivity - the external API may occasionally
        return 5xx errors, so we check the response is not empty and
        the request was executed (not blocked by internal error).
        """
        response = client.post(
            "/api/v1/agents/openapi-services/test-request",
            json={
                "service_config": {
                    "name": "petstore",
                    "spec_url": PETSTORE_SPEC_URL,
                    "base_url": "https://petstore3.swagger.io/api/v3",
                },
                "operation_id": "findPetsByStatus",
                "params": {"status": "available"},
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["response_body"] != ""
        assert "Spec error" not in data["status_message"]
        assert "not found" not in data["status_message"]

    def test_nonexistent_endpoint(self, client: TestClient):
        """Should report error for missing operation_id."""
        response = client.post(
            "/api/v1/agents/openapi-services/test-request",
            json={
                "service_config": {
                    "name": "petstore",
                    "spec_url": PETSTORE_SPEC_URL,
                },
                "operation_id": "nonExistentOperation",
                "params": {},
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "not found" in data["status_message"]
