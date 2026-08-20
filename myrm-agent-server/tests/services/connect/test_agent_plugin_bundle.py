"""Tests for Agent Plugins 1.0.0 bundle generation.

Validates template rendering (plugin.json / mcp.json / SKILL.md), the two token
modes (embedded vs env-var), and ConnectService integration (state persistence,
token verification, revocation).
"""

import json
from pathlib import Path

import jsonschema
import pytest

from app.services.connect.agent_plugin import (
    AGENT_PLUGIN_PROFILE,
    TOKEN_ENV_VAR,
    build_agent_plugin_bundle,
)
from app.services.connect.service import ConnectorStatus, ConnectService

# tests/services/connect/test_agent_plugin_bundle.py -> tests/fixtures/agent_plugins/
_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "agent_plugins"


@pytest.fixture(scope="module")
def plugin_schema() -> dict[str, object]:
    """Official Agent Plugins 1.0.0 plugin manifest schema (frozen fixture)."""
    return json.loads((_FIXTURES / "plugin.schema.json").read_text())


@pytest.fixture(scope="module")
def mcp_schema() -> dict[str, object]:
    """Official Agent Plugins 1.0.0 mcp configuration schema (frozen fixture)."""
    return json.loads((_FIXTURES / "mcp.schema.json").read_text())


@pytest.fixture
def service(tmp_path: Path) -> ConnectService:
    """Create ConnectService with a temp data dir."""
    return ConnectService(data_dir=tmp_path)


class TestBuildBundle:
    """Pure template rendering tests."""

    def test_bundle_file_set(self) -> None:
        bundle = build_agent_plugin_bundle("http://x:8080/mcp", "tok123", agent_id="default")
        assert set(bundle.files) == {
            "plugin.json",
            "mcp.json",
            "skills/myrm-memory/SKILL.md",
        }

    def test_plugin_json_manifest(self) -> None:
        bundle = build_agent_plugin_bundle("http://x/mcp", "tok", agent_id="default")
        manifest = json.loads(bundle.files["plugin.json"])
        assert manifest["$schema"].startswith("https://agent-plugins.org/schemas/1.0.0/")
        assert manifest["name"] == "myrm-memory"
        assert manifest["version"] == "1.0.0"
        assert manifest["homepage"]
        assert "memory" in manifest["keywords"]

    def test_plugin_json_validates_against_official_schema(self, plugin_schema: dict[str, object]) -> None:
        bundle = build_agent_plugin_bundle("http://x/mcp", "tok", agent_id="default")
        jsonschema.validate(json.loads(bundle.files["plugin.json"]), plugin_schema)

    def test_mcp_json_validates_against_official_schema(self, mcp_schema: dict[str, object]) -> None:
        for embed in (True, False):
            bundle = build_agent_plugin_bundle("http://x/mcp", "tok", agent_id="default", embed_token=embed)
            jsonschema.validate(json.loads(bundle.files["mcp.json"]), mcp_schema)

    def test_mcp_json_embedded_token(self) -> None:
        bundle = build_agent_plugin_bundle("http://x/mcp", "tok123", agent_id="default", embed_token=True)
        mcp = json.loads(bundle.files["mcp.json"])
        server = mcp["mcpServers"]["myrm-memory"]
        assert server["type"] == "streamable-http"
        assert server["url"] == "http://x/mcp"
        assert server["headers"]["Authorization"] == "Bearer tok123"

    def test_mcp_json_env_token_mode(self) -> None:
        bundle = build_agent_plugin_bundle("http://x/mcp", "tok123", agent_id="default", embed_token=False)
        mcp = json.loads(bundle.files["mcp.json"])
        auth = mcp["mcpServers"]["myrm-memory"]["headers"]["Authorization"]
        assert auth == f"Bearer ${{{TOKEN_ENV_VAR}}}"
        assert "tok123" not in bundle.files["mcp.json"]

    def test_skill_markdown_tool_surface_matches_server(self) -> None:
        bundle = build_agent_plugin_bundle("http://x/mcp", "tok", agent_id="default")
        skill = bundle.files["skills/myrm-memory/SKILL.md"]
        assert "name: myrm-memory" in skill
        for tool in ("memory_recall", "memory_store", "memory_list", "memory_manage"):
            assert tool in skill
        for parameter in ('category: "preference"', "rule_trigger", "write_target"):
            assert parameter in skill

    def test_skill_markdown_guards_secrets(self) -> None:
        bundle = build_agent_plugin_bundle("http://x/mcp", "tok", agent_id="default")
        skill = bundle.files["skills/myrm-memory/SKILL.md"]
        assert "Never store passwords, API keys, or other secrets" in skill

    def test_env_mode_instructions_mention_var(self) -> None:
        bundle = build_agent_plugin_bundle("http://x/mcp", "tok", agent_id="default", embed_token=False)
        assert TOKEN_ENV_VAR in bundle.instructions

    def test_instructions_prescribe_file_layout(self) -> None:
        for embed in (True, False):
            bundle = build_agent_plugin_bundle("http://x/mcp", "tok", agent_id="default", embed_token=embed)
            assert "skills/myrm-memory/" in bundle.instructions
            assert "plugin.json" in bundle.instructions
            assert "mcp.json" in bundle.instructions


class TestServiceBundleGeneration:
    """ConnectService integration for bundle generation."""

    @pytest.mark.asyncio
    async def test_generate_persists_state(self, service: ConnectService) -> None:
        await service.generate_agent_plugin_bundle(agent_id="my-agent")
        state = service.get_connector_status(AGENT_PLUGIN_PROFILE)
        assert state.status == ConnectorStatus.CONFIGURED
        assert state.agent_id == "my-agent"
        assert state.token_hash != ""

    @pytest.mark.asyncio
    async def test_generated_token_verifies(self, service: ConnectService) -> None:
        bundle = await service.generate_agent_plugin_bundle()
        resolved = service.resolve_token(bundle.token)
        assert resolved is not None
        assert resolved.profile_id == AGENT_PLUGIN_PROFILE
        assert resolved.agent_id == "default"

    @pytest.mark.asyncio
    async def test_generated_bundle_has_mcp_url(self, service: ConnectService) -> None:
        bundle = await service.generate_agent_plugin_bundle()
        assert bundle.mcp_url.endswith("/mcp")
        assert bundle.embed_token is False

    @pytest.mark.asyncio
    async def test_default_bundle_env_mode_no_plaintext_token(self, service: ConnectService) -> None:
        bundle = await service.generate_agent_plugin_bundle()
        assert bundle.embed_token is False
        assert bundle.token not in bundle.files["mcp.json"]
        assert TOKEN_ENV_VAR in bundle.files["mcp.json"]
        assert TOKEN_ENV_VAR in bundle.instructions

    @pytest.mark.asyncio
    async def test_revoke_invalidates_bundle_token(self, service: ConnectService) -> None:
        bundle = await service.generate_agent_plugin_bundle()
        assert service.revoke(AGENT_PLUGIN_PROFILE) is True
        assert service.resolve_token(bundle.token) is None

    @pytest.mark.asyncio
    async def test_bundle_not_in_profiles(self, service: ConnectService) -> None:
        await service.generate_agent_plugin_bundle()
        assert all(p.id != AGENT_PLUGIN_PROFILE for p in service.list_profiles())
