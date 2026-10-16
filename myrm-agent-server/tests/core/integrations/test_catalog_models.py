"""Tests for Integration Catalog Pydantic models.

Mirrors ``app.core.integrations.catalog.models``: entry/preconfig/auth model
construction, validation, and camelCase serialization.
"""

import pytest

from app.core.integrations.catalog.models import (
    AuthRequirements,
    AuthType,
    CatalogEntry,
    ConnectorType,
    DeploymentScope,
    MCPPreConfig,
    OpenAPIPreConfig,
)


class TestCatalogModels:
    """Tests for Pydantic catalog models."""

    def test_catalog_entry_creation(self) -> None:
        entry = CatalogEntry(
            id="test-service",
            name="Test Service",
            description="A test service",
            icon="test",
            category="test",
            connector_type=ConnectorType.MCP,
            auth=AuthRequirements(type=AuthType.API_KEY, env_key="TEST_KEY"),
        )
        assert entry.id == "test-service"
        assert entry.connector_type == ConnectorType.MCP
        assert entry.auth.type == AuthType.API_KEY
        assert entry.auth.env_key == "TEST_KEY"
        assert entry.name_zh == ""
        assert entry.tags == []

    def test_mcp_preconfig(self) -> None:
        config = MCPPreConfig(
            name="test-mcp",
            type="stdio",
            command="npx",
            args=["-y", "test-server"],
            description="Test MCP server",
        )
        assert config.name == "test-mcp"
        assert config.type == "stdio"
        assert config.args == ["-y", "test-server"]
        assert config.host_serial is False
        assert config.keepalive_interval is None
        assert config.probe_url is None
        assert config.deployment_scope is None
        assert config.post_connect_guide is None
        assert config.post_connect_guide_zh is None

    def test_mcp_preconfig_with_host_serial(self) -> None:
        config = MCPPreConfig(
            name="ue",
            type="streamable_http",
            url="http://127.0.0.1:8000/mcp",
            description="UE MCP",
            host_serial=True,
            keepalive_interval=30.0,
            probe_url="http://127.0.0.1:8000/mcp",
            deployment_scope=DeploymentScope.LOCAL_TAURI_ONLY,
            post_connect_guide="Enable the plugin",
            post_connect_guide_zh="启用插件",
        )
        assert config.host_serial is True
        assert config.keepalive_interval == 30.0
        assert config.probe_url == "http://127.0.0.1:8000/mcp"
        assert config.deployment_scope == DeploymentScope.LOCAL_TAURI_ONLY
        assert config.post_connect_guide == "Enable the plugin"
        assert config.post_connect_guide_zh == "启用插件"

    def test_mcp_preconfig_rejects_local_tauri_only_without_target_url(self) -> None:
        with pytest.raises(ValueError, match="requires probe_url or url"):
            MCPPreConfig(
                name="ue",
                type="streamable_http",
                description="UE MCP",
                deployment_scope=DeploymentScope.LOCAL_TAURI_ONLY,
            )

    def test_mcp_preconfig_rejects_non_loopback_local_tauri_only(self) -> None:
        with pytest.raises(ValueError, match="requires a loopback probe/url"):
            MCPPreConfig(
                name="ue",
                type="streamable_http",
                probe_url="https://example.com/mcp",
                description="UE MCP",
                deployment_scope=DeploymentScope.LOCAL_TAURI_ONLY,
            )

    def test_mcp_preconfig_camel_serialization(self) -> None:
        config = MCPPreConfig(
            name="blender",
            type="sse",
            url="http://127.0.0.1:9876/sse",
            host_serial=True,
            keepalive_interval=30.0,
            probe_url="http://127.0.0.1:9876/sse",
            deployment_scope=DeploymentScope.LOCAL_TAURI_ONLY,
            post_connect_guide="Start MCP server",
        )
        dumped = config.model_dump(by_alias=True, exclude_none=True)
        assert "hostSerial" in dumped
        assert "keepaliveInterval" in dumped
        assert "probeUrl" in dumped
        assert "deploymentScope" in dumped
        assert "postConnectGuide" in dumped
        assert dumped["hostSerial"] is True

    def test_openapi_preconfig(self) -> None:
        config = OpenAPIPreConfig(
            name="test-api",
            spec_url="https://api.example.com/openapi.json",
            description="Test API",
        )
        assert config.spec_url == "https://api.example.com/openapi.json"

    def test_auth_requirements_full(self) -> None:
        auth = AuthRequirements(
            type=AuthType.OAUTH2,
            env_key="OAUTH_TOKEN",
            help_url="https://example.com/auth",
            help_text="Get your OAuth token here",
            help_text_zh="在此获取你的 OAuth 令牌",
        )
        assert auth.type == AuthType.OAUTH2
        assert auth.help_text_zh == "在此获取你的 OAuth 令牌"

    def test_auth_type_none(self) -> None:
        auth = AuthRequirements(type=AuthType.NONE)
        assert auth.env_key is None
        assert auth.help_url is None

    def test_catalog_entry_camel_case_serialization(self) -> None:
        entry = CatalogEntry(
            id="test",
            name="Test",
            name_zh="测试",
            description="Desc",
            description_zh="描述",
            icon="test",
            category="dev",
            connector_type=ConnectorType.MCP,
            auth=AuthRequirements(type=AuthType.API_KEY),
        )
        dumped = entry.model_dump(by_alias=True)
        assert "connectorType" in dumped
        assert dumped["connectorType"] == "mcp"
        assert dumped["nameZh"] == "测试"
