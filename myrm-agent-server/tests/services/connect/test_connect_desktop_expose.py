"""Unit tests for ConnectService desktop tools exposure.

Tests verify:
- snippet_builder server_key and instructions with expose_desktop=True/False
- doctor_check finds both 'myrm' and 'myrm-memory' server entries
- ConnectService persists and resolves expose_desktop state and token
"""

from pathlib import Path

import pytest

from app.services.connect.doctor_check import (
    DoctorVerdict,
    _find_mym_entry,
    hash_token,
    verify_connector_config,
)
from app.services.connect.profiles import PROFILES, ConnectionProfile
from app.services.connect.service import (
    ConfigSnippet,
    ConnectorStatus,
    ConnectService,
)
from app.services.connect.snippet_builder import (
    build_config_json,
    build_instructions,
)


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def service(tmp_data_dir: Path) -> ConnectService:
    return ConnectService(data_dir=tmp_data_dir)


class TestSnippetBuilderExposeDesktop:
    """Test pure snippet builders with desktop exposure toggled."""

    def test_build_config_json_default_memory_only(self) -> None:
        profile = PROFILES["claude_code"]
        snippet = ConfigSnippet(
            token="myrm_mcp_test_token_123456",
            mcp_url="http://127.0.0.1:8080/mcp",
            config_json={},
            instructions="",
            expose_desktop=False,
        )
        data = build_config_json(profile, snippet, expose_desktop=False)
        assert "mcpServers" in data
        assert "myrm-memory" in data["mcpServers"]
        assert "myrm" not in data["mcpServers"]
        server_entry = data["mcpServers"]["myrm-memory"]
        assert server_entry["url"] == "http://127.0.0.1:8080/mcp"
        assert server_entry["headers"]["Authorization"] == "Bearer myrm_mcp_test_token_123456"

    def test_build_config_json_expose_desktop_uses_myrm_key(self) -> None:
        profile = PROFILES["claude_code"]
        snippet = ConfigSnippet(
            token="myrm_mcp_test_token_123456",
            mcp_url="http://127.0.0.1:8080/mcp",
            config_json={},
            instructions="",
            expose_desktop=True,
        )
        data = build_config_json(profile, snippet, expose_desktop=True)
        assert "mcpServers" in data
        assert "myrm" in data["mcpServers"]
        assert "myrm-memory" not in data["mcpServers"]
        server_entry = data["mcpServers"]["myrm"]
        assert server_entry["url"] == "http://127.0.0.1:8080/mcp"

    def test_build_config_json_codex_toml_expose_desktop(self) -> None:
        profile = PROFILES["codex"]
        snippet = ConfigSnippet(
            token="myrm_mcp_test_token_123456",
            mcp_url="http://127.0.0.1:8080/mcp",
            config_json={},
            instructions="",
            expose_desktop=True,
        )
        data = build_config_json(profile, snippet, expose_desktop=True)
        assert data["_format"] == "toml"
        assert "[mcp_servers.myrm]" in data["_toml_snippet"]
        assert "[mcp_servers.myrm-memory]" not in data["_toml_snippet"]

    def test_build_instructions_desktop_enabled(self) -> None:
        profile = PROFILES["cursor"]
        snippet = ConfigSnippet(
            token="myrm_mcp_test_token_123456",
            mcp_url="http://127.0.0.1:8080/mcp",
            config_json={},
            instructions="",
            expose_desktop=True,
        )
        instructions = build_instructions(profile, snippet, expose_desktop=True)
        assert "desktop automation tools" in instructions
        assert "desktop_snapshot_tool" in instructions
        assert "desktop_interact_tool" in instructions

    def test_build_instructions_desktop_disabled(self) -> None:
        profile = PROFILES["cursor"]
        snippet = ConfigSnippet(
            token="myrm_mcp_test_token_123456",
            mcp_url="http://127.0.0.1:8080/mcp",
            config_json={},
            instructions="",
            expose_desktop=False,
        )
        instructions = build_instructions(profile, snippet, expose_desktop=False)
        assert "desktop automation tools" not in instructions


class TestDoctorCheckServerEntries:
    """Test doctor check compatibility with both 'myrm' and 'myrm-memory' entries."""

    def test_find_myrm_entry_with_memory_key(self) -> None:
        config_content = {
            "mcpServers": {
                "myrm-memory": {
                    "url": "http://127.0.0.1:8080/mcp",
                    "headers": {"Authorization": "Bearer myrm_mcp_valid_token"},
                }
            }
        }
        entry = _find_mym_entry(config_content, "mcpServers")
        assert entry is not None
        assert entry["url"] == "http://127.0.0.1:8080/mcp"

    def test_find_myrm_entry_with_myrm_key(self) -> None:
        config_content = {
            "mcpServers": {
                "myrm": {
                    "url": "http://127.0.0.1:8080/mcp",
                    "headers": {"Authorization": "Bearer myrm_mcp_valid_token"},
                }
            }
        }
        entry = _find_mym_entry(config_content, "mcpServers")
        assert entry is not None
        assert entry["url"] == "http://127.0.0.1:8080/mcp"


class TestConnectServiceStatePersistence:
    """Test state persistence and token resolution with expose_desktop."""

    @pytest.mark.asyncio
    async def test_generate_config_stores_expose_desktop(self, service: ConnectService) -> None:
        snippet = await service.generate_config("cursor", agent_id="agent-desk", expose_desktop=True)
        assert snippet.expose_desktop is True

        status = service.get_connector_status("cursor")
        assert status.status == ConnectorStatus.CONFIGURED
        assert status.expose_desktop is True

        resolved = service.resolve_token(snippet.token)
        assert resolved is not None
        assert resolved.profile_id == "cursor"
        assert resolved.agent_id == "agent-desk"
        assert resolved.expose_desktop is True

    @pytest.mark.asyncio
    async def test_reload_service_preserves_expose_desktop(self, tmp_data_dir: Path) -> None:
        svc1 = ConnectService(data_dir=tmp_data_dir)
        snippet = await svc1.generate_config("claude_code", agent_id="agent-c", expose_desktop=True)

        svc2 = ConnectService(data_dir=tmp_data_dir)
        status = svc2.get_connector_status("claude_code")
        assert status.expose_desktop is True

        resolved = svc2.resolve_token(snippet.token)
        assert resolved is not None
        assert resolved.expose_desktop is True
