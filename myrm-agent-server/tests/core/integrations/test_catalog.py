"""Tests for Integration Catalog core module.

Tests cover:
- CatalogRegistry singleton and lazy loading
- JSON data loading and validation
- Search, filter, and get operations
- Model serialization
- Edge cases (empty queries, nonexistent IDs)
"""

import pytest

from app.core.integrations.catalog.models import (
    AuthRequirements,
    AuthType,
    CatalogEntry,
    ConnectorType,
    MCPPreConfig,
    OpenAPIPreConfig,
)
from app.core.integrations.catalog.registry import CatalogRegistry


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
            post_connect_guide="Enable the plugin",
            post_connect_guide_zh="启用插件",
        )
        assert config.host_serial is True
        assert config.keepalive_interval == 30.0
        assert config.probe_url == "http://127.0.0.1:8000/mcp"
        assert config.post_connect_guide == "Enable the plugin"
        assert config.post_connect_guide_zh == "启用插件"

    def test_mcp_preconfig_camel_serialization(self) -> None:
        config = MCPPreConfig(
            name="blender",
            type="sse",
            url="http://127.0.0.1:9876/sse",
            host_serial=True,
            keepalive_interval=30.0,
            probe_url="http://127.0.0.1:9876/sse",
            post_connect_guide="Start MCP server",
        )
        dumped = config.model_dump(by_alias=True, exclude_none=True)
        assert "hostSerial" in dumped
        assert "keepaliveInterval" in dumped
        assert "probeUrl" in dumped
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


class TestCatalogRegistry:
    """Tests for CatalogRegistry loading and query operations."""

    @pytest.fixture
    def registry(self) -> CatalogRegistry:
        reg = CatalogRegistry()
        reg._ensure_loaded()
        return reg

    def test_singleton(self) -> None:
        r1 = CatalogRegistry.get_instance()
        r2 = CatalogRegistry.get_instance()
        assert r1 is r2

    def test_loads_entries(self, registry: CatalogRegistry) -> None:
        entries = registry.list_all()
        assert len(entries) >= 17

    def test_all_entries_valid(self, registry: CatalogRegistry) -> None:
        for entry in registry.list_all():
            assert entry.id
            assert entry.name
            assert entry.category
            assert entry.connector_type in (ConnectorType.MCP, ConnectorType.OPENAPI)
            assert entry.auth.type in (
                AuthType.API_KEY,
                AuthType.OAUTH2,
                AuthType.BEARER,
                AuthType.NONE,
            )

    def test_get_by_id_exists(self, registry: CatalogRegistry) -> None:
        entry = registry.get_by_id("notion")
        assert entry is not None
        assert entry.name == "Notion"
        assert entry.category == "productivity"
        assert entry.mcp_config is not None
        assert entry.mcp_config.type == "stdio"

    def test_get_by_id_not_found(self, registry: CatalogRegistry) -> None:
        assert registry.get_by_id("nonexistent") is None

    def test_search_by_name(self, registry: CatalogRegistry) -> None:
        results = registry.search("github")
        assert len(results) == 1
        assert results[0].id == "github"

    def test_search_by_tag(self, registry: CatalogRegistry) -> None:
        results = registry.search("wiki")
        assert any(e.id == "notion" for e in results)

    def test_search_by_chinese_name(self, registry: CatalogRegistry) -> None:
        results = registry.search("数据库")
        assert any(e.id == "postgres" for e in results)

    def test_search_case_insensitive(self, registry: CatalogRegistry) -> None:
        results = registry.search("GITHUB")
        assert len(results) == 1

    def test_search_empty_query(self, registry: CatalogRegistry) -> None:
        results = registry.search("")
        assert len(results) >= 17

    def test_search_no_results(self, registry: CatalogRegistry) -> None:
        results = registry.search("xyznonexistent")
        assert len(results) == 0

    def test_list_by_category(self, registry: CatalogRegistry) -> None:
        dev = registry.list_by_category("development")
        assert len(dev) >= 3
        assert all(e.category == "development" for e in dev)

    def test_list_by_category_empty(self, registry: CatalogRegistry) -> None:
        results = registry.list_by_category("nonexistent")
        assert results == []

    def test_get_categories(self, registry: CatalogRegistry) -> None:
        cats = registry.get_categories()
        assert "productivity" in cats
        assert "development" in cats
        assert "communication" in cats
        assert "data_storage" in cats
        assert "browser" in cats
        assert "web_search" in cats
        assert "docs" in cats
        assert "design" in cats
        assert len(cats) == 9

    def test_mcp_configs_present(self, registry: CatalogRegistry) -> None:
        """All MCP-type entries must have mcp_config populated."""
        for entry in registry.list_all():
            if entry.connector_type == ConnectorType.MCP:
                assert entry.mcp_config is not None
                assert entry.mcp_config.name
                assert entry.mcp_config.type in ("sse", "stdio", "streamable_http")

    def test_auth_env_keys_for_api_key(self, registry: CatalogRegistry) -> None:
        """API_KEY entries must have env_key or credential_fields for credential injection."""
        for entry in registry.list_all():
            if entry.auth.type == AuthType.API_KEY:
                assert entry.auth.env_key or entry.auth.credential_fields, (
                    f"Entry {entry.id} requires API key but missing both env_key and credential_fields"
                )

    def test_oauth_entries_have_help_url(self, registry: CatalogRegistry) -> None:
        """OAuth entries must have help_url for users to obtain credentials."""
        for entry in registry.list_all():
            if entry.auth.type == AuthType.OAUTH2:
                assert entry.auth.help_url, f"Entry {entry.id} uses OAuth2 but missing help_url"

    def test_cn_entries_present(self, registry: CatalogRegistry) -> None:
        """Chinese domestic office services must be present in the catalog."""
        cn_ids = {"tencent-docs", "wps", "qq-mail", "qichacha"}
        loaded_ids = {e.id for e in registry.list_all()}
        assert cn_ids.issubset(loaded_ids), f"Missing CN entries: {cn_ids - loaded_ids}"

    def test_bearer_entries_have_credential_fields(self, registry: CatalogRegistry) -> None:
        """Bearer auth entries must use credential_fields with header inject."""
        for entry in registry.list_all():
            if entry.auth.type == AuthType.BEARER:
                assert entry.auth.credential_fields, (
                    f"Entry {entry.id} uses bearer auth but missing credential_fields"
                )
                header_fields = [f for f in entry.auth.credential_fields if f.inject.value == "header"]
                assert header_fields, (
                    f"Entry {entry.id} uses bearer auth but no credential field has inject=header"
                )

    def test_streamable_http_with_headers(self, registry: CatalogRegistry) -> None:
        """Streamable HTTP entries with bearer auth must have headers in mcp_config."""
        for entry in registry.list_all():
            if (
                entry.auth.type == AuthType.BEARER
                and entry.mcp_config
                and entry.mcp_config.type == "streamable_http"
            ):
                assert entry.mcp_config.headers, (
                    f"Entry {entry.id} uses streamable_http+bearer but mcp_config missing headers"
                )

    def test_search_chinese_service(self, registry: CatalogRegistry) -> None:
        """Searching by Chinese service names should find CN entries."""
        results = registry.search("腾讯文档")
        assert any(e.id == "tencent-docs" for e in results)
        results = registry.search("企查查")
        assert any(e.id == "qichacha" for e in results)

    def test_unreal_engine_entry(self, registry: CatalogRegistry) -> None:
        """Unreal Engine entry must exist with correct host_serial config."""
        entry = registry.get_by_id("unreal-engine")
        assert entry is not None
        assert entry.name == "Unreal Engine"
        assert entry.category == "design"
        assert entry.auth.type == AuthType.NONE
        assert entry.mcp_config is not None
        assert entry.mcp_config.type == "streamable_http"
        assert entry.mcp_config.host_serial is True
        assert entry.mcp_config.keepalive_interval == 30.0
        assert entry.mcp_config.probe_url == "http://127.0.0.1:8000/mcp"
        assert entry.mcp_config.post_connect_guide is not None
        assert entry.mcp_config.post_connect_guide_zh is not None

    def test_blender_entry(self, registry: CatalogRegistry) -> None:
        """Blender entry must exist with correct host_serial config."""
        entry = registry.get_by_id("blender")
        assert entry is not None
        assert entry.name == "Blender"
        assert entry.category == "design"
        assert entry.auth.type == AuthType.NONE
        assert entry.mcp_config is not None
        assert entry.mcp_config.type == "sse"
        assert entry.mcp_config.host_serial is True
        assert entry.mcp_config.keepalive_interval == 30.0
        assert entry.mcp_config.probe_url == "http://127.0.0.1:9876/sse"
        assert entry.mcp_config.post_connect_guide is not None

    def test_design_category_has_three_entries(self, registry: CatalogRegistry) -> None:
        """Design category must have at least Figma, Unreal Engine, and Blender."""
        design = registry.list_by_category("design")
        ids = {e.id for e in design}
        assert {"figma", "unreal-engine", "blender"}.issubset(ids)
