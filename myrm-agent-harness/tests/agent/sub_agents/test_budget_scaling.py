"""[INPUT] Harness budget_scaling submodule exports and subagent configuration loader.
[OUTPUT] Unit tests verifying zero-disruption configuration migration.
[POS] Unit tests for the subagent turn-budget upgrade.
"""

from __future__ import annotations

from myrm_agent_harness.agent.sub_agents.budget_scaling import (
    DEFAULT_MAX_CHILDREN_PER_AGENT,
    DEFAULT_MAX_DESCENDANTS_PER_RUN,
    DEFAULT_SCALED_MAX_TURNS,
    ConfigUpgradeMigrator,
)


def test_migrator_lifts_legacy_default_turns() -> None:
    # 1. Standard legacy default (max_turns=50)
    raw = {"max_turns": 50}
    migrated_dict, result = ConfigUpgradeMigrator.migrate_config_dict(raw)

    assert result.migrated is True
    assert result.old_max_turns == 50
    assert result.new_max_turns == DEFAULT_SCALED_MAX_TURNS  # 250
    assert result.reasons
    assert migrated_dict["max_turns"] == 250
    assert migrated_dict["max_children_per_agent"] == DEFAULT_MAX_CHILDREN_PER_AGENT
    assert migrated_dict["max_descendants_per_run"] == DEFAULT_MAX_DESCENDANTS_PER_RUN

    # 2. Alternative legacy default (max_turns=25)
    _, result_alt = ConfigUpgradeMigrator.migrate_config_dict({"max_turns": 25})
    assert result_alt.migrated is True
    assert result_alt.new_max_turns == 250


def test_migrator_preserves_user_customized_config() -> None:
    # Custom non-default values (max_turns=120) stay exactly as the user wrote them
    raw_custom = {
        "max_turns": 120,
        "max_children_per_agent": 6,
        "max_descendants_per_run": 30,
    }
    migrated_dict, result = ConfigUpgradeMigrator.migrate_config_dict(raw_custom)

    assert result.migrated is False
    assert result.old_max_turns == 120
    assert result.new_max_turns == 120
    assert migrated_dict["max_turns"] == 120
    assert migrated_dict["max_children_per_agent"] == 6
    assert migrated_dict["max_descendants_per_run"] == 30


def test_migrator_handles_missing_and_malformed_values() -> None:
    # Empty dict -> assigned scaled defaults
    migrated_dict, result = ConfigUpgradeMigrator.migrate_config_dict({})
    assert result.migrated is False
    assert migrated_dict["max_turns"] == DEFAULT_SCALED_MAX_TURNS

    # Malformed non-numeric value -> gracefully fallback to the default
    migrated_malformed, _ = ConfigUpgradeMigrator.migrate_config_dict({"max_turns": "not-an-int"})
    assert migrated_malformed["max_turns"] == DEFAULT_SCALED_MAX_TURNS
