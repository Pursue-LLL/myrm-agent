"""Tests for /integrations/llm/discover-models endpoint."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.core.security.guards.ssrf import SSRFSecurityError

from app.api.integrations.llms import (
    _LOCAL_NO_AUTH_KEY_MARKER,
    _apply_local_no_auth_marker_transport_overrides,
    _is_trusted_split_stack_host,
)
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="integrations")


@asynccontextmanager
async def _mock_httpx_client(*_args: object, **_kwargs: object):
    yield object()


def _json_response(payload: object, url: str = "http://127.0.0.1:8899/v1/models", status_code: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        content=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
        request=httpx.Request("GET", url),
    )


@pytest.fixture
def client() -> TestClient:
    with patch(
        "app.core.security.auth.identity.is_loopback_ip",
        return_value=True,
    ):
        with TestClient(app) as client:
            yield client


def test_discover_models_requires_key_for_non_local_endpoint(client: TestClient) -> None:
    response = client.post(
        "/api/v1/integrations/llm/discover-models",
        json={"api_url": "https://api.openai.com/v1", "api_key": ""},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["success"] is False
    assert "API key is required" in (data.get("error") or "")


def test_discover_models_allows_loopback_no_auth_in_local_mode(client: TestClient) -> None:
    with (
        patch("app.api.integrations.llms.create_httpx_client", _mock_httpx_client),
        patch(
            "app.api.integrations.llms.secure_request",
            return_value=_json_response({"data": [{"id": "qwen3:8b"}]}),
        ) as secure_request_mock,
        patch("app.api.integrations.llms.is_local_mode", return_value=True),
    ):
        response = client.post(
            "/api/v1/integrations/llm/discover-models",
            json={"api_url": "127.0.0.1:8899/v1"},
        )
        assert secure_request_mock.called

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["success"] is True
    assert payload["no_auth_local"] is True
    assert payload["normalized_api_url"] == "http://127.0.0.1:8899/v1"
    assert payload["models"] == ["qwen3:8b"]


def test_discover_models_allows_loopback_with_explicit_key_in_local_mode(client: TestClient) -> None:
    with (
        patch("app.api.integrations.llms.create_httpx_client", _mock_httpx_client),
        patch(
            "app.api.integrations.llms.secure_request",
            return_value=_json_response({"data": [{"id": "qwen3:14b"}]}),
        ) as secure_request_mock,
        patch("app.api.integrations.llms.is_local_mode", return_value=True),
    ):
        response = client.post(
            "/api/v1/integrations/llm/discover-models",
            json={"api_url": "127.0.0.1:8899/v1", "api_key": "sk-local"},
        )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["success"] is True
    assert payload["no_auth_local"] is False
    assert payload["models"] == ["qwen3:14b"]

    assert secure_request_mock.call_count == 1
    called_kwargs = secure_request_mock.call_args.kwargs
    assert called_kwargs["allowed_internal_hosts"] == ["127.0.0.1"]
    assert called_kwargs["headers"]["Authorization"] == "Bearer sk-local"


def test_discover_models_reports_ssrf_block(client: TestClient) -> None:
    with (
        patch("app.api.integrations.llms.create_httpx_client", _mock_httpx_client),
        patch(
            "app.api.integrations.llms.secure_request",
            side_effect=SSRFSecurityError("blocked internal target"),
        ),
        patch("app.api.integrations.llms.is_local_mode", return_value=True),
    ):
        response = client.post(
            "/api/v1/integrations/llm/discover-models",
            json={"api_url": "http://127.0.0.1:8899/v1"},
        )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["success"] is False
    assert "SSRF blocked" in (payload.get("error") or "")


def test_discover_models_external_https_provider(client: TestClient) -> None:
    with (
        patch("app.api.integrations.llms.create_httpx_client", _mock_httpx_client),
        patch(
            "app.api.integrations.llms.secure_request",
            return_value=_json_response(
                {"data": [{"id": "deepseek-v4-flash"}, {"id": "minimax-m3"}]},
                url="https://93.184.216.34/zen/go/v1/models",
            ),
        ) as secure_request_mock,
        patch("app.api.integrations.llms.is_local_mode", return_value=True),
    ):
        response = client.post(
            "/api/v1/integrations/llm/discover-models",
            json={
                "api_url": "https://opencode.ai/zen/go/v1",
                "api_key": "sk-test-opencode-go",
            },
        )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["success"] is True
    assert payload["normalized_api_url"] == "https://opencode.ai/zen/go/v1"
    assert payload["models"] == ["deepseek-v4-flash", "minimax-m3"]
    assert secure_request_mock.await_count >= 1


def test_local_no_auth_marker_overrides_authorization_header() -> None:
    result = _apply_local_no_auth_marker_transport_overrides(
        {"extra_headers": {"X-Test": "1"}},
        _LOCAL_NO_AUTH_KEY_MARKER,
    )
    assert result["extra_headers"]["Authorization"] == ""
    assert result["extra_headers"]["X-Test"] == "1"


def test_non_marker_preserves_model_kwargs() -> None:
    original = {"extra_headers": {"Authorization": "Bearer sk-real"}, "temperature": 0.2}
    result = _apply_local_no_auth_marker_transport_overrides(original, "sk-real")
    assert result == original


def test_normalize_api_base_adds_scheme_and_strips_suffix(client: TestClient) -> None:
    """_normalize_api_base: scheme defaulting, endpoint suffix strip, validation."""
    from app.api.integrations.llms import _normalize_api_base

    assert _normalize_api_base("127.0.0.1:8899/v1/chat/completions") == "http://127.0.0.1:8899/v1"
    assert _normalize_api_base("https://api.openai.com/v1/models") == "https://api.openai.com/v1"
    assert _normalize_api_base("http://localhost:8080/v1/") == "http://localhost:8080/v1"


def test_normalize_api_base_rejects_invalid_inputs() -> None:
    """_normalize_api_base: empty, non-http scheme, missing hostname raise."""
    from app.api.integrations.llms import _normalize_api_base

    with pytest.raises(ValueError, match="required"):
        _normalize_api_base("   ")
    with pytest.raises(ValueError, match="http or https"):
        _normalize_api_base("ftp://host/v1")
    with pytest.raises(ValueError, match="hostname"):
        _normalize_api_base("http:///v1")


def test_build_models_candidates_path_variants() -> None:
    """_build_models_candidates covers /models path, parents, and root fallbacks."""
    from app.api.integrations.llms import _build_models_candidates

    with_models = _build_models_candidates("http://host/v1/models")
    assert "http://host/v1/models" in with_models

    nested = _build_models_candidates("http://host/a/b/v1")
    assert "http://host/a/b/models" in nested
    assert "http://host/a/models" in nested

    root = _build_models_candidates("http://host")
    assert "http://host/v1/models" in root
    assert "http://host/api/v1/models" in root
    assert "http://host/api/models" in root
    assert "http://host/models" in root


def test_extract_model_ids_all_shapes() -> None:
    """_extract_model_ids covers data, models, and top-level list payloads."""
    from app.api.integrations.llms import _extract_model_ids

    assert _extract_model_ids({"data": [{"id": "a"}, {"id": "b"}]}) == ["a", "b"]
    assert _extract_model_ids({"models": [{"id": "c"}]}) == ["c"]
    assert _extract_model_ids([{"id": "d"}, {"id": "e"}]) == ["d", "e"]
    assert _extract_model_ids({"unrelated": 1}) == []
    assert _extract_model_ids("nope") == []


def test_is_loopback_host_variants() -> None:
    """_is_loopback_host covers None, localhost, IPv4/IPv6 loopback, and public IP."""
    from app.api.integrations.llms import _is_loopback_host

    assert _is_loopback_host(None) is False
    assert _is_loopback_host("") is False
    assert _is_loopback_host("LOCALHOST") is True
    assert _is_loopback_host("127.0.0.1") is True
    assert _is_loopback_host("::1") is True
    assert _is_loopback_host("0.0.0.0") is True
    assert _is_loopback_host("8.8.8.8") is False
    assert _is_loopback_host("not-an-ip") is False


def test_discover_models_rejects_invalid_url(client: TestClient) -> None:
    """Invalid API URL surfaces the normalization error."""
    response = client.post(
        "/api/v1/integrations/llm/discover-models",
        json={"api_url": "   ", "api_key": "sk-test"},
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["success"] is False
    assert payload["error"] is not None


def test_discover_models_provider_http_error(client: TestClient) -> None:
    """Provider 4xx/5xx response is recorded and probing continues."""
    with (
        patch("app.api.integrations.llms.create_httpx_client", _mock_httpx_client),
        patch(
            "app.api.integrations.llms.secure_request",
            return_value=_json_response({"error": "boom"}, status_code=503),
        ),
        patch("app.api.integrations.llms.is_local_mode", return_value=True),
    ):
        response = client.post(
            "/api/v1/integrations/llm/discover-models",
            json={"api_url": "127.0.0.1:8899/v1"},
        )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["success"] is False
    assert "Provider returned 503" in (payload.get("error") or "")


def test_discover_models_invalid_json(client: TestClient) -> None:
    """Invalid JSON payload is recorded and probing continues."""
    with (
        patch("app.api.integrations.llms.create_httpx_client", _mock_httpx_client),
        patch(
            "app.api.integrations.llms.secure_request",
            return_value=httpx.Response(
                status_code=200,
                content=b"<html>not json</html>",
                headers={"content-type": "text/html"},
                request=httpx.Request("GET", "http://127.0.0.1:8899/v1/models"),
            ),
        ),
        patch("app.api.integrations.llms.is_local_mode", return_value=True),
    ):
        response = client.post(
            "/api/v1/integrations/llm/discover-models",
            json={"api_url": "127.0.0.1:8899/v1"},
        )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["success"] is False
    assert "invalid JSON" in (payload.get("error") or "")


def test_discover_models_generic_error(client: TestClient) -> None:
    """Generic transport error surfaces as last_error."""
    with (
        patch("app.api.integrations.llms.create_httpx_client", _mock_httpx_client),
        patch(
            "app.api.integrations.llms.secure_request",
            side_effect=RuntimeError("connection refused"),
        ),
        patch("app.api.integrations.llms.is_local_mode", return_value=True),
    ):
        response = client.post(
            "/api/v1/integrations/llm/discover-models",
            json={"api_url": "127.0.0.1:8899/v1"},
        )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["success"] is False
    assert "connection refused" in (payload.get("error") or "")


def test_is_trusted_split_stack_host_classifies_rfc1918_tailscale_and_mdns() -> None:
    assert _is_trusted_split_stack_host("localhost") is True
    assert _is_trusted_split_stack_host("127.0.0.1") is True
    assert _is_trusted_split_stack_host("10.0.0.1") is True
    assert _is_trusted_split_stack_host("172.16.0.1") is True
    assert _is_trusted_split_stack_host("192.168.1.100") is True
    assert _is_trusted_split_stack_host("100.80.20.10") is True
    assert _is_trusted_split_stack_host("mac-mini.local") is True
    assert _is_trusted_split_stack_host("::1") is True


def test_is_trusted_split_stack_host_rejects_link_local_and_public() -> None:
    assert _is_trusted_split_stack_host("169.254.169.254") is False
    assert _is_trusted_split_stack_host("8.8.8.8") is False
    assert _is_trusted_split_stack_host("api.openai.com") is False
    assert _is_trusted_split_stack_host(None) is False
    assert _is_trusted_split_stack_host("") is False


def test_discover_models_allows_lan_rfc1918_no_auth_in_local_mode(client: TestClient) -> None:
    with (
        patch("app.api.integrations.llms.create_httpx_client", _mock_httpx_client),
        patch(
            "app.api.integrations.llms.secure_request",
            return_value=_json_response(
                {"data": [{"id": "deepseek-r1:32b"}]},
                url="http://192.168.1.50:11434/v1/models",
            ),
        ) as secure_request_mock,
        patch("app.api.integrations.llms.is_local_mode", return_value=True),
    ):
        response = client.post(
            "/api/v1/integrations/llm/discover-models",
            json={"api_url": "http://192.168.1.50:11434/v1"},
        )
        assert secure_request_mock.called
        called_kwargs = secure_request_mock.call_args.kwargs
        assert called_kwargs["allowed_internal_hosts"] == ["192.168.1.50"]

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["success"] is True
    assert payload["no_auth_local"] is True
    assert payload["models"] == ["deepseek-r1:32b"]


def test_discover_models_allows_tailscale_cgnat_no_auth_in_local_mode(client: TestClient) -> None:
    with (
        patch("app.api.integrations.llms.create_httpx_client", _mock_httpx_client),
        patch(
            "app.api.integrations.llms.secure_request",
            return_value=_json_response(
                {"data": [{"id": "qwen2.5:72b"}]},
                url="http://100.80.20.10:8000/v1/models",
            ),
        ) as secure_request_mock,
        patch("app.api.integrations.llms.is_local_mode", return_value=True),
    ):
        response = client.post(
            "/api/v1/integrations/llm/discover-models",
            json={"api_url": "http://100.80.20.10:8000/v1"},
        )
        assert secure_request_mock.called
        called_kwargs = secure_request_mock.call_args.kwargs
        assert called_kwargs["allowed_internal_hosts"] == ["100.80.20.10"]

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["success"] is True
    assert payload["no_auth_local"] is True
    assert payload["models"] == ["qwen2.5:72b"]


def test_discover_models_blocks_lan_in_sandbox_mode(client: TestClient) -> None:
    """In cloud SaaS / Sandbox mode, private LAN endpoints require key and are blocked by SSRF."""
    with (
        patch("app.api.integrations.llms.create_httpx_client", _mock_httpx_client),
        patch("app.api.integrations.llms.is_local_mode", return_value=False),
    ):
        # Without key in sandbox -> blocked immediately
        response = client.post(
            "/api/v1/integrations/llm/discover-models",
            json={"api_url": "http://192.168.1.50:11434/v1"},
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["success"] is False
        assert "API key is required" in (data.get("error") or "")


def test_discover_models_rejects_link_local_metadata_in_local_mode(client: TestClient) -> None:
    """169.254.169.254 (link-local cloud metadata) is never trusted as split-stack, requiring key and not whitelisted."""
    with (
        patch("app.api.integrations.llms.create_httpx_client", _mock_httpx_client),
        patch("app.api.integrations.llms.is_local_mode", return_value=True),
    ):
        response = client.post(
            "/api/v1/integrations/llm/discover-models",
            json={"api_url": "http://169.254.169.254/latest/meta-data"},
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["success"] is False
        assert "API key is required" in (data.get("error") or "")
