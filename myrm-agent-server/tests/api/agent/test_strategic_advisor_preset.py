"""Unit tests for the bundled strategic-advisor core preset in DatabaseSubagentCatalog."""

import pytest
from myrm_agent_harness.agent.sub_agents.strategic_advisor_schema import READONLY_FORBIDDEN_TOOLS
from myrm_agent_harness.agent.sub_agents.types import (
    ControlScope,
    MemoryIsolationPolicy,
    SubagentConfig,
    WorkspacePolicy,
)

from app.ai_agents.subagent_catalog import DatabaseSubagentCatalog


@pytest.mark.asyncio
class TestStrategicAdvisorPreset:
    """Test resolution, read-only safety, and 4-section schema of strategic-advisor preset."""

    async def test_resolve_strategic_advisor_preset(self) -> None:
        catalog = DatabaseSubagentCatalog()
        config = await catalog.resolve("strategic-advisor")

        assert config is not None
        assert isinstance(config, SubagentConfig)
        assert config.display_name == "Strategic Advisor"
        assert config.theme_color == "purple"
        assert config.is_advisory is True

        # Verify 4-section schema presence
        schema = config.advisory_schema
        assert schema is not None
        assert "identity" in schema
        assert "scope" in schema
        assert "advisory_principles" in schema
        assert "output_protocol" in schema

        assert schema["identity"]["role"] == "Principal Systems Architect & Strategic Advisor"
        assert schema["scope"]["mode"] == "readonly"
        assert len(schema["advisory_principles"]) >= 3
        assert len(schema["output_protocol"]["required_sections"]) >= 3

    async def test_strategic_advisor_strict_readonly_tools_isolation(self) -> None:
        catalog = DatabaseSubagentCatalog()
        config = await catalog.resolve("strategic-advisor")
        assert config is not None

        # Verify active tools are strictly read-only
        assert config.tools == ("file_read_tool", "grep_tool", "glob_tool")

        # Verify forbidden mutation tools are absent from active tools
        active_tools_set = set(config.tools)
        forbidden_in_active = active_tools_set & READONLY_FORBIDDEN_TOOLS
        assert not forbidden_in_active, f"Forbidden tools found in strategic advisor: {forbidden_in_active}"

        # Verify forbidden mutation tools are explicitly blacklisted
        for forbidden in READONLY_FORBIDDEN_TOOLS:
            assert forbidden in config.disallowed_tools, f"Missing blacklist for forbidden tool {forbidden}"

    async def test_strategic_advisor_execution_policies(self) -> None:
        catalog = DatabaseSubagentCatalog()
        config = await catalog.resolve("strategic-advisor")
        assert config is not None

        assert config.control_scope == ControlScope.LEAF
        assert config.memory_isolation == MemoryIsolationPolicy.EPHEMERAL_SESSION
        assert config.workspace_policy == WorkspacePolicy.INHERIT
        assert config.max_spawn_depth == 0
        assert config.timeout_seconds == 120

    async def test_strategic_advisor_in_list_available(self) -> None:
        catalog = DatabaseSubagentCatalog()
        available = await catalog.list_available()
        assert "strategic-advisor" in available
