"""Unit tests for the SubagentConfig dataclass.

Tests:
1. Field values and defaults
2. Immutability (configs are shared as module-level constants and catalog entries)
"""

from dataclasses import FrozenInstanceError

import pytest

from myrm_agent_harness.agent.sub_agents.types import SubagentConfig


def test_subagent_config_dataclass():
    config = SubagentConfig(
        tools=("tool1", "tool2"),
        system_prompt="Test prompt",
        timeout_seconds=60,
        max_retries=3,
        retry_backoff_seconds=2.0,
        max_spawn_depth=1,
    )

    assert config.tools == ("tool1", "tool2")
    assert config.system_prompt == "Test prompt"
    assert config.timeout_seconds == 60
    assert config.max_retries == 3
    assert config.retry_backoff_seconds == 2.0
    assert config.max_spawn_depth == 1


def test_subagent_config_defaults():
    config = SubagentConfig(tools=("tool1"), system_prompt="Test", timeout_seconds=5)

    assert config.max_retries == 3
    assert config.retry_backoff_seconds == 2.0
    assert config.max_spawn_depth == 0


def test_subagent_config_is_immutable():
    config = SubagentConfig(system_prompt="Test prompt")

    with pytest.raises(FrozenInstanceError):
        config.max_turns = 1  # type: ignore[misc]
