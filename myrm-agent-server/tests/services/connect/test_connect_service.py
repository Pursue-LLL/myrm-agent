"""Tests for ConnectService.

Validates token generation, verification, state persistence, profile listing,
doctor checks, revoke, and mark_ready flows.
"""

import json
from pathlib import Path

import pytest

from app.services.connect.service import (
    ConnectorStatus,
    ConnectService,
)


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    """Create a temporary data directory for ConnectService state."""
    return tmp_path


@pytest.fixture
def service(tmp_data_dir: Path) -> ConnectService:
    """Create ConnectService with temp data dir."""
    return ConnectService(data_dir=tmp_data_dir)


class TestProfiles:
    """Test profile listing and configuration."""

    def test_list_profiles_returns_all(self, service: ConnectService):
        profiles = service.list_profiles()
        assert len(profiles) == 5
        ids = {p.id for p in profiles}
        assert ids == {"claude_code", "cursor", "windsurf", "codex", "gemini_cli"}

    def test_profiles_have_required_fields(self, service: ConnectService):
        for profile in service.list_profiles():
            assert profile.label
            assert profile.description
            assert profile.config_file_path
            assert profile.config_format in ("json_mcp", "toml_mcp", "claude_hooks")


class TestTokenGeneration:
    """Test token generation and verification."""

    @pytest.mark.asyncio
    async def test_generate_config_creates_token(self, service: ConnectService):
        snippet = await service.generate_config("claude_code")
        assert snippet.token.startswith("myrm_mcp_")
        assert len(snippet.token) > 20

    @pytest.mark.asyncio
    async def test_generate_config_returns_mcp_url(self, service: ConnectService):
        snippet = await service.generate_config("cursor")
        assert "/mcp" in snippet.mcp_url

    @pytest.mark.asyncio
    async def test_verify_token_succeeds(self, service: ConnectService):
        snippet = await service.generate_config("claude_code")
        verified = service.verify_token(snippet.token)
        assert verified == "claude_code"

    @pytest.mark.asyncio
    async def test_verify_invalid_token_returns_none(self, service: ConnectService):
        assert service.verify_token("invalid_token_xyz") is None

    @pytest.mark.asyncio
    async def test_unknown_profile_raises(self, service: ConnectService):
        with pytest.raises(ValueError, match="Unknown profile"):
            await service.generate_config("nonexistent_agent")


class TestConnectorState:
    """Test state management and persistence."""

    @pytest.mark.asyncio
    async def test_state_transitions_to_configured(self, service: ConnectService):
        await service.generate_config("cursor")
        state = service.get_connector_status("cursor")
        assert state.status == ConnectorStatus.CONFIGURED

    @pytest.mark.asyncio
    async def test_mark_ready_updates_status(self, service: ConnectService):
        await service.generate_config("cursor")
        service.mark_ready("cursor")
        state = service.get_connector_status("cursor")
        assert state.status == ConnectorStatus.READY
        assert state.doctor_ok is True

    @pytest.mark.asyncio
    async def test_mark_ready_noop_when_already_ready(self, service: ConnectService):
        await service.generate_config("cursor")
        service.mark_ready("cursor")
        service.mark_ready("cursor")
        state = service.get_connector_status("cursor")
        assert state.status == ConnectorStatus.READY

    def test_mark_ready_noop_for_unknown(self, service: ConnectService):
        service.mark_ready("unknown_profile")

    @pytest.mark.asyncio
    async def test_state_persists_to_disk(
        self, service: ConnectService, tmp_data_dir: Path
    ):
        await service.generate_config("windsurf")

        service2 = ConnectService(data_dir=tmp_data_dir)
        state = service2.get_connector_status("windsurf")
        assert state.status == ConnectorStatus.CONFIGURED
        assert state.token_hash != ""

    @pytest.mark.asyncio
    async def test_list_all_states_includes_all_profiles(self, service: ConnectService):
        states = service.list_all_states()
        assert len(states) == 5
        profile_ids = {s.profile_id for s in states}
        assert profile_ids == {
            "claude_code",
            "cursor",
            "windsurf",
            "codex",
            "gemini_cli",
        }

    def test_get_status_for_unconfigured_returns_missing(self, service: ConnectService):
        state = service.get_connector_status("claude_code")
        assert state.status == ConnectorStatus.MISSING
        assert state.token_hash == ""


class TestDoctor:
    """Test doctor (health check) functionality."""

    @pytest.mark.asyncio
    async def test_doctor_healthy(self, service: ConnectService):
        await service.generate_config("cursor")
        healthy = await service.doctor("cursor")
        assert healthy is True
        state = service.get_connector_status("cursor")
        assert state.status == ConnectorStatus.READY
        assert state.doctor_ok is True

    @pytest.mark.asyncio
    async def test_doctor_unknown_profile(self, service: ConnectService):
        healthy = await service.doctor("nonexistent")
        assert healthy is False


class TestRevoke:
    """Test token revocation."""

    @pytest.mark.asyncio
    async def test_revoke_resets_state(self, service: ConnectService):
        await service.generate_config("claude_code")
        revoked = service.revoke("claude_code")
        assert revoked is True
        state = service.get_connector_status("claude_code")
        assert state.status == ConnectorStatus.MISSING
        assert state.token_hash == ""

    @pytest.mark.asyncio
    async def test_revoke_invalidates_token(self, service: ConnectService):
        snippet = await service.generate_config("claude_code")
        service.revoke("claude_code")
        assert service.verify_token(snippet.token) is None

    def test_revoke_unknown_returns_false(self, service: ConnectService):
        assert service.revoke("nonexistent") is False


class TestConfigFormat:
    """Test config snippet generation for different formats."""

    @pytest.mark.asyncio
    async def test_json_format_for_claude_code(self, service: ConnectService):
        snippet = await service.generate_config("claude_code")
        assert "mcpServers" in snippet.config_json
        assert "_format" not in snippet.config_json

    @pytest.mark.asyncio
    async def test_toml_format_for_codex(self, service: ConnectService):
        snippet = await service.generate_config("codex")
        assert snippet.config_json["_format"] == "toml"
        assert "_toml_snippet" in snippet.config_json
        toml_str = snippet.config_json["_toml_snippet"]
        assert isinstance(toml_str, str)
        assert "[mcp_servers.myrm-memory]" in toml_str
        assert "streamable-http" in toml_str

    @pytest.mark.asyncio
    async def test_instructions_contain_file_path(self, service: ConnectService):
        snippet = await service.generate_config("cursor")
        assert "~/.cursor/mcp.json" in snippet.instructions

    @pytest.mark.asyncio
    async def test_gemini_json_format(self, service: ConnectService):
        snippet = await service.generate_config("gemini_cli")
        assert "mcpServers" in snippet.config_json
        assert "_format" not in snippet.config_json
        server_cfg = snippet.config_json["mcpServers"]["myrm-memory"]
        assert server_cfg["transport"] == "streamable-http"


class TestCorruptedState:
    """Test resilience to corrupted state files."""

    def test_loads_gracefully_with_invalid_json(self, tmp_data_dir: Path):
        state_file = tmp_data_dir / "connect_state.json"
        state_file.write_text("not valid json {{{")
        service = ConnectService(data_dir=tmp_data_dir)
        states = service.list_all_states()
        assert all(s.status == ConnectorStatus.MISSING for s in states)

    def test_loads_gracefully_with_missing_fields(self, tmp_data_dir: Path):
        state_file = tmp_data_dir / "connect_state.json"
        state_file.write_text(json.dumps({"cursor": {"status": "ready"}}))
        service = ConnectService(data_dir=tmp_data_dir)
        state = service.get_connector_status("cursor")
        assert state.status == ConnectorStatus.READY
