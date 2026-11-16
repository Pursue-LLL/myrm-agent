"""Tests for the hosts discover-models trusts without a key: loopback, LAN, Tailscale and `.local` split-stack hosts."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.api.integrations.llms import _is_trusted_split_stack_host
from tests.api.integrations.discover_models_support import discovery_test_client, json_response, mock_httpx_client


@pytest.fixture
def client() -> Iterator[TestClient]:
    with discovery_test_client() as client:
        yield client


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
        patch("app.api.integrations.llms.discovery.create_httpx_client", mock_httpx_client),
        patch(
            "app.api.integrations.llms.discovery.secure_request",
            return_value=json_response(
                {"data": [{"id": "deepseek-r1:32b"}]},
                url="http://192.168.1.50:11434/v1/models",
            ),
        ) as secure_request_mock,
        patch("app.api.integrations.llms.discovery.is_local_mode", return_value=True),
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
        patch("app.api.integrations.llms.discovery.create_httpx_client", mock_httpx_client),
        patch(
            "app.api.integrations.llms.discovery.secure_request",
            return_value=json_response(
                {"data": [{"id": "qwen2.5:72b"}]},
                url="http://100.80.20.10:8000/v1/models",
            ),
        ) as secure_request_mock,
        patch("app.api.integrations.llms.discovery.is_local_mode", return_value=True),
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
        patch("app.api.integrations.llms.discovery.create_httpx_client", mock_httpx_client),
        patch("app.api.integrations.llms.discovery.is_local_mode", return_value=False),
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
        patch("app.api.integrations.llms.discovery.create_httpx_client", mock_httpx_client),
        patch("app.api.integrations.llms.discovery.is_local_mode", return_value=True),
    ):
        response = client.post(
            "/api/v1/integrations/llm/discover-models",
            json={"api_url": "http://169.254.169.254/latest/meta-data"},
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["success"] is False
        assert "API key is required" in (data.get("error") or "")


def test_discover_models_bare_lan_ip_with_port(client: TestClient) -> None:
    """Bare URL like 192.168.1.50:11434 is normalized to http://192.168.1.50:11434 and discovered without key."""
    with (
        patch("app.api.integrations.llms.discovery.create_httpx_client", mock_httpx_client),
        patch(
            "app.api.integrations.llms.discovery.secure_request",
            return_value=json_response(
                {"data": [{"id": "llama3.3:70b"}]},
                url="http://192.168.1.50:11434/v1/models",
            ),
        ) as secure_request_mock,
        patch("app.api.integrations.llms.discovery.is_local_mode", return_value=True),
    ):
        response = client.post(
            "/api/v1/integrations/llm/discover-models",
            json={"api_url": "http://192.168.1.50:11434/v1"},
        )
        assert secure_request_mock.called
        assert secure_request_mock.call_args.kwargs["allowed_internal_hosts"] == ["192.168.1.50"]

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["success"] is True
    assert payload["no_auth_local"] is True
    assert payload["models"] == ["llama3.3:70b"]


def test_discover_models_lan_with_explicit_key_preserves_auth_header(client: TestClient) -> None:
    """When user provides an explicit key for a LAN/Tailscale host, it is preserved and the host is whitelisted."""
    with (
        patch("app.api.integrations.llms.discovery.create_httpx_client", mock_httpx_client),
        patch(
            "app.api.integrations.llms.discovery.secure_request",
            return_value=json_response(
                {"data": [{"id": "qwen2.5-coder:32b"}]},
                url="http://100.80.20.10:8000/v1/models",
            ),
        ) as secure_request_mock,
        patch("app.api.integrations.llms.discovery.is_local_mode", return_value=True),
    ):
        response = client.post(
            "/api/v1/integrations/llm/discover-models",
            json={"api_url": "http://100.80.20.10:8000/v1", "api_key": "sk-lan-auth"},
        )
        assert secure_request_mock.called
        called_kwargs = secure_request_mock.call_args.kwargs
        assert called_kwargs["allowed_internal_hosts"] == ["100.80.20.10"]
        assert called_kwargs["headers"]["Authorization"] == "Bearer sk-lan-auth"

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["success"] is True
    assert payload["no_auth_local"] is False
    assert payload["models"] == ["qwen2.5-coder:32b"]


def test_is_trusted_split_stack_host_exact_cidr_boundaries() -> None:
    # 172.16.0.0/12 boundaries
    assert _is_trusted_split_stack_host("172.15.255.255") is False
    assert _is_trusted_split_stack_host("172.16.0.0") is True
    assert _is_trusted_split_stack_host("172.31.255.255") is True
    assert _is_trusted_split_stack_host("172.32.0.0") is False

    # Tailscale 100.64.0.0/10 boundaries
    assert _is_trusted_split_stack_host("100.63.255.255") is False
    assert _is_trusted_split_stack_host("100.64.0.0") is True
    assert _is_trusted_split_stack_host("100.127.255.255") is True
    assert _is_trusted_split_stack_host("100.128.0.0") is False
