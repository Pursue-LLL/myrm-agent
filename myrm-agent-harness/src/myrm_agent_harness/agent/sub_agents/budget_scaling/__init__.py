"""Subagent turn-budget upgrade package.

[INPUT]
- migrator
- types

[OUTPUT]
- (模块级副作用与注册)

[POS]
Subagent turn-budget upgrade package.

"""

from .migrator import ConfigUpgradeMigrator
from .types import (
    DEFAULT_MAX_CHILDREN_PER_AGENT,
    DEFAULT_MAX_DESCENDANTS_PER_RUN,
    DEFAULT_SCALED_MAX_TURNS,
    LEGACY_DEFAULT_MAX_TURNS,
    ConfigMigrationResult,
)

__all__ = [
    "ConfigMigrationResult",
    "ConfigUpgradeMigrator",
    "DEFAULT_MAX_CHILDREN_PER_AGENT",
    "DEFAULT_MAX_DESCENDANTS_PER_RUN",
    "DEFAULT_SCALED_MAX_TURNS",
    "LEGACY_DEFAULT_MAX_TURNS",
]
