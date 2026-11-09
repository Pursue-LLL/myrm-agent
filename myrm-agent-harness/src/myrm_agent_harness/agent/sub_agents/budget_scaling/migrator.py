"""Zero-disruption configuration upgrade migrator for subagents.

Detects the legacy uncustomized turn budget (turns in {25, 50}) and smoothly lifts it
to the modern industrial-grade default while 100% preserving any user-customized
configurations.

[INPUT]
- typing
- types

[OUTPUT]
- ConfigUpgradeMigrator

[POS]
Zero-disruption configuration upgrade migrator for subagents.
"""

from typing import cast

from .types import (
    DEFAULT_MAX_CHILDREN_PER_AGENT,
    DEFAULT_MAX_DESCENDANTS_PER_RUN,
    DEFAULT_SCALED_MAX_TURNS,
    LEGACY_DEFAULT_MAX_TURNS,
    ConfigMigrationResult,
)


class ConfigUpgradeMigrator:
    """Detects and smoothly migrates legacy subagent execution quotas."""

    @staticmethod
    def migrate_config_dict(raw_config: dict[str, object]) -> tuple[dict[str, object], ConfigMigrationResult]:
        """Inspect and adapt a subagent configuration dictionary.

        Returns:
            A tuple of (migrated_dict, migration_result).
        """
        data = dict(raw_config)
        reasons: list[str] = []
        migrated = False

        # 1. Max turns inspection & migration
        raw_turns = data.get("max_turns")
        old_max_turns: int | None = None
        new_max_turns: int = DEFAULT_SCALED_MAX_TURNS

        if raw_turns is None:
            data["max_turns"] = DEFAULT_SCALED_MAX_TURNS
            new_max_turns = DEFAULT_SCALED_MAX_TURNS
        else:
            try:
                parsed_t = int(cast(int | str, raw_turns))
                old_max_turns = parsed_t
                if parsed_t in LEGACY_DEFAULT_MAX_TURNS:
                    data["max_turns"] = DEFAULT_SCALED_MAX_TURNS
                    new_max_turns = DEFAULT_SCALED_MAX_TURNS
                    migrated = True
                    reasons.append(
                        f"Lifted legacy default max_turns ({parsed_t}) to scaled default ({DEFAULT_SCALED_MAX_TURNS})"
                    )
                else:
                    new_max_turns = parsed_t
            except (ValueError, TypeError):
                data["max_turns"] = DEFAULT_SCALED_MAX_TURNS
                new_max_turns = DEFAULT_SCALED_MAX_TURNS

        # 2. Children and descendants defaults
        if "max_children_per_agent" not in data or data["max_children_per_agent"] in {3, 5}:
            data["max_children_per_agent"] = DEFAULT_MAX_CHILDREN_PER_AGENT

        if "max_descendants_per_run" not in data or data["max_descendants_per_run"] in {10, 20}:
            data["max_descendants_per_run"] = DEFAULT_MAX_DESCENDANTS_PER_RUN

        result = ConfigMigrationResult(
            migrated=migrated,
            old_max_turns=old_max_turns,
            new_max_turns=new_max_turns,
            reasons=tuple(reasons),
        )

        return data, result
