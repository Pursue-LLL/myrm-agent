"""Live integration tests for /integrations/llm/discover-models — real OpenCode Go, no fetch mocks."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from tests.support.minimal_app import build_minimal_app
from tests.support.test_secrets import resolve_test_env

app = build_minimal_app(preset="integrations")

_OPENCODE_GO_BASE_URL = "https://opencode.ai/zen/go/v1"
_EXPECTED_MODEL_IDS = frozenset(
    {
        "deepseek-v4-flash",
        "minimax-m3",
        "glm-5.2",
        "kimi-k3",
    }
)


@pytest.fixture
def client() -> Iterator[TestClient]:
    with patch(
        "app.core.security.auth.identity.is_loopback_ip",
        return_value=True,
    ):
        with TestClient(app) as test_client:
            yield test_client


@pytest.mark.integration
def test_discover_models_opencode_go_live(client: TestClient) -> None:
    """Real SSRF-pinned fetch to OpenCode Go /models — validates HTTPS SNI + model list."""
    api_key = resolve_test_env("BASIC_API_KEY")
    base_url = resolve_test_env("BASIC_BASE_URL", _OPENCODE_GO_BASE_URL)
    if not api_key or "opencode.ai" not in base_url:
        pytest.skip("OpenCode Go credentials not configured in .env.test")

    response = client.post(
        "/api/v1/integrations/llm/discover-models",
        json={"api_url": base_url, "api_key": api_key},
    )
    assert response.status_code == 200, response.text
    payload = response.json()["data"]
    assert payload["success"] is True, payload.get("error")
    assert payload["normalized_api_url"] == _OPENCODE_GO_BASE_URL
    assert payload["models_url"] == f"{_OPENCODE_GO_BASE_URL}/models"

    models = payload["models"]
    assert len(models) >= 20
    assert _EXPECTED_MODEL_IDS.issubset(set(models))


@pytest.mark.integration
def test_discover_models_opencode_go_requires_key(client: TestClient) -> None:
    """Failure path: external endpoint without API key must not attempt provider fetch."""
    response = client.post(
        "/api/v1/integrations/llm/discover-models",
        json={"api_url": _OPENCODE_GO_BASE_URL, "api_key": ""},
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["success"] is False
    assert "API key is required" in (payload.get("error") or "")


class _MockModelEndpointHandler(BaseHTTPRequestHandler):
    last_auth_header: str | None = None

    def do_GET(self) -> None:
        _MockModelEndpointHandler.last_auth_header = self.headers.get("Authorization")
        if self.path in ("/v1/models", "/models"):
            body = b'{"data": [{"id": "deepseek-v4-flash-local"}, {"id": "qwen2.5:32b"}]}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.mark.integration
def test_discover_models_local_live_http_server(client: TestClient) -> None:
    """Real socket connection to a local HTTP server — validates real unmocked network fetch and no-auth policy."""
    _MockModelEndpointHandler.last_auth_header = "unset"
    server = HTTPServer(("127.0.0.1", 0), _MockModelEndpointHandler)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        response = client.post(
            "/api/v1/integrations/llm/discover-models",
            json={"api_url": f"http://127.0.0.1:{port}/v1"},
        )
        assert response.status_code == 200
        payload = response.json()["data"]
        assert payload["success"] is True
        assert payload["no_auth_local"] is True
        assert "deepseek-v4-flash-local" in payload["models"]
        assert "qwen2.5:32b" in payload["models"]
        # Verify wire-level proof that no Authorization header is sent
        assert _MockModelEndpointHandler.last_auth_header is None
    finally:
        server.shutdown()
        server.server_close()
