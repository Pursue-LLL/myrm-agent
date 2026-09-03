"""Tests for ConnectService.

Validates token generation, verification, state persistence, profile listing,
doctor checks, revoke, and mark_ready flows.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.connect.doctor_check import DoctorVerdict, _find_mym_entry
from app.services.connect.profiles import PROFILES
from app.services.connect.service import (
    ConnectorStatus,
    ConnectService,
)
from app.services.connect.snippet_builder import (
    build_config_json,
    build_instructions,
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
            assert profile.config_format in ("json_mcp", "toml_mcp")


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
    async def test_resolve_token_matches_profile(self, service: ConnectService):
        snippet = await service.generate_config("claude_code", agent_id="my-agent")
        resolved = service.resolve_token(snippet.token)
        assert resolved is not None
        assert resolved.profile_id == "claude_code"

    @pytest.mark.asyncio
    async def test_resolve_token_returns_agent_scope(self, service: ConnectService):
        snippet = await service.generate_config("cursor", agent_id="research-agent")
        resolved = service.resolve_token(snippet.token)
        assert resolved is not None
        assert resolved.profile_id == "cursor"
        assert resolved.agent_id == "research-agent"

    @pytest.mark.asyncio
    async def test_resolve_invalid_token_returns_none(self, service: ConnectService):
        assert service.resolve_token("invalid_token_xyz") is None

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
        assert state.doctor_ok is False

    @pytest.mark.asyncio
    async def test_connected_at_set_on_first_ready_not_generate(
        self, service: ConnectService
    ):
        """connected_at records first real connection, not config generation."""
        await service.generate_config("cursor")
        state = service.get_connector_status("cursor")
        assert state.connected_at is None
        service.mark_ready("cursor")
        state = service.get_connector_status("cursor")
        assert state.connected_at is not None

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
    async def test_state_persists_agent_id(
        self, service: ConnectService, tmp_data_dir: Path
    ):
        await service.generate_config("codex", agent_id="ops-agent")

        service2 = ConnectService(data_dir=tmp_data_dir)
        state = service2.get_connector_status("codex")
        assert state.agent_id == "ops-agent"

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
    async def test_doctor_healthy_token_only(self, service: ConnectService):
        """Without local file access (sandbox), a valid token reports healthy."""
        await service.generate_config("cursor")
        with patch("app.services.connect.service.is_local_mode", return_value=False):
            result = await service.doctor("cursor")
        assert result.healthy is True
        assert result.detail == "token_valid"
        assert result.severity == "warn"
        state = service.get_connector_status("cursor")
        # doctor must not promote the lifecycle status: READY is set only by
        # mark_ready on real MCP traffic.
        assert state.status == ConnectorStatus.CONFIGURED
        assert state.doctor_ok is True
        assert state.last_doctor_at is not None
        # The detail code is persisted so the frontend can render the amber
        # "partially verified" state instead of a plain green healthy dot.
        assert state.last_doctor_detail == "token_valid"

    @pytest.mark.asyncio
    async def test_doctor_token_env_uses_info_not_warning(
        self, service: ConnectService, caplog
    ):
        """Env-var token references are a blind spot, not a failure: log at INFO."""
        await service.generate_config("cursor")
        with (
            caplog.at_level("WARNING", logger="app.services.connect.service"),
            patch("app.services.connect.service.is_local_mode", return_value=True),
            patch(
                "app.services.connect.service.verify_connector_config",
                return_value=DoctorVerdict(
                    healthy=False, detail="token_env", severity="warn"
                ),
            ),
        ):
            result = await service.doctor("cursor")
        assert result.detail == "token_env"
        assert result.severity == "warn"
        assert not any(r.levelno >= 30 for r in caplog.records)

    @pytest.mark.asyncio
    async def test_doctor_mismatch_logs_warning(self, service: ConnectService, caplog):
        """A real failure (token mismatch) still logs at WARNING for ops."""
        await service.generate_config("cursor")
        with (
            caplog.at_level("WARNING", logger="app.services.connect.service"),
            patch("app.services.connect.service.is_local_mode", return_value=True),
            patch(
                "app.services.connect.service.verify_connector_config",
                return_value=DoctorVerdict(healthy=False, detail="token_mismatch"),
            ),
        ):
            await service.doctor("cursor")
        assert any(r.levelno >= 30 for r in caplog.records)

    @pytest.mark.asyncio
    async def test_doctor_detail_persists_across_instances(
        self, service: ConnectService, tmp_data_dir: Path
    ):
        """Doctor detail survives a service reload (drives card severity)."""
        await service.generate_config("cursor")
        with patch("app.services.connect.service.is_local_mode", return_value=False):
            await service.doctor("cursor")

        reloaded = ConnectService(data_dir=tmp_data_dir)
        state = reloaded.get_connector_status("cursor")
        assert state.last_doctor_detail == "token_valid"
        assert state.doctor_ok is True

    @pytest.mark.asyncio
    async def test_doctor_detail_defaults_empty_for_legacy_state(
        self, service: ConnectService, tmp_data_dir: Path
    ):
        """Legacy state files without the field load with an empty detail."""
        state_file = tmp_data_dir / "connect_state.json"
        state_file.write_text(
            json.dumps(
                {
                    "cursor": {
                        "status": "ready",
                        "token_hash": "abc",
                        "doctor_ok": True,
                        "last_doctor_at": "2026-08-15T00:00:00+00:00",
                    }
                }
            )
        )
        service2 = ConnectService(data_dir=tmp_data_dir)
        state = service2.get_connector_status("cursor")
        assert state.doctor_ok is True
        assert state.last_doctor_detail == ""

    @pytest.mark.asyncio
    async def test_doctor_local_verified_config(self, service: ConnectService):
        """In local mode a matching on-disk config reports verified."""
        await service.generate_config("cursor")
        with (
            patch("app.services.connect.service.is_local_mode", return_value=True),
            patch(
                "app.services.connect.service.verify_connector_config",
                return_value=DoctorVerdict(healthy=True, detail="verified"),
            ),
        ):
            result = await service.doctor("cursor")
        assert result.healthy is True
        assert result.detail == "verified"

    @pytest.mark.asyncio
    async def test_doctor_local_mismatched_config_reports_unhealthy(
        self, service: ConnectService
    ):
        """A stale on-disk token makes the connector unhealthy in local mode."""
        await service.generate_config("cursor")
        with (
            patch("app.services.connect.service.is_local_mode", return_value=True),
            patch(
                "app.services.connect.service.verify_connector_config",
                return_value=DoctorVerdict(healthy=False, detail="token_mismatch"),
            ),
        ):
            result = await service.doctor("cursor")
        assert result.healthy is False
        assert result.detail == "token_mismatch"
        state = service.get_connector_status("cursor")
        assert state.doctor_ok is False
        assert state.status == ConnectorStatus.CONFIGURED

    @pytest.mark.asyncio
    async def test_doctor_unknown_profile(self, service: ConnectService):
        result = await service.doctor("nonexistent")
        assert result.healthy is False
        assert result.detail == "unknown"


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
        assert service.resolve_token(snippet.token) is None

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
        assert state.agent_id == "default"


class TestSnippetBuilderExposeDesktop:
    """Test pure snippet builders with desktop exposure toggled."""

    def test_build_config_json_default_memory_only(self) -> None:
        profile = PROFILES["claude_code"]
        mcp_url = "http://127.0.0.1:8080/mcp"
        token = "myrm_mcp_test_token_123456"
        data = build_config_json(profile, mcp_url, token, expose_desktop=False)
        assert "mcpServers" in data
        assert "myrm-memory" in data["mcpServers"]
        assert "myrm" not in data["mcpServers"]
        server_entry = data["mcpServers"]["myrm-memory"]
        assert server_entry["url"] == "http://127.0.0.1:8080/mcp"
        assert (
            server_entry["headers"]["Authorization"]
            == "Bearer myrm_mcp_test_token_123456"
        )

    def test_build_config_json_expose_desktop_uses_myrm_key(self) -> None:
        profile = PROFILES["claude_code"]
        mcp_url = "http://127.0.0.1:8080/mcp"
        token = "myrm_mcp_test_token_123456"
        data = build_config_json(profile, mcp_url, token, expose_desktop=True)
        assert "mcpServers" in data
        assert "myrm" in data["mcpServers"]
        assert "myrm-memory" not in data["mcpServers"]
        server_entry = data["mcpServers"]["myrm"]
        assert server_entry["url"] == "http://127.0.0.1:8080/mcp"

    def test_build_config_json_codex_toml_expose_desktop(self) -> None:
        profile = PROFILES["codex"]
        mcp_url = "http://127.0.0.1:8080/mcp"
        token = "myrm_mcp_test_token_123456"
        data = build_config_json(profile, mcp_url, token, expose_desktop=True)
        assert data["_format"] == "toml"
        assert "[mcp_servers.myrm]" in data["_toml_snippet"]
        assert "[mcp_servers.myrm-memory]" not in data["_toml_snippet"]

    def test_build_instructions_desktop_enabled(self) -> None:
        profile = PROFILES["cursor"]
        mcp_url = "http://127.0.0.1:8080/mcp"
        instructions = build_instructions(profile, mcp_url, expose_desktop=True)
        assert "semantic desktop control tools" in instructions
        assert "myrm" in instructions

    def test_build_instructions_desktop_disabled(self) -> None:
        profile = PROFILES["cursor"]
        mcp_url = "http://127.0.0.1:8080/mcp"
        instructions = build_instructions(profile, mcp_url, expose_desktop=False)
        assert "semantic desktop control tools" not in instructions
        assert "myrm-memory" in instructions


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


class TestConnectServiceDesktopExpose:
    """Test state persistence and token resolution with expose_desktop."""

    @pytest.mark.asyncio
    async def test_generate_config_stores_expose_desktop(
        self, service: ConnectService
    ) -> None:
        snippet = await service.generate_config(
            "cursor", agent_id="agent-desk", expose_desktop=True
        )
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
    async def test_reload_service_preserves_expose_desktop(
        self, tmp_data_dir: Path
    ) -> None:
        svc1 = ConnectService(data_dir=tmp_data_dir)
        snippet = await svc1.generate_config(
            "claude_code", agent_id="agent-c", expose_desktop=True
        )

        svc2 = ConnectService(data_dir=tmp_data_dir)
        status = svc2.get_connector_status("claude_code")
        assert status.expose_desktop is True

        resolved = svc2.resolve_token(snippet.token)
        assert resolved is not None
        assert resolved.expose_desktop is True
