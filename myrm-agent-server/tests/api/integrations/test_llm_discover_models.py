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
