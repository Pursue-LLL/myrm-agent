"""Strongly-typed DTOs and constants for the subagent turn-budget upgrade.

Defines legacy default recognition constants, new scaled defaults,
and the migration contract.

[INPUT]
- dataclasses
- datetime

[OUTPUT]
- LEGACY_DEFAULT_MAX_TURNS
- DEFAULT_SCALED_MAX_TURNS
- DEFAULT_MAX_CHILDREN_PER_AGENT
- DEFAULT_MAX_DESCENDANTS_PER_RUN
- ConfigMigrationResult

[POS]
Strongly-typed DTOs and constants for the subagent turn-budget upgrade.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime

# Legacy default value for the subagent turn budget
LEGACY_DEFAULT_MAX_TURNS = frozenset({25, 50})

# Scaled production defaults
DEFAULT_SCALED_MAX_TURNS: int = 250
DEFAULT_MAX_CHILDREN_PER_AGENT: int = 10
DEFAULT_MAX_DESCENDANTS_PER_RUN: int = 50


@dataclass(frozen=True)
class ConfigMigrationResult:
    """Audit report for zero-disruption subagent configuration migration."""

    migrated: bool
    old_max_turns: int | None
    new_max_turns: int
    reasons: tuple[str, ...] = field(default_factory=tuple)
    timestamp: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
