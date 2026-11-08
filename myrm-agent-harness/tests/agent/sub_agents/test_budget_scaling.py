"""[INPUT] Harness budget_scaling submodule exports and subagent configuration loader.
[OUTPUT] Unit tests verifying zero-disruption configuration migration.
[POS] Unit tests for Subagent Concurrency & Tool Budget Adaptive Scaling (Item 31).
"""

from __future__ import annotations

from myrm_agent_harness.agent.sub_agents.budget_scaling import (
    DEFAULT_MAX_CHILDREN_PER_AGENT,
    DEFAULT_MAX_DESCENDANTS_PER_RUN,
    DEFAULT_SCALED_CONCURRENCY,
    DEFAULT_SCALED_MAX_TURNS,
    ConfigUpgradeMigrator,
)


def test_migrator_lifts_legacy_default_concurrency_and_turns() -> None:
    # 1. Standard legacy defaults (concurrency=3, max_turns=50)
    raw = {"concurrency_limit": 3, "max_turns": 50}
    migrated_dict, result = ConfigUpgradeMigrator.migrate_config_dict(raw)

    assert result.migrated is True
    assert result.concurrency_migrated is True
    assert result.max_turns_migrated is True
    assert result.old_concurrency == 3
    assert result.new_concurrency == DEFAULT_SCALED_CONCURRENCY  # 10
    assert result.old_max_turns == 50
    assert result.new_max_turns == DEFAULT_SCALED_MAX_TURNS  # 250
    assert migrated_dict["concurrency_limit"] == 10
    assert migrated_dict["max_turns"] == 250
    assert migrated_dict["max_children_per_agent"] == DEFAULT_MAX_CHILDREN_PER_AGENT
    assert migrated_dict["max_descendants_per_run"] == DEFAULT_MAX_DESCENDANTS_PER_RUN

    # 2. Alternative legacy defaults (concurrency=5, max_turns=25)
    raw_alt = {"concurrency_limit": 5, "max_turns": 25}
    _, result_alt = ConfigUpgradeMigrator.migrate_config_dict(raw_alt)
    assert result_alt.migrated is True
    assert result_alt.concurrency_migrated is True
    assert result_alt.max_turns_migrated is True
    assert result_alt.new_concurrency == 10
    assert result_alt.new_max_turns == 250


def test_migrator_preserves_user_customized_config() -> None:
    # 1. Custom non-default values (concurrency=8, max_turns=120)
    raw_custom = {
        "concurrency_limit": 8,
        "max_turns": 120,
        "max_children_per_agent": 6,
        "max_descendants_per_run": 30,
    }
    migrated_dict, result = ConfigUpgradeMigrator.migrate_config_dict(raw_custom)

    assert result.migrated is False
    assert result.concurrency_migrated is False
    assert result.max_turns_migrated is False
    assert result.old_concurrency == 8
    assert result.new_concurrency == 8
    assert result.old_max_turns == 120
    assert result.new_max_turns == 120
    assert migrated_dict["concurrency_limit"] == 8
    assert migrated_dict["max_turns"] == 120
    assert migrated_dict["max_children_per_agent"] == 6
    assert migrated_dict["max_descendants_per_run"] == 30

    # 2. Hybrid: legacy concurrency (3) but customized max_turns (88)
    raw_hybrid = {"concurrency_limit": 3, "max_turns": 88}
    migrated_hybrid, result_hybrid = ConfigUpgradeMigrator.migrate_config_dict(raw_hybrid)
    assert result_hybrid.migrated is True
    assert result_hybrid.concurrency_migrated is True
    assert result_hybrid.max_turns_migrated is False
    assert result_hybrid.new_concurrency == 10
    assert result_hybrid.new_max_turns == 88
    assert migrated_hybrid["concurrency_limit"] == 10
    assert migrated_hybrid["max_turns"] == 88


def test_migrator_handles_missing_and_malformed_values() -> None:
    # Empty dict -> assigned scaled defaults
    migrated_dict, result = ConfigUpgradeMigrator.migrate_config_dict({})
    assert result.migrated is False
    assert migrated_dict["concurrency_limit"] == DEFAULT_SCALED_CONCURRENCY
    assert migrated_dict["max_turns"] == DEFAULT_SCALED_MAX_TURNS

    # Malformed non-numeric values -> gracefully fallback to defaults
    malformed = {"concurrency_limit": "not-an-int", "max_turns": None}
    migrated_malformed, _ = ConfigUpgradeMigrator.migrate_config_dict(malformed)
    assert migrated_malformed["concurrency_limit"] == DEFAULT_SCALED_CONCURRENCY
    assert migrated_malformed["max_turns"] == DEFAULT_SCALED_MAX_TURNS
