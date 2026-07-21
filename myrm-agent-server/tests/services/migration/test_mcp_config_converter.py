"""Tests for mcp_config_converter — stateless converter from competitor MCP configs."""

from __future__ import annotations

from app.services.migration.mcp_config_converter import (
    MCPMigrationItem,
    convert_competitor_mcp_servers,
    mcp_migration_item_to_config_dict,
    mcp_migration_item_to_preview,
)

_HERMES_RAW: dict[str, object] = {
    "filesystem": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "/home/user"],
        "env": {"HOME": "/home/user"},
    },
    "slack": {
        "command": "python",
        "args": ["-m", "slack_mcp"],
        "env": {"SLACK_TOKEN": "xoxb-secret", "SLACK_CHANNEL": "#general"},
        "tools": {"include": ["send_message", "list_channels"]},
        "supports_parallel_tool_calls": False,
        "keepalive_interval": 30,
    },
}

_CLAUDE_RAW: dict[str, object] = {
    "brave-search": {
        "url": "https://brave.search.mcp.example.com/sse",
        "type": "streamable_http",
        "env": {"BRAVE_API_KEY": "sk-xxx"},
    },
    "invalid-entry": "not-a-dict",
    "empty-entry": {},
}


class TestConvertCompetitorMCPServers:
    def test_hermes_stdio_servers(self) -> None:
        items = convert_competitor_mcp_servers(_HERMES_RAW, competitor="hermes")
        assert len(items) == 2
        fs = next(i for i in items if i.name == "filesystem")
        assert fs.server_type == "stdio"
        assert fs.command == "npx"
        assert fs.args == ["-y", "@modelcontextprotocol/server-filesystem", "/home/user"]
        assert fs.url is None
        assert "HOME" in fs.env_key_names
        assert fs.tool_include is None
        assert fs.host_serial is False
        assert fs.keepalive_interval is None

    def test_hermes_tool_filters(self) -> None:
        items = convert_competitor_mcp_servers(_HERMES_RAW, competitor="hermes")
        slack = next(i for i in items if i.name == "slack")
        assert slack.tool_include == ["send_message", "list_channels"]
        assert slack.tool_exclude is None
        assert "SLACK_TOKEN" in slack.env_key_names
        assert slack.host_serial is True
        assert slack.keepalive_interval == 30
        assert slack.keepalive_interval_ignored is False

    def test_explicit_host_serial_overrides_parallel_flag(self) -> None:
        raw = {
            "stateful": {
                "command": "python",
                "args": ["-m", "stateful_mcp"],
                "supports_parallel_tool_calls": True,
                "hostSerial": True,
            }
        }
        items = convert_competitor_mcp_servers(raw, competitor="hermes")
        assert len(items) == 1
        assert items[0].host_serial is True

    def test_keepalive_too_small_is_ignored(self) -> None:
        raw = {
            "stateful": {
                "command": "python",
                "args": ["-m", "stateful_mcp"],
                "keepalive_interval": 1,
            }
        }
        items = convert_competitor_mcp_servers(raw, competitor="hermes")
        assert len(items) == 1
        assert items[0].keepalive_interval is None
        assert items[0].keepalive_interval_ignored is True

    def test_claude_sse_server(self) -> None:
        items = convert_competitor_mcp_servers(_CLAUDE_RAW, competitor="claude")
        assert len(items) == 1
        brave = items[0]
        assert brave.name == "brave-search"
        assert brave.server_type == "streamable_http"
        assert brave.url == "https://brave.search.mcp.example.com/sse"
        assert brave.command is None
        assert "BRAVE_API_KEY" in brave.env_key_names
        assert brave.host_serial is False

    def test_skips_invalid_entries(self) -> None:
        items = convert_competitor_mcp_servers(_CLAUDE_RAW, competitor="claude")
        names = [i.name for i in items]
        assert "invalid-entry" not in names
        assert "empty-entry" not in names

    def test_empty_input(self) -> None:
        assert convert_competitor_mcp_servers({}, competitor="hermes") == []

    def test_description_includes_competitor(self) -> None:
        items = convert_competitor_mcp_servers(_HERMES_RAW, competitor="hermes")
        for item in items:
            assert "hermes" in item.description.lower()


class TestMCPMigrationItemToConfigDict:
    def test_stdio_config(self) -> None:
        item = MCPMigrationItem(
            name="test-server",
            server_type="stdio",
            command="node",
            args=["server.js"],
            url=None,
            description="Test — Migrated from hermes",
            connect_timeout=15.0,
            execute_timeout=120.0,
            keepalive_interval=30.0,
            host_serial=True,
            tool_include=None,
            tool_exclude=["dangerous_tool"],
            env_key_names=["API_KEY"],
        )
        cfg = mcp_migration_item_to_config_dict(item)
        assert cfg["name"] == "test-server"
        assert cfg["type"] == "stdio"
        assert cfg["enabled"] is False
        assert cfg["command"] == "node"
        assert cfg["args"] == ["server.js"]
        assert "url" not in cfg
        assert cfg["hostSerial"] is True
        assert cfg["keepaliveInterval"] == 30.0
        assert cfg["tool_exclude"] == ["dangerous_tool"]
        assert "tool_include" not in cfg

    def test_sse_config(self) -> None:
        item = MCPMigrationItem(
            name="remote",
            server_type="sse",
            command=None,
            args=None,
            url="https://example.com/sse",
            description="Remote — Migrated from claude",
            connect_timeout=10.0,
            execute_timeout=60.0,
            keepalive_interval=None,
            host_serial=False,
            tool_include=None,
            tool_exclude=None,
            env_key_names=[],
        )
        cfg = mcp_migration_item_to_config_dict(item)
        assert cfg["url"] == "https://example.com/sse"
        assert "command" not in cfg
        assert "args" not in cfg
        assert "keepaliveInterval" not in cfg


class TestMCPMigrationItemToPreview:
    def test_stdio_preview(self) -> None:
        item = MCPMigrationItem(
            name="fs",
            server_type="stdio",
            command="npx",
            args=["-y", "@mcp/server-fs", "/home"],
            url=None,
            description="Migrated from hermes",
            connect_timeout=15.0,
            execute_timeout=120.0,
            keepalive_interval=None,
            host_serial=False,
            tool_include=None,
            tool_exclude=None,
            env_key_names=["HOME"],
        )
        preview = mcp_migration_item_to_preview(item)
        assert preview["name"] == "fs"
        assert preview["type"] == "stdio"
        assert preview["hostSerial"] is False
        assert preview["command"] == "npx"
        assert "commandPreview" in preview
        assert preview["envKeyCount"] == 1
        assert "keepaliveInterval" not in preview

    def test_sse_preview_no_env(self) -> None:
        item = MCPMigrationItem(
            name="remote",
            server_type="sse",
            command=None,
            args=None,
            url="https://example.com/sse",
            description="Migrated from claude",
            connect_timeout=15.0,
            execute_timeout=120.0,
            keepalive_interval=None,
            host_serial=False,
            tool_include=None,
            tool_exclude=None,
            env_key_names=[],
        )
        preview = mcp_migration_item_to_preview(item)
        assert preview["url"] == "https://example.com/sse"
        assert preview["hostSerial"] is False
        assert "envKeyCount" not in preview
        assert "command" not in preview

    def test_preview_marks_host_serial_true(self) -> None:
        item = MCPMigrationItem(
            name="stateful",
            server_type="stdio",
            command="python",
            args=["-m", "stateful_mcp"],
            url=None,
            description="Migrated from hermes",
            connect_timeout=15.0,
            execute_timeout=120.0,
            keepalive_interval=20,
            host_serial=True,
            tool_include=None,
            tool_exclude=None,
            env_key_names=[],
        )
        preview = mcp_migration_item_to_preview(item)
        assert preview["hostSerial"] is True
        assert preview["keepaliveInterval"] == 20

    def test_preview_marks_ignored_keepalive(self) -> None:
        item = MCPMigrationItem(
            name="stateful",
            server_type="stdio",
            command="python",
            args=["-m", "stateful_mcp"],
            url=None,
            description="Migrated from hermes",
            connect_timeout=15.0,
            execute_timeout=120.0,
            keepalive_interval=None,
            keepalive_interval_ignored=True,
            host_serial=True,
            tool_include=None,
            tool_exclude=None,
            env_key_names=[],
        )
        preview = mcp_migration_item_to_preview(item)
        assert preview["keepaliveIntervalIgnored"] is True
