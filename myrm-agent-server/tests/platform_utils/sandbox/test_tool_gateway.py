"""Unit tests for sandbox Unified Tool Gateway credential merge."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.platform_utils.sandbox.tool_gateway import (
    ResolvedToolGatewayConfig,
    fetch_sandbox_tool_gateway_config,
    merge_tool_gateway_config,
)

MODULE = "app.platform_utils.sandbox.tool_gateway"


def _safe_clear_gateway_cache() -> None:
    if hasattr(fetch_sandbox_tool_gateway_config, "cache_clear"):
        fetch_sandbox_tool_gateway_config.cache_clear()


class TestMergeToolGatewayConfig:
    def test_non_sandbox_returns_agent_config_unchanged(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("app.config.deploy_mode.is_sandbox", lambda: False)
        agent_cfg = {"use_gateway": False, "gateway_url": "http://agent"}
        assert merge_tool_gateway_config(agent_cfg) is agent_cfg

    def test_sandbox_applies_platform_when_agent_not_using_gateway(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("app.config.deploy_mode.is_sandbox", lambda: True)
        platform = ResolvedToolGatewayConfig(
            use_gateway=True,
            gateway_url="https://cp.example/tool-relay",
            auth_token="vk-test",
        )
        monkeypatch.setattr(f"{MODULE}.fetch_sandbox_tool_gateway_config", lambda: platform)

        merged = merge_tool_gateway_config({"use_gateway": False})
        assert merged == {
            "use_gateway": True,
            "gateway_url": "https://cp.example/tool-relay",
            "auth_token": "vk-test",
        }

    def test_sandbox_keeps_explicit_agent_gateway_override(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("app.config.deploy_mode.is_sandbox", lambda: True)
        platform = ResolvedToolGatewayConfig(
            use_gateway=True,
            gateway_url="https://cp.example/tool-relay",
            auth_token="platform-token",
        )
        monkeypatch.setattr(f"{MODULE}.fetch_sandbox_tool_gateway_config", lambda: platform)

        agent_cfg = {
            "use_gateway": True,
            "gateway_url": "https://custom.example",
            "auth_token": "agent-token",
        }
        assert merge_tool_gateway_config(agent_cfg) is agent_cfg

    def test_sandbox_no_platform_credentials_returns_agent_config(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("app.config.deploy_mode.is_sandbox", lambda: True)
        monkeypatch.setattr(f"{MODULE}.fetch_sandbox_tool_gateway_config", lambda: None)
        agent_cfg = {"use_gateway": False}
        assert merge_tool_gateway_config(agent_cfg) is agent_cfg

    def test_sandbox_none_agent_config_gets_platform_defaults(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("app.config.deploy_mode.is_sandbox", lambda: True)
        platform = ResolvedToolGatewayConfig(
            use_gateway=True,
            gateway_url="https://cp.example/tool-relay",
            auth_token="vk-test",
        )
        monkeypatch.setattr(f"{MODULE}.fetch_sandbox_tool_gateway_config", lambda: platform)

        assert merge_tool_gateway_config(None) == {
            "use_gateway": True,
            "gateway_url": "https://cp.example/tool-relay",
            "auth_token": "vk-test",
        }


class TestToolGatewayHelpers:
    def test_clear_tool_gateway_cache_is_safe(self) -> None:
        from app.platform_utils.sandbox.tool_gateway import clear_tool_gateway_cache

        clear_tool_gateway_cache()

    def test_telemetry_headers_none_when_unconfigured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.platform_utils.sandbox import tool_gateway as tg

        settings = MagicMock()
        settings.control_plane.url = ""
        settings.control_plane.telemetry_token.get_secret_value.return_value = ""
        settings.control_plane.sandbox_id = ""
        monkeypatch.setattr(tg, "settings", settings)

        assert tg._telemetry_headers() is None


class TestFetchSandboxToolGatewayConfig:
    def test_returns_none_when_not_sandbox_instance(self, monkeypatch: pytest.MonkeyPatch) -> None:
        caps = MagicMock()
        caps.is_sandbox_instance = False
        monkeypatch.setattr(
            "app.platform_utils.deployment_capabilities.get_deployment_capabilities",
            lambda: caps,
        )

        from app.platform_utils.sandbox.tool_gateway import fetch_sandbox_tool_gateway_config

        assert fetch_sandbox_tool_gateway_config() is None

    def test_returns_none_when_telemetry_headers_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        caps = MagicMock()
        caps.is_sandbox_instance = True
        monkeypatch.setattr(
            "app.platform_utils.deployment_capabilities.get_deployment_capabilities",
            lambda: caps,
        )
        monkeypatch.setattr(f"{MODULE}._telemetry_headers", lambda: None)

        from app.platform_utils.sandbox.tool_gateway import fetch_sandbox_tool_gateway_config

        _safe_clear_gateway_cache()
        assert fetch_sandbox_tool_gateway_config() is None

    @patch(f"{MODULE}.httpx.Client")
    def test_returns_none_on_http_error(
        self,
        client_cls: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        caps = MagicMock()
        caps.is_sandbox_instance = True
        monkeypatch.setattr(
            "app.platform_utils.deployment_capabilities.get_deployment_capabilities",
            lambda: caps,
        )
        monkeypatch.setattr(
            f"{MODULE}._telemetry_headers",
            lambda: {"X-Telemetry-Token": "t", "X-Sandbox-Id": "sb-1"},
        )
        settings = MagicMock()
        settings.control_plane.url = "https://cp.example"
        settings.control_plane.sandbox_id = "sb-1"
        monkeypatch.setattr(f"{MODULE}.settings", settings)

        client = MagicMock()
        client.__enter__.return_value = client
        client.get.side_effect = RuntimeError("network down")
        client_cls.return_value = client

        from app.platform_utils.sandbox.tool_gateway import fetch_sandbox_tool_gateway_config

        _safe_clear_gateway_cache()
        assert fetch_sandbox_tool_gateway_config() is None

    @patch(f"{MODULE}.httpx.Client")
    def test_returns_none_when_gateway_disabled_in_payload(
        self,
        client_cls: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        caps = MagicMock()
        caps.is_sandbox_instance = True
        monkeypatch.setattr(
            "app.platform_utils.deployment_capabilities.get_deployment_capabilities",
            lambda: caps,
        )
        monkeypatch.setattr(
            f"{MODULE}._telemetry_headers",
            lambda: {"X-Telemetry-Token": "t", "X-Sandbox-Id": "sb-1"},
        )
        settings = MagicMock()
        settings.control_plane.url = "https://cp.example"
        settings.control_plane.sandbox_id = "sb-1"
        monkeypatch.setattr(f"{MODULE}.settings", settings)

        response = MagicMock()
        response.json.return_value = {
            "use_gateway": False,
            "gateway_url": "https://cp.example/tool-relay",
            "auth_token": "minted-key",
        }
        client = MagicMock()
        client.__enter__.return_value = client
        client.get.return_value = response
        client_cls.return_value = client

        from app.platform_utils.sandbox.tool_gateway import fetch_sandbox_tool_gateway_config

        _safe_clear_gateway_cache()
        assert fetch_sandbox_tool_gateway_config() is None

    @patch(f"{MODULE}.httpx.Client")
    def test_parses_internal_api_response(
        self,
        client_cls: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        caps = MagicMock()
        caps.is_sandbox_instance = True
        monkeypatch.setattr(
            "app.platform_utils.deployment_capabilities.get_deployment_capabilities",
            lambda: caps,
        )
        monkeypatch.setattr(
            f"{MODULE}._telemetry_headers",
            lambda: {"X-Telemetry-Token": "t", "X-Sandbox-Id": "sb-1"},
        )
        settings = MagicMock()
        settings.control_plane.url = "https://cp.example"
        settings.control_plane.sandbox_id = "sb-1"
        monkeypatch.setattr(f"{MODULE}.settings", settings)

        response = MagicMock()
        response.json.return_value = {
            "use_gateway": True,
            "gateway_url": "https://cp.example/tool-relay",
            "auth_token": "minted-key",
        }
        client = MagicMock()
        client.__enter__.return_value = client
        client.get.return_value = response
        client_cls.return_value = client

        from app.platform_utils.sandbox.tool_gateway import fetch_sandbox_tool_gateway_config

        _safe_clear_gateway_cache()
        cfg = fetch_sandbox_tool_gateway_config()
        assert cfg == ResolvedToolGatewayConfig(
            use_gateway=True,
            gateway_url="https://cp.example/tool-relay",
            auth_token="minted-key",
        )
