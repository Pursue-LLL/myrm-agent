"""Unit tests for blueprint_materializer module.

Tests the materialize_jit_configs function that parses ephemeral subagent
configurations from frontend into SubagentConfig objects.
"""

from myrm_agent_harness.agent.sub_agents.types import (
    ControlScope,
    MemoryIsolationPolicy,
    SubagentConfig,
)

from app.ai_agents.general_agent.blueprint_materializer import materialize_jit_configs


class TestMaterializeJitConfigs:
    """Test suite for materialize_jit_configs function."""

    def test_empty_configs(self):
        """Test handling of None and empty dict configs."""
        assert materialize_jit_configs(None) == {}
        assert materialize_jit_configs({}) == {}

    def test_basic_display_name_and_theme_color(self):
        """Test parsing of display_name and theme_color fields."""
        raw_configs = {
            "researcher": {
                "display_name": "Research Agent",
                "theme_color": "blue",
                "system_prompt": "You are a researcher.",
            }
        }

        result = materialize_jit_configs(raw_configs)

        assert "researcher" in result
        config = result["researcher"]
        assert isinstance(config, SubagentConfig)
        assert config.display_name == "Research Agent"
        assert config.theme_color == "blue"
        assert config.system_prompt == "You are a researcher."

    def test_default_values_when_fields_missing(self):
        """Test default values are used when display_name or theme_color are missing."""
        raw_configs = {
            "coder": {
                "system_prompt": "You are a coder.",
            }
        }

        result = materialize_jit_configs(raw_configs)

        assert "coder" in result
        config = result["coder"]
        assert config.display_name == "coder"  # Defaults to type_id
        assert config.theme_color == ""  # Defaults to empty string

    def test_multiple_subagents(self):
        """Test parsing multiple subagents at once."""
        raw_configs = {
            "researcher": {
                "display_name": "@Researcher",
                "theme_color": "blue",
                "system_prompt": "Research expert.",
            },
            "coder": {
                "display_name": "@Coder",
                "theme_color": "green",
                "system_prompt": "Coding expert.",
            },
            "reviewer": {
                "display_name": "@Reviewer",
                "theme_color": "purple",
                "system_prompt": "Code reviewer.",
            },
        }

        result = materialize_jit_configs(raw_configs)

        assert len(result) == 3
        assert result["researcher"].display_name == "@Researcher"
        assert result["researcher"].theme_color == "blue"
        assert result["coder"].display_name == "@Coder"
        assert result["coder"].theme_color == "green"
        assert result["reviewer"].display_name == "@Reviewer"
        assert result["reviewer"].theme_color == "purple"

    def test_invalid_config_data_skipped(self):
        """Test that invalid config data is skipped with warning."""
        raw_configs = {
            "valid_agent": {
                "display_name": "Valid Agent",
                "theme_color": "orange",
                "system_prompt": "Valid.",
            },
            "invalid_agent": "this is a string, not a dict",  # Invalid
        }

        result = materialize_jit_configs(raw_configs)

        assert len(result) == 1  # Only valid_agent should be parsed
        assert "valid_agent" in result
        assert "invalid_agent" not in result

    def test_all_config_fields_preserved(self):
        """Test that all SubagentConfig fields are correctly parsed."""
        raw_configs = {
            "analyst": {
                "display_name": "@Analyst",
                "theme_color": "amber",
                "system_prompt": "Data analyst.",
                "description": "Analyzes data.",
                "model": "gpt-4o",
                "tools": ["web_search", "read_file"],
                "max_turns": 30,
                "memory_isolation": "collaborative_session",
                "context_mode": "fork",
                "max_fork_tokens": 10000,
                "control_scope": "leaf",
            }
        }

        result = materialize_jit_configs(raw_configs)

        config = result["analyst"]
        assert config.display_name == "@Analyst"
        assert config.theme_color == "amber"
        assert config.system_prompt == "Data analyst."
        assert config.description == "Analyzes data."
        assert config.model == "gpt-4o"
        assert config.tools == ("web_search", "read_file")
        assert config.max_turns == 30
        assert config.memory_isolation == MemoryIsolationPolicy.COLLABORATIVE_SESSION
        assert config.context_mode == "fork"
        assert config.max_fork_tokens == 10000
        assert config.control_scope == ControlScope.LEAF
        assert config.max_spawn_depth == 0
        assert config.agent_factory is not None

    def test_orchestrator_control_scope_enables_single_delegation_layer(self):
        raw_configs = {
            "coordinator": {
                "display_name": "@Coordinator",
                "control_scope": "orchestrator",
                "max_spawn_depth": 3,
                "max_children_per_agent": 2,
                "max_descendants_per_run": 7,
                "max_batch_size": 2,
            }
        }

        result = materialize_jit_configs(raw_configs)

        config = result["coordinator"]
        assert config.control_scope == ControlScope.ORCHESTRATOR
        assert config.max_spawn_depth == 3
        assert config.max_children_per_agent == 2
        assert config.max_descendants_per_run == 7
        assert config.max_batch_size == 2

    def test_orchestrator_role_never_has_zero_spawn_depth(self):
        raw_configs = {
            "coordinator": {
                "display_name": "@Coordinator",
                "control_scope": "orchestrator",
                "max_spawn_depth": 0,
            }
        }

        result = materialize_jit_configs(raw_configs)

        assert result["coordinator"].control_scope == ControlScope.ORCHESTRATOR
        assert result["coordinator"].max_spawn_depth == 1

    def test_invalid_control_scope_skips_config(self):
        raw_configs = {
            "invalid": {
                "display_name": "@Invalid",
                "control_scope": "full",
            }
        }

        result = materialize_jit_configs(raw_configs)

        assert "invalid" not in result

    def test_theme_color_empty_string_default(self):
        """Test theme_color defaults to empty string when not provided."""
        raw_configs = {
            "test_agent": {
                "display_name": "Test Agent",
                # theme_color intentionally omitted
            }
        }

        result = materialize_jit_configs(raw_configs)
        config = result["test_agent"]
        assert config.theme_color == ""

    def test_display_name_defaults_to_type_id(self):
        """Test display_name defaults to type_id when not provided."""
        raw_configs = {
            "my_custom_agent": {
                "system_prompt": "Custom agent.",
                # display_name intentionally omitted
            }
        }

        result = materialize_jit_configs(raw_configs)
        config = result["my_custom_agent"]
        assert config.display_name == "my_custom_agent"

    def test_memory_isolation_invalid_value_fallback(self):
        """Test invalid memory_isolation value falls back to default."""
        raw_configs = {
            "test_agent": {
                "display_name": "Test",
                "memory_isolation": "invalid_value",  # Invalid
            }
        }

        result = materialize_jit_configs(raw_configs)
        config = result["test_agent"]
        assert config.memory_isolation == MemoryIsolationPolicy.COLLABORATIVE_SESSION

    def test_context_mode_fallback(self):
        """Test context_mode fallback to 'isolated' when invalid."""
        raw_configs = {
            "agent_isolated": {
                "display_name": "Isolated Agent",
                "context_mode": "unknown_mode",  # Should fallback to 'isolated'
            },
            "agent_fork": {
                "display_name": "Fork Agent",
                "context_mode": "fork",
            },
        }

        result = materialize_jit_configs(raw_configs)
        assert result["agent_isolated"].context_mode == "isolated"
        assert result["agent_fork"].context_mode == "fork"

    def test_max_fork_tokens_invalid_value_handled(self):
        """Test max_fork_tokens with invalid value is set to None."""
        raw_configs = {
            "test_agent": {
                "display_name": "Test",
                "max_fork_tokens": "not_a_number",  # Invalid
            }
        }

        result = materialize_jit_configs(raw_configs)
        config = result["test_agent"]
        assert config.max_fork_tokens is None
